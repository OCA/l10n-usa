# Copyright 2026 Ledo <https://ledoweb.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestACHBase(TransactionCase):
    """Exercise the three pieces of value this module ships:

    1. ``res.bank.routing_number`` US-RTN format constraint.
    2. ``account.banking.mandate.delay_days`` blocks payment-line creation
       while the delay has not elapsed.
    3. ``account.banking.mandate.create`` auto-sets payment modes on the
       partner when matching modes exist.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        cls.ca = cls.env.ref("base.ca")

    # ─── 1. routing_number constraint ───────────────────────────────────

    def test_us_routing_number_valid(self):
        """A valid 9-digit US routing number passes the constraint."""
        # 122000661 (Wells Fargo) — passes stdnum.us.rtn checksum.
        bank = self.env["res.bank"].create(
            {
                "name": "Wells Fargo Test",
                "country": self.us.id,
                "routing_number": "122000661",
            }
        )
        self.assertEqual(bank.routing_number, "122000661")

    def test_us_routing_number_invalid_raises(self):
        """A 9-digit number with a bad checksum triggers ValidationError.

        Note: stdnum.us.rtn uses a Luhn-like mod-10 weighting; 000000000
        actually passes (sum == 0). Use 123456789 which the same algorithm
        rejects (sum mod 10 = 9, not 0).
        """
        with self.assertRaises(ValidationError):
            self.env["res.bank"].create(
                {
                    "name": "Bogus US Bank",
                    "country": self.us.id,
                    "routing_number": "123456789",
                }
            )

    def test_ca_routing_number_format(self):
        """A Canadian routing number must be exactly 8 digits."""
        # 8-digit valid example.
        self.env["res.bank"].create(
            {
                "name": "Royal Bank of Canada Test",
                "country": self.ca.id,
                "routing_number": "00030001",
            }
        )
        # 7 digits fails.
        with self.assertRaises(ValidationError):
            self.env["res.bank"].create(
                {
                    "name": "Bad CA Bank",
                    "country": self.ca.id,
                    "routing_number": "0003000",
                }
            )

    # ─── 2. mandate.delay_days enforced on payment-line creation ────────

    def test_mandate_validate_requires_delay_days(self):
        """validate() on a mandate with delay_days=0 raises UserError."""
        # Create the minimum partner + bank account + mandate scaffold.
        partner = self.env["res.partner"].create(
            {"name": "Customer ACH Test", "customer_rank": 1}
        )
        bank = self.env["res.bank"].create(
            {
                "name": "Test Bank Delay",
                "country": self.us.id,
                "routing_number": "122000661",
            }
        )
        partner_bank = self.env["res.partner.bank"].create(
            {"partner_id": partner.id, "bank_id": bank.id, "acc_number": "TEST-ACH-001"}
        )
        mandate = self.env["account.banking.mandate"].create(
            {
                "partner_bank_id": partner_bank.id,
                "delay_days": 0,
                "signature_date": "2024-01-01",
            }
        )
        with self.assertRaises(UserError):
            mandate.validate()
