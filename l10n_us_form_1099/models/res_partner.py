# -*- coding: utf-8 -*-
# Copyright <2017> <Jenny Wu>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api


class ResPartner(models.Model) :
    _inherit = "res.partner"

    is1099 = fields.Boolean('Is a 1099')
    supplier = fields.Boolean(string='Is a Vendor',
                help="Check this box if this contact is a vendor. "
                "If it's not checked, purchase people will not see it when encoding a purchase order.")

    @api.onchange('is1099')
    def _on_change_is1099(self):

        if self.is1099 and not self.supplier:
           self.supplier = True

    @api.onchange('supplier')
    def _on_change_supplier(self):

        if self.is1099 and not self.supplier:
            self.is1099=False
			