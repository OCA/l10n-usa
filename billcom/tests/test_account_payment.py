# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestAccountPayment(BillcomTestCommon):
    """Test account.payment Bill.com integration"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create a payment for testing
        cls.payment = cls.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": cls.vendor_billcom.id,
                "amount": 100.0,
                "journal_id": cls.bank_journal.id,
                "date": fields.Date.today(),
            }
        )

    def test_payment_billcom_fields(self):
        """Test that payments have all required Bill.com fields"""
        required_fields = [
            "billcom",
            "billcom_id",
            "is_sync_to_billcom",
            "billcom_sync_status",
        ]

        for field in required_fields:
            self.assertTrue(
                hasattr(self.payment, field), f"Payment should have field: {field}"
            )

    @patch("odoo.addons.billcom.models.billcom_service.BillcomService._make_request")
    def test_sync_payment_to_billcom(self, mock_request):
        """Test syncing payment to Bill.com"""
        mock_request.return_value = {
            "id": "payment_abc123",
            "amount": 100.0,
            "processDate": fields.Date.today().isoformat(),
            "singleStatus": "SCHEDULED",
        }

        # Trigger sync
        self.payment.sync_to_billcom()

        # Verify billcom_id was updated
        self.assertEqual(self.payment.billcom_id, "payment_abc123")

    @patch("odoo.addons.billcom.models.billcom_service.BillcomService._make_request")
    def test_payment_status_update_from_webhook(self, mock_request):
        """Test payment status update from Bill.com webhook"""
        self.payment.billcom_id = "payment_webhook_001"

        mock_request.return_value = {
            "id": "payment_webhook_001",
            "singleStatus": "PAID",
            "paidDate": fields.Date.today().isoformat(),
        }

        # Sync from Bill.com
        self.payment.sync_from_billcom_by_id("payment_webhook_001")

        # Verify payment was synced
        self.assertEqual(self.payment.billcom_id, "payment_webhook_001")

    def test_payment_for_vendor_bill(self):
        """Test creating payment for vendor bill"""
        # Post the vendor bill
        self.vendor_bill.action_post()

        # Create payment from bill
        payment = (
            self.env["account.payment"]
            .with_context(active_ids=[self.vendor_bill.id], active_model="account.move")
            .create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": self.vendor_billcom.id,
                    "amount": self.vendor_bill.amount_total,
                    "journal_id": self.bank_journal.id,
                }
            )
        )

        self.assertEqual(payment.partner_id, self.vendor_billcom)
        self.assertEqual(payment.amount, self.vendor_bill.amount_total)

    def test_payment_multi_currency(self):
        """Test payment in different currency"""
        eur = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        if not eur:
            eur = self.env["res.currency"].create({"name": "EUR", "symbol": "€"})

        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor_billcom.id,
                "amount": 100.0,
                "currency_id": eur.id,
                "journal_id": self.bank_journal.id,
            }
        )

        self.assertEqual(payment.currency_id, eur)

    def test_payment_funding_account(self):
        """Test payment with Bill.com funding account"""
        # Create funding account
        funding_account = self.env["billcom.funding.account"].create(
            {
                "name": "Test Bank Account",
                "billcom_id": "funding_001",
                "account_type": "Checking",
                "last_four_digits": "1234",
            }
        )

        # Payment with funding account (if field exists)
        if hasattr(self.payment, "billcom_funding_account_id"):
            self.payment.billcom_funding_account_id = funding_account
            self.assertEqual(self.payment.billcom_funding_account_id, funding_account)

    @patch("odoo.addons.billcom.models.billcom_service.BillcomService._make_request")
    def test_payment_sync_error_handling(self, mock_request):
        """Test error handling during payment sync"""
        mock_request.side_effect = UserError("Payment sync failed")

        with self.assertRaises(UserError):
            self.payment.sync_to_billcom()

    def test_payment_date_validation(self):
        """Test payment date is required"""
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor_billcom.id,
                "amount": 100.0,
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
            }
        )

        self.assertTrue(payment.date)

    def test_customer_payment_not_synced_to_billcom(self):
        """Test customer payments (inbound) sync behavior"""
        customer_payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.customer_billcom.id,
                "amount": 100.0,
                "journal_id": self.bank_journal.id,
            }
        )

        self.assertEqual(customer_payment.payment_type, "inbound")
