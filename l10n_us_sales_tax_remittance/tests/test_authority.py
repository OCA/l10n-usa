# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAuthority(AccountTestInvoicingCommon):
    """Per-state DOR authorities + state-scoped reconcile on a shared account."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("l10n_us_sales_tax_engine.group_us_tax_manager").sudo().write(
            {"users": [(4, cls.env.user.id)]}
        )
        cls.company = cls.company_data["company"]
        us = cls.env.ref("base.us")
        states = cls.env["res.country.state"]
        cls.tx = states.search([("code", "=", "TX"), ("country_id", "=", us.id)])
        cls.pa = states.search([("code", "=", "PA"), ("country_id", "=", us.id)])
        # One SHARED payable account for every state (no sub-accounts).
        cls.payable = cls.env["account.account"].create(
            {
                "name": "Sales Tax Payable",
                "code": "USTAXPAY",
                "account_type": "liability_current",
                "reconcile": True,
            }
        )
        cls.income = cls.company_data["default_account_revenue"]
        cls.company.write(
            {
                "us_tax_payable_account_id": cls.payable.id,
                "us_tax_allowance_account_id": cls.income.id,
                "us_tax_remittance_journal_id": cls.company_data[
                    "default_journal_purchase"
                ].id,
            }
        )
        cls.dor_tx = cls.env["res.partner"].create({"name": "Texas Comptroller"})
        cls.dor_pa = cls.env["res.partner"].create({"name": "PA DOR"})
        Authority = cls.env["us.tax.authority"]
        # TX allowance set deliberately != the built-in 0.5% to prove the
        # authority record (not the state_returns table) is the source.
        cls.auth_tx = Authority.create(
            {
                "state_id": cls.tx.id,
                "partner_id": cls.dor_tx.id,
                "allowance_rate": 0.02,
            }
        )
        cls.auth_pa = Authority.create(
            {
                "state_id": cls.pa.id,
                "partner_id": cls.dor_pa.id,
                "allowance_rate": 0.01,
                "allowance_cap": 25.0,
            }
        )

    def _collect(self, amount, state):
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2026-01-15",
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    (0, 0, {"account_id": self.income.id, "debit": amount}),
                    (
                        0,
                        0,
                        {
                            "account_id": self.payable.id,
                            "credit": amount,
                            "us_tax_state_id": state.id,
                        },
                    ),
                ],
            }
        )
        entry.action_post()
        return entry

    def _return(self, state, tax):
        ret = self.env["us.tax.return"].create(
            {
                "state_id": state.id,
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
                "company_id": self.company.id,
            }
        )
        self.env["us.tax.return.line"].create(
            {
                "return_id": ret.id,
                "level": "state",
                "taxable_base": tax / 0.06,
                "tax_amount": tax,
            }
        )
        ret.state = "generated"
        return ret

    def test_authority_resolved_by_state(self):
        ret_tx = self._return(self.tx, 100.0)
        ret_pa = self._return(self.pa, 100.0)
        self.assertEqual(ret_tx.authority_id, self.auth_tx)
        self.assertEqual(ret_pa.authority_id, self.auth_pa)

    def test_bill_goes_to_states_own_dor(self):
        self._collect(100.0, self.tx)
        ret = self._return(self.tx, 100.0)
        ret.action_create_remittance()
        self.assertEqual(ret.move_id.partner_id, self.dor_tx)

    def test_allowance_comes_from_authority_record(self):
        ret = self._return(self.tx, 100.0)
        # Authority rate 2% -> 2.00, not the built-in TX 0.5% (0.50).
        self.assertEqual(ret.collection_allowance, 2.0)
        self.assertEqual(ret.net_tax_due, 98.0)

    def test_allowance_rate_must_be_a_fraction(self):
        with self.assertRaises(ValidationError):
            self.auth_tx.allowance_rate = 2.5  # 250% — fat-fingered percent

    def test_authority_journal_override(self):
        other = self.company_data["default_journal_purchase"].copy(
            {"name": "TX Remittance", "code": "TXRMT"}
        )
        self.auth_tx.journal_id = other
        self._collect(100.0, self.tx)
        ret = self._return(self.tx, 100.0)
        ret.action_create_remittance()
        self.assertEqual(ret.move_id.journal_id, other)

    def test_state_scoped_reconcile_on_shared_account(self):
        """TX and PA tax accrue to ONE account; remitting TX clears only TX."""
        tx_entry = self._collect(100.0, self.tx)
        pa_entry = self._collect(100.0, self.pa)
        tx_line = tx_entry.line_ids.filtered(lambda line: line.credit)
        pa_line = pa_entry.line_ids.filtered(lambda line: line.credit)
        self.assertEqual(tx_line.us_tax_state_id, self.tx)
        self.assertEqual(pa_line.us_tax_state_id, self.pa)

        ret_tx = self._return(self.tx, 100.0)
        # Tie-out sees only TX's collected tax on the shared account.
        self.assertEqual(ret_tx.tax_collected_gl, 100.0)
        self.assertEqual(ret_tx.tie_out_variance, 0.0)

        ret_tx.action_create_remittance()
        self.assertTrue(tx_line.reconciled)
        self.assertFalse(pa_line.reconciled)  # PA liability untouched

        # PA can still be remitted independently against its own DOR.
        ret_pa = self._return(self.pa, 100.0)
        ret_pa.action_create_remittance()
        self.assertEqual(ret_pa.move_id.partner_id, self.dor_pa)
        self.assertTrue(pa_line.reconciled)
