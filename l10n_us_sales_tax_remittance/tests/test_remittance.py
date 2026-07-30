# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestRemittance(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("l10n_us_sales_tax_engine.group_us_tax_manager").sudo().write(
            {"users": [(4, cls.env.user.id)]}
        )
        cls.company = cls.company_data["company"]
        cls.us = cls.env.ref("base.us")
        cls.pa = cls.env["res.country.state"].search(
            [("code", "=", "PA"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.payable = cls.env["account.account"].create(
            {
                "name": "Sales Tax Payable",
                "code": "USTAXPAY",
                "account_type": "liability_current",
                "reconcile": True,
            }
        )
        cls.income = cls.company_data["default_account_revenue"]
        cls.authority = cls.env["res.partner"].create({"name": "PA DOR"})
        cls.env["us.tax.authority"].create(
            {
                "company_id": cls.company.id,
                "state_id": cls.pa.id,
                "partner_id": cls.authority.id,
            }
        )
        cls.company.write(
            {
                "us_tax_payable_account_id": cls.payable.id,
                "us_tax_allowance_account_id": cls.income.id,
                "us_tax_remittance_journal_id": cls.company_data[
                    "default_journal_purchase"
                ].id,
            }
        )

    def _collect(self, amount, date="2026-01-15"):
        """Post a journal entry crediting the payable account (collected tax)."""
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    (
                        0,
                        0,
                        {"account_id": self.income.id, "debit": amount, "credit": 0.0},
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.payable.id,
                            "debit": 0.0,
                            "credit": amount,
                            "us_tax_state_id": self.pa.id,
                        },
                    ),
                ],
            }
        )
        entry.action_post()
        return entry

    def _return(self, tax):
        ret = self.env["us.tax.return"].create(
            {
                "state_id": self.pa.id,
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

    def test_remittance_books_bill_and_reconciles(self):
        self._collect(100.0)
        ret = self._return(100.0)
        # PA allowance = 1% capped $25 -> 1.00; net = 99.00; ties out to GL.
        self.assertEqual(ret.collection_allowance, 1.0)
        self.assertEqual(ret.net_tax_due, 99.0)
        self.assertEqual(ret.tax_collected_gl, 100.0)
        self.assertEqual(ret.tie_out_variance, 0.0)

        ret.action_create_remittance()
        bill = ret.move_id
        self.assertEqual(ret.state, "remitted")
        self.assertEqual(bill.move_type, "in_invoice")
        self.assertEqual(bill.partner_id, self.authority)
        self.assertEqual(bill.amount_total, 99.0)  # net owed to DOR
        self.assertEqual(bill.state, "posted")

        # Payable is cleared: the bill's debit reconciled the collected credit.
        payable_lines = self.env["account.move.line"].search(
            [
                ("account_id", "=", self.payable.id),
            ]
        )
        self.assertTrue(payable_lines)
        self.assertTrue(all(payable_lines.mapped("reconciled")))

    def test_allowance_credited_to_income(self):
        self._collect(100.0)
        ret = self._return(100.0)
        ret.action_create_remittance()
        income_line = ret.move_id.line_ids.filtered(
            lambda line: line.account_id == self.income
        )
        # Allowance is a 1.00 credit to income (negative-priced bill line).
        self.assertAlmostEqual(sum(income_line.mapped("credit")), 1.0, places=2)

    def test_cannot_remit_twice_or_draft(self):
        self._collect(100.0)
        ret = self._return(100.0)
        ret.action_create_remittance()
        with self.assertRaises(UserError):
            ret.action_create_remittance()
        ret2 = self._return(50.0)
        ret2.state = "draft"
        with self.assertRaises(UserError):
            ret2.action_create_remittance()

    def test_missing_config_raises(self):
        self.company.us_tax_payable_account_id = False
        ret = self._return(100.0)
        with self.assertRaises(UserError):
            ret.action_create_remittance()

    def test_tie_out_variance_flags_gap(self):
        self._collect(90.0)  # only 90 hit the GL but the return totals 100
        ret = self._return(100.0)
        self.assertEqual(ret.tax_collected_gl, 90.0)
        self.assertEqual(ret.tie_out_variance, 10.0)

    def test_zero_and_negative_tax_blocked(self):
        for tax in (0.0, -50.0):
            ret = self._return(tax)
            with self.assertRaises(UserError):
                ret.action_create_remittance()

    def test_variance_skips_auto_reconcile(self):
        """A non-zero tie-out posts the bill but must NOT auto-reconcile (no
        stranded residual on the tax-payable account)."""
        self._collect(90.0)
        ret = self._return(100.0)
        ret.action_create_remittance()
        self.assertEqual(ret.state, "remitted")
        self.assertTrue(ret.move_id)
        payable_lines = self.env["account.move.line"].search(
            [("account_id", "=", self.payable.id)]
        )
        self.assertFalse(any(payable_lines.mapped("reconciled")))

    def test_re_remit_after_cancelling_bill(self):
        self._collect(100.0)
        ret = self._return(100.0)
        ret.action_create_remittance()
        first_bill = ret.move_id
        first_bill.button_cancel()
        # A cancelled bill may be re-remitted; a fresh bill is booked.
        ret.action_create_remittance()
        self.assertNotEqual(ret.move_id, first_bill)
        self.assertEqual(ret.move_id.state, "posted")
