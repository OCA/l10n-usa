# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    weight_oz = fields.Float(
        compute='_compute_weight_oz',
        inverse='_inverse_weight_oz',
        help='Weight of the product, in ounces.',
    )
    volume_in = fields.Float(
        compute='_compute_volume_in',
        inverse='_inverse_volume_in',
        help='Volume of the product, in inches cubed.',
    )

    @api.multi
    @api.depends('weight')
    def _compute_weight_oz(self):
        for record in self:
            record.weight_oz = self._convert_kilogram_ounce(
                record.weight,
            )

    @api.multi
    def _inverse_weight_oz(self):
        for record in self:
            record.weight = self._convert_kilogram_ounce(
                record.weight_oz, to_oz=False,
            )

    @api.multi
    @api.depends('volume')
    def _compute_volume_in(self):
        for record in self:
            record.volume_in = self._convert_meter_inch(record.volume)

    @api.multi
    def _inverse_volume_in(self):
        for record in self:
            record.volume = self._convert_meter_inch(
                record.volume_in, to_in=False,
            )

    @api.model_cr_context
    def _convert_kilogram_ounce(self, quantity, to_oz=True):
        """Convert between kilograms and ounces.

        Args:
            quantity (float): Amount to convert.
            to_oz (bool): Set to True if ``quantity`` is in kg, otherwise
                False.

        Returns:
            float: The value of ``quantity`` in either kg or oz, depending on
                ``to_oz``.
        """
        oz = self.env.ref('product.product_uom_oz')
        kg = self.env.ref('product.product_uom_kgm')
        if to_oz:
            return kg._compute_quantity(quantity, oz)
        else:
            return oz._compute_quantity(quantity, kg)

    @api.model_cr_context
    def _convert_meter_inch(self, quantity, to_in=True):
        """Convert between cubic meters and inches.

        Args:
            quantity (float): Amount to convert.
            to_in (bool): Set to True if ``quantity`` is in meters, otherwise
                False.

        Returns:
            float: The value of ``quantity`` in either meter or inch,
                depending on ``to_in``.
        """
        inch_factor = 61023.7441
        if to_in:
            return quantity * inch_factor
        else:
            return quantity / inch_factor
