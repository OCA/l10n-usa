from odoo import fields, models


class Partner(models.Model):
    _inherit = "res.partner"

    county_id = fields.Many2one(
        "res.country.state.county",
        ondelete="restrict",
        domain="[('state_id', '=', state_id)]",
    )
