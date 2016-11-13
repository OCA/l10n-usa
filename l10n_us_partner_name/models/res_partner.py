# -*- coding: utf-8 -*-
# Copyright 2016 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import api, models


class ResPartner(models.Model):

    _inherit = 'res.partner'

    @api.model
    def _get_computed_name(self, lastname, firstname):
        return u" ".join((p for p in (firstname, lastname) if p))

    @api.model
    def _get_inverse_name(self, name, is_company=False):
        """ It reverses the results of the super to provide ``First Last`` """
        result = super(ResPartner, self)._get_inverse_name(
            name, is_company=is_company,
        )
        result.update({
            'firstname': result['lastname'],
            'lastname': result['firstname'],
        })
        return result
