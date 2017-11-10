# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    shipping_weight_uom_id = fields.Many2one(
        string='Shipping Weight UoM',
        related='picking_id.weight_uom_id',
        readonly=True,
    )
