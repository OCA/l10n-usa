from odoo import fields, models


class ResCompany(models.Model):
    _name = 'res.company'
    _inherit = ['countinghouse.legal_id_number', 'res.company']

    mandate_url = fields.Char(string='Mandate URL', required=False,
                              help='''Full URL to download ACH Mandate /
                              Authorization form. Useful to include in email
                              templates for customer to access and
                              complete the Mandate form.''')
