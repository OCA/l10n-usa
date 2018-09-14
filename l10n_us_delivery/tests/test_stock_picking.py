# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo.tests.common import TransactionCase


class TestStockPicking(TransactionCase):

    def setUp(self):
        super(TestStockPicking, self).setUp()
        self.model = self.env['stock.picking']
        self.oz = self.env.ref('product.product_uom_oz')

    def test_stock_picking_ounces(self):
        """It should try to pick ounces first."""
        self.assertEqual(self.model._default_uom(), self.oz)

    def test_stock_picking_fallback(self):
        """It should fallback to super when no ounces."""
        self.oz.unlink()
        self.assertTrue(self.model._default_uom())
