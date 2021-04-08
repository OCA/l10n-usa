# Copyright (C) 2021 Open Source Integrators
# Copyright (C) 2019 Brian McMaster
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_1099 = fields.Boolean("Is a 1099?")
    type_1099_id = fields.Many2one("type.1099", string="1099 Type")
    box_1099_misc_id = fields.Many2one("box.1099.misc", string="1099-MISC Box")
