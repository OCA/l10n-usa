# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _dynamicherit = 'product.template'

    weight_dynamic = fields.Float(
        string='Weight',
        compute='_compute_weight_dynamic',
        inverse='_inverse_weight_dynamic',
        help='Weight of the product.',
    )
    weight_dynamic_uom_id = fields.Many2one(
        string='Weight UoM',
        comodel_name='product.uom',
        help='Unit of measure for the product weight.',
        default=lambda s: s.env['res.lang'].default_uom_by_category('Weight'),
    )
    volume_dynamic = fields.Float(
        string='Volume',
        compute='_compute_volume_dynamic',
        inverse='_inverse_volume_dynamic',
        help='Volume of the product.',
    )
    volume_dynamic_uom_id = fields.Many2one(
        string='Weight UoM',
        comodel_name='product.uom',
        help='Unit of measure for the product volume.',
    )

    @api.multi
    @api.depends('weight')
    def _compute_weight_dynamic(self):
        for record in self:
            record.weight_dynamic = self._convert_kilogram_dynamic(
                record.weight,
            )

    @api.multi
    def _inverse_weight_dynamic(self):
        for record in self:
            record.weight = self._convert_kilogram_dynamic(
                record.weight_dynamic, to_dynamic=False,
            )

    @api.multi
    @api.depends('volume')
    def _compute_volume_dynamic(self):
        for record in self:
            record.volume_dynamic = self._convert_meter_dynamic(record.volume)

    @api.multi
    def _inverse_volume_dynamic(self):
        for record in self:
            record.volume = self._convert_meter_dynamic(
                record.volume_dynamic, to_dynamic=False,
            )

    @api.model_cr_context
    def _convert_kilogram_dynamic(self, quantity, dynamic_unit, in_kg=True):
        """Convert between kilograms dynamically.

        Args:
            quantity (float): Amount to convert.
            dynamic_unit (ProductUom): Unit of measure to convert with.
            in_kg (bool): Set to True if ``quantity`` is in kg, otherwise
                False.

        Returns:
            float: The value of ``quantity`` in either kg or the dynamic unit,
                depending on ``in_kg``.
        """
        kg = self.env.ref('product.product_uom_kgm')
        if in_kg:
            return kg._compute_quantity(quantity, dynamic_unit)
        else:
            return dynamic._compute_quantity(quantity, kg)

    @api.model_cr_context
    def _convert_meter_dynamic(self, quantity, dynamic_unit, in_meter=True):
        """Convert between cubic meters dynamically.

        Args:
            quantity (float): Amount to convert.
            dynamic_unit (ProductUom): Unit of measure to convert with.
            in_meter (bool): Set to True if ``quantity`` is in cubic meter,
                otherwise False.

        Returns:
            float: The value of ``quantity`` in either kg or the dynamic unit,
                depending on ``in_meter``.
        """
        inch_factor = 61023.7441
        if in_meter:
            return quantity * inch_factor
        else:
            return quantity / inch_factor
