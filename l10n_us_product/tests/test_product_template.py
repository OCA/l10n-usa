# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo.tests.common import TransactionCase


class TestProductTemplate(TransactionCase):

    def setUp(self):
        super(TestProductTemplate, self).setUp()
        self.product = self.env['product.template'].search([], limit=1)
        self.product.write({
            'weight': 1.02058,  # 35.980000000000004 oz,
            'volume': 2,  # 2 cubic meter, 122047.4882 cubic inch
        })

    def test_compute_weight_oz(self):
        self.assertEqual(self.product.weight_oz, 35.980000000000004)

    def test_inverse_weight_oz(self):
        self.product.weight_oz = 20
        self.assertEqual(self.product.weight, 0.5700000000000001)

    def test_compute_volume_in(self):
        self.assertEqual(self.product.volume_in, 122047.4882)

    def test_inverse_volume_in(self):
        self.product.volume_in = 2000
        self.assertEqual(self.product.volume, 0.03277412799717086)
