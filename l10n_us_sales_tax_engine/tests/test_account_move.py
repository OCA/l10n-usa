# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields

from .common import UsTaxBaseTest


class TestAccountMoveTax(UsTaxBaseTest):
    """Regression guard for the action_post() -> _post() migration: tax must
    be auto-calculated when an invoice/credit note is actually posted, not
    just when action_post() is called (action_post() can, on some Odoo 18
    core paths, return a wizard instead of posting).

    Every move is created before l10n_us_tax.auto_calculate is turned on.
    account.move.create() runs the same automatic trigger, so a move
    created with the setting already on reaches action_post() with its
    tax already applied and the guard would hold whether _post() ran or
    not."""

    def _enable_auto_calculate(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.auto_calculate", "True"
        )

    def _us_taxes(self, move):
        return move.invoice_line_ids.tax_ids.filtered(
            lambda t: t.name.startswith("US Sales Tax")
        )

    @classmethod
    def setUpClass(cls):
        """Leave _post()'s own call as the only thing that can calculate.

        The automatic trigger fires on any write to a draft document
        whose fingerprint moved, and core's _post() makes two of them
        before the move leaves the draft state: it fills invoice_date in
        when it is empty, and it sets checked from the journal's
        Auto-Check on Post, which defaults to on. Either one calculates
        the tax on its own and the guard would hold whether _post()
        called the engine or not.
        """
        super().setUpClass()
        cls.env["account.journal"].search(
            [("type", "=", "sale")]
        ).autocheck_on_post = False

    def _create_invoice(self, move_type="out_invoice"):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_fl.id,
                "invoice_date": fields.Date.context_today(self.env.user),
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
        self.assertFalse(
            self._us_taxes(move),
            "the move must reach action_post() with no tax, or the guard is void",
        )
        self._enable_auto_calculate()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertTrue(
            self._us_taxes(move),
            "posting an invoice must auto-calculate US tax on its lines",
        )

    def test_tax_auto_calculated_on_credit_note_post(self):
        """Credit notes (out_refund) are in scope too — the manual
        'Calculate US Tax' button already allowed out_refund, the
        auto-calc-on-post path must match that scope."""
        move = self._create_invoice("out_refund")
        self.assertFalse(self._us_taxes(move))
        self._enable_auto_calculate()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertTrue(
            self._us_taxes(move),
            "posting a credit note must auto-calculate US tax on its lines",
        )

    def test_tax_not_calculated_when_engine_disabled(self):
        """The engine switch overrides the automation switch.

        Both are read at runtime and both have to be on, so turning the
        automation on while the engine is off must still calculate
        nothing.
        """
        self._enable_auto_calculate()
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
            self._us_taxes(move),
            "engine disabled — no US Sales Tax should be auto-calculated",
        )
