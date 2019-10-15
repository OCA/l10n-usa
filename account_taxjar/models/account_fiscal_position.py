# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    taxjar_nexus_sourcing_id = fields.Many2one(
        'taxjar.nexus.sourcing', string='TaxJar Nexus Sourcing',
    )

    @api.multi
    def map_tax(self, taxes, product=None, partner=None):
        """Use TaxJar taxes instead of mapped taxes"""
        if self.taxjar_nexus_sourcing_id:
            return self.env['account.tax'].browse()
        else:
            return super().map_tax(taxes, product=product, partner=partner)
