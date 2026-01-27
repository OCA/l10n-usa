from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    partner_bank_id = fields.Many2one(
        "res.partner.bank",
        string="Bank Account",
        domain="[('partner_id', '=', partner_id)]",
        help="Bank account to be displayed on the sale order / invoice.",
    )
