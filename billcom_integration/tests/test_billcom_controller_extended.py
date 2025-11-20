# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
import hmac
import logging

from odoo.tests import tagged

from odoo.addons.billcom_integration.controllers.billcom_controller import (
    BillComController,
)

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomControllerExtended(BillcomTestCommon):
    """Extended tests for Bill.com webhook controller"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.controller = BillComController()

    # ===== Webhook Signature Validation Tests =====

    def test_validate_webhook_signature_valid(self):
        """Should validate correct webhook signature"""
        secret = "test_webhook_secret_123"
        payload = b'{"test": "data"}'

        # Generate correct signature
        hash_digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
        signature = base64.b64encode(hash_digest).decode("utf-8")

        is_valid = self.controller._validate_webhook_signature(
            payload, signature, secret
        )

        self.assertTrue(is_valid)

    def test_validate_webhook_signature_invalid(self):
        """Should reject invalid webhook signature"""
        secret = "test_webhook_secret_123"
        payload = b'{"test": "data"}'
        wrong_signature = "invalid_signature_here"

        is_valid = self.controller._validate_webhook_signature(
            payload, wrong_signature, secret
        )

        self.assertFalse(is_valid)

    def test_validate_webhook_signature_no_secret(self):
        """Should skip validation if no secret configured"""
        payload = b'{"test": "data"}'
        signature = "any_signature"

        is_valid = self.controller._validate_webhook_signature(payload, signature, None)

        self.assertTrue(is_valid)  # Returns True when no secret

    def test_validate_webhook_signature_no_signature_header(self):
        """Should return False if signature header missing"""
        secret = "test_secret"
        payload = b'{"test": "data"}'

        is_valid = self.controller._validate_webhook_signature(payload, None, secret)

        self.assertFalse(is_valid)

    def test_validate_webhook_signature_string_payload(self):
        """Should handle string payload by converting to bytes"""
        secret = "test_secret"
        payload_str = '{"test": "data"}'

        # Generate signature for bytes version
        hash_digest = hmac.new(
            secret.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256
        ).digest()
        signature = base64.b64encode(hash_digest).decode("utf-8")

        is_valid = self.controller._validate_webhook_signature(
            payload_str, signature, secret
        )

        self.assertTrue(is_valid)

    # ===== Webhook Data Extraction Tests =====

    def test_extract_webhook_data_bill_event(self):
        """Should correctly extract bill webhook data"""
        data = {
            "metadata": {
                "eventId": "evt_123",
                "eventType": "bill.created",
                "organizationId": "org_456",
                "subscriptionId": "sub_789",
            },
            "bill": {
                "id": "bill_001",
                "invoiceNumber": "INV-001",
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["event_type"], "bill.created")
        self.assertEqual(result["organization_id"], "org_456")
        self.assertEqual(result["entity_id"], "bill_001")
        self.assertEqual(result["entity_data"]["invoiceNumber"], "INV-001")
        self.assertEqual(result["idempotency_key"], "evt_123")

    def test_extract_webhook_data_vendor_event(self):
        """Should correctly extract vendor webhook data"""
        data = {
            "metadata": {
                "eventId": "evt_456",
                "eventType": "vendor.updated",
                "organizationId": "org_456",
            },
            "vendor": {
                "id": "vendor_123",
                "name": "Test Vendor",
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["event_type"], "vendor.updated")
        self.assertEqual(result["entity_id"], "vendor_123")
        self.assertEqual(result["entity_data"]["name"], "Test Vendor")

    def test_extract_webhook_data_payment_event(self):
        """Should correctly extract payment webhook data"""
        data = {
            "metadata": {
                "eventId": "evt_789",
                "eventType": "payment.created",
                "organizationId": "org_456",
            },
            "payment": {
                "id": "pay_001",
                "amount": 500.00,
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["event_type"], "payment.created")
        self.assertEqual(result["entity_id"], "pay_001")
        self.assertEqual(result["entity_data"]["amount"], 500.00)

    def test_extract_webhook_data_autopay_event(self):
        """Should handle autopay events"""
        data = {
            "metadata": {
                "eventId": "evt_auto_123",
                "eventType": "autopay.failed",
                "organizationId": "org_456",
            },
            "payment": {
                "id": "pay_auto_001",
                "status": "FAILED",
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["event_type"], "autopay.failed")
        self.assertEqual(result["entity_id"], "pay_auto_001")

    def test_extract_webhook_data_bank_account_event(self):
        """Should correctly extract bank account webhook data"""
        data = {
            "metadata": {
                "eventId": "evt_bank_123",
                "eventType": "bank-account.updated",
                "organizationId": "org_456",
            },
            "bankAccount": {
                "id": "bank_001",
                "accountNumber": "****1234",
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["event_type"], "bank-account.updated")
        self.assertEqual(result["entity_id"], "bank_001")

    def test_extract_webhook_data_card_account_event(self):
        """Should correctly extract card account webhook data"""
        data = {
            "metadata": {
                "eventId": "evt_card_123",
                "eventType": "card-account.updated",
                "organizationId": "org_456",
            },
            "cardAccount": {
                "id": "card_001",
                "lastFourDigits": "4242",
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["event_type"], "card-account.updated")
        self.assertEqual(result["entity_id"], "card_001")

    def test_extract_webhook_data_no_entity_id(self):
        """Should use event_id as entity_id when entity_id missing"""
        data = {
            "metadata": {
                "eventId": "evt_no_entity_123",
                "eventType": "payment.failed",
                "organizationId": "org_456",
            },
            "payment": {
                # No 'id' field
                "status": "FAILED",
                "reason": "Insufficient funds",
            },
        }

        result = self.controller._extract_webhook_data(data)

        self.assertEqual(result["entity_id"], "event-evt_no_entity_123")

    def test_extract_webhook_data_missing_event_type(self):
        """Should raise ValueError if event type missing"""
        data = {
            "metadata": {
                "eventId": "evt_123",
                # No eventType
                "organizationId": "org_456",
            },
        }

        with self.assertRaises(ValueError) as context:
            self.controller._extract_webhook_data(data)

        self.assertIn("No event type", str(context.exception))

    def test_extract_webhook_data_missing_organization_id(self):
        """Should raise ValueError if organization ID missing"""
        data = {
            "metadata": {
                "eventId": "evt_123",
                "eventType": "bill.created",
                # No organizationId
            },
        }

        with self.assertRaises(ValueError) as context:
            self.controller._extract_webhook_data(data)

        self.assertIn("No organization ID", str(context.exception))

    def test_extract_webhook_data_invalid_format(self):
        """Should raise ValueError if data not a dict"""
        data = "invalid_string_data"

        with self.assertRaises(ValueError) as context:
            self.controller._extract_webhook_data(data)

        self.assertIn("Invalid webhook data format", str(context.exception))

    # ===== Get Config Tests =====

    def test_get_config_from_organization_id_no_org_id(self):
        """Should return None if organization ID not provided"""
        config = self.controller._get_config_from_organization_id(None)

        self.assertIsNone(config)

    # ===== Vendor Webhook Handler Tests =====

    def test_format_vendor_comment(self):
        """Should format vendor data as comment"""
        vendor_data = {
            "name": "Test Vendor Inc",
            "networkStatus": "CONNECTED",
            "paymentNetworkId": "pn_12345",
            "rppsId": "rpps_67890",
            "paymentInformation": {
                "payByType": "ACH",
                "lastPaymentDate": "2024-01-15T10:30:00Z",
            },
            "balance": {
                "amount": 1500.50,
                "lastUpdatedDate": "2024-01-20T14:45:00Z",
            },
        }

        comment = self.controller._format_vendor_comment(vendor_data)

        self.assertIn("Bill.com Vendor Info", comment)
        self.assertIn("CONNECTED", comment)
        self.assertIn("pn_12345", comment)
        self.assertIn("ACH", comment)

    # ===== Error Handler Tests =====

    def test_handle_error(self):
        """Should format error as JSON response"""
        error = Exception("Test error message")

        result = self.controller._handle_error(error)

        self.assertFalse(result["success"])
        self.assertIn("Test error message", result["error"])

    def test_handle_error_user_error(self):
        """Should handle UserError specifically"""
        from odoo.exceptions import UserError

        error = UserError("User-facing error")

        result = self.controller._handle_error(error)

        self.assertFalse(result["success"])
        self.assertIn("User-facing error", result["error"])
