from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    autopay = fields.Selection(
        selection=[
            ("disabled", "Disabled"),
            ("end_of_month", "End Of Month"),
            ("on_due_date", "On Due Date"),
        ],
        default="disabled",
    )
