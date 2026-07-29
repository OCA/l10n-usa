# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestUsTaxReturn(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        # The test user has accounting access but not the US Tax groups; grant
        # manager so it can read the engine config models and create returns.
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_tax.engine_active", "True")
        ICP.set_param("l10n_us_tax.engine_mode", "hybrid")
        ICP.set_param("l10n_us_tax.fail_policy", "warn")

        cls.us = cls.env.ref("base.us")
        cls.fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.cat_tangible = cls.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )

        cls.jurisdiction = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Miami-Dade",
                "type": "county",
                "state_id": cls.fl.id,
                "county": "MIAMI-DADE",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jurisdiction.id,
                "product_tax_category_id": cls.cat_tangible.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33101",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jurisdiction.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        cls.env["us.tax.nexus"].create(
            {
                "company_id": cls.company.id,
                "state_id": cls.fl.id,
                "active": True,
            }
        )

        cls.partner_fl = cls.env["res.partner"].create(
            {
                "name": "Customer FL",
                "zip": "33101",
                "city": "Miami",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )
        cls.product_a.us_tax_category_id = cls.cat_tangible

    def _post_invoice(self, move_type="out_invoice", price=100.0, date="2025-01-15"):
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_fl.id,
                "invoice_date": date,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "price_unit": price,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        if move_type == "out_refund":
            # The engine auto-calculates on posting invoices only; a standalone
            # credit note needs an explicit calculation (a reversal would inherit
            # the invoice's taxes instead).
            self.env["us.tax.engine.service"].calculate_for_invoice(move)
        move.action_post()
        return move

    def _make_return(self, date_from="2025-01-01", date_to="2025-01-31"):
        return self.env["us.tax.return"].create(
            {
                "company_id": self.company.id,
                "state_id": self.fl.id,
                "date_from": date_from,
                "date_to": date_to,
            }
        )

    def test_engine_books_per_jurisdiction_tax_lines(self):
        """Posting books one tax line per jurisdiction level, each tagged."""
        move = self._post_invoice()
        tax_lines = move.line_ids.filtered("tax_line_id")
        self.assertEqual(len(tax_lines), 2, "Expected a state and a county tax line")
        by_level = {tl.tax_line_id.us_tax_level: tl for tl in tax_lines}
        self.assertEqual(set(by_level), {"state", "county"})
        for tl in tax_lines:
            self.assertEqual(tl.tax_line_id.us_tax_state_id, self.fl)
            # Collected tax must book to a payable liability (to remit), not income.
            self.assertEqual(
                tl.account_id.account_type,
                "liability_current",
                "collected US tax must book to a tax-payable liability account",
            )
        # Sale tax lines are credits → -balance is the collected amount.
        self.assertAlmostEqual(-by_level["state"].balance, 6.0, places=2)
        self.assertAlmostEqual(-by_level["county"].balance, 1.0, places=2)

    def test_return_aggregates_by_jurisdiction(self):
        self._post_invoice()
        tax_return = self._make_return()
        tax_return.action_generate()

        self.assertEqual(tax_return.state, "generated")
        levels = {line.level: line for line in tax_return.line_ids}
        self.assertEqual(set(levels), {"state", "county"})
        self.assertAlmostEqual(levels["state"].tax_amount, 6.0, places=2)
        self.assertAlmostEqual(levels["state"].taxable_base, 100.0, places=2)
        self.assertAlmostEqual(levels["county"].tax_amount, 1.0, places=2)
        # Tax is summed across levels; taxable sales counted once (state base).
        self.assertAlmostEqual(tax_return.total_tax, 7.0, places=2)
        self.assertAlmostEqual(tax_return.total_taxable, 100.0, places=2)

    def test_refund_offsets_collected_tax(self):
        """A credit note in the period nets down collected tax and base."""
        self._post_invoice(price=100.0)
        self._post_invoice(move_type="out_refund", price=40.0)
        tax_return = self._make_return()
        tax_return.action_generate()
        # Net taxable sales = 100 - 40 = 60; state tax = 6% * 60 = 3.6.
        levels = {line.level: line for line in tax_return.line_ids}
        self.assertAlmostEqual(levels["state"].taxable_base, 60.0, places=2)
        self.assertAlmostEqual(levels["state"].tax_amount, 3.6, places=2)
        self.assertAlmostEqual(tax_return.total_tax, 4.2, places=2)

    def test_period_excludes_out_of_range_moves(self):
        self._post_invoice(date="2025-01-15")
        self._post_invoice(date="2025-03-15")
        tax_return = self._make_return(date_from="2025-01-01", date_to="2025-01-31")
        tax_return.action_generate()
        self.assertAlmostEqual(tax_return.total_tax, 7.0, places=2)

    def test_file_and_reset(self):
        self._post_invoice()
        tax_return = self._make_return()
        tax_return.action_generate()
        tax_return.action_file()
        self.assertEqual(tax_return.state, "filed")
        self.assertTrue(tax_return.filed_date)
        tax_return.action_reset_to_draft()
        self.assertEqual(tax_return.state, "draft")
        self.assertFalse(tax_return.filed_date)

    def test_export_worksheet_creates_attachment(self):
        self._post_invoice()
        tax_return = self._make_return()
        tax_return.action_generate()
        action = tax_return.action_export_worksheet()
        self.assertEqual(action["type"], "ir.actions.act_url")
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "us.tax.return"), ("res_id", "=", tax_return.id)]
        )
        self.assertTrue(attachment)
        self.assertEqual(attachment.mimetype, "text/csv")
