# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
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
