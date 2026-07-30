# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import xml.etree.ElementTree as ET

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestSerEndToEnd(AccountTestInvoicingCommon):
    """The full chain: post a customer invoice → the engine books a tax line
    per jurisdiction → generate the period's return → export the SER, and the
    SER's amounts are derived from the posted invoice (not hand-fed)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.write(
            {"sst_id": "S12345678", "sst_fein": "123456789", "sst_test_mode": True}
        )
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_tax.engine_active", "True")
        ICP.set_param("l10n_us_tax.engine_mode", "hybrid")
        ICP.set_param("l10n_us_tax.fail_policy", "warn")

        cls.us = cls.env.ref("base.us")
        cls.fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.cat_tangible = cls.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )
        # State-level FIPS (12 = Florida) drives the SER filing header. County
        # FIPS detail on the SER schedule requires per-level named jurisdictions
        # (the SST resolver path) — exercised end-to-end in the SST suite.
        cls.jurisdiction = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Miami-Dade",
                "type": "county",
                "state_id": cls.fl.id,
                "county": "MIAMI-DADE",
                "fips_state": "12",
                "fips_county": "086",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jurisdiction.id,
                "product_tax_category_id": cls.cat_tangible.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33101",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jurisdiction.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        cls.env["us.tax.nexus"].create(
            {"company_id": cls.company.id, "state_id": cls.fl.id, "active": True}
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Customer FL",
                "zip": "33101",
                "city": "Miami",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )
        cls.product_a.us_tax_category_id = cls.cat_tangible

    def _post_invoice(self, price=100.0, date="2025-01-15"):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
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

    def test_posted_invoice_flows_through_to_ser(self):
        # 1. Post a $200 taxable invoice — engine books state + county tax lines.
        move = self._post_invoice(price=200.0)
        tax_lines = move.line_ids.filtered("tax_line_id")
        self.assertEqual(len(tax_lines), 2)

        # 2. Generate the period return — aggregates the posted invoice.
        tax_return = self.env["us.tax.return"].create(
            {
                "company_id": self.company.id,
                "state_id": self.fl.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
            }
        )
        tax_return.action_generate()
        self.assertEqual(tax_return.state, "generated")
        # 6% state + 1% county on 200 = 12 + 2 = 14.
        self.assertAlmostEqual(tax_return.total_tax, 14.0, places=2)
        self.assertAlmostEqual(tax_return.total_taxable, 200.0, places=2)
        self.assertAlmostEqual(tax_return.total_sales, 200.0, places=2)

        # 3. Export the SER and parse it.
        tax_return.action_export_ser()
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "us.tax.return"), ("res_id", "=", tax_return.id)],
            limit=1,
        )
        self.assertEqual(attachment.mimetype, "application/xml")
        root = ET.fromstring(base64.b64decode(attachment.datas))

        # 4. The SER amounts come from the posted invoice, end to end.
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        self.assertEqual(ser.find("TotalSales").text, "200.00")
        self.assertEqual(ser.find("TaxableSales").text, "200.00")
        self.assertEqual(ser.find("StateTaxDueSalesInState").text, "12.00")
        self.assertEqual(ser.find("TotalTaxDue").text, "14.00")
        # State FIPS on the filing header, derived from the booked state line.
        filing = root.find("SimplifiedReturnDocument/SSTPFilingHeader")
        self.assertEqual(filing.find("FIPSCode").text, "12")
