# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEcomRecompute(TransactionCase):
    """The checkout recompute fires only when ship-to + lines change."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        us = cls.env.ref("base.us")
        tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", us.id)], limit=1
        )
        cls.ship = cls.env["res.partner"].create(
            {"name": "Cust", "country_id": us.id, "state_id": tx.id, "zip": "77001"}
        )
        cls.product = cls.env["product.product"].create({"name": "P"})
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.ship.id,
                "partner_shipping_id": cls.ship.id,
                "order_line": [
                    (0, 0, {"product_id": cls.product.id, "product_uom_qty": 1})
                ],
            }
        )

    def _spy(self):
        return patch.object(
            type(self.env["us.tax.engine.service"]),
            "calculate_for_sale_order",
            return_value={},
        )

    def test_recompute_once_then_skips_when_unchanged(self):
        with self._spy() as m:
            self.order._us_tax_recompute_if_needed()
            self.order._us_tax_recompute_if_needed()  # inputs unchanged
            self.assertEqual(m.call_count, 1)
            self.assertTrue(self.order.us_tax_input_hash)

    def test_line_change_triggers_recompute(self):
        with self._spy() as m:
            self.order._us_tax_recompute_if_needed()
            self.order.order_line.product_uom_qty = 5
            self.order._us_tax_recompute_if_needed()
            self.assertEqual(m.call_count, 2)

    def test_no_recompute_without_us_shipto(self):
        self.order.partner_shipping_id.zip = False
        with self._spy() as m:
            self.order._us_tax_recompute_if_needed()
            self.assertEqual(m.call_count, 0)

    def test_no_recompute_when_engine_inactive(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "False"
        )
        with self._spy() as m:
            self.order._us_tax_recompute_if_needed()
            self.assertEqual(m.call_count, 0)

    def test_engine_failure_is_not_swallowed(self):
        """A hard failure propagates (the engine's fail_policy governs) rather
        than silently shipping an under-taxed order."""
        with patch.object(
            type(self.env["us.tax.engine.service"]),
            "calculate_for_sale_order",
            side_effect=UserError("provider down"),
        ):
            with self.assertRaises(UserError):
                self.order._us_tax_recompute_if_needed()
        self.assertFalse(self.order.us_tax_input_hash)  # not marked done

    def test_recompute_taxes_hook_covers_express_checkout(self):
        """_recompute_taxes is the hook express checkout (Apple/Google Pay)
        calls after the wallet supplies the shipping address."""
        with self._spy() as m:
            self.order.with_context(is_express_checkout_flow=True)._recompute_taxes()
            # A second identical recompute (re-render) must not re-call.
            self.order.with_context(is_express_checkout_flow=True)._recompute_taxes()
            self.assertEqual(m.call_count, 1)
