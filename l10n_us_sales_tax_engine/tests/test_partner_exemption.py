# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests.common import mute_logger

from .common import UsTaxBaseTest

_LOGGER = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"


class TestPartnerExemption(UsTaxBaseTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Exempt partner in FL (has nexus)
        cls.partner_exempt = cls.env["res.partner"].create(
            {
                "name": "Exempt Customer FL",
                "zip": "33101",
                "city": "Miami",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
                "us_tax_exempt": True,
                "us_tax_exemption_code": "RESALE",
                "us_tax_exemption_number": "FL-RESALE-99999",
            }
        )

        # Invoice partner in NY (no nexus) — used for the address-toggle test
        cls.partner_ny = cls.env["res.partner"].create(
            {
                "name": "Invoice Customer NY",
                "zip": "10001",
                "city": "New York",
                "state_id": cls.ny.id,
                "country_id": cls.us.id,
            }
        )

    def _make_order(self, partner, shipping_partner=None):
        vals = {
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
        if shipping_partner:
            vals["partner_shipping_id"] = shipping_partner.id
        return self.env["sale.order"].create(vals)

    def test_exempt_partner_short_circuits_engine(self):
        """Exempt partner returns exempt_partner before any provider call."""
        order = self._make_order(self.partner_exempt)
        result = self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        self.assertEqual(result["source"], "exempt_partner")
        self.assertEqual(result["tax_amount"], 0.0)

    def test_non_exempt_partner_in_fl_calculates_tax(self):
        """Non-exempt partner in a nexus state proceeds to normal calculation."""
        result = self.env["us.tax.engine.service"].calculate_for_sale_order(
            self.sale_order_fl
        )
        # Engine is in hybrid mode with local DB data — should return local rate
        self.assertIn(result["source"], ("local", "cache", "api"))
        self.assertGreater(result["tax_amount"], 0.0)

    @mute_logger(_LOGGER)
    def test_shipping_address_toggle_uses_invoice_address(self):
        """When us_tax_based_on_shipping=False, invoice address (NY) is used."""
        # Order: FL exempt partner as customer, but billing address in NY (no nexus).
        # Shipping defaults to FL partner.  With toggle OFF → engine uses NY → no nexus.
        order = self._make_order(self.partner_fl, shipping_partner=self.partner_fl)
        # Override invoice address to NY
        order.partner_invoice_id = self.partner_ny.id
        order.us_tax_based_on_shipping = False
        result = self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        self.assertEqual(result["source"], "exempt_nexus")

    def test_shipping_address_toggle_default_uses_shipping(self):
        """Default (us_tax_based_on_shipping=True) still uses shipping address (FL)."""
        order = self._make_order(self.partner_fl, shipping_partner=self.partner_fl)
        order.partner_invoice_id = self.partner_ny.id
        # us_tax_based_on_shipping defaults to True
        result = self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        # FL has nexus → should calculate tax (not exempt_nexus)
        self.assertNotEqual(result["source"], "exempt_nexus")

    def test_exempt_partner_audit_log_created(self):
        """An audit log entry with source=exempt_partner must be written."""
        order = self._make_order(self.partner_exempt)
        before = self.env["us.tax.calculation.log"].search_count(
            [("source", "=", "exempt_partner")]
        )
        self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        after = self.env["us.tax.calculation.log"].search_count(
            [("source", "=", "exempt_partner")]
        )
        self.assertEqual(after, before + 1)

    def test_exempt_partner_on_invoice(self):
        """Exempt partner also short-circuits on invoice calculation."""
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_exempt.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        result = self.env["us.tax.engine.service"].calculate_for_invoice(move)
        self.assertEqual(result["source"], "exempt_partner")
        self.assertEqual(result["tax_amount"], 0.0)
        # Verify 0 % exempt tax was applied to invoice lines
        exempt_taxes = move.invoice_line_ids.tax_ids.filtered(
            lambda t: "Exempt" in t.name
        )
        self.assertTrue(exempt_taxes)

    @mute_logger(_LOGGER)
    def test_exempt_partner_apply_error_logged_not_raised(self):
        """apply_fn failure during exempt_partner is logged but not re-raised."""

        def _bad_apply(result):
            raise RuntimeError("apply failed intentionally")

        result = self.env["us.tax.engine.service"]._process(
            "sale.order",
            0,
            {"zip": "33101", "state": "FL", "country_code": "US"},
            [],
            None,
            self.env.company.id,
            self.env.company.currency_id.id,
            apply_fn=_bad_apply,
            partner=self.partner_exempt,
        )
        self.assertEqual(result["source"], "exempt_partner")

    def test_resolve_invoice_address_fallback_to_partner_id(self):
        """resolve_invoice_address falls back to partner_id when no invoice partner."""
        from ..services.address_resolver import resolve_invoice_address

        class _FakeRecord:
            partner_id = self.partner_fl

        addr = resolve_invoice_address(_FakeRecord())
        self.assertEqual(addr["zip"], "33101")
        self.assertEqual(addr["state"], "FL")
        self.assertEqual(addr["partner_id"], self.partner_fl.id)
