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
         ('new_construction', 'New Constructions'),
         ('apartment', 'Apartments')],
        'Partner Type')
    address_type = fields.Char('AddressType')
    num_unit = fields.Integer(compute="_compute_number_unit",
                              string="Number of Apartments")
    owner_id = fields.Many2one('res.partner', string='Owner')
    aln_id = fields.Char('ALN ID')
    sub_market_id = fields.Many2one('res.partner.industry',
                                    string='Sub-Market'
                                    )

    @api.model
    def create(self, vals):
        parent_id = False
        # Update address type to other
        vals.update({'type': 'other'})
        # Update Internal Ref while creation
        if not vals.get('ref', False) and self._context.get('ref', False):
            vals.update({'ref': self._context.get('ref')})

        # Update Parent while creation
        if self._context.get('RegionalManagementCompanyId', False):
            parent_id = self.search(
                [('ref',
                 '=',
                 self._context.get('RegionalManagementCompanyId', False)
                 )],
                limit=1)
        else:
            if self._context.get('CorporateManagementCompanyId', False) and\
                    not parent_id:
                parent_id = self.search(
                    [('ref',
                      '=',
                      self._context.get('CorporateManagementCompanyId', False)
                      )],
                    limit=1)
        vals.update({'parent_id': parent_id and parent_id.id or False})

        # Update Owner while creation
        if self._context.get('OwnerId', False):
            owner_id = self.search(
                [('ref',
                  '=',
                  self._context.get('OwnerId', False)
                  )],
                limit=1)
            vals.update({'owner_id': owner_id and owner_id.id or False})

        # Update Industry while creation
        if self._context.get('industry_id', False):
            vals.update({'industry_id': self._context.get('industry_id', False)})

        # Update Partner Type while creation
        if self._context.get('partner_type', False):
            vals.update({'partner_type': self._context.get('partner_type', False)})

        return super(ResPartner, self).create(vals)
