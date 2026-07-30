# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    us_tax_marketplace_id = fields.Many2one(
        "us.tax.marketplace",
        string="Marketplace Facilitator",
        help="Set when this order is collected and remitted by a marketplace "
        "facilitator — the engine then does not collect US sales tax.",
    )

    def _prepare_invoice(self):
        # Carry the facilitator onto the invoice so it isn't taxed at posting.
        vals = super()._prepare_invoice()
        if self.us_tax_marketplace_id:
            vals["us_tax_marketplace_id"] = self.us_tax_marketplace_id.id
        return vals
