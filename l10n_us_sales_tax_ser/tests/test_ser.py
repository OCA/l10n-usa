# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        cls.company = cls.env.company
        cls.company.write({"sst_id": "S12345678", "sst_fein": "123456789"})
        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        Jur = cls.env["us.tax.jurisdiction"]
        cls.j_state = Jur.create(
            {"name": "WY", "type": "state", "state_id": cls.wy.id, "fips_state": "56"}
        )
        cls.j_county = Jur.create(
            {
                "name": "Laramie",
                "type": "county",
                "state_id": cls.wy.id,
                "fips_state": "56",
                "fips_county": "021",
            }
        )
        cls.j_district = Jur.create(
            {
                "name": "District 55555",
                "type": "district",
                "state_id": cls.wy.id,
                "fips_state": "56",
                "district_code": "55555",
            }
        )
        cls.ret = cls.env["us.tax.return"].create(
            {
                "company_id": cls.company.id,
                "state_id": cls.wy.id,
                "date_from": "2025-01-01",
                "date_to": "2025-01-31",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "level": "state",
                            "jurisdiction_id": cls.j_state.id,
                            "taxable_base": 100.0,
                            "tax_amount": 4.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "level": "county",
                            "jurisdiction_id": cls.j_county.id,
                            "taxable_base": 100.0,
                            "tax_amount": 1.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "level": "district",
                            "jurisdiction_id": cls.j_district.id,
                            "taxable_base": 100.0,
                            "tax_amount": 0.5,
                        },
                    ),
                ],
            }
        )
        cls.ret.write(
            {"state": "generated", "total_sales": 120.0, "exempt_sales": 20.0}
        )

    def _build_root(self):
        self.ret.action_export_ser()
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "us.tax.return"), ("res_id", "=", self.ret.id)],
            limit=1,
        )
        self.assertTrue(attachment)
        self.assertEqual(attachment.mimetype, "application/xml")
        return ET.fromstring(base64.b64decode(attachment.datas))

    def test_transmission_envelope(self):
        root = self._build_root()
        self.assertEqual(root.tag, "SSTSimplifiedReturnTransmission")
        self.assertEqual(root.attrib["transmissionVersion"], "SSTSER2025V01")
        self.assertEqual(root.find("TransmissionHeader/DocumentCount").text, "1")

    def test_filing_header_identity(self):
        root = self._build_root()
        filing = root.find("SimplifiedReturnDocument/SSTPFilingHeader")
        self.assertEqual(filing.find("SSTPID").text, "S12345678")
        self.assertEqual(filing.find("FIPSCode").text, "56")
        fed = filing.find("TIN/FedTIN")
        self.assertEqual(fed.text, "123456789")
        self.assertEqual(fed.attrib["TypeTIN"], "FEIN")

    def test_state_summary_amounts(self):
        root = self._build_root()
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        self.assertEqual(ser.find("TotalSales").text, "120.00")
        self.assertEqual(ser.find("ExemptionsDeductions").text, "20.00")
        self.assertEqual(ser.find("TaxableSales").text, "100.00")
        self.assertEqual(ser.find("StateTaxDueSalesInState").text, "4.00")
        self.assertEqual(ser.find("TotalTaxDue").text, "5.50")
        self.assertEqual(ser.find("AmountDueOrRefund").text, "5.50")

    def test_jurisdiction_detail_keyed_by_fips(self):
        root = self._build_root()
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        details = ser.findall("JurisdictionDetail")
        # State is reported in the summary, not the schedule → 2 local entries.
        self.assertEqual(len(details), 2)
        by_fips = {
            d.find("JurisdictionCode").text: d.find("JurisTaxDueSalesInState").text
            for d in details
        }
        self.assertEqual(by_fips.get("021"), "1.00")
        self.assertEqual(by_fips.get("55555"), "0.50")

    def test_mandatory_elements_and_filing_type(self):
        root = self._build_root()
        filing = root.find("SimplifiedReturnDocument/SSTPFilingHeader")
        self.assertEqual(filing.find("FilingType").text, "SEROnly")
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        for tag in (
            "StateTaxDueSalesOrigOutOfState",
            "StateTaxDueOwnPurchWithdraw",
            "StateTaxDueFoodDrug",
        ):
            self.assertEqual(ser.find(tag).text, "0.00")
        detail = ser.find("JurisdictionDetail")
        self.assertEqual(detail.find("JurisTaxDueSalesOrigOutOfState").text, "0.00")
        self.assertEqual(detail.find("JurisTaxDueOwnPurchWithdraw").text, "0.00")

    def test_process_type_production_toggle(self):
        self.assertEqual(
            self._build_root().find("TransmissionHeader/ProcessType").text, "T"
        )
        self.company.sst_test_mode = False
        self.assertEqual(
            self._build_root().find("TransmissionHeader/ProcessType").text, "P"
        )

    def test_schema_version_configurable(self):
        self.company.sst_transmission_version = "SST2015V01"
        self.assertEqual(self._build_root().attrib["transmissionVersion"], "SST2015V01")

    def test_requires_filer_identity(self):
        self.company.sst_id = False
        self.ret.state_registration_id = False
        with self.assertRaises(UserError):
            self.ret.action_export_ser()

    def test_requires_fein(self):
        self.company.sst_fein = False
        with self.assertRaises(UserError):
            self.ret.action_export_ser()

    def test_state_registration_fallback(self):
        self.company.sst_id = False
        self.ret.state_registration_id = "WY-9999"
        root = self._build_root()
        filing = root.find("SimplifiedReturnDocument/SSTPFilingHeader")
        self.assertIsNone(filing.find("SSTPID"))
        self.assertEqual(filing.find("StateID").text, "WY-9999")

    def test_composite_ser_code_used_for_jurisdiction(self):
        self.j_county.composite_ser_code = "99999"
        root = self._build_root()
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        codes = {
            d.find("JurisdictionCode").text for d in ser.findall("JurisdictionDetail")
        }
        # County reports under its composite code, not its plain FIPS.
        self.assertIn("99999", codes)
        self.assertNotIn("021", codes)

    def test_negative_amounts_formatted(self):
        """A net-refund return serialises negative amounts (no crash)."""
        ret = self.env["us.tax.return"].create(
            {
                "company_id": self.company.id,
                "state_id": self.wy.id,
                "date_from": "2025-02-01",
                "date_to": "2025-02-28",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "level": "state",
                            "jurisdiction_id": self.j_state.id,
                            "taxable_base": -50.0,
                            "tax_amount": -2.0,
                        },
                    )
                ],
            }
        )
        ret.write({"state": "generated", "total_sales": -50.0, "exempt_sales": 0.0})
        ret.action_export_ser()
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "us.tax.return"), ("res_id", "=", ret.id)], limit=1
        )
        root = ET.fromstring(base64.b64decode(attachment.datas))
        ser = root.find("SimplifiedReturnDocument/SimplifiedElectronicReturn")
        self.assertEqual(ser.find("AmountDueOrRefund").text, "-2.00")
