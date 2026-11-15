# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .common import UsTaxBaseTest


class TestJurisdictionBooking(UsTaxBaseTest):
    """Booking composition: the per-jurisdiction breakdown must survive into
    the applied account.tax records — distinct children per level, groups
    keyed by composition (never by state + total alone)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Alpha: city-type jurisdiction where county and city share the SAME
        # rate (1% each) — the collapse trap.
        cls.jur_alpha = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Alphaville",
                "type": "city",
                "state_id": cls.fl.id,
                "county": "ALPHA",
                "city": "ALPHAVILLE",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_alpha.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.01,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33201",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jur_alpha.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        # Beta: same 8% combined total as Alpha, but split differently
        # (6 + 2 city, no county) — the same-total/different-composition trap.
        cls.jur_beta = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Betaville",
                "type": "city",
                "state_id": cls.fl.id,
                "county": "BETA",
                "city": "BETAVILLE",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_beta.id,
                "state_rate": 0.06,
                "county_rate": 0.00,
                "city_rate": 0.02,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33301",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jur_beta.id,
                "confidence": 1.0,
                "source": "test",
            }
        )

    def _order_for_zip(self, zip_code):
        partner = self.env["res.partner"].create(
            {
                "name": f"Customer {zip_code}",
                "zip": zip_code,
                "state_id": self.fl.id,
                "country_id": self.us.id,
            }
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )

    def test_equal_rate_levels_book_distinct_taxes(self):
        """County 1% + city 1% must produce two distinct child taxes — equal
        rates on different levels must never collapse into one record."""
        order = self._order_for_zip("33201")
        self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        tax = order.order_line.tax_id
        self.assertEqual(tax.amount_type, "group")
        children = tax.children_tax_ids
        self.assertEqual(len(children), 3, "state + county + city children")
        self.assertEqual(
            sorted(children.mapped("amount")), [1.0, 1.0, 6.0], "no collapsed child"
        )
        self.assertEqual(
            len(set(children.mapped("name"))), 3, "child names must be distinct"
        )
        self.assertEqual(
            sorted(children.mapped("us_tax_level")), ["city", "county", "state"]
        )
        city_child = children.filtered(lambda t: t.us_tax_level == "city")
        self.assertEqual(
            city_child.us_tax_jurisdiction_id,
            self.jur_alpha,
            "only the level matching the resolved record's type is tagged",
        )
        other = children - city_child
        self.assertFalse(
            other.us_tax_jurisdiction_id,
            "state/county lines of a city-type record book level-only",
        )

    def test_same_total_different_composition_groups_stay_distinct(self):
        """Two destinations sharing a combined total must keep separate group
        taxes; recalculating one must not rewrite the other's children."""
        order_a = self._order_for_zip("33201")
        order_b = self._order_for_zip("33301")
        engine = self.env["us.tax.engine.service"]
        engine.calculate_for_sale_order(order_a)
        tax_a = order_a.order_line.tax_id
        children_a = tax_a.children_tax_ids
        engine.calculate_for_sale_order(order_b)
        tax_b = order_b.order_line.tax_id
        self.assertNotEqual(tax_a, tax_b, "same total, different composition")
        self.assertEqual(sorted(tax_b.children_tax_ids.mapped("amount")), [2.0, 6.0])
        self.assertEqual(
            tax_a.children_tax_ids,
            children_a,
            "recalculating another destination must not rewrite this group",
        )
        # Recalculate A — must reuse the same group, not create a third.
        engine.calculate_for_sale_order(order_a)
        self.assertEqual(order_a.order_line.tax_id, tax_a)


