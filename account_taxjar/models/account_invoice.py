# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _name = 'account.invoice'
    _inherit = ['account.invoice', 'taxjar.abstract.base']

    # If we have several warehouses on account_invoice_lines we need to get
    # their related partner. If no information is provided use company address.
    def _get_from_addresses(self):
        return list(set(self.invoice_line_ids.mapped(
            'warehouse_id.partner_id'))) or self.company_id.partner_id

    def _get_to_address(self):
        return self.partner_id

    @staticmethod
    def _get_price(line):
        return line.price_unit, line.quantity, line.discount

    @staticmethod
    def _set_tax_ids(line, taxes):
        line.invoice_line_tax_ids = [
            (6, 0, [x.id for x in taxes])]

    def prepare_taxes(self):
        super().prepare_taxes()
        # Force on change to update taxes on view.
        self._onchange_invoice_line_ids()
        return True
