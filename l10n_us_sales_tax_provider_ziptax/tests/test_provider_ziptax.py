# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.tests.common import mute_logger

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import ProviderError
from odoo.addons.l10n_us_sales_tax_engine.services.provider_local import ProviderLocal
from odoo.addons.l10n_us_sales_tax_engine.tests.common import UsTaxBaseTest

from ..services.provider_ziptax import ProviderZipTax


class TestProviderZipTax(UsTaxBaseTest):
    def _ziptax_provider(self):
        return (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "ziptax")], limit=1)
        )

    def test_ziptax_registered_in_provider_service_classes(self):
        """Installing this module must register "ziptax" without editing the
        engine — the registry must still contain "local" too."""
        provider = self._ziptax_provider()
        self.assertTrue(provider, "ziptax provider record should exist from data")
        classes = provider._provider_service_classes()
        self.assertTrue({"local", "ziptax"} <= set(classes))
        self.assertIs(classes["ziptax"], ProviderZipTax)
        self.assertIs(provider._get_provider_service(), ProviderZipTax)

    @mute_logger("odoo.addons.l10n_us_sales_tax_engine.services.tax_engine")
    def test_local_to_ziptax_fallback(self):
        """If the local provider fails, the engine must fall back to ZipTax
        when it is active with a lower priority than local."""
        ziptax = self._ziptax_provider()
        ziptax.write({"active": True, "priority": 5})

        fake_rate = {
            "state_rate": 0.06,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": 0.0,
            "total_rate": 0.06,
            "source_date": None,
            "raw_response": {},
        }
        engine = self.env["us.tax.engine.service"]
        with (
            patch.object(
                ProviderLocal, "get_rate", side_effect=ProviderError("local down")
            ),
            patch.object(ProviderZipTax, "get_rate", return_value=fake_rate),
        ):
            result = engine.calculate_for_sale_order(self.sale_order_fl)

        self.assertEqual(result["source"], "api")
        rate_detail = result["lines"][0]["rate_detail"]
        self.assertEqual(rate_detail["provider_id"], ziptax.id)
        self.assertAlmostEqual(rate_detail["total_rate"], 0.06, places=4)

    def test_get_rate_sends_postalcode_and_parses_real_response_shape(self):
        """Regression guard: zip.tax's v40 endpoint requires the request
        param "postalcode" (not "zip") and returns field names like
        "taxSales"/"countySalesTax" (not "combinedSalesTaxRate"/
        "countyTaxRate"). Both were wrong before and silently produced
        rCode=104/empty results or 0.0 rates against the real API — this
        captures the exact JSON shape of a real successful response."""
        ziptax = self._ziptax_provider()
        ziptax.write({"active": True})
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.ziptax_api_key", "fake-test-key"
        )
        service = ziptax._get_provider_service()(ziptax)

        real_response_json = {
            "version": "v40",
            "rCode": 100,
            "results": [
                {
                    "geoPostalCode": "33101",
                    "geoCity": "MIAMI",
                    "geoCounty": "MIAMI-DADE",
                    "geoState": "FL",
                    "taxSales": 0.07,
                    "taxUse": 0.07,
                    "stateSalesTax": 0.06,
                    "stateUseTax": 0.06,
                    "citySalesTax": 0,
                    "cityUseTax": 0,
                    "countySalesTax": 0.01,
                    "countyUseTax": 0.01,
                    "districtSalesTax": 0,
                    "districtUseTax": 0,
                    "originDestination": "D",
                }
            ],
        }

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return real_response_json

        with patch("requests.get", return_value=FakeResponse()) as mock_get:
            result = service.get_rate({"zip": "33101"})

        self.assertEqual(mock_get.call_args.kwargs["params"]["postalcode"], "33101")
        self.assertNotIn("zip", mock_get.call_args.kwargs["params"])
        self.assertAlmostEqual(result["total_rate"], 0.07, places=4)
        self.assertAlmostEqual(result["state_rate"], 0.06, places=4)
        self.assertAlmostEqual(result["county_rate"], 0.01, places=4)
        self.assertAlmostEqual(result["city_rate"], 0.0, places=4)
