# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestAccountMoveTax(UsTaxBaseTest):
    """Regression guard for the action_post() -> _post() migration: tax must
    be auto-calculated when an invoice/credit note is actually posted, not
    just when action_post() is called (action_post() can, on some Odoo 18
    core paths, return a wizard instead of posting)."""

    def _create_invoice(self, move_type="out_invoice"):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_fl.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )

    def test_tax_auto_calculated_on_invoice_post(self):
        move = self._create_invoice("out_invoice")
        move.action_post()
        self.assertEqual(move.state, "posted")
        us_taxes = move.invoice_line_ids.tax_ids.filtered(
            lambda t: t.name.startswith("US Sales Tax")
        )
        self.assertTrue(
            us_taxes, "posting an invoice must auto-calculate US tax on its lines"
        )

    def test_tax_auto_calculated_on_credit_note_post(self):
        """Credit notes (out_refund) are in scope too — the manual
        'Calculate US Tax' button already allowed out_refund, the
        auto-calc-on-post path must match that scope."""
        move = self._create_invoice("out_refund")
        move.action_post()
        self.assertEqual(move.state, "posted")
        us_taxes = move.invoice_line_ids.tax_ids.filtered(
            lambda t: t.name.startswith("US Sales Tax")
        )
        self.assertTrue(
            us_taxes, "posting a credit note must auto-calculate US tax on its lines"
        )

    def test_tax_not_calculated_when_engine_disabled(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "False"
        )
        move = self._create_invoice("out_invoice")
        move.action_post()
        self.assertEqual(move.state, "posted")
        # The product/company may still carry an unrelated default Odoo
        # tax — assert specifically that the engine never created/applied
        # one of its own (its naming convention is "US Sales Tax ...").
        self.assertFalse(
            move.invoice_line_ids.tax_ids.filtered(
                lambda t: t.name.startswith("US Sales Tax")
            ),
            "engine disabled — no US Sales Tax should be auto-calculated",
        )