@tagged("post_install", "-at_install")
class TestJurisdictionBookingGL(AccountTestInvoicingCommon):
    """End to end: posted invoice books one move line per jurisdiction level
    on the US tax payable account."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_mode", "hybrid"
        )
        cls.us = cls.env.ref("base.us")
        cls.fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", cls.us.id)], limit=1
        )
        jurisdiction = (
            cls.env["us.tax.jurisdiction"]
            .sudo()
            .create(
                {
                    "name": "Miami-Dade GL",
                    "type": "county",
                    "state_id": cls.fl.id,
                    "county": "MIAMI-DADE",
                }
            )
        )
        cls.env["us.tax.rate"].sudo().create(
            {
                "jurisdiction_id": jurisdiction.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.00,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].sudo().create(
            {
                "zip": "33401",
                "state_id": cls.fl.id,
                "jurisdiction_id": jurisdiction.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        cls.env["us.tax.nexus"].sudo().create(
            {
                "company_id": cls.env.company.id,
                "state_id": cls.fl.id,
                "active": True,
                "start_date": "2020-01-01",
            }
        )
        cls.partner_fl = cls.env["res.partner"].create(
            {
                "name": "GL Customer",
                "zip": "33401",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )
        cat_tangible = (
            cls.env["us.tax.product.category"]
            .sudo()
            .search([("code", "=", "TANGIBLE")], limit=1)
        )
        cls.product_gl = cls.env["product.product"].create(
            {
                "name": "GL Widget",
                "type": "consu",
                "list_price": 100.0,
                "us_tax_category_id": cat_tangible.id,
            }
        )

    def test_posted_invoice_books_per_jurisdiction_move_lines(self):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_fl,
            invoice_date="2024-06-01",
            products=self.product_gl,
        )
        self.env["us.tax.engine.service"].calculate_for_invoice(invoice)
        invoice.action_post()
        tax_lines = invoice.line_ids.filtered("tax_line_id")
        self.assertEqual(
            len(tax_lines), 2, "one move line per jurisdiction level (state, county)"
        )
        self.assertEqual(
            sorted(tax_lines.mapped("tax_line_id.us_tax_level")),
            ["county", "state"],
        )
        payable = invoice.company_id.get_us_tax_payable_account()
        for line in tax_lines:
            self.assertEqual(
                line.account_id,
                payable,
                "collected tax must book to the US tax payable account",
            )
        self.assertAlmostEqual(sum(tax_lines.mapped("credit")), 7.0, places=2)

    def test_reuses_the_chart_tax_account_instead_of_creating_one(self):
        """Charts already ship a sales-tax account; don't split the balance.

        Creating a second liability alongside the chart's own account would
        scatter the sales-tax balance over two accounts and leave the tax
        report reconciling against the wrong one.
        """
        company = self.env.company
        chart_account = company._us_tax_account_from_chart()
        self.assertTrue(
            chart_account,
            "fixture chart has no sale tax to inherit an account from",
        )
        company.us_tax_payable_account_id = False

        resolved = company.get_us_tax_payable_account()
        self.assertEqual(
            resolved,
            chart_account,
            "engine invented an account instead of reusing the chart's",
        )
        # And it is written back, so the choice is visible in Settings.
        self.assertEqual(company.us_tax_payable_account_id, chart_account)

    def test_explicit_configuration_wins_over_the_chart(self):
        company = self.env.company
        chosen = self.env["account.account"].create(
            {
                "name": "Custom Sales Tax Payable",
                "code": "251900",
                "account_type": "liability_current",
                "company_ids": [(4, company.id)],
            }
        )
        company.us_tax_payable_account_id = chosen
        self.assertEqual(company.get_us_tax_payable_account(), chosen)

    def test_tax_group_is_configured_for_the_tax_closing_entry(self):
        """Odoo reports a group with no payable/receivable account as broken."""
        company = self.env.company
        group = self.env["us.tax.engine.service"]._get_us_tax_group(company)
        self.assertTrue(
            group.tax_payable_account_id,
            "US Sales Tax group has no payable account; tax closing cannot run",
        )
        self.assertTrue(group.tax_receivable_account_id)
        self.assertFalse(
            self.env["account.tax.group"]._check_misconfigured_tax_groups(
                company, company.account_fiscal_country_id or self.us
            ),
            "Odoo still reports the tax groups as misconfigured",
        )
