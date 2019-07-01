from odoo import models


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['countinghouse.legal_id_number', 'res.partner']
