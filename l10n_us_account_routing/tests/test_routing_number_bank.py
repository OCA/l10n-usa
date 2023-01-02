from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestResBank(TransactionCase):
    def setUp(self):
        super(TestResBank, self).setUp()
        self.us_bank = self.env["res.bank"].create(
            {
                "name": "US Bank",
                "country": self.env["res.country"].search([("code", "=", "US")]).id,
            }
        )

        self.canadian_bank = self.env["res.bank"].create(
            {
                "name": "Canadian Bank",
                "country": self.env["res.country"].search([("code", "=", "CA")]).id,
            }
        )

        self.belgium_bank = self.env["res.bank"].create(
            {
                "name": "Belgium Bank",
                "country": self.env["res.country"].search([("code", "=", "BE")]).id,
            }
        )

    def test_routing_number_us_bank(self):
        number = self.us_bank.routing_number = 310033974
        self.assertEqual(
            number,
            310033974,
            "You should have the routing number 310033974 for the bank %s"
            % self.us_bank.name,
        )
        # We want to test the exception
        with self.assertRaises(ValidationError):
            self.us_bank.routing_number = 1

    def test_routing_number_canadian_bank(self):
        number = self.canadian_bank.routing_number = 12162004
        self.assertEqual(
            number,
            12162004,
            "You should have the routing number 12162004 for the bank %s"
            % self.canadian_bank.name,
        )
        # We want to test the exception
        with self.assertRaises(ValidationError):
            self.canadian_bank.routing_number = 1

    def test_routing_number_belgium_bank(self):
        number = self.belgium_bank.routing_number = 5
        self.assertEqual(
            number,
            5,
            "You should have the routing number 5 for the bank %s"
            % self.belgium_bank.name,
        )
