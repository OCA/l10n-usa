# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.tests.common import mute_logger

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import ProviderError
from odoo.addons.l10n_us_sales_tax_engine.services.provider_local import ProviderLocal
from odoo.addons.l10n_us_sales_tax_engine.tests.common import UsTaxBaseTest

from ..services.provider_api_ninjas import ProviderApiNinjas


class TestProviderApiNinjas(UsTaxBaseTest):
    def _api_ninjas_provider(self):
        return (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "api_ninjas")], limit=1)
        )

    def test_api_ninjas_registered_in_provider_service_classes(self):
        """Installing this module must register "api_ninjas" without editing
        the engine — the registry must still contain the other providers."""
        provider = self._api_ninjas_provider()
        self.assertTrue(provider, "api_ninjas provider record should exist from data")
        classes = provider._provider_service_classes()
        self.assertTrue({"local", "api_ninjas"} <= set(classes))
        self.assertIs(classes["api_ninjas"], ProviderApiNinjas)
        self.assertIs(provider._get_provider_service(), ProviderApiNinjas)

    @mute_logger("odoo.addons.l10n_us_sales_tax_engine.services.tax_engine")
    def test_local_to_api_ninjas_fallback(self):
        """If the local provider fails, the engine must fall back to API
        Ninjas when it is active with a lower priority than local."""
        api_ninjas = self._api_ninjas_provider()
        api_ninjas.write({"active": True, "priority": 5})

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
            patch.object(ProviderApiNinjas, "get_rate", return_value=fake_rate),
        ):
            result = engine.calculate_for_sale_order(self.sale_order_fl)

        self.assertEqual(result["source"], "api")
        rate_detail = result["lines"][0]["rate_detail"]
        self.assertEqual(rate_detail["provider_id"], api_ninjas.id)
        self.assertAlmostEqual(rate_detail["total_rate"], 0.06, places=4)

    def test_get_rate_parses_real_response_shape(self):
        """Regression guard: api-ninjas.com's salestax endpoint returns a
        JSON list (not a dict), and free-tier accounts get the literal
        string "This field is for premium subscribers only" instead of a
        number for county/city/special/total_rate — confirmed live against
        a real California ZIP during manual QA (state_rate only, county/city
        locked). normalize_response() must fall back to summing the
        available numeric components when total_rate isn't a number."""
        api_ninjas = self._api_ninjas_provider()
        api_ninjas.write({"active": True})
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.api_ninjas_key", "fake-test-key"
        )
        service = api_ninjas._get_provider_service()(api_ninjas)

        premium_locked = "This field is for premium subscribers only"
        real_response_json = [
            {
                "state": "California",
                "state_rate": "0.06",
                "county_rate": premium_locked,
                "city_rate": premium_locked,
                "special_rate": premium_locked,
                "total_rate": premium_locked,
                "zip_code": "94103",
            }
        ]

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return real_response_json

        with patch("requests.get", return_value=FakeResponse()) as mock_get:
            result = service.get_rate({"zip": "94103"})

        self.assertEqual(mock_get.call_args.kwargs["params"]["zip_code"], "94103")
        self.assertAlmostEqual(result["state_rate"], 0.06, places=4)
        self.assertAlmostEqual(result["county_rate"], 0.0, places=4)
        self.assertAlmostEqual(result["city_rate"], 0.0, places=4)
        self.assertAlmostEqual(result["district_rate"], 0.0, places=4)
        self.assertAlmostEqual(result["total_rate"], 0.06, places=4)
