# Copyright 2026 Ledo <https://ledoweb.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestLegalIDNumber(TransactionCase):
    """Validate the EIN / SSN / Canadian-BN constraint on res.partner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    def test_valid_ssn_accepted(self):
        """A valid SSN (NNN-NN-NNNN with non-blacklisted area) saves cleanly.

        stdnum.us.ssn rejects 666-XX-XXXX, 9XX-XX-XXXX, XXX-00-XXXX, etc.
        Use 123-45-6789 which passes the format check.
        """
        partner = self.Partner.create(
            {"name": "Jane Doe", "legal_id_number": "123-45-6789"}
        )
        self.assertEqual(partner.legal_id_number, "123-45-6789")

    def test_invalid_legal_id_raises(self):
        """A garbage string fails EIN, SSN, and CBN validation → UserError."""
        with self.assertRaises(UserError):
            self.Partner.create(
                {"name": "Bad Co", "legal_id_number": "not-a-real-number"}
            )

    def test_canadian_business_number_accepted(self):
        """A valid 9-digit Canadian Business Number saves cleanly."""
        # 123456782 is the stdnum.ca.bn example with valid check digit.
        partner = self.Partner.create(
            {"name": "Maple Co Ltd", "legal_id_number": "123456782"}
        )
        self.assertEqual(partner.legal_id_number, "123456782")

    def test_blank_legal_id_allowed(self):
        """Legal ID is optional — partners without one save cleanly."""
        partner = self.Partner.create({"name": "Anon Co"})
        self.assertFalse(partner.legal_id_number)
