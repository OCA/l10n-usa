from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    autopay = fields.Selection(
        selection=[
            ("disabled", "Disabled"),
            ("specific_date", "Specific date"),
            ("on_due_date", "On Due Date"),
            ("end_of_month", "End of month"),
        ],
        default="disabled",
    )

    autopay_method = fields.Many2one(
        "res.partner.bank",
        domain="[('partner_id', '=', id)]",
    )

    autopay_specific_date = fields.Date()
