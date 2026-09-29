# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestOriginWarehouse(AccountTestInvoicingCommon):
    """Origin-based sourcing resolves the ship-from from the warehouse."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svc = cls.env["us.tax.engine.service"]
        cls.company = cls.company_data["company"]
        us = cls.env.ref("base.us")
        tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", us.id)], limit=1
        )
        cls.wh_partner = cls.env["res.partner"].create(
            {
                "name": "Houston WH",
                "country_id": us.id,
                "state_id": tx.id,
                "zip": "77001",
            }
        )
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.warehouse.partner_id = cls.wh_partner
        cls.customer = cls.env["res.partner"].create({"name": "Cust"})
        cls.product = cls.env["product.product"].create({"name": "P"})

    def test_origin_is_warehouse_for_sale_order(self):
        so = self.env["sale.order"].create(
            {"partner_id": self.customer.id, "warehouse_id": self.warehouse.id}
        )
        origin = self.svc._get_origin_partner("sale.order", so.id, self.company.id)
        self.assertEqual(origin, self.wh_partner)

    def test_origin_for_invoice_derives_from_sale_order(self):
        so = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [
                    (0, 0, {"product_id": self.product.id, "product_uom_qty": 1})
                ],
            }
        )
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 10,
                        },
                    )
                ],
            }
        )
        move.invoice_line_ids.sale_line_ids = [(6, 0, so.order_line.ids)]
        origin = self.svc._get_origin_partner("account.move", move.id, self.company.id)
        self.assertEqual(origin, self.wh_partner)

    def test_falls_back_to_company_without_warehouse(self):
        # An unknown / warehouse-less document → the engine's company default.
        origin = self.svc._get_origin_partner(
            "res.partner", self.customer.id, self.company.id
        )
        self.assertEqual(origin, self.company.partner_id)

    def test_manual_invoice_without_sale_link_falls_back(self):
        """A manual invoice (no originating order) → company default, not the
        company's default warehouse."""
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 10,
                        },
                    )
                ],
            }
        )
        origin = self.svc._get_origin_partner("account.move", move.id, self.company.id)
        self.assertEqual(origin, self.company.partner_id)

    def test_multi_warehouse_invoice_picks_one(self):
        wh2_partner = self.env["res.partner"].create({"name": "Dallas WH"})
        wh2 = self.env["stock.warehouse"].create(
            {"name": "WH2", "code": "WH2", "partner_id": wh2_partner.id}
        )
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": 10,
                        },
                    )
                ],
            }
        )
        so1 = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": self.warehouse.id,
                "order_line": [
                    (0, 0, {"product_id": self.product.id, "product_uom_qty": 1})
                ],
            }
        )
        so2 = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "warehouse_id": wh2.id,
                "order_line": [
                    (0, 0, {"product_id": self.product.id, "product_uom_qty": 1})
                ],
            }
        )
        move.invoice_line_ids.sale_line_ids = [
            (6, 0, (so1.order_line | so2.order_line).ids)
        ]
        # Consolidating two warehouses logs a WARNING; assert it (and keep it
        # out of the checklog handler) via assertLogs.
        with self.assertLogs(
            "odoo.addons.l10n_us_sales_tax_stock.models.tax_engine", "WARNING"
        ):
            origin = self.svc._get_origin_partner(
                "account.move", move.id, self.company.id
            )
        self.assertIn(origin, self.wh_partner | wh2_partner)
