# Copyright (C) 2019 Open Source Integrators
# Copyright (C) 2019 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class FsmLocation(models.Model):
    _inherit = "fsm.location"

    industry_id = fields.Many2one('res.partner.industry', 'Market')
    num_of_unit = fields.Integer('Number of Units')
    year_built = fields.Char('Build Year')
    year_remodeled = fields.Char('YearRemodeled')
    owner_id = fields.Many2one('res.partner', string='Related Owner',
                               required=False, ondelete='restrict',
                               auto_join=True)
    customer_id = fields.Many2one(
        'res.partner', string='Billed Customer', required=False,
        ondelete='restrict', auto_join=True, track_visibility='onchange')
