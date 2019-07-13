# Copyright 2017 Open Source Integrators <https://opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


TYPES_1099 = [
    ('a', "1099-A"),
    ('b', "1099-B"),
    ('c', "1099-C"),
    ('cap', "1099-CAP"),
    ('div', "1099-DIV"),
    ('g', "1099-G"),
    ('h', "1099-H"),
    ('int', "1099-INT"),
    ('k', "1099-K"),
    ('ltc', "1099-LTC"),
    ('misc', "1099-MISC"),
    ('oid', "1099-OID"),
    ('pair', "1099-PATR"),
    ('q', "1099-Q"),
    ('r', "1099-R"),
    ('s', "1099-S"),
    ('sa', "1099-SA"),
    ('rrb', "RRB-1099"),
    ('ssa', "SSA-1099"),
]

class ResPartner(models.Model):
    _inherit = "res.partner"

    is_1099 = fields.Boolean('Is a 1099?')
    type_1099 = fields.Selection(
        TYPES_1099, string='1099 Type')

    @api.onchange('is_1099')
    def _on_change_is_1099(self):
        if self.is_1099 and not self.supplier:
            self.supplier = True

    @api.onchange('supplier')
    def _on_change_supplier(self):
        if self.is_1099 and not self.supplier:
            self.is_1099 = False
