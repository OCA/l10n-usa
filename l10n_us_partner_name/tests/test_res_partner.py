# -*- coding: utf-8 -*-
# Copyright 2016 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo.tests.common import TransactionCase


class TestResPartner(TransactionCase):

    def setUp(self):
        super(TestResPartner, self).setUp()
        self.first_name = 'Dave'
        self.last_name = 'Lasley'
        self.partner = self.env['res.partner'].create({
            'name': '%s %s' % (self.first_name, self.last_name),
        })

    def test_get_inverse_name_firstname(self):
        """ It should properly set firstname on partner """
        self.assertEqual(
            self.partner.firstname, self.first_name,
        )

    def test_get_inverse_name_lastname(self):
        """ It should properly set lastname on partner """
        self.assertEqual(
            self.partner.lastname, self.last_name,
        )

    def test_get_computed_name(self):
        """ It should compute name as `Firstname Lastname` """
        self.assertEqual(
            self.partner.name,
            '%s %s' % (self.first_name, self.last_name),
        )
