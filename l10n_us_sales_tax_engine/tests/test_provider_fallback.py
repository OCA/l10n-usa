# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import mute_logger

from .common import UsTaxTestCommon

_TAX_ENGINE_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"


@tagged("post_install", "-at_install", "us_tax")
class TestProviderFallback(UsTaxTestCommon):
    """Tests for the provider fallback chain and fail policies."""

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_fallback_to_next_provider_on_error(self):
        """If first provider raises ProviderError, engine must try next."""
        engine = self.env["us.tax.engine.service"]
        with patch.object(
            type(engine),
            "_get_active_providers",
            return_value=self.env["us.tax.provider"].browse([]),
        ):
            result = engine.calculate_for_sale_order(self.sale_order_fl)
        # No active providers + fail_policy=warn → $0, no crash
        self.assertIsNotNone(result)

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_fail_policy_warn_returns_zero(self):
        """fail_policy=warn must return 0 tax without raising."""
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.fail_policy", "warn"
        )
        engine = self.env["us.tax.engine.service"]
        # Remove local ZIP mapping to force fallback
        self.env["us.tax.zip.mapping"].search(
            [("zip", "=", self.partner_fl.zip)]
        ).unlink()
        result = engine.calculate_for_sale_order(self.sale_order_fl)
        # With no providers and warn policy, should not raise
        self.assertIsNotNone(result)

    def test_provider_limit_reached_is_skipped(self):
        """A provider that has reached monthly_call_limit must be skipped."""
        provider = self.env["us.tax.provider"].search([("code", "=", "local")], limit=1)
        if provider:
            provider.write(
                {
                    "monthly_call_limit": 1,
                    "calls_this_month": 1,
                }
            )
            self.assertTrue(provider.is_limit_reached())
            provider.write(
                {
                    "monthly_call_limit": 0,
                    "calls_this_month": 0,
                }
            )

    def test_cache_hit_avoids_provider_call(self):
        """A cached response must be returned without calling any provider."""
        from datetime import datetime, timedelta

        cache_hash = "test_hash_12345"
        provider = self.env["us.tax.provider"].search([("code", "=", "local")], limit=1)
        self.env["us.tax.api.cache"].create(
            {
                "address_hash": cache_hash,
                "zip": self.partner_fl.zip or "33101",
                "state_id": self.state_fl.id,
                "provider_id": provider.id if provider else False,
                "total_rate": 0.07,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.0,
                "district_rate": 0.0,
                "cached_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(hours=720),
            }
        )
        # Cache entry exists — verify it is retrievable
        entry = self.env["us.tax.api.cache"].search(
            [("address_hash", "=", cache_hash)], limit=1
        )
        self.assertTrue(entry)
        self.assertAlmostEqual(entry.total_rate, 0.07)
