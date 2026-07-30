# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestFiscalPositionTrigger(AccountTestInvoicingCommon):
    """Fiscal position as a second exemption trigger, and the post-time snapshot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.resale = cls.env.ref("l10n_us_sales_tax_exemption.reason_resale")
        cls.government = cls.env.ref("l10n_us_sales_tax_exemption.reason_government")
        cls.engine = cls.env["us.tax.engine.service"]

        cls.position = cls.env["account.fiscal.position"].create(
            {
                "name": "US Tax Exempt",
                "company_id": cls.env.company.id,
                "is_us_tax_exempt": True,
                "us_tax_exemption_reason_id": cls.government.id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "City of Cheyenne",
                "zip": "82001",
                "city": "Cheyenne",
                "state_id": cls.wy.id,
                "country_id": cls.us.id,
                "property_account_position_id": cls.position.id,
            }
        )

    def _resolve(self, partner):
        return self.engine._get_customer_exemption(
            partner.id, self.wy, date(2026, 1, 15), self.env.company.id
        )

    def test_fiscal_position_triggers_exemption(self):
        self.assertEqual(self._resolve(self.partner), "government")

    def test_plain_fiscal_position_does_not_exempt(self):
        plain = self.env["account.fiscal.position"].create(
            {"name": "Domestic", "company_id": self.env.company.id}
        )
        self.partner.property_account_position_id = plain
        self.assertFalse(self._resolve(self.partner))

    def test_certificate_wins_over_fiscal_position(self):
        """Both triggers present: the certificate is the more specific answer."""
        self.env["us.tax.exemption"].create(
            {
                "partner_id": self.partner.id,
                "reason_id": self.resale.id,
                "state_ids": [(6, 0, [self.wy.id])],
                "certificate_number": "WY-RESALE-777",
                "effective_date": "2020-01-01",
                "state": "valid",
                "company_id": self.env.company.id,
            }
        )
        self.assertEqual(self._resolve(self.partner), "resale")

    def test_fiscal_position_without_reason_falls_back_to_other(self):
        self.position.us_tax_exemption_reason_id = False
        self.assertEqual(self._resolve(self.partner), "other")


@tagged("post_install", "-at_install")
class TestExemptionSnapshot(AccountTestInvoicingCommon):
    """A zero-tax line must stay defensible after the customer record moves on."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.resale = cls.env.ref("l10n_us_sales_tax_exemption.reason_resale")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Frontier Resale Co",
                "zip": "82001",
                "city": "Cheyenne",
                "state_id": cls.wy.id,
                "country_id": cls.us.id,
            }
        )
        cls.certificate = cls.env["us.tax.exemption"].create(
            {
                "partner_id": cls.partner.id,
                "reason_id": cls.resale.id,
                "state_ids": [(6, 0, [cls.wy.id])],
                "certificate_number": "WY-RESALE-12345",
                "effective_date": "2020-01-01",
                "state": "valid",
                "company_id": cls.env.company.id,
            }
        )

    def _invoice(self):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": date(2026, 1, 15),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Fencing",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        move.action_post()
        return move

    def test_snapshot_written_at_post(self):
        move = self._invoice()
        self.assertEqual(move.us_tax_exemption_id, self.certificate)
        self.assertEqual(move.us_tax_exemption_number, "WY-RESALE-12345")
        self.assertEqual(move.us_tax_exemption_reason, "resale")

    def test_snapshot_survives_certificate_revocation(self):
        """The audit question is what was true at post time, not today."""
        move = self._invoice()
        self.certificate.action_revoke()
        self.certificate.certificate_number = "EDITED-LATER"
        move.invalidate_recordset()
        self.assertEqual(move.us_tax_exemption_number, "WY-RESALE-12345")
        self.assertEqual(move.us_tax_exemption_reason, "resale")

    def test_no_certificate_leaves_snapshot_empty(self):
        other = self.env["res.partner"].create(
            {
                "name": "Taxable Co",
                "zip": "82001",
                "state_id": self.wy.id,
                "country_id": self.us.id,
            }
        )
        self.partner = other
        move = self._invoice()
        self.assertFalse(move.us_tax_exemption_number)
        self.assertFalse(move.us_tax_exemption_reason)
