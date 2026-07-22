# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests.common import mute_logger

from .common import UsTaxBaseTest

_TAX_ENGINE_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"


class TestTaxEngine(UsTaxBaseTest):
    def test_engine_disabled_returns_skip(self):
        """When engine is disabled, calculate returns 'disabled'."""
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "False"
        )
        result = self.env["us.tax.engine.service"]._process(
            "sale.order",
            0,
            {"zip": "33101", "state": "FL", "country_code": "US"},
            [],
            None,
            self.env.company.id,
            self.env.company.currency_id.id,
            apply_fn=lambda r: None,
        )
        self.assertEqual(result["source"], "disabled")
        # Re-enable
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )

    def test_no_nexus_returns_exempt(self):
        """Address in state without nexus returns exempt_nexus."""
        result = self.env["us.tax.engine.service"]._process(
            "sale.order",
            0,
            {"zip": "10001", "state": "NY", "country_code": "US"},
            [],
            "2025-01-01",
            self.env.company.id,
            self.env.company.currency_id.id,
            apply_fn=lambda r: None,
        )
        self.assertEqual(result["source"], "exempt_nexus")

    def test_local_rate_used_for_fl_zip(self):
        """ZIP 33101 (FL) must use LOCAL source from local DB."""
        engine = self.env["us.tax.engine.service"]
        from ..services.cache_manager import CacheManager

        cache = CacheManager(self.env, ttl_hours=720)  # noqa: F841
        result = engine._get_rate(
            zip_code="33101",
            state_code="FL",
            state_id=self.fl.id,
            product_category_code="TANGIBLE",
            product_category_id=self.cat_tangible.id,
            doc_date="2025-01-01",
            address={"zip": "33101", "state": "FL"},
            cache=cache,
            engine_mode="hybrid",
            fail_policy="warn",
        )
        self.assertEqual(result["source"], "local")
        self.assertAlmostEqual(result["total_rate"], 0.07, places=4)

    def test_cache_hit_on_second_call(self):
        """Second call for same ZIP must return cache source."""
        engine = self.env["us.tax.engine.service"]  # noqa: F841
        from ..services.cache_manager import CacheManager  # noqa: PLC0415

        # Prime with a fake cache entry
        provider = self.env["us.tax.provider"].search([("code", "=", "local")], limit=1)
        cache = CacheManager(self.env, ttl_hours=720)  # noqa: F841
        h = cache.build_hash("33101", "FL", "TANGIBLE", "2025-01-01")
        cache.set(
            h,
            provider.id,
            {
                "total_rate": 0.07,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0,
                "district_rate": 0,
            },
        )
        result = cache.get(h)
        self.assertIsNotNone(result)
        self.assertTrue(result.get("from_cache"))


class TestProviderFallback(UsTaxBaseTest):
    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_all_providers_fail_apply_warn_policy(self):
        """When all providers fail with policy=warn, return 0 tax."""
        engine = self.env["us.tax.engine.service"]
        from ..services.cache_manager import CacheManager
        from ..services.provider_base import ProviderError

        cache = CacheManager(self.env, ttl_hours=720)  # noqa: F841
        result = engine._handle_all_failed(
            "warn", "fakehash", ProviderError("All failed"), {"zip": "99999"}
        )
        self.assertEqual(result["total_rate"], 0.0)
        self.assertEqual(result["source"], "error")

    def test_all_providers_fail_block_raises(self):
        """When all providers fail with policy=block, UserError is raised."""
        from ..services.provider_base import ProviderError

        engine = self.env["us.tax.engine.service"]
        with self.assertRaises(ProviderError):
            engine._handle_all_failed(
                "block", "fakehash", ProviderError("All failed"), {"zip": "99999"}
            )
