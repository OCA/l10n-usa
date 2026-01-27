from odoo import fields, models


class ResBank(models.Model):
    _inherit = "res.bank"

    plaid_institution_id = fields.Char()
