# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models

from ..services.address_resolver import (
    resolve_invoice_address,
    resolve_shipping_address,
)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["us.tax.auto.mixin", "sale.order"]

    us_tax_based_on_shipping = fields.Boolean(
        string="Tax Based on Shipping Address",
        default=True,
        help=(
            "When checked (default), US Sales Tax is calculated using the shipping "
            "address. Uncheck to use the billing/invoice address instead."
        ),
    )

    def _us_tax_partner_fields(self):
        """Add the billing partner: us_tax_based_on_shipping may pick it."""
        return super()._us_tax_partner_fields() + ["partner_invoice_id"]

    def _us_tax_extra_depends(self):
        """Add what the order contributes to the hash beyond the address."""
        return [
            "us_tax_based_on_shipping",
            "date_order",
            "company_id",
            "order_line.price_subtotal",
            "order_line.product_id.us_tax_category_id",
        ]

    def _us_tax_state_depends(self):
        """Return the fields _us_tax_state_domain() is expressed on."""
        return ["state", "locked", "invoice_status"]

    def _us_tax_get_address(self):
        """Resolve shipping or billing, as us_tax_based_on_shipping says."""
        if self.us_tax_based_on_shipping:
            return resolve_shipping_address(self)
        return resolve_invoice_address(self)

    def _us_tax_get_date(self):
        """Return date_order as a date-only ISO string."""
        return self.date_order.date().isoformat() if self.date_order else ""

    def _us_tax_get_lines(self):
        """Return the order lines."""
        return self.order_line

    def _us_tax_engine_run(self):
        """Run the engine for this order."""
        return self.env["us.tax.engine.service"].calculate_for_sale_order(self)

    def _us_tax_state_domain(self):
        """Only orders that can still take a tax change.

        tax_id is a protected field on a locked order, so writing it
        raises, and an order whose quantities are all invoiced has
        nothing left for a new rate to reach. Both extra clauses are
        stored fields, which is what lets the same expression serve the
        write guard and the cron's search().

        Neither clause blocks the confirmation pass: invoice_status is
        "no" for anything not in state sale, and the auto-lock from
        sale.group_auto_done_setting happens after the confirmation
        write. Partially invoiced orders stay in, because their
        uninvoiced remainder must follow the new rate.
        """
        return [
            ("state", "in", ("draft", "sent", "sale")),
            ("locked", "=", False),
            ("invoice_status", "not in", ("invoiced", "upselling")),
        ]
