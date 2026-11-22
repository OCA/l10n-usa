# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestUsTaxAutoMode(UsTaxBaseTest):
    """When the engine runs without anyone pressing Calculate US Tax."""

    def _set_auto_mode(self, mode):
        self.env["ir.config_parameter"].sudo().set_param("l10n_us_tax.auto_mode", mode)

    def _log_count_for(self, document):
        return (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search_count(
                [("res_model", "=", document._name), ("res_id", "=", document.id)]
            )
        )

    def test_on_validate_is_the_default(self):
        self._set_auto_mode(False)
        self.assertEqual(self.env["sale.order"]._us_tax_auto_mode(), "on_validate")

    def test_disabled_engine_turns_every_mode_off(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "False"
        )
        self.assertEqual(self.env["sale.order"]._us_tax_auto_mode(), "off")

    def test_settings_store_the_mode(self):
        """set_values() rather than execute(), which can reload the registry."""
        self.env["res.config.settings"].create({"us_tax_auto_mode": "off"}).set_values()
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param("l10n_us_tax.auto_mode"),
            "off",
        )

    def test_editing_a_draft_calculates_nothing(self):
        order = self._create_fl_order()
        order.order_line.product_uom_qty = 5.0
        move = self._create_fl_invoice()
        self.assertFalse(self._us_taxes(order.order_line.tax_id))
        self.assertFalse(self._us_taxes(move.invoice_line_ids.tax_ids))
        self.assertEqual(self._log_count_for(order) + self._log_count_for(move), 0)

    def test_confirm_calculates_once(self):
        order = self._create_fl_order()
        order.action_confirm()
        self.assertTrue(self._us_taxes(order.order_line.tax_id))
        self.assertEqual(self._log_count_for(order), 1)

    def test_post_calculates_once(self):
        move = self._create_fl_invoice()
        move.action_post()
        self.assertTrue(self._us_taxes(move.invoice_line_ids.tax_ids))
        self.assertEqual(self._log_count_for(move), 1)

    def test_confirm_in_off_mode_assigns_no_tax(self):
        self._set_auto_mode("off")
        order = self._create_fl_order()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertFalse(
            self._us_taxes(order.order_line.tax_id),
            "confirming in the off mode must not assign US tax",
        )
        self.assertEqual(self._log_count_for(order), 0)

    def test_post_in_off_mode_assigns_no_tax(self):
        self._set_auto_mode("off")
        move = self._create_fl_invoice()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertFalse(
            self._us_taxes(move.invoice_line_ids.tax_ids),
            "posting in the off mode must not assign US tax",
        )
        self.assertEqual(self._log_count_for(move), 0)
