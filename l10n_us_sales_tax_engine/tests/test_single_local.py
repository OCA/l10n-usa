# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestSingleLocalUseRate(UsTaxBaseTest):
    """Remote-seller single/simplified local rate (generalized beyond Texas).

    A remote (interstate) seller that has elected (or is subject to) a state's
    single local rate collects a flat rate instead of the actual local rate at
    each destination ZIP - add-on (TX: 6.25% + 1.75% = 8.00%) or combined-flat
    (AL SSUT 8%).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svc = cls.env["us.tax.engine.service"]
        cls.Nexus = cls.env["us.tax.nexus"]
        cls.tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", cls.us.id)], limit=1
        )
        # A TX destination with a real local rate: 6.25% state + 2.00% city.
        cls.jur_tx = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Houston",
                "type": "city",
                "state_id": cls.tx.id,
                "city": "HOUSTON",
                "fips_state": "48",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_tx.id,
                "state_rate": 0.0625,
                "county_rate": 0.0,
                "city_rate": 0.02,
                "district_rate": 0.0,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "77001",
                "state_id": cls.tx.id,
                "jurisdiction_id": cls.jur_tx.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        # Seller in FL -> interstate (remote) relative to TX.
        cls.env.company.partner_id.write(
            {"country_id": cls.us.id, "state_id": cls.fl.id, "zip": "33102"}
        )
        cls.nexus_tx = cls.Nexus.create(
            {"company_id": cls.env.company.id, "state_id": cls.tx.id, "active": True}
        )

    def _tx_base_rate(self):
        prov = self.env["us.tax.provider"].search([("code", "=", "local")], limit=1)
        svc = prov._get_provider_service()(prov)
        return svc.get_rate({"zip": "77001", "state": "TX", "date": "2026-01-15"})

    def test_fl_seller_is_interstate_into_tx(self):
        self.assertTrue(self.svc._is_interstate(self.env.company.id, "TX"))

    def test_no_election_keeps_actual_local_rate(self):
        base = self._tx_base_rate()
        self.assertAlmostEqual(base["total_rate"], 0.0825, places=4)
        self.assertFalse(
            self.Nexus._single_local_nexus(self.env.company.id, self.tx.id)
        )

    def test_election_helper_returns_rate(self):
        self.nexus_tx.write(
            {"single_local_rate_elected": True, "single_local_rate": 0.0175}
        )
        self.assertEqual(
            self.Nexus._single_local_nexus(
                self.env.company.id, self.tx.id
            ).single_local_rate,
            0.0175,
        )

    def test_election_not_elected_returns_none(self):
        self.nexus_tx.write(
            {"single_local_rate_elected": False, "single_local_rate": 0.0175}
        )
        self.assertFalse(
            self.Nexus._single_local_nexus(self.env.company.id, self.tx.id)
        )

    def test_intrastate_seller_gets_no_single_local(self):
        """An in-TX seller is destination-sourced at the real local rate even
        with the election set - single-local is a remote-seller mechanism."""
        self.nexus_tx.write(
            {"single_local_rate_elected": True, "single_local_rate": 0.0175}
        )
        self.env.company.partner_id.write(
            {"country_id": self.us.id, "state_id": self.tx.id, "zip": "77001"}
        )
        self.assertFalse(self.svc._is_interstate(self.env.company.id, "TX"))
        self.assertIsNone(
            self.svc._single_local_for(self.env.company.id, self.tx, "TX")
        )

    def test_add_on_mode_flattens_to_state_plus_single(self):
        base = self._tx_base_rate()  # 6.25 + 2.00 city = 8.25 actual
        out = self.svc._apply_single_local_rate(
            base, {"rate": 0.0175, "mode": "add_on"}, "TX"
        )
        self.assertAlmostEqual(out["total_rate"], 0.08, places=4)
        self.assertAlmostEqual(out["state_rate"], 0.0625, places=4)
        self.assertAlmostEqual(out["district_rate"], 0.0175, places=4)
        self.assertEqual(out["county_rate"], 0.0)
        self.assertEqual(out["city_rate"], 0.0)  # actual city rate dropped
        self.assertEqual(out["source"], "single_local")
        # State component keeps its jurisdiction tag + FIPS.
        state_j = [j for j in out["jurisdictions"] if j["level"] == "state"][0]
        self.assertEqual(state_j["fips"], "48")

    def test_combined_mode_replaces_state_and_local(self):
        """Alabama-SSUT style: the flat rate replaces state + local entirely."""
        base = self._tx_base_rate()
        out = self.svc._apply_single_local_rate(
            base, {"rate": 0.08, "mode": "combined"}, "AL"
        )
        self.assertAlmostEqual(out["total_rate"], 0.08, places=4)
        self.assertAlmostEqual(out["state_rate"], 0.08, places=4)
        self.assertEqual(out["district_rate"], 0.0)
        self.assertEqual(len(out["jurisdictions"]), 1)  # one combined line

    def test_mandatory_rate_applies_without_election(self):
        self.nexus_tx.write(
            {
                "single_local_rate_elected": False,
                "single_local_mandatory": True,
                "single_local_rate": 0.0175,
            }
        )
        self.assertEqual(
            self.Nexus._single_local_nexus(
                self.env.company.id, self.tx.id
            ).single_local_rate,
            0.0175,
        )

    def test_single_local_for_returns_mode_for_mandatory_combined(self):
        """End-to-end: a mandatory + combined nexus drives _single_local_for."""
        self.nexus_tx.write(
            {
                "single_local_rate_elected": False,
                "single_local_mandatory": True,
                "single_local_rate": 0.08,
                "single_local_mode": "combined",
            }
        )
        cfg = self.svc._single_local_for(self.env.company.id, self.tx, "TX")
        self.assertEqual(cfg, {"rate": 0.08, "mode": "combined"})

    def test_zero_rate_is_excluded_even_if_flagged(self):
        """A flagged nexus with a 0 rate must not match (OR-domain guard)."""
        self.nexus_tx.write({"single_local_mandatory": True, "single_local_rate": 0.0})
        self.assertFalse(
            self.Nexus._single_local_nexus(self.env.company.id, self.tx.id)
        )

    def test_apply_defaults_to_add_on_mode(self):
        base = self._tx_base_rate()
        out = self.svc._apply_single_local_rate(base, {"rate": 0.0175}, "TX")
        self.assertAlmostEqual(out["total_rate"], 0.08, places=4)
        self.assertEqual(len(out["jurisdictions"]), 2)  # add-on: state + district

    def test_full_calculation_logs_the_single_local_source(self):
        """The whole flow, not just the helpers.

        Every other test here calls ``_single_local_for`` / ``_apply_single_local_rate``
        directly, so nothing ever carried source='single_local' through to the
        audit log. Drive ``_process`` so the log write is exercised too.
        """
        from types import SimpleNamespace

        self.nexus_tx.write(
            {"single_local_rate_elected": True, "single_local_rate": 0.0175}
        )
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_tax.engine_active", "True")
        ICP.set_param("l10n_us_tax.engine_mode", "local")

        result = self.svc._process(
            "sale.order",
            0,
            {"zip": "77001", "state": "TX", "city": "HOUSTON", "country": "US"},
            [
                SimpleNamespace(
                    id=0,
                    price_subtotal=100.0,
                    product_id=self.env["product.product"],
                )
            ],
            "2026-01-15",
            self.env.company.id,
            self.env.company.currency_id.id,
            lambda res: None,
        )
        detail = result["lines"][0]["rate_detail"]
        self.assertEqual(detail["source"], "single_local")
        # 6.25% state + 1.75% elected single local, not the actual 2% city rate.
        self.assertAlmostEqual(detail["total_rate"], 0.08, places=4)

        log = self.env["us.tax.calculation.log"].search(
            [("res_model", "=", "sale.order"), ("res_id", "=", 0)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.source, "single_local")
