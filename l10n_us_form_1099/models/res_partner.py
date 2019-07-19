# Copyright (C) 2017 Open Source Integrators
# Copyright (C) 2019 Brian McMaster
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_1099 = fields.Boolean('Is a 1099?')
    type_1099_id = fields.Many2one('type.1099', string='1099 Type')
    box_1099_misc_id = fields.Many2one('box.1099.misc',
                                       string='1099-MISC Box')

    @api.onchange('is_1099')
    def _on_change_is_1099(self):
        if self.is_1099 and not self.supplier:
            self.supplier = True

    @api.onchange('supplier')
    def _on_change_supplier(self):
        if self.is_1099 and not self.supplier:
            self.is_1099 = False
