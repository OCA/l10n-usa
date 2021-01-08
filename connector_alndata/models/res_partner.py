# Copyright (C) 2019 Open Source Integrators
# Copyright (C) 2019 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.multi
    def _compute_number_unit(self):
        """Calculate Number of Units.

        This method is used to calculate the number of units
        of the apartment which links with a particular corporate company.
        """
        apart_obj = self.env['fsm.location']
        for rec in self:
            apartments = apart_obj.search_read(
                [('commercial_partner_id', '=', rec.id)], ['num_of_unit'])
            rec.num_unit = sum([apart.get('num_of_unit')
                                for apart in apartments])

    partner_type = fields.Selection(
        [('owner', 'Owner'),
         ('management_company', 'Management Company'),
         ('contact', 'Contact'),
         ('new_construction', 'New Constructions')],
        'Partner Type')
    address_type = fields.Char('AddressType')
    num_unit = fields.Integer(compute="_compute_number_unit",
                              string="Number of Apartments")
