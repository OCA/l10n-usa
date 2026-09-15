# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestAddressJurisdictionCache(UsTaxBaseTest):
    """Address -> jurisdiction learned cache.

    A ZIP can straddle two jurisdictions; ZIP-level resolution picks one
    (possibly wrong). Once an authoritative source resolves the rooftop, the
    address -> jurisdiction assignment is learned and wins thereafter, so the
    same address always resolves to the same correct jurisdiction and the
    upstream provider is not called again.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ZM = cls.env["us.tax.zip.mapping"]
        # Base fixture: 33101 -> Miami-Dade (the ZIP-level guess).
        # Add a second FL jurisdiction the same ZIP could straddle.
        cls.jur_broward = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Broward",
                "type": "county",
                "state_id": cls.fl.id,
                "county": "BROWARD",
                "fips_state": "12",
                "fips_county": "011",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_broward.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.0,
                "district_rate": 0.0,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.addr = {
            "zip": "33101",
            "state": "FL",
            "city": "MIAMI",
            "address": "123 Straddle Rd, Miami, FL 33101",
        }

    def test_address_key_normalizes_and_empties_without_street(self):
        self.assertEqual(
            self.ZM._address_key(self.addr), "123 STRADDLE RD, MIAMI, FL 33101"
        )
        self.assertEqual(self.ZM._address_key({"address": " ,  Miami, FL 33101"}), "")
        self.assertEqual(self.ZM._address_key({"address": ""}), "")

    def test_resolve_falls_back_to_zip_before_learning(self):
        # No learned rooftop yet -> ZIP-level pick (Miami-Dade).
        self.assertEqual(self.ZM.resolve_jurisdiction(self.addr), self.jur_miami)

    def test_learned_rooftop_wins_over_zip(self):
        # ZIP still says Miami-Dade...
        self.assertEqual(self.ZM.get_best_jurisdiction("33101", "FL"), self.jur_miami)
        # ...but once the rooftop is learned, the address resolves to Broward.
        self.ZM.learn_jurisdiction(self.addr, self.jur_broward, source="api")
        self.assertEqual(self.ZM.resolve_jurisdiction(self.addr), self.jur_broward)
        # ZIP-level resolution is untouched.
        self.assertEqual(self.ZM.get_best_jurisdiction("33101", "FL"), self.jur_miami)

    def test_learn_is_idempotent_one_row_per_address(self):
        self.ZM.learn_jurisdiction(self.addr, self.jur_broward)
        self.ZM.learn_jurisdiction(self.addr, self.jur_broward)
        rows = self.ZM.search([("address_key", "=", self.ZM._address_key(self.addr))])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows.verified)
        self.assertEqual(rows.confidence, 1.0)

    def test_relearn_updates_jurisdiction(self):
        self.ZM.learn_jurisdiction(self.addr, self.jur_miami)
        self.ZM.learn_jurisdiction(self.addr, self.jur_broward)  # corrected
        self.assertEqual(self.ZM.resolve_jurisdiction(self.addr), self.jur_broward)

    def test_provider_local_uses_learned_rooftop(self):
        # The local provider resolves via the address, so after learning it
        # returns the rooftop jurisdiction's rate without any external call.
        self.ZM.learn_jurisdiction(self.addr, self.jur_broward, source="api")
        prov = self.env["us.tax.provider"].search([("code", "=", "local")], limit=1)
        svc = prov._get_provider_service()(prov)
        res = svc.get_rate(
            {
                "zip": "33101",
                "state": "FL",
                "city": "MIAMI",
                "address": "123 Straddle Rd, Miami, FL 33101",
                "date": "2026-01-15",
            }
        )
        # Broward rate (6% + 1% county). Jurisdiction tag is Broward.
        self.assertAlmostEqual(res["total_rate"], 0.07, places=4)
        jl = res.get("jurisdictions") or []
        self.assertTrue(any(j["jurisdiction_id"] == self.jur_broward.id for j in jl))
