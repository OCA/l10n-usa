# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class Box1099Misc(models.Model):
    _name = 'box.1099.misc'
    _description = '1099-MISC Box'

    name = fields.Char()
