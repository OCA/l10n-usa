# Copyright 2026 Ledo <https://ledoweb.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from stdnum.exceptions import InvalidComponent
from stdnum.us import ein, ssn

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestLegalIDNumber(TransactionCase):
    """Validate the EIN / SSN / Canadian-BN constraint on res.partner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    def test_valid_ssn_accepted(self):
        """A valid SSN saves cleanly."""
        partner = self.Partner.create(
            {"name": "Jane Doe", "legal_id_number": "123-45-6789"}
        )
        self.assertEqual(partner.legal_id_number, "123-45-6789")

    def test_valid_ein_accepted(self):
        """A valid EIN (NN-NNNNNNN) saves cleanly, hyphenated or bare."""
        for number in ("12-3456789", "123456789"):
            partner = self.Partner.create(
                {"name": f"Acme {number}", "legal_id_number": number}
            )
            self.assertEqual(partner.legal_id_number, number)

    def test_misplaced_ein_separator_rejected(self):
        """1-23456789 is nine digits but is not an EIN, SSN or Canadian BN."""
        with self.assertRaises(UserError):
            self.Partner.create({"name": "Bad Sep Co", "legal_id_number": "1-23456789"})

    def test_multiple_partners_created_at_once(self):
        """The constraint runs over a recordset, not a single record."""
        partners = self.Partner.create(
            [
                {"name": "Acme Inc", "legal_id_number": "12-3456789"},
                {"name": "Jane Doe", "legal_id_number": "123-45-6789"},
            ]
        )
        self.assertEqual(len(partners), 2)

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

    def test_ein_prefix_unchecked_when_the_campus_data_is_unreadable(self):
        """00-1234567 owns no IRS campus, but the fallback checks format only."""
        with patch.object(ein, "validate", side_effect=OSError("orphan path")):
            partner = self.Partner.create(
                {"name": "Unassigned Prefix Co", "legal_id_number": "00-1234567"}
            )
        self.assertEqual(partner.legal_id_number, "00-1234567")

    def test_ein_prefix_is_rejected_when_the_campus_data_is_readable(self):
        """stdnum's campus rejection is honoured wherever it can be read."""
        with patch.object(ein, "validate", side_effect=InvalidComponent()):
            with self.assertRaises(UserError):
                self.Partner.create(
                    {"name": "Unassigned Prefix Co", "legal_id_number": "00-1234567"}
                )

    def test_non_validation_errors_are_not_swallowed(self):
        """An environment failure surfaces instead of reading as a bad number."""
        with patch.object(ssn, "validate", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                self.Partner.create(
                    {"name": "Env Broken", "legal_id_number": "123-45-6789"}
                )

    def test_blank_legal_id_allowed(self):
        """Legal ID is optional — partners without one save cleanly."""
        partner = self.Partner.create({"name": "Anon Co"})
        self.assertFalse(partner.legal_id_number)
