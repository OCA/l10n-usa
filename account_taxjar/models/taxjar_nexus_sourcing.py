# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class TaxJarNexusSourcing(models.Model):
    _name = 'taxjar.nexus.sourcing'
    _description = 'TaxJar Nexus Sourcing'

    name = fields.Char('Name')
    taxjar_id = fields.Many2one('taxjar.api.key', string='TaxJar API ID')
    sourcing_type = fields.Selection([
        ('origin', 'Origin Sourcing'),
        ('destination', 'Destination Sourcing'),
    ])

    taxable_account_id = fields.Many2one(
        'account.account', string='Taxable Account TaxJar',
    )
