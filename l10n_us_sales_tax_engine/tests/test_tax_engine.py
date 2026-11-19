# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.fields import Command
from odoo.tests import new_test_user
from odoo.tests.common import mute_logger

from ..services.provider_base import ProviderError
from ..services.provider_local import ProviderLocal
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


class TestTaxEngineApply(UsTaxBaseTest):
    """How the engine writes its result on the document lines."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesman = new_test_user(
            cls.env,
            login="us_tax_apply_salesman",
            groups="sales_team.group_sale_salesman",
        )
        cls.invoicer = new_test_user(
            cls.env,
            login="us_tax_apply_invoicer",
            groups="account.group_account_invoice",
        )
        cls.partner_fr = cls.env["res.partner"].create(
            {"name": "Test Customer FR", "country_id": cls.env.ref("base.fr").id}
        )

    def _create_fee_tax(self):
        return self.env["account.tax"].create(
            {
                "name": "Recycling Fee 1%",
                "type_tax_use": "sale",
                "amount_type": "percent",
                "amount": 1.0,
            }
        )

    def _last_log(self, document):
        return (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search(
                [("res_model", "=", document._name), ("res_id", "=", document.id)],
                order="id desc",
                limit=1,
            )
        )

    def _fail_state_tax_from_call(self, nth):
        """Make _get_or_create_state_tax raise from its nth call on."""
        service = type(self.env["us.tax.engine.service"])
        original = service._get_or_create_state_tax
        calls = []

        def failing(service_self, state_code, company, rate_pct=0.0):
            calls.append(state_code)
            if len(calls) >= nth:
                raise ValueError("apply failure under test")
            return original(service_self, state_code, company, rate_pct)

        return patch.object(service, "_get_or_create_state_tax", failing)

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_failed_apply_keeps_the_previous_taxes(self):
        order = self._create_fl_order(self._priced_line_vals())
        taxes_before = [line.tax_id for line in order.order_line]
        with self._fail_state_tax_from_call(2):
            order.action_calculate_us_tax()
        self.assertEqual([line.tax_id for line in order.order_line], taxes_before)
        self.assertEqual(self._last_log(order).status, "error")

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_line_without_a_rate_makes_the_calculation_an_error(self):
        order = self._create_fl_order(self._priced_line_vals())
        second_line_fails = [{"total_rate": 0.07}, ProviderError("unavailable")]
        with patch.object(ProviderLocal, "get_rate", side_effect=second_line_fails):
            result = self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        self.assertEqual(result["source"], "error")
        self.assertEqual(self._last_log(order).status, "error")

    def test_engine_taxes_are_price_excluded(self):
        """Reused taxes: one without override, one set to tax_included."""
        company = self.env["res.company"].create(
            {
                "name": "US Tax Included Co",
                "country_id": self.us.id,
                "account_price_include": "tax_included",
            }
        )
        engine = self.env["us.tax.engine.service"].with_company(company)
        tax_vals = {
            "type_tax_use": "sale",
            "amount_type": "percent",
            "company_id": company.id,
            "tax_group_id": engine._get_us_tax_group(company).id,
        }
        reused = self.env["account.tax"].create(
            [
                dict(tax_vals, name="US Sales Tax FL 8.25%", amount=8.25),
                dict(
                    tax_vals,
                    name="US Sales Tax - Exempt (0%)",
                    amount=0.0,
                    price_include_override="tax_included",
                ),
            ]
        )
        taxes = (
            engine._get_or_create_state_tax("FL", company, 0.0825)
            | engine._get_or_create_exempt_tax(company)
            | engine._get_or_create_state_tax("FL", company, 0.06)
        )
        self.assertEqual(len(taxes), 3)
        self.assertLessEqual(reused, taxes)
        for tax in taxes:
            self.assertEqual(tax.price_include_override, "tax_excluded")
            self.assertFalse(tax.price_include, tax.name)

    def test_sections_and_notes_get_no_tax_on_order(self):
        order = self._create_fl_order(
            {"display_type": "line_section", "name": "Materials"},
            {"display_type": "line_note", "name": "Delivered loose"},
        )
        order.action_calculate_us_tax()
        self.assertFalse(order.order_line.filtered("display_type").tax_id)
        self.assertTrue(self._us_taxes(order._get_priced_lines().tax_id))

    def test_sections_and_notes_get_no_tax_on_invoice(self):
        move = self._create_fl_invoice(
            {"display_type": "line_section", "name": "Materials"},
            {"display_type": "line_note", "name": "Delivered loose"},
        )
        move.action_calculate_us_tax()
        lines = move.invoice_line_ids
        sections = lines.filtered(
            lambda line: line.display_type in ("line_section", "line_note")
        )
        self.assertEqual(len(sections), 2)
        self.assertFalse(sections.tax_ids)
        products = lines.filtered(lambda line: line.display_type == "product")
        self.assertTrue(self._us_taxes(products.tax_ids))

    def test_exempt_order_leaves_sections_untouched(self):
        self.partner_fl.us_tax_exempt = True
        order = self._create_fl_order({"display_type": "line_section", "name": "S"})
        order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "exempt_partner")
        self.assertFalse(order.order_line.filtered("display_type").tax_id)
        self.assertTrue(self._us_taxes(order._get_priced_lines().tax_id))

    def test_order_shipped_abroad_loses_only_its_us_tax(self):
        fee = self._create_fee_tax()
        order = self._create_fl_order()
        order.action_calculate_us_tax()
        line = order.order_line
        self.assertTrue(self._us_taxes(line.tax_id))
        line.tax_id = [Command.link(fee.id)]
        order.partner_shipping_id = self.env["res.partner"].create(
            {"name": "Test Customer FR", "country_id": self.env.ref("base.fr").id}
        )
        order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "skip_non_us")
        self.assertEqual(line.tax_id, fee)

    def test_invoice_skipped_as_non_us_loses_only_its_us_tax(self):
        fee = self._create_fee_tax()
        move = self._create_fl_invoice()
        move.action_calculate_us_tax()
        line = move.invoice_line_ids
        self.assertTrue(self._us_taxes(line.tax_ids))
        line.tax_ids = [Command.link(fee.id)]
        self.env["us.tax.engine.service"]._apply_to_invoice(
            move, {"source": "skip_non_us", "lines": []}
        )
        self.assertEqual(line.tax_ids, fee)

    def _log_count(self, document):
        return (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search_count(
                [("res_model", "=", document._name), ("res_id", "=", document.id)]
            )
        )

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_failed_apply_marks_the_order_source_as_error(self):
        order = self._create_fl_order(user=self.salesman)
        with self._fail_state_tax_from_call(1):
            order.with_user(self.salesman).action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "error")

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_failed_apply_marks_the_invoice_source_as_error(self):
        move = self._create_fl_invoice(user=self.invoicer)
        with self._fail_state_tax_from_call(1):
            move.with_user(self.invoicer).action_calculate_us_tax()
        self.assertEqual(move.us_tax_source, "error")

    def _apply_failure_notes(self, document):
        return document.sudo().message_ids.filtered(
            lambda message: "could not be written" in (message.body or "")
        )

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_failed_apply_on_confirm_leaves_a_note(self):
        order = self._create_fl_order(user=self.salesman)
        with self._fail_state_tax_from_call(1):
            order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertTrue(self._apply_failure_notes(order))

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_failed_apply_on_post_leaves_a_note(self):
        move = self._create_fl_invoice(user=self.invoicer)
        with self._fail_state_tax_from_call(1):
            move.with_user(self.invoicer).action_post()
        self.assertEqual(move.state, "posted")
        self.assertTrue(self._apply_failure_notes(move))

    def test_skip_that_removes_the_us_tax_leaves_a_skipped_row(self):
        order = self._create_fl_order(user=self.salesman)
        order.action_calculate_us_tax()
        rows_before = self._log_count(order)
        order.partner_shipping_id = self.partner_fr
        order.action_calculate_us_tax()
        self.assertEqual(self._log_count(order), rows_before + 1)
        row = self._last_log(order)
        self.assertEqual(row.source, "skip_non_us")
        self.assertEqual(row.status, "skipped")

    def _tax_removed_notes(self, document):
        return document.sudo().message_ids.filtered(
            lambda message: "taken off" in (message.body or "")
        )

    def test_confirm_that_takes_the_us_tax_off_leaves_a_note(self):
        order = self._create_fl_order(user=self.salesman)
        order.action_calculate_us_tax()
        order.partner_shipping_id = self.partner_fr
        order.with_user(self.salesman).action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertFalse(self._us_taxes(order.order_line.tax_id))
        self.assertTrue(self._tax_removed_notes(order))

    def test_post_that_takes_the_us_tax_off_leaves_a_note(self):
        move = self._create_fl_invoice(user=self.invoicer)
        move.action_calculate_us_tax()
        move.partner_shipping_id = self.partner_fr
        move.with_user(self.invoicer).action_post()
        self.assertEqual(move.state, "posted")
        self.assertFalse(self._us_taxes(move.invoice_line_ids.tax_ids))
        self.assertTrue(self._tax_removed_notes(move))

    def test_skip_that_changes_nothing_leaves_no_row(self):
        order = self._create_fl_order(user=self.salesman)
        order.partner_shipping_id = self.partner_fr
        order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "skip_non_us")
        self.assertEqual(self._log_count(order), 0)

    @mute_logger(_TAX_ENGINE_LOGGER)
    def test_skip_that_cannot_remove_the_us_tax_leaves_an_error_row(self):
        order = self._create_fl_order(user=self.salesman)
        order.action_calculate_us_tax()
        us_tax = self._us_taxes(order.order_line.tax_id)
        order.partner_shipping_id = self.partner_fr
        service = type(self.env["us.tax.engine.service"])
        with patch.object(
            service, "_remove_us_taxes", side_effect=ValueError("under test")
        ):
            order.action_calculate_us_tax()
        self.assertEqual(order.us_tax_source, "error")
        self.assertEqual(self._us_taxes(order.order_line.tax_id), us_tax)
        row = self._last_log(order)
        self.assertEqual(row.source, "skip_non_us")
        self.assertEqual(row.status, "error")
