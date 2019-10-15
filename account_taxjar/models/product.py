# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tax_code_id = fields.Many2one('taxjar.category', string="TaxJar Tax Code")


class ProductCategory(models.Model):
    _inherit = 'product.category'

    tax_code_id = fields.Many2one('taxjar.category', string="TaxJar Tax Code")
