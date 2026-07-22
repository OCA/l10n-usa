# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestSaleOrderTax(UsTaxBaseTest):
    def test_calculate_tax_action(self):
        """manual 'Calculate US Tax' button on SO must not raise errors."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_fl.id,
                "partner_shipping_id": self.partner_fl.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        # Should not raise
        try:
            order.action_calculate_us_tax()
        except Exception as exc:
            self.fail(f"action_calculate_us_tax raised unexpectedly: {exc}")

    def test_non_us_partner_skips_tax(self):
        """Non-US partner should be skipped by engine."""
        fr = self.env.ref("base.fr")
        partner_fr = self.env["res.partner"].create(
            {
                "name": "Test FR Partner",
                "country_id": fr.id,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner_fr.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 50.0,
                        },
                    )
                ],
            }
        )
        engine = self.env["us.tax.engine.service"]
        result = engine.calculate_for_sale_order(order)
        self.assertIn(
            result.get("source", ""), ["skip_non_us", "skip_no_address", "disabled"]
        )

    def test_calculate_tax_action_as_user_without_tax_groups(self):
        """A regular salesperson with none of the us_tax_user/manager/
        technical groups must still get tax calculated on their own order —
        those groups gate manual access to the configuration screens, not
        the engine's own background calculation."""
        salesperson = self.env["res.users"].create(
            {
                "name": "Plain Salesperson",
                "login": "plain_salesperson_test",
                "groups_id": [
                    (6, 0, [self.env.ref("sales_team.group_sale_salesman").id])
                ],
            }
        )
        self.assertFalse(
            salesperson.groups_id.filtered(
                lambda g: g.category_id
                == self.env.ref("l10n_us_sales_tax_engine.module_category_us_sales_tax")
            ),
            "test setup invariant — salesperson must hold no us_tax_* group",
        )
        order = (
            self.env["sale.order"]
            .with_user(salesperson)
            .create(
                {
                    "partner_id": self.partner_fl.id,
                    "partner_shipping_id": self.partner_fl.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1,
                                "price_unit": 100.0,
                            },
                        )
                    ],
                }
            )
        )
        order.with_user(salesperson).action_calculate_us_tax()
        self.assertTrue(
            order.order_line.tax_id, "tax must be applied despite no groups"
        )

    def test_exempt_rule_gets_explicit_zero_tax(self):
        """An EXEMPT-category product must get an explicit 0% tax line, not
        an empty tax_id — distinguishes "evaluated and exempt" from "tax
        was never calculated" on the document/report."""
        exempt_product = self.env["product.product"].create(
            {
                "name": "Exempt Test Product",
                "type": "consu",
                "list_price": 50.0,
                "us_tax_category_id": self.cat_exempt.id,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_fl.id,
                "partner_shipping_id": self.partner_fl.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": exempt_product.id,
                            "product_uom_qty": 1,
                            "price_unit": 50.0,
                        },
                    )
                ],
            }
        )
        order.action_calculate_us_tax()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax - Exempt (0%)")
        self.assertEqual(order.amount_tax, 0.0)

    def test_no_nexus_gets_explicit_exempt_tax(self):
        """An order in a state without nexus must get the explicit exempt
        tax applied too — not just an empty result dict. Also a regression
        guard: _process() must call apply_fn for the no-nexus path (it used
        to return before ever applying anything to the order)."""
        partner_ny = self.env["res.partner"].create(
            {
                "name": "Test Customer NY",
                "zip": "10001",
                "city": "New York",
                "state_id": self.ny.id,
                "country_id": self.us.id,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner_ny.id,
                "partner_shipping_id": partner_ny.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        order.action_calculate_us_tax()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax - Exempt (0%)")
        self.assertEqual(order.amount_tax, 0.0)

    def test_real_zero_rate_state_gets_explicit_zero_percent_tax(self):
        """A state with a real (non-exempt) 0% combined rate must get its
        own "US Sales Tax {state} 0%" tax — distinct from the shared
        exempt tax, since this is a real rate, not a category/nexus
        exemption."""
        self.env["us.tax.nexus"].create(
            {
                "company_id": self.env.company.id,
                "state_id": self.ny.id,
                "active": True,
                "start_date": "2020-01-01",
            }
        )
        jur_ny = self.env["us.tax.jurisdiction"].create(
            {
                "name": "New York City",
                "type": "city",
                "state_id": self.ny.id,
                "city": "NEW YORK",
            }
        )
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jur_ny.id,
                "state_rate": 0.0,
                "county_rate": 0.0,
                "city_rate": 0.0,
                "district_rate": 0.0,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        self.env["us.tax.zip.mapping"].create(
            {
                "zip": "10001",
                "state_id": self.ny.id,
                "jurisdiction_id": jur_ny.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        partner_ny = self.env["res.partner"].create(
            {
                "name": "Test Customer NY Zero Rate",
                "zip": "10001",
                "city": "New York",
                "state_id": self.ny.id,
                "country_id": self.us.id,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner_ny.id,
                "partner_shipping_id": partner_ny.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        order.action_calculate_us_tax()
        self.assertEqual(order.order_line.tax_id.name, "US Sales Tax NY 0%")
        self.assertEqual(order.amount_tax, 0.0)
