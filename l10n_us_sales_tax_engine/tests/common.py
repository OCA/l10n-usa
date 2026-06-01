# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests.common import TransactionCase


class UsTaxBaseTest(TransactionCase):
    """Base test class with shared fixtures for US Tax Engine tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Enable engine
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_mode", "hybrid"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.fail_policy", "warn"
        )

        # US country + FL state
        cls.us = cls.env.ref("base.us")
        cls.fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.ny = cls.env["res.country.state"].search(
            [("code", "=", "NY"), ("country_id", "=", cls.us.id)], limit=1
        )

        # Product categories
        cls.cat_tangible = cls.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )
        cls.cat_exempt = cls.env["us.tax.product.category"].search(
            [("code", "=", "EXEMPT")], limit=1
        )

        # Test jurisdiction (Miami-Dade, FL)
        cls.jur_miami = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Miami-Dade",
                "type": "county",
                "state_id": cls.fl.id,
                "county": "MIAMI-DADE",
            }
        )

        # Generic rate (no category) — used by lookups without a category
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_miami.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.00,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        # Category-specific rate — used by TANGIBLE lookups
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_miami.id,
                "product_tax_category_id": cls.cat_tangible.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.00,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )

        # Test ZIP mapping
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33101",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jur_miami.id,
                "county": "MIAMI-DADE",
                "confidence": 1.0,
                "source": "test",
            }
        )

        # Nexus
        cls.env["us.tax.nexus"].create(
            {
                "company_id": cls.env.company.id,
                "state_id": cls.fl.id,
                "active": True,
                "start_date": "2020-01-01",
            }
        )

        # Test partner (FL)
        cls.partner_fl = cls.env["res.partner"].create(
            {
                "name": "Test Customer FL",
                "zip": "33101",
                "city": "Miami",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )

        # Test product
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Tile",
                "type": "consu",
                "list_price": 100.0,
                "us_tax_category_id": cls.cat_tangible.id,
            }
        )

        # Sale order fixture (FL)
        cls.sale_order_fl = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner_fl.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        cls.state_fl = cls.fl


class UsTaxTestCommon(UsTaxBaseTest):
    """Alias used by test_provider_fallback — same fixtures as UsTaxBaseTest."""
