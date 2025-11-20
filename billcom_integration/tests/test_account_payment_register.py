# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .common import BillcomTestCommon


@tagged("post_install", "-at_install", "billcom")
class TestAccountPaymentRegister(BillcomTestCommon):
    """Tests for account.payment.register wizard"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create a vendor configured for Bill.com
        cls.vendor_billcom = cls.env["res.partner"].create(
            {
                "name": "Bill.com Vendor",
                "is_company": True,
                "is_sync_to_billcom": True,
                "billcom_id": "vendor_123",
                "property_account_payable_id": cls.account_payable.id,
                "property_account_receivable_id": cls.account_receivable.id,
            }
        )

        # Create a vendor invoice
        cls.invoice = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.vendor_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test Service",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": cls.account_expense.id,
                        },
                    )
                ],
            }
        )
        cls.invoice.action_post()

    def test_default_get_sync_flag(self):
        """Should default is_sync_to_billcom from vendor"""
        ctx = {
            "active_model": "account.move",
            "active_ids": [self.invoice.id],
        }

        wizard = self.env["account.payment.register"].with_context(**ctx).create({})
        wizard.default_get(["is_sync_to_billcom"])

        # Note: default_get might not be called automatically by create,
        # but we can call it directly to test logic
        defaults = (
            self.env["account.payment.register"]
            .with_context(**ctx)
            .default_get(["is_sync_to_billcom"])
        )
        self.assertTrue(defaults.get("is_sync_to_billcom"))

    def test_compute_is_international_payment(self):
        """Should detect international payments"""
        # Set vendor to different country
        fr = self.env.ref("base.fr")
        self.vendor_billcom.country_id = fr.id

        ctx = {
            "active_model": "account.move",
            "active_ids": [self.invoice.id],
        }

        wizard = (
            self.env["account.payment.register"]
            .with_context(**ctx)
            .create(
                {
                    "partner_id": self.vendor_billcom.id,
                }
            )
        )

        self.assertTrue(wizard.is_international_payment)

    def test_create_payments_triggers_sync(self):
        """Should trigger sync when creating payments"""
        ctx = {
            "active_model": "account.move",
            "active_ids": [self.invoice.id],
        }
        payment_method_line_ids = self.bank_journal.outbound_payment_method_line_ids
        wizard = (
            self.env["account.payment.register"]
            .with_context(**ctx)
            .create(
                {
                    "partner_id": self.vendor_billcom.id,
                    "amount": 100.0,
                    "payment_date": fields.Date.today(),
                    "journal_id": self.bank_journal.id,
                    "payment_method_line_id": payment_method_line_ids[0].id,
                    "is_sync_to_billcom": True,
                    "billcom_funding_account_type": "WALLET",
                }
            )
        )

        with patch(
            "odoo.addons.billcom_integration.models.account_payment.AccountPayment.button_sync_to_billcom"  # noqa B950
        ) as mock_sync:
            payments = wizard._create_payments()

            self.assertTrue(payments)
            self.assertEqual(payments.billcom_funding_account_type, "WALLET")
            mock_sync.assert_called_once()

    def test_create_payments_sync_error(self):
        """Should handle sync errors gracefully"""
        ctx = {
            "active_model": "account.move",
            "active_ids": [self.invoice.id],
        }

        payment_method_line_ids = self.bank_journal.outbound_payment_method_line_ids
        wizard = (
            self.env["account.payment.register"]
            .with_context(**ctx)
            .create(
                {
                    "partner_id": self.vendor_billcom.id,
                    "amount": 100.0,
                    "payment_date": fields.Date.today(),
                    "journal_id": self.bank_journal.id,
                    "payment_method_line_id": payment_method_line_ids[0].id,
                    "is_sync_to_billcom": True,
                }
            )
        )

        with patch(
            "odoo.addons.billcom_integration.models.account_payment.AccountPayment.button_sync_to_billcom"  # noqa B950
        ) as mock_sync:
            mock_sync.side_effect = Exception("Sync Error")

            payments = wizard._create_payments()

            self.assertTrue(payments)
            self.assertEqual(payments.billcom_sync_status, "sync_failed")
            self.assertIn("Sync Error", payments.billcom_sync_error)
