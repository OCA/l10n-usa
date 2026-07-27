# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    us_tax_source = fields.Char(
        string="Tax Source",
        help="Source used for the last US tax calculation.",
    )
    us_tax_calculated_at = fields.Datetime(
        string="Tax Calculated At",
    )
    us_tax_based_on_shipping = fields.Boolean(
        string="Tax Based on Shipping Address",
        default=True,
        help=(
            "When checked (default), US Sales Tax is calculated using the shipping "
            "address. Uncheck to use the billing/invoice address instead."
        ),
    )

    def action_calculate_us_tax(self):
        """Manual trigger — recalculate US tax for this order."""
        self.ensure_one()
        engine = self.env["us.tax.engine.service"]
        try:
            result = engine.calculate_for_sale_order(self)
            self.write(
                {
                    "us_tax_source": result.get("source", ""),
                    "us_tax_calculated_at": fields.Datetime.now(),
                }
            )
        except Exception as exc:
            _logger.error("US Tax calculation error on SO %s: %s", self.name, exc)
            raise

    def action_confirm(self):
        """Auto-calculate tax on confirmation if engine is active."""
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param("l10n_us_tax.engine_active", "False") == "True":
            for order in self:
                try:
                    self.env["us.tax.engine.service"].calculate_for_sale_order(order)
                except Exception as exc:
                    _logger.warning("US Tax auto-calc on confirm failed: %s", exc)
        return super().action_confirm()
