# Copyright (C) 2019 Brian McMaster
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class Type1099(models.Model):
    _name = 'type.1099'
    _description = '1099 Type'

    name = fields.Char()
