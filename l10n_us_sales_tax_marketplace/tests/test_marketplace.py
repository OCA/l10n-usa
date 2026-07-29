# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarketplace(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_tax.engine_active", "True")
        ICP.set_param("l10n_us_tax.fail_policy", "warn")
        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.amazon = cls.env.ref("l10n_us_sales_tax_marketplace.marketplace_amazon")
        # Nexus in WY — proves marketplace overrides nexus (we still don't collect).
        cls.env["us.tax.nexus"].create(
            {"company_id": cls.company.id, "state_id": cls.wy.id, "active": True}
        )
        # WY rate data so a *non*-marketplace sale rates cleanly (otherwise the
        # provider legitimately fails for an unmapped ZIP and warns, which the
        # OCA checklog gate would flag).
        cat_tangible = cls.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )
        cls.product_a.us_tax_category_id = cat_tangible
        jurisdiction = cls.env["us.tax.jurisdiction"].create(
            {"name": "Laramie", "type": "county", "state_id": cls.wy.id}
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jurisdiction.id,
                "product_tax_category_id": cat_tangible.id,
                "state_rate": 0.04,
                "county_rate": 0.02,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "82001",
                "state_id": cls.wy.id,
                "jurisdiction_id": jurisdiction.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "MP Buyer",
                "state_id": cls.wy.id,
                "zip": "82001",
                "country_id": cls.us.id,
            }
        )

    def _invoice(self, marketplace=None, price=100.0):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": "2025-01-15",
                "company_id": self.company.id,
                "us_tax_marketplace_id": marketplace.id if marketplace else False,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "price_unit": price,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        move.action_post()
        return move

    def test_hook_returns_marketplace_code(self):
        move = self._invoice(marketplace=self.amazon)
        code = self.env["us.tax.engine.service"]._get_marketplace_collection(
            "account.move", move.id
        )
        self.assertEqual(code, "amazon")

    def test_marketplace_invoice_collects_no_tax(self):
        move = self._invoice(marketplace=self.amazon)
        self.assertFalse(move.line_ids.filtered("tax_line_id"))
        log = self.env["us.tax.calculation.log"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", move.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.source, "marketplace")

    def test_return_captures_marketplace_sales(self):
        self._invoice(marketplace=self.amazon, price=250.0)
        tax_return = self.env["us.tax.return"].create(
            {
                "company_id": self.company.id,
                "state_id": self.wy.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
            }
        )
        tax_return.action_generate()
        self.assertAlmostEqual(tax_return.marketplace_sales, 250.0, places=2)

    def test_non_marketplace_invoice_not_flagged_as_collected(self):
        """A plain invoice is calculated normally — not short-circuited as
        marketplace — so marketplace handling stays strictly opt-in."""
        move = self._invoice(marketplace=None)
        log = self.env["us.tax.calculation.log"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", move.id)],
            order="id desc",
            limit=1,
        )
        self.assertNotEqual(log.source, "marketplace")

    def test_marketplace_flag_propagates_so_to_invoice(self):
        """Confirming a marketplace order and invoicing it carries the
        facilitator onto the invoice, so the invoice isn't taxed at posting."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "us_tax_marketplace_id": self.amazon.id,
                "order_line": [
                    (0, 0, {"product_id": self.product_a.id, "product_uom_qty": 1.0})
                ],
            }
        )
        order.action_confirm()
        invoice = order._create_invoices()
        self.assertEqual(invoice.us_tax_marketplace_id, self.amazon)
        invoice.action_post()
        self.assertFalse(invoice.line_ids.filtered("tax_line_id"))
        log = self.env["us.tax.calculation.log"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", invoice.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.source, "marketplace")

    def test_marketplace_refund_nets_down_sales(self):
        """A marketplace refund reduces the period's marketplace sales."""
        self._invoice(marketplace=self.amazon, price=250.0)
        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner.id,
                "invoice_date": "2025-01-20",
                "company_id": self.company.id,
                "us_tax_marketplace_id": self.amazon.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        refund.action_post()
        tax_return = self.env["us.tax.return"].create(
            {
                "company_id": self.company.id,
                "state_id": self.wy.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
            }
        )
        tax_return.action_generate()
        self.assertAlmostEqual(tax_return.marketplace_sales, 150.0, places=2)
