# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import ProviderError
from odoo.addons.l10n_us_sales_tax_engine.tests.common import UsTaxBaseTest

from ..services.provider_taxjar import ProviderTaxJar


class TestTaxjarProvider(UsTaxBaseTest):
    def _provider(self):
        return (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "taxjar")], limit=1)
        )

    def test_taxjar_registers_via_extension_point(self):
        prov = self._provider()
        self.assertTrue(prov, "taxjar provider record should ship from this module")
        self.assertIn("taxjar", prov._provider_service_classes())
        self.assertIs(prov._get_provider_service(), ProviderTaxJar)

    def test_taxjar_uses_lowercase_name_keys(self):
        svc = ProviderTaxJar(self._provider())
        normalized = {
            "state_rate": 0.0,
            "county_rate": 0.01,
            "city_rate": 0.005,
            "district_rate": 0.0,
        }
        raw = {"county": "Erie", "city": "Buffalo"}
        result = svc._named_jurisdictions("NY", normalized, raw)
        by_level = {j["level"]: j["label"] for j in result}
        self.assertEqual(by_level["county"], "Erie")
        self.assertEqual(by_level["city"], "Buffalo")


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} Server Error")


class TestTaxjarHttp(UsTaxBaseTest):
    """HTTP-level coverage: what is sent, how the payload is parsed, and how
    transport failures surface. Mirrors the ziptax/api_ninjas test pattern."""

    RATE = {
        "rate": {
            "zip": "77001",
            "state": "TX",
            "state_rate": "0.0625",
            "county": "HARRIS",
            "county_rate": "0.005",
            "city": "HOUSTON",
            "city_rate": "0.01",
            "combined_rate": "0.0825",
        }
    }

    def _svc(self, sandbox=False):
        prov = (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "taxjar")], limit=1)
        )
        prov.sandbox_mode = sandbox
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.taxjar_token", "TEST-TOKEN"
        )
        return ProviderTaxJar(prov)

    def test_get_rate_sends_bearer_and_zip_path(self):
        svc = self._svc()
        with patch(
            "odoo.addons.l10n_us_sales_tax_provider_taxjar.services."
            "provider_taxjar.requests.get",
            return_value=_FakeResponse(self.RATE),
        ) as mocked:
            result = svc.get_rate({"zip": "77001", "state": "TX", "city": "Houston"})
        url = mocked.call_args[0][0]
        kwargs = mocked.call_args[1]
        self.assertTrue(url.endswith("/rates/77001"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer TEST-TOKEN")
        self.assertEqual(kwargs["params"]["state"], "TX")
        self.assertAlmostEqual(result["total_rate"], 0.0825, places=6)

    def test_sandbox_mode_switches_base_url(self):
        svc = self._svc(sandbox=True)
        with patch(
            "odoo.addons.l10n_us_sales_tax_provider_taxjar.services."
            "provider_taxjar.requests.get",
            return_value=_FakeResponse(self.RATE),
        ) as mocked:
            svc.get_rate({"zip": "77001", "state": "TX"})
        self.assertIn("api.sandbox.taxjar.com", mocked.call_args[0][0])

    def test_district_rate_derived_and_clamped(self):
        svc = self._svc()
        result = svc.normalize_response(self.RATE["rate"])
        # combined 8.25 - 6.25 - 0.5 - 1.0 = 0.5% district
        self.assertAlmostEqual(result["district_rate"], 0.005, places=6)
        # components exceeding the combined rate must clamp to 0, not go negative
        low = dict(self.RATE["rate"], combined_rate="0.06")
        self.assertEqual(svc.normalize_response(low)["district_rate"], 0.0)

    def test_timeout_and_http_error_become_provider_errors(self):
        import requests

        svc = self._svc()
        for effect in (
            {"side_effect": requests.Timeout("boom")},
            {"return_value": _FakeResponse({}, status_code=500)},
        ):
            with (
                patch(
                    "odoo.addons.l10n_us_sales_tax_provider_taxjar.services."
                    "provider_taxjar.requests.get",
                    **effect,
                ),
                self.assertRaises(ProviderError),
            ):
                svc.get_rate({"zip": "77001", "state": "TX"})

    def test_non_json_body_is_a_provider_error(self):
        # A gateway error page is not JSON; it must fall through the provider
        # chain as a ProviderError, never escape as a raw ValueError.
        svc = self._svc()
        with (
            patch(
                "odoo.addons.l10n_us_sales_tax_provider_taxjar.services."
                "provider_taxjar.requests.get",
                return_value=_FakeResponse(ValueError("not JSON")),
            ),
            self.assertRaises(ProviderError),
        ):
            svc.get_rate({"zip": "77001", "state": "TX"})

    def test_call_counter_incremented(self):
        svc = self._svc()
        before = svc.record.calls_this_month
        with patch(
            "odoo.addons.l10n_us_sales_tax_provider_taxjar.services."
            "provider_taxjar.requests.get",
            return_value=_FakeResponse(self.RATE),
        ):
            svc.get_rate({"zip": "77001", "state": "TX"})
        self.assertEqual(svc.record.calls_this_month, before + 1)
