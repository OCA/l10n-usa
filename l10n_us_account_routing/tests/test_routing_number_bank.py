from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestResBank(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us_bank = cls.env["res.bank"].create(
            {
                "name": "US Bank",
                "country": cls.env.ref("base.us").id,
            }
        )
        cls.canadian_bank = cls.env["res.bank"].create(
            {
                "name": "Canadian Bank",
                "country": cls.env.ref("base.ca").id,
            }
        )
        cls.belgium_bank = cls.env["res.bank"].create(
            {
                "name": "Belgium Bank",
                "country": cls.env.ref("base.be").id,
            }
        )

    def test_routing_number_us_bank(self):
        number = self.us_bank.routing_number = 310033974
        bank_name = self.us_bank.name
        self.assertEqual(
            number,
            310033974,
            f"You should have the routing number {number} for the bank {bank_name}",
        )
        # We want to test the exception
        with self.assertRaises(ValidationError):
            self.us_bank.routing_number = 1

    def test_routing_number_canadian_bank(self):
        number = self.canadian_bank.routing_number = 12162004
        bank_name = self.canadian_bank.name
        self.assertEqual(
            number,
            12162004,
            f"You should have the routing number 12162004 for the bank {bank_name}",
        )
        # We want to test the exception
        with self.assertRaises(ValidationError):
            self.canadian_bank.routing_number = 1

    def test_routing_number_belgium_bank(self):
        number = self.belgium_bank.routing_number = 5
        bank_name = self.belgium_bank.name
        self.assertEqual(
            number,
            5,
            f"You should have the routing number 5 for the bank {bank_name}",
        )
