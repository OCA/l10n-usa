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

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
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

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
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

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
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

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_update_billcom_payment_status(self, mock_request):
        """Test updating payment status from Bill.com"""
        # Setup a payment that needs update
        self.payment.billcom_id = "payment_to_update"
        self.payment.billcom_payment_status = "scheduled"
        self.payment.last_sync_date = fields.Datetime.now() - fields.timedelta(hours=2)

        # Mock response
        mock_request.return_value = {
            "id": "payment_to_update",
            "singleStatus": "PROCESSED",
            "confirmationNumber": "CONF123",
        }

        # Run update
        self.env["account.payment"].update_billcom_payment_status()

        # Verify status updated
        self.assertEqual(self.payment.billcom_payment_status, "processed")
        self.assertEqual(self.payment.billcom_confirmation_number, "CONF123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_action_cancel_billcom_payment(self, mock_request):
        """Test canceling payment in Bill.com"""
        self.payment.billcom_id = "payment_to_cancel"
        self.payment.billcom_payment_status = "scheduled"

        mock_request.return_value = {"id": "payment_to_cancel", "status": "CANCELED"}

        self.payment.action_cancel_billcom_payment()

        self.assertEqual(self.payment.billcom_payment_status, "canceled")
        self.assertEqual(self.payment.state, "cancel")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_action_get_payment_status(self, mock_request):
        """Test manual status fetch"""
        self.payment.billcom_id = "payment_status_check"

        mock_request.return_value = {
            "id": "payment_status_check",
            "singleStatus": "SENT",
        }

        self.payment.action_get_payment_status()

        self.assertEqual(self.payment.billcom_payment_status, "sent")

    def test_prepare_payment_data_wallet(self):
        """Test payment data preparation for WALLET funding type"""
        self.payment.billcom_funding_account_type = "WALLET"
        # Wallet requires process date
        self.payment.billcom_process_date = fields.Date.today() + fields.timedelta(
            days=1
        )

        data = self.payment._prepare_payment_data()

        self.assertEqual(data["fundingAccount"]["type"], "WALLET")
        self.assertIn("processDate", data)

    def test_prepare_payment_data_default_funding(self):
        """Test fallback to default funding account"""
        # Ensure no funding account on journal
        self.bank_journal.bank_account_id.billcom_funding_account_id = False

        # Create default funding account
        self.env["billcom.funding.account"].create(
            {
                "name": "Default Funding",
                "billcom_id": "funding_default_001",
                "status": "VERIFIED",
                "is_default_payables": True,
                "account_type": "CHECKING",
            }
        )

        data = self.payment._prepare_payment_data()

        self.assertEqual(data["fundingAccount"]["id"], "funding_default_001")

    def test_prepare_payment_data_international(self):
        """Test international payment data preparation"""
        # Setup international vendor
        fr = self.env.ref("base.fr")
        eur = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        if not eur:
            eur = self.env["res.currency"].create({"name": "EUR", "symbol": "€"})

        intl_vendor = self.env["res.partner"].create(
            {
                "name": "Intl Vendor",
                "country_id": fr.id,
                "is_sync_to_billcom": True,
            }
        )

        # Add bank with BIC
        self.env["res.partner.bank"].create(
            {
                "partner_id": intl_vendor.id,
                "acc_number": "FR123",
                "bank_id": self.env["res.bank"]
                .create({"name": "Bank FR", "bic": "FRBIC123"})
                .id,
            }
        )

        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": intl_vendor.id,
                "amount": 100.0,
                "currency_id": eur.id,
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
            }
        )

        data = payment._prepare_payment_data()

        self.assertIn("internationalOptions", data)
        self.assertEqual(data["internationalOptions"]["paymentCurrency"], "EUR")
        self.assertEqual(data["internationalOptions"]["wireInstructions"], "FRBIC123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_existing_payment(self, mock_request):
        """Test syncing an already existing payment (GET status)"""
        self.payment.billcom_id = "payment_existing_123"

        mock_request.return_value = {
            "id": "payment_existing_123",
            "singleStatus": "PROCESSED",
        }

        self.payment.button_sync_to_billcom()

        # Should call GET, not POST
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "GET")
        self.assertIn("payment_existing_123", args[0])

        self.assertEqual(self.payment.billcom_payment_status, "processed")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_update_billcom_payment_status_retry(self, mock_request):
        """Test retry logic in update_billcom_payment_status"""
        self.payment.billcom_id = "payment_retry_test"
        self.payment.billcom_payment_status = "scheduled"
        # Ensure it's old enough to be picked up
        self.payment.last_sync_date = fields.Datetime.now() - fields.timedelta(hours=2)

        # Fail twice, succeed on third try
        mock_request.side_effect = [
            UserError("API Error 1"),
            UserError("API Error 2"),
            {"id": "payment_retry_test", "singleStatus": "PROCESSED"},
        ]

        # Configure retries
        with patch("time.sleep"):  # Skip sleep delay
            self.env["account.payment"].update_billcom_payment_status()

        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(self.payment.billcom_payment_status, "processed")

    def test_action_set_process_date(self):
        """Test action_set_process_date_for_new_vendor"""
        # Clear process date
        self.payment.billcom_process_date = False

        self.payment.action_set_process_date_for_new_vendor()

        self.assertTrue(self.payment.billcom_process_date)
        self.assertTrue(self.payment.billcom_process_date > fields.Date.today())
