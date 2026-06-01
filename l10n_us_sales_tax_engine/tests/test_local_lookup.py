# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date

from .common import UsTaxBaseTest


class TestLocalLookup(UsTaxBaseTest):
    def test_zip_to_jurisdiction(self):
        """ZIP 33101 must resolve to Miami-Dade jurisdiction."""
        jur = self.env["us.tax.zip.mapping"].get_best_jurisdiction("33101", "FL")
        self.assertTrue(jur, "Jurisdiction not found for ZIP 33101")
        self.assertEqual(jur.county, "MIAMI-DADE")

    def test_rate_for_date(self):
        """Rate must return FL 7% for Miami-Dade on 2025-01-01."""
        rate = self.env["us.tax.rate"].get_rate_for_date(
            self.jur_miami.id, date(2025, 1, 1)
        )
        self.assertTrue(rate, "No rate found for Miami-Dade")
        self.assertAlmostEqual(rate.state_rate, 0.06, places=4)
        self.assertAlmostEqual(rate.county_rate, 0.01, places=4)
        self.assertAlmostEqual(rate.total_rate, 0.07, places=4)

    def test_rate_before_effective_date(self):
        """No rate should be found before effective_date."""
        rate = self.env["us.tax.rate"].get_rate_for_date(
            self.jur_miami.id, date(2019, 12, 31)
        )
        self.assertFalse(rate, "Rate found before effective date — should be empty")

    def test_rate_falls_back_to_generic_when_no_category_specific_rate(self):
        """A jurisdiction imported with only a generic rate (the normal case
        for bulk imports like Florida DOR) must still resolve a rate when a
        specific category is requested — this is the bug fixed today."""
        jur_broward = self.env["us.tax.jurisdiction"].create(
            {
                "name": "Broward",
                "type": "county",
                "state_id": self.fl.id,
                "county": "BROWARD",
            }
        )
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jur_broward.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        rate = self.env["us.tax.rate"].get_rate_for_date(
            jur_broward.id, date(2025, 1, 1), product_category_id=self.cat_tangible.id
        )
        self.assertTrue(
            rate, "Generic rate must be used as fallback for TANGIBLE lookup"
        )
        self.assertFalse(rate.product_tax_category_id)
        self.assertAlmostEqual(rate.total_rate, 0.07, places=4)

    def test_rate_prefers_category_specific_over_generic(self):
        """When both a generic and a TANGIBLE-specific rate exist for the
        same jurisdiction, the specific one must win."""
        rate = self.env["us.tax.rate"].get_rate_for_date(
            self.jur_miami.id,
            date(2025, 1, 1),
            product_category_id=self.cat_tangible.id,
        )
        self.assertTrue(rate)
        self.assertEqual(rate.product_tax_category_id, self.cat_tangible)

    def test_low_confidence_zip_not_matched(self):
        """ZIP mapping with confidence below threshold should not match."""
        # Create low-confidence mapping
        self.env["us.tax.zip.mapping"].create(
            {
                "zip": "33999",
                "state_id": self.fl.id,
                "jurisdiction_id": self.jur_miami.id,
                "confidence": 0.3,
                "source": "test",
            }
        )
        jur = self.env["us.tax.zip.mapping"].get_best_jurisdiction(
            "33999", "FL", confidence_min=0.7
        )
        self.assertFalse(jur, "Low confidence ZIP should not match at threshold 0.7")

    def test_unknown_zip_returns_empty(self):
        """Unknown ZIP must return empty recordset."""
        jur = self.env["us.tax.zip.mapping"].get_best_jurisdiction("99999", "FL")
        self.assertFalse(jur)


class TestNexus(UsTaxBaseTest):
    def test_nexus_exists_for_fl(self):
        """Company must have nexus in FL."""
        has = self.env["us.tax.nexus"].has_nexus(self.env.company.id, self.fl.id)
        self.assertTrue(has)

    def test_no_nexus_for_ny(self):
        """Company should NOT have nexus in NY (not configured)."""
        has = self.env["us.tax.nexus"].has_nexus(self.env.company.id, self.ny.id)
        self.assertFalse(has)


class TestProductCategory(UsTaxBaseTest):
    def test_tangible_is_taxable(self):
        """TANGIBLE category must be taxable by default."""
        taxable, override = self.env["us.tax.rule"].is_taxable(
            self.fl.id, self.cat_tangible.id
        )
        self.assertTrue(taxable)
        self.assertIsNone(override)

    def test_exempt_not_taxable(self):
        """EXEMPT category must never be taxable."""
        taxable, _ = self.env["us.tax.rule"].is_taxable(self.fl.id, self.cat_exempt.id)
        self.assertFalse(taxable)
