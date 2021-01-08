# Copyright (C) 2019 Open Source Integrators
# Copyright (C) 2019 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class ResPartnerIndustry(models.Model):
    _inherit = "res.partner.industry"

    ref = fields.Char('Reference')
    parent_id = fields.Many2one('res.partner.industry', 'Parent')

    _sql_constraints = [
        ('ref_uniq', 'unique(ref)', 'Reference must be unique!'),
    ]

    @api.multi
    def name_get(self):
        """Compute Display Name.

        Return the display name, including their direct parent by default.
        """
        res = []
        for partner in self:
            display_name = ''
            if partner.parent_id and not partner.name:
                display_name += partner.parent_id.name
            if partner.parent_id and partner.name:
                display_name += partner.parent_id.name + '/' + partner.name
            if partner.name and not partner.parent_id:
                display_name += partner.name
            res.append((partner.id, display_name))
        return res
