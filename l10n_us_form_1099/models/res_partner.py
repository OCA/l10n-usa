# -*- coding: utf-8 -*-
# Copyright 2017 Ursa Information Systems <http://www.ursainfosystems.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is1099 = fields.Boolean('Is a 1099')

    @api.onchange('is1099')
    def _on_change_is1099(self):

        if self.is1099 and not self.supplier:
            self.supplier = True

    @api.onchange('supplier')
    def _on_change_supplier(self):

        if self.is1099 and not self.supplier:
            self.is1099 = False
