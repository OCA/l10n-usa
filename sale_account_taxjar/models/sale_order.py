# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'taxjar.abstract.base']

    def _get_to_address(self):
        return self.partner_shipping_id

    def _get_from_addresses(self):
        from_addresses = list(
            set(self.order_line.mapped('sourcing_address_id')))
        return from_addresses or [self.company_id.partner_id]

    def _get_lines_from_address(self, from_address):
        lines = []
        for line in self.order_line.filtered(
                lambda l: l.warehouse_id.partner_id == from_address):
            lines.append(line)
        return lines

    @staticmethod
    def _get_price(line):
        return line.price_unit, line.product_uom_qty, line.discount

    @staticmethod
    def _set_tax_ids(line, taxes):
        line.tax_id = [
            (6, 0, [x.id for x in taxes])]
