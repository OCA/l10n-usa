# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..services.importer_sst import SstImporter
from .common import BOUNDARY_CSV, RATE_CSV


@tagged("post_install", "-at_install")
class TestSstBooking(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_tax.engine_active", "True")
        ICP.set_param("l10n_us_tax.engine_mode", "hybrid")
        ICP.set_param("l10n_us_tax.fail_policy", "warn")

        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        batch = cls.env["us.tax.import.batch"].create(
            {"source": "sst", "state_id": cls.wy.id}
        )
        importer = SstImporter(cls.env, batch)
        importer.import_rate_file(RATE_CSV, cls.wy)
        importer.import_boundary_file(BOUNDARY_CSV, cls.wy)

        cls.cat_tangible = cls.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )
        cls.product_a.us_tax_category_id = cls.cat_tangible
        cls.env["us.tax.nexus"].create(
            {"company_id": cls.company.id, "state_id": cls.wy.id, "active": True}
        )
        cls.partner_wy = cls.env["res.partner"].create(
            {
                "name": "Customer WY",
                "zip": "82001",
                "city": "Cheyenne",
                "state_id": cls.wy.id,
                "country_id": cls.us.id,
            }
        )

    def _post_invoice(self, price=100.0, date="2025-01-15"):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_wy.id,
                "invoice_date": date,
                "company_id": self.company.id,
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

    def test_books_one_tax_line_per_named_jurisdiction(self):
        move = self._post_invoice()
        tax_lines = move.line_ids.filtered("tax_line_id")
        # State 4% + county 1% + district 0.5% = three jurisdiction tax lines.
        self.assertEqual(len(tax_lines), 3)
        for tl in tax_lines:
            # Every booked tax resolves to a *named* jurisdiction now.
            self.assertTrue(tl.tax_line_id.us_tax_jurisdiction_id)
            self.assertEqual(tl.tax_line_id.us_tax_state_id, self.wy)
        total_tax = sum(-tl.balance for tl in tax_lines)
        self.assertAlmostEqual(total_tax, 5.5, places=2)

    def test_return_aggregates_by_jurisdiction_with_fips(self):
        if "us.tax.return" not in self.env:
            self.skipTest("l10n_us_sales_tax_report not installed")
        self._post_invoice()
        tax_return = self.env["us.tax.return"].create(
            {
                "company_id": self.company.id,
                "state_id": self.wy.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
            }
        )
        tax_return.action_generate()
        self.assertEqual(len(tax_return.line_ids), 3)
        # Each line carries its named jurisdiction (→ FIPS for SER).
        self.assertTrue(all(tax_return.line_ids.mapped("jurisdiction_id")))
        county_line = tax_return.line_ids.filtered(lambda r: r.level == "county")
        self.assertEqual(county_line.jurisdiction_id.fips_county, "021")
        self.assertAlmostEqual(county_line.tax_amount, 1.0, places=2)
        self.assertAlmostEqual(tax_return.total_tax, 5.5, places=2)
        self.assertAlmostEqual(tax_return.total_taxable, 100.0, places=2)

    def test_ser_export_end_to_end_with_fips_detail(self):
        """Full chain on the SST path: post an invoice → book per FIPS-coded
        jurisdiction → generate the return → export the SER, and the county FIPS
        appears in the SER schedule. Skipped when the SER addon isn't installed."""
        if "us.tax.return" not in self.env:
            self.skipTest("l10n_us_sales_tax_report not installed")
        tax_return = self.env["us.tax.return"]
        if not hasattr(tax_return, "action_export_ser"):
            self.skipTest("l10n_us_sales_tax_ser not installed")
        import base64
        import xml.etree.ElementTree as ET

        self.env.company.write({"sst_id": "S12345678", "sst_fein": "123456789"})
        self._post_invoice(price=100.0)
        ret = tax_return.create(
            {
                "company_id": self.company.id,
                "state_id": self.wy.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
            }
        )
        ret.action_generate()
        ret.action_export_ser()
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "us.tax.return"), ("res_id", "=", ret.id)], limit=1
        )
        root = ET.fromstring(base64.b64decode(attachment.datas))
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        codes = {
            d.find("JurisdictionCode").text for d in ser.findall("JurisdictionDetail")
        }
        # Laramie County FIPS (021) from the imported boundary file reaches the SER.
        self.assertIn("021", codes)

    def test_no_nexus_clears_existing_tax(self):
        """Engine active + no nexus in the ship-to state clears default taxes."""
        ny = self.env["res.country.state"].search(
            [("code", "=", "NY"), ("country_id", "=", self.us.id)], limit=1
        )
        tax = self.env["account.tax"].create(
            {
                "name": "Default 10%",
                "amount_type": "percent",
                "amount": 10.0,
                "type_tax_use": "sale",
                "country_id": self.us.id,
                "company_id": self.company.id,
            }
        )
        partner_ny = self.env["res.partner"].create(
            {
                "name": "NY Buyer",
                "state_id": ny.id,
                "zip": "10001",
                "country_id": self.us.id,
            }
        )
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner_ny.id,
                "invoice_date": "2025-01-15",
                "company_id": self.company.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [(6, 0, [tax.id])],
                        },
                    )
                ],
            }
        )
        move.action_post()
        self.assertFalse(move.line_ids.filtered("tax_line_id"))

    def test_origin_based_sourcing_intrastate(self):
        """In an origin-based state, an intrastate sale rates the ship-from."""
        from .common import boundary_row

        tx = self.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", self.us.id)], limit=1
        )
        # TX state 6.25%; Dallas county (113) 0.5% (origin), Harris (201) 2% (dest).
        rate_csv = "\n".join(
            [
                "48,45,48,0.0625,0.0625,0,0,20200101,29991231",
                "48,00,113,0.005,0.005,0,0,20200101,29991231",
                "48,00,201,0.02,0.02,0,0,20200101,29991231",
            ]
        )
        boundary_csv = "\n".join(
            [
                boundary_row("75001", "48", "113", districts=()),  # Dallas (origin)
                boundary_row("77001", "48", "201", districts=()),  # Houston (dest)
            ]
        )
        batch = self.env["us.tax.import.batch"].create(
            {"source": "sst", "state_id": tx.id}
        )
        importer = SstImporter(self.env, batch)
        importer.import_rate_file(rate_csv, tx)
        importer.import_boundary_file(boundary_csv, tx)
        # Seller (ship-from) is in Dallas; nexus in TX.
        self.company.partner_id.write({"state_id": tx.id, "zip": "75001"})
        self.env["us.tax.nexus"].create(
            {"company_id": self.company.id, "state_id": tx.id, "active": True}
        )
        customer = self.env["res.partner"].create(
            {
                "name": "TX Buyer",
                "state_id": tx.id,
                "zip": "77001",
                "country_id": self.us.id,
            }
        )
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": customer.id,
                "invoice_date": "2025-01-15",
                "company_id": self.company.id,
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
        move.action_post()
        total_tax = sum(-tl.balance for tl in move.line_ids.filtered("tax_line_id"))
        # Origin (Dallas): 6.25% + 0.5% = 6.75 — NOT destination's 8.25%.
        self.assertAlmostEqual(total_tax, 6.75, places=2)
