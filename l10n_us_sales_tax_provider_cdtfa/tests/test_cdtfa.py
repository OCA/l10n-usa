# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import MagicMock, patch

import requests

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import ProviderError
from odoo.addons.l10n_us_sales_tax_engine.tests.common import UsTaxBaseTest

from ..services.provider_cdtfa import CA_BASE_RATE, ProviderCdtfa

# Real CDTFA GetRateByAddress response shape (Sacramento, 8.75%).
SAMPLE = {
    "taxRateInfo": [
        {
            "rate": 0.0875,
            "jurisdiction": "SACRAMENTO",
            "city": "SACRAMENTO",
            "county": "SACRAMENTO",
            "tac": "340607050000",
        }
    ],
    "geocodeInfo": {"calcMethod": "Rooftop", "confidence": "High"},
}

_PATH = (
    "odoo.addons.l10n_us_sales_tax_provider_cdtfa.services.provider_cdtfa.requests.get"
)


class TestCdtfaProvider(UsTaxBaseTest):
    def _provider(self):
        return (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "cdtfa")], limit=1)
        )

    def test_cdtfa_registers_via_extension_point(self):
        prov = self._provider()
        self.assertTrue(prov, "cdtfa provider record should ship from this module")
        self.assertIn("cdtfa", prov._provider_service_classes())
        self.assertIs(prov._get_provider_service(), ProviderCdtfa)

    def test_normalize_splits_combined_into_base_and_district(self):
        svc = ProviderCdtfa(self._provider())
        result = svc.normalize_response(SAMPLE["taxRateInfo"][0])
        self.assertAlmostEqual(result["total_rate"], 0.0875, places=6)
        self.assertAlmostEqual(result["state_rate"], CA_BASE_RATE, places=6)
        self.assertAlmostEqual(result["district_rate"], 0.0875 - CA_BASE_RATE, places=6)
        # State + district reproduce the exact rooftop total.
        self.assertAlmostEqual(
            result["state_rate"] + result["district_rate"],
            result["total_rate"],
            places=6,
        )

    def test_non_ca_raises_so_engine_falls_through(self):
        svc = ProviderCdtfa(self._provider())
        with self.assertRaises(ProviderError):
            svc.get_rate({"state": "NY", "zip": "10001"})

    @patch(_PATH)
    def test_get_rate_books_state_and_named_district(self, mock_get):
        resp = MagicMock()
        resp.json.return_value = SAMPLE
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp

        svc = ProviderCdtfa(self._provider())
        result = svc.get_rate(
            {
                "state": "CA",
                "zip": "95814",
                "city": "Sacramento",
                "address": "450 N St",
            }
        )
        self.assertAlmostEqual(result["total_rate"], 0.0875, places=6)
        by_level = {j["level"]: j for j in result["jurisdictions"]}
        self.assertEqual(by_level["state"]["label"], "California")
        self.assertIn("district", by_level)
        self.assertEqual(by_level["district"]["label"], "Sacramento (CA)")
        self.assertAlmostEqual(
            by_level["district"]["rate"], 0.0875 - CA_BASE_RATE, places=6
        )

    @patch(_PATH)
    def test_no_rate_raises_provider_error(self, mock_get):
        # An empty taxRateInfo (CDTFA found no rooftop) must raise ProviderError
        # so the engine falls through rather than booking a 0% rate.
        resp = MagicMock()
        resp.json.return_value = {"taxRateInfo": []}
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp

        svc = ProviderCdtfa(self._provider())
        with self.assertRaises(ProviderError):
            svc.get_rate({"state": "CA", "zip": "95814", "address": "1 Main St"})

    @patch(_PATH)
    def test_request_error_wrapped_as_provider_error(self, mock_get):
        # A connection failure (DNS/network down) must surface as a ProviderError,
        # not escape uncaught and abort the engine's calculation.
        mock_get.side_effect = requests.ConnectionError("network down")

        svc = ProviderCdtfa(self._provider())
        with self.assertRaises(ProviderError):
            svc.get_rate({"state": "CA", "zip": "95814", "address": "1 Main St"})
