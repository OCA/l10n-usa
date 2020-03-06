# Copyright (C) 2019 Open Source Integrators
# Copyright (C) 2019 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class ResPartnerIndustry(models.Model):
    _inherit = "res.partner.industry"

    ref = fields.Char('ALN ID Reference', help='Reference to the ALN DB')
    parent_id = fields.Many2one('res.partner.industry', 'Market')
    child_ids = fields.One2many('res.partner.industry', 'parent_id', 'SubMarkets')

    _sql_constraints = [
        ('ref_uniq', 'unique(ref)', 'Reference must be unique!'),
    ]

    @api.multi
    def name_get(self):
        """Compute Display Name.

        Return the display name, including their direct parent by default.
        """
        res = []
        for rec in self:
            display_name = ''
            if rec.parent_id:
                display_name += rec.parent_id.name
                if rec.name:
                    display_name += '/' + rec.name
            else:
                display_name += rec.name
            res.append((rec.id, display_name))
        return res
