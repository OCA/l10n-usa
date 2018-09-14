# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def _default_uom(self):
        try:
            return self.env.ref('product.product_uom_oz')
        except ValueError:
            return super(StockPicking, self)._default_uom()
