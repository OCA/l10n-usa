# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import hmac
import json
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .common import BillcomTestCommon


@tagged("post_install", "-at_install", "billcom")
class TestBillcomWebhookController(BillcomTestCommon):
    """Test Bill.com webhook controller"""

    def setUp(self):
        super().setUp()
        self.webhook_url = "/billcom/webhook"

    def _generate_signature(self, payload_data, secret=None):
        """Generate HMAC-SHA256 signature for webhook (Base64 encoded)

        Bill.com uses HMAC-SHA256 with Base64 encoding, not hexadecimal.
        This matches the actual Bill.com webhook signature format.
        """
        import base64

        if secret is None:
            secret = self.billcom_config.webhook_secret

        payload_str = json.dumps(payload_data)
        hash_digest = hmac.new(
            secret.encode(), payload_str.encode(), hashlib.sha256
        ).digest()

        # Encode as Base64 (NOT hexdigest)
        signature = base64.b64encode(hash_digest).decode("utf-8")
        return signature

    def _get_bill_created_payload(self):
        """Get Bill.com webhook payload for bill.created event"""
        return {
            "idempotencyKey": "bill-created-12345",
            "eventType": "bill.created",
            "entityId": "bill_abc123",
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "id": "bill_abc123",
                "vendorId": self.vendor_billcom.billcom_id,
                "amount": 250.50,
                "invoiceNumber": "INV-001",
                "invoiceDate": fields.Date.today().isoformat(),
                "dueDate": (
                    fields.Date.today() + fields.timedelta(days=30)
                ).isoformat(),
            },
        }

    def _get_bill_updated_payload(self):
        """Get Bill.com webhook payload for bill.updated event"""
        return {
            "idempotencyKey": "bill-updated-67890",
            "eventType": "bill.updated",
            "entityId": self.vendor_bill.billcom_id,
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "id": self.vendor_bill.billcom_id,
                "vendorId": self.vendor_billcom.billcom_id,
                "amount": 150.75,
                "status": "OPEN",
            },
        }

    def _get_bill_archived_payload(self):
        """Get Bill.com webhook payload for bill.archived event"""
        return {
            "idempotencyKey": "bill-archived-11111",
            "eventType": "bill.archived",
            "entityId": self.vendor_bill.billcom_id,
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
        }

    def _get_vendor_created_payload(self):
        """Get Bill.com webhook payload for vendor.created event"""
        return {
            "idempotencyKey": "vendor-created-22222",
            "eventType": "vendor.created",
            "entityId": "vendor_xyz789",
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "id": "vendor_xyz789",
                "name": "New Vendor Inc",
                "email": "newvendor@example.com",
                "isActive": True,
            },
        }

    def _get_vendor_updated_payload(self):
        """Get Bill.com webhook payload for vendor.updated event"""
        return {
            "idempotencyKey": "vendor-updated-33333",
            "eventType": "vendor.updated",
            "entityId": self.vendor_billcom.billcom_id,
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "id": self.vendor_billcom.billcom_id,
                "name": "Updated Vendor Name",
                "email": "updated@example.com",
            },
        }

    def _get_customer_created_payload(self):
        """Get Bill.com webhook payload for customer.created event"""
        return {
            "idempotencyKey": "customer-created-44444",
            "eventType": "customer.created",
            "entityId": "customer_def456",
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "id": "customer_def456",
                "name": "New Customer LLC",
                "email": "newcustomer@example.com",
                "isActive": True,
            },
        }

    def _get_payment_updated_payload(self):
        """Get Bill.com webhook payload for payment.updated event"""
        return {
            "idempotencyKey": "payment-updated-55555",
            "eventType": "payment.updated",
            "entityId": "payment_pqr321",
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "id": "payment_pqr321",
                "status": "PAID",
                "amount": 100.00,
            },
        }

    def test_webhook_bill_created(self):
        """Test webhook handling for bill.created event"""
        payload = self._get_bill_created_payload()
        signature = self._generate_signature(payload)

        # Mock the sync_from_billcom method
        with patch.object(
            type(self.env["account.move"]), "sync_from_billcom"
        ) as mock_sync:
            mock_sync.return_value = self.vendor_bill

            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            # Verify response
            self.assertEqual(response.status_code, 200)
            result = json.loads(response.content.decode())
            self.assertTrue(result.get("success"))

            # Verify sync method was called
            mock_sync.assert_called_once_with("bill_abc123")

            # Verify webhook log created
            webhook_log = self.env["billcom.webhook.log"].search(
                [("idempotency_key", "=", payload["idempotencyKey"])]
            )
            self.assertEqual(len(webhook_log), 1)
            self.assertEqual(webhook_log.event_type, "bill.created")
            self.assertEqual(webhook_log.state, "success")
            self.assertTrue(webhook_log.signature_valid)

    def test_webhook_bill_updated(self):
        """Test webhook handling for bill.updated event"""
        payload = self._get_bill_updated_payload()
        signature = self._generate_signature(payload)

        # Mock the sync_from_billcom method
        with patch.object(
            type(self.env["account.move"]), "sync_from_billcom"
        ) as mock_sync:
            mock_sync.return_value = self.vendor_bill

            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            self.assertEqual(response.status_code, 200)
            mock_sync.assert_called_once()

    def test_webhook_bill_archived(self):
        """Test webhook handling for bill.archived event"""
        payload = self._get_bill_archived_payload()
        signature = self._generate_signature(payload)

        # Ensure bill is active before test
        self.vendor_bill.active = True

        response = self.url_open(
            self.webhook_url,
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "X-Bill-Signature": signature,
            },
        )

        self.assertEqual(response.status_code, 200)

        # Verify bill was archived
        self.vendor_bill.invalidate_cache()
        self.assertFalse(self.vendor_bill.active)

    def test_webhook_vendor_created(self):
        """Test webhook handling for vendor.created event"""
        payload = self._get_vendor_created_payload()
        signature = self._generate_signature(payload)

        # Mock the sync method
        with patch.object(
            type(self.env["res.partner"]), "sync_from_billcom_by_id"
        ) as mock_sync:
            mock_partner = self.env["res.partner"].create(
                {
                    "name": "New Vendor Inc",
                    "billcom_id": "vendor_xyz789",
                    "supplier_rank": 1,
                }
            )
            mock_sync.return_value = mock_partner

            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            self.assertEqual(response.status_code, 200)
            mock_sync.assert_called_once_with(
                billcom_id="vendor_xyz789", partner_type="vendor"
            )

    def test_webhook_customer_created(self):
        """Test webhook handling for customer.created event"""
        payload = self._get_customer_created_payload()
        signature = self._generate_signature(payload)

        # Mock the sync method
        with patch.object(
            type(self.env["res.partner"]), "sync_from_billcom_by_id"
        ) as mock_sync:
            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            self.assertEqual(response.status_code, 200)
            mock_sync.assert_called_once_with(
                billcom_id="customer_def456", partner_type="customer"
            )

    def test_webhook_invalid_signature(self):
        """Test webhook with invalid signature is rejected"""
        payload = self._get_bill_created_payload()
        invalid_signature = "invalid_signature_here"

        response = self.url_open(
            self.webhook_url,
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "X-Bill-Signature": invalid_signature,
            },
        )

        # Verify rejection
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.content.decode())
        self.assertFalse(result.get("success"))

        # Verify webhook log shows invalid signature
        webhook_log = self.env["billcom.webhook.log"].search(
            [("idempotency_key", "=", payload["idempotencyKey"])]
        )
        self.assertEqual(len(webhook_log), 1)
        self.assertFalse(webhook_log.signature_valid)

    def test_webhook_idempotency(self):
        """Test webhook idempotency - duplicate events are ignored"""
        payload = self._get_bill_created_payload()
        signature = self._generate_signature(payload)

        # Send first webhook
        with patch.object(
            type(self.env["account.move"]), "sync_from_billcom"
        ) as mock_sync:
            mock_sync.return_value = self.vendor_bill

            response1 = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            self.assertEqual(response1.status_code, 200)
            self.assertEqual(mock_sync.call_count, 1)

            # Send duplicate webhook
            response2 = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            self.assertEqual(response2.status_code, 200)
            result = json.loads(response2.content.decode())
            self.assertTrue(result.get("success"))

            # Verify sync was NOT called again (idempotency)
            self.assertEqual(mock_sync.call_count, 1)

        # Verify only one webhook log exists
        webhook_logs = self.env["billcom.webhook.log"].search(
            [("idempotency_key", "=", payload["idempotencyKey"])]
        )
        self.assertEqual(len(webhook_logs), 1)

    def test_webhook_missing_signature(self):
        """Test webhook without signature header"""
        payload = self._get_bill_created_payload()

        response = self.url_open(
            self.webhook_url,
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                # No X-Bill-Signature header
            },
        )

        # Should still process but mark as invalid signature
        self.assertEqual(response.status_code, 200)

        webhook_log = self.env["billcom.webhook.log"].search(
            [("idempotency_key", "=", payload["idempotencyKey"])]
        )
        self.assertFalse(webhook_log.signature_valid)

    def test_webhook_error_handling(self):
        """Test webhook error handling when sync fails"""
        payload = self._get_bill_created_payload()
        signature = self._generate_signature(payload)

        # Mock sync to raise exception
        with patch.object(
            type(self.env["account.move"]), "sync_from_billcom"
        ) as mock_sync:
            mock_sync.side_effect = Exception("Sync failed!")

            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            # Should return success (webhook received) but log error
            self.assertEqual(response.status_code, 200)

            # Verify webhook log shows error
            webhook_log = self.env["billcom.webhook.log"].search(
                [("idempotency_key", "=", payload["idempotencyKey"])]
            )
            self.assertEqual(webhook_log.state, "error")
            self.assertIn("Sync failed!", webhook_log.error_message)

    def test_webhook_payment_updated(self):
        """Test webhook handling for payment.updated event"""
        payload = self._get_payment_updated_payload()
        signature = self._generate_signature(payload)

        # Mock the sync method
        with patch.object(
            type(self.env["account.payment"]), "sync_from_billcom_by_id"
        ) as mock_sync:
            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )

            self.assertEqual(response.status_code, 200)
            mock_sync.assert_called_once_with("payment_pqr321")

    def test_webhook_all_event_types(self):
        """Test that all supported event types are processed"""
        event_types = [
            "bill.created",
            "bill.updated",
            "bill.archived",
            "bill.restored",
            "vendor.created",
            "vendor.updated",
            "vendor.archived",
            "vendor.restored",
            "customer.created",
            "customer.updated",
            "customer.archived",
            "customer.restored",
            "invoice.created",
            "invoice.updated",
            "payment.updated",
            "payment.failed",
        ]

        for event_type in event_types:
            payload = {
                "idempotencyKey": f"test-{event_type}-{fields.Datetime.now().timestamp()}",
                "eventType": event_type,
                "entityId": "test_entity_id",
                "timestamp": fields.Datetime.now().isoformat(),
                "organizationId": self.billcom_config.organization_id,
            }
            signature = self._generate_signature(payload)

            with self.subTest(event_type=event_type):
                response = self.url_open(
                    self.webhook_url,
                    data=json.dumps(payload),
                    headers={
                        "Content-Type": "application/json",
                        "X-Bill-Signature": signature,
                    },
                )

                # All events should be accepted
                self.assertEqual(
                    response.status_code,
                    200,
                    f"Event {event_type} failed with status {response.status_code}",
                )

                # Verify webhook log created
                webhook_log = self.env["billcom.webhook.log"].search(
                    [("idempotency_key", "=", payload["idempotencyKey"])]
                )
                self.assertEqual(len(webhook_log), 1, f"No log for {event_type}")
                self.assertEqual(webhook_log.event_type, event_type)

    def test_webhook_payment_failed(self):
        """Test webhook handling for payment.failed event"""
        # Create a payment and related bill
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor_billcom.id,
                "amount": 100.0,
                "journal_id": self.bank_journal.id,
                "billcom_id": "payment_failed_001",
                "is_sync_to_billcom": True,
            }
        )

        self.vendor_bill.billcom_id = "bill_failed_001"
        if hasattr(self.vendor_bill, "payment_id"):
            self.vendor_bill.payment_id = payment

        payload = {
            "idempotencyKey": "payment-failed-test",
            "eventType": "payment.failed",
            "entityId": "payment_failed_001",
            "timestamp": fields.Datetime.now().isoformat(),
            "organizationId": self.billcom_config.organization_id,
            "data": {
                "transactionNumber": "TRANS_FAIL_1",
                "vendor": {"name": "Test Vendor"},
                "bills": [{"billId": "bill_failed_001"}],
                "errors": [{"message": "Insufficient funds", "code": "101"}],
            },
        }
        signature = self._generate_signature(payload)

        with patch.object(type(self.env["account.move"]), "search") as mock_search:
            mock_search.return_value = self.vendor_bill

            self.vendor_bill.action_post()
            payment.action_post()

            pass  # Placeholder for logic above

        with patch.object(
            type(self.env["account.move"]), "search", return_value=self.vendor_bill
        ):
            response = self.url_open(
                self.webhook_url,
                data=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Bill-Signature": signature,
                },
            )
            self.assertEqual(response.status_code, 200)
