# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models

from .taxjar_request import TaxJarRequest


class TaxJarAPIConfigurator(models.Model):
    _name = 'taxjar.api.key'
    _description = 'Base TaxJar Configuration'

    name = fields.Char('Name')

    taxjar_api_url = fields.Char(
        string='TaxJar API URL',
    )
    taxjar_api_token = fields.Char(
        string='TaxJar API KEY',
    )

    @api.multi
    def sync_taxjar_tax_code(self):
        tax_code = self.env['taxjar.category']
        request = TaxJarRequest(self.taxjar_api_url, self.taxjar_api_token)
        categories = request.get_product_tax_code()

        for category in categories.data[:]:
            exist_tax = tax_code.search(
                [('code', '=', category['product_tax_code'])], limit=1)
            if not exist_tax:
                tax_code.create({'code': category['product_tax_code'],
                                 'description': category['description'],
                                 'name': category['name'],
                                 'taxjar_id': self.id
                                 })
            else:
                if tax_code.code != category['product_tax_code'] or \
                        tax_code.description != category['description'] or \
                        tax_code.name != category['name']:
                    tax_code.update({'code': category['product_tax_code'],
                                     'description': category['description'],
                                     'name': category['name'],
                                     'taxjar_id': self.id})
        return True

    def _update_nexus_sourcing(self, nexus):
        nexus_sourcing = self.env['taxjar.nexus.sourcing']
        nexus_exist = nexus_sourcing.search(
            [('name', '=', '[%s]: %s' % (self.name, nexus['region']))],
            limit=1)
        if not nexus_exist.id:
            nexus_sourcing.create({
                'name': '[%s]: %s' % (self.name, nexus['region']),
                'taxjar_id': self.id
            })
        return True

    @api.multi
    def sync_taxjar_nexus_sourcing(self):
        request = TaxJarRequest(self.taxjar_api_url, self.taxjar_api_token)
        res = request.get_nexus_regions()
        for nexus in res.data:
            self._update_nexus_sourcing(nexus)
        return True
