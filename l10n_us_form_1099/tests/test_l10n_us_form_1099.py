# Copyright (C) 2019 Brian McMaster
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestL10nUsForm1099(TransactionCase):

    def test_on_change_is_1099(self):
        """
            Test that supplier is True if is_1099 is True
        """
        partner = self.env.ref('base.res_partner_2')
        partner.is_1099 = True
        partner._on_change_is_1099()
        self.assertTrue(partner.supplier)

    def test_on_change_supplier(self):
        """
            Test that is_1099 is False if supplier is False
        """
        partner = self.env.ref('base.res_partner_2')
        partner.supplier = False
        partner._on_change_supplier()
        self.assertFalse(partner.is_1099)
