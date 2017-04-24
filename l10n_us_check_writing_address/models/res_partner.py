# -*- coding: utf-8 -*-
# Copyright 2017 Ursa Information Systems <http://www.ursainfosystems.com>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).


from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.multi
    def _display_address(self, without_company=False):
        '''Build a formatted address based on the country.

        The purpose of this function is to build and return an address
        formatted according to the standards of the country where it belongs.

        Args:
            address (res.partner): browse record of the res.partner to format

        Returns:
            string: the address formatted in a display that fit its country
            habits (or the default one if no country is specified)

        '''
        # get the information that will be injected into the display format
        # get the address format
        address_format = self.country_id.address_format
        if not self.street2:
            address_format = address_format.replace('%(street2)\n', '')
        args = {
            'state_code': self.state_id.code or '',
            'state_name': self.state_id.name or '',
            'country_code': self.country_id.code or '',
            'country_name': self.country_id.name or '',
            'company_name': self.parent_name or '',
        }
        for field in self._address_fields():
            args[field] = getattr(self, field) or ''
        if without_company:
            args['company_name'] = ''
        elif self.parent_id:
            address_format = '%(company_name)s\n' + address_format
        return address_format % args
