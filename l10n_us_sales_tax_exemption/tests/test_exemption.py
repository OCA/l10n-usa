# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestExemption(AccountTestInvoicingCommon):
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
        cls.ny = cls.env["res.country.state"].search(
            [("code", "=", "NY"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.resale = cls.env.ref("l10n_us_sales_tax_exemption.reason_resale")
        cls.engine = cls.env["us.tax.engine.service"]
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Reseller LLC",
                "zip": "82001",
                "city": "Cheyenne",
                "state_id": cls.wy.id,
                "country_id": cls.us.id,
            }
        )
        cls.cert = cls.env["us.tax.exemption"].create(
            {
                "partner_id": cls.partner.id,
                "reason_id": cls.resale.id,
                "state_ids": [(6, 0, cls.wy.ids)],
                "certificate_number": "WY-RESALE-1",
                "effective_date": "2020-01-01",
                "state": "valid",
            }
        )
        cls.env["us.tax.nexus"].create(
            {"company_id": cls.company.id, "state_id": cls.wy.id, "active": True}
        )

    # ── Hook unit tests ───────────────────────────────────────────────────────

    def _hook(self, state=None, on=None, company=None):
        return self.engine._get_customer_exemption(
            self.partner.id,
            state or self.wy,
            on or date(2025, 6, 15),
            (company or self.company).id,
        )

    def test_valid_cert_returns_reason(self):
        self.assertEqual(self._hook(), "resale")

    def test_wrong_state_not_exempt(self):
        self.assertFalse(self._hook(state=self.ny))

    def test_before_effective_not_exempt(self):
        self.assertFalse(self._hook(on=date(2019, 1, 1)))

    def test_expired_cert_not_exempt(self):
        self.cert.expiry_date = "2024-12-31"
        self.assertFalse(self._hook(on=date(2025, 6, 15)))
        self.assertEqual(self._hook(on=date(2024, 6, 1)), "resale")

    def test_revoked_and_draft_not_exempt(self):
        self.cert.action_revoke()
        self.assertFalse(self._hook())
        self.cert.action_reset_draft()
        self.assertFalse(self._hook())
        self.cert.action_validate()
        self.assertEqual(self._hook(), "resale")

    def test_cron_expires_lapsed_certificate(self):
        self.cert.expiry_date = date.today() - timedelta(days=1)
        self.env["us.tax.exemption"]._cron_expire_certificates()
        self.assertEqual(self.cert.state, "expired")

    def test_reason_maps_to_ser_breakout(self):
        self.assertEqual(self.resale.ser_breakout, "resale")
        self.assertEqual(
            self.env.ref("l10n_us_sales_tax_exemption.reason_agriculture").ser_breakout,
            "agriculture",
        )

    def test_multi_state_blanket(self):
        self.cert.state_ids = [(6, 0, (self.wy + self.ny).ids)]
        self.assertEqual(self._hook(state=self.wy), "resale")
        self.assertEqual(self._hook(state=self.ny), "resale")
        ca = self.env["res.country.state"].search(
            [("code", "=", "CA"), ("country_id", "=", self.us.id)], limit=1
        )
        self.assertFalse(self._hook(state=ca))

    def test_company_scoped(self):
        # The certificate belongs to the main company; another company's sale
        # must not pick it up.
        other = self.env["res.company"].create({"name": "Other Co"})
        self.assertEqual(self._hook(company=self.company), "resale")
        self.assertFalse(self._hook(company=other))

    def test_check_dates_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["us.tax.exemption"].create(
                {
                    "partner_id": self.partner.id,
                    "reason_id": self.resale.id,
                    "state_ids": [(6, 0, self.wy.ids)],
                    "effective_date": "2025-01-01",
                    "expiry_date": "2024-01-01",
                }
            )

    # ── Integration ───────────────────────────────────────────────────────────

    def test_child_contact_uses_parent_certificate(self):
        child = self.env["res.partner"].create(
            {
                "name": "Branch",
                "parent_id": self.partner.id,
                "type": "delivery",
                "state_id": self.wy.id,
                "country_id": self.us.id,
                "zip": "82001",
            }
        )
        move = self._invoice(child)
        self.assertFalse(move.line_ids.filtered("tax_line_id"))

    def test_sale_order_exemption_books_exempt_tax(self):
        """An exempt customer's order gets the explicit 0% exempt tax — the
        audit marker for "evaluated, no tax due" — not bare tax-less lines."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "product_uom_qty": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        self.engine.calculate_for_sale_order(order)
        tax = order.order_line.tax_id
        self.assertEqual(len(tax), 1)
        self.assertEqual(tax.amount, 0.0)
        self.assertIn("Exempt", tax.name)
        self.assertEqual(order.amount_tax, 0.0)

    def _invoice(self, partner):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
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
        return move

    def test_exempt_customer_invoice_has_no_tax(self):
        move = self._invoice(self.partner)
        self.assertFalse(move.line_ids.filtered("tax_line_id"))
        log = self.env["us.tax.calculation.log"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", move.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.source, "exempt_customer")
        self.assertEqual(log.exemption_reason, "resale")

    # ── submission lifecycle ────────────────────────────────────────────────

    def test_a_draft_may_be_incomplete(self):
        """A portal form or an API caller has to be able to save what it has.

        Demanding every field at creation makes a partially completed
        submission impossible to persist.
        """
        partial = self.env["us.tax.exemption"].create(
            {"partner_id": self.partner.id, "effective_date": date.today()}
        )
        self.assertEqual(partial.state, "draft")
        self.assertFalse(partial.reason_id)
        self.assertFalse(partial.state_ids)

    def test_leaving_draft_demands_the_missing_pieces(self):
        partial = self.env["us.tax.exemption"].create(
            {"partner_id": self.partner.id, "effective_date": date.today()}
        )
        with self.assertRaises(ValidationError):
            partial.action_mark_signed()

    def test_a_signed_certificate_does_not_exempt_anything_yet(self):
        """The control that matters for portal and API submissions.

        Anything able to create a record could otherwise grant itself an
        exemption; the engine gates on 'valid', so a submission waits.
        """
        self.cert.action_mark_signed()
        self.assertEqual(self.cert.state, "signed")
        self.assertFalse(self._hook(), "an unapproved submission is already exempting")

    def test_approval_makes_a_signed_certificate_effective(self):
        self.cert.action_mark_signed()
        self.cert.action_validate()
        self.assertEqual(self.cert.state, "valid")
        self.assertEqual(self._hook(), "resale")
