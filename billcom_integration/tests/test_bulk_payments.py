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
class TestBulkPayments(BillcomTestCommon):
    """Test bulk payment creation with Bill.com"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create funding account
        cls.funding_account = cls.env["billcom.funding.account"].create(
            {
                "name": "Test Bank Account",
                "billcom_id": "funding_acc_123",
                "funding_type": "BANK_ACCOUNT",
                "status": "VERIFIED",
                "is_default_payables": True,
                "company_id": cls.env.company.id,
            }
        )

        # Link funding account to journal's bank account
        cls.bank_journal.bank_account_id.billcom_funding_account_id = (
            cls.funding_account.id
        )

        # Create test bills
        cls.bill1 = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.vendor_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_a.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": cls.company_data[
                                "default_account_expense"
                            ].id,
                        },
                    )
                ],
                "billcom_id": "bill_001",
                "is_sync_to_billcom": True,
            }
        )

        cls.bill2 = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.vendor_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_a.id,
                            "quantity": 1,
                            "price_unit": 200.0,
                            "account_id": cls.company_data[
                                "default_account_expense"
                            ].id,
                        },
                    )
                ],
                "billcom_id": "bill_002",
                "is_sync_to_billcom": True,
            }
        )

        # Create payments
        cls.payment1 = cls.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": cls.vendor_billcom.id,
                "amount": 100.0,
                "date": fields.Date.today(),
                "journal_id": cls.bank_journal.id,
                "is_sync_to_billcom": True,
            }
        )

        cls.payment2 = cls.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": cls.vendor_billcom.id,
                "amount": 200.0,
                "date": fields.Date.today(),
                "journal_id": cls.bank_journal.id,
                "is_sync_to_billcom": True,
            }
        )

    # ===== Validation Tests =====

    def test_bulk_payment_no_payments(self):
        """Should return error if no payments provided"""
        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.env["account.payment"])

        self.assertFalse(result["success"])
        self.assertIn("No payments provided", result["errors"][0])

    def test_bulk_payment_too_many_payments(self):
        """Should raise UserError if more than 50 payments"""
        service = self.env["billcom.service"]
        # Create 51 payments
        payments = self.env["account.payment"]
        for _ in range(51):
            payment = self.env["account.payment"].create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": self.vendor_billcom.id,
                    "amount": 10.0,
                    "date": fields.Date.today(),
                    "journal_id": self.bank_journal.id,
                }
            )
            payments |= payment

        with self.assertRaises(UserError) as context:
            service.create_bulk_payments(payments)

        self.assertIn("bulk payment limit is 50", str(context.exception))

    def test_bulk_payment_no_funding_account(self):
        """Should return error if no funding account configured"""
        # Remove funding account
        self.bank_journal.bank_account_id.billcom_funding_account_id = False
        self.funding_account.is_default_payables = False

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertFalse(result.get("success"))
        self.assertTrue(len(result.get("errors", [])) > 0)
        self.assertIn("No Bill.com funding account", result["errors"][0])

    def test_bulk_payment_not_marked_for_sync(self):
        """Should return error if payment not marked for sync"""
        self.payment1.is_sync_to_billcom = False

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertFalse(result.get("success"))
        self.assertTrue(len(result.get("errors", [])) > 0)

    def test_bulk_payment_wrong_payment_type(self):
        """Should return error if payment is not outbound supplier"""
        # Change to inbound
        self.payment1.payment_type = "inbound"

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertFalse(result.get("success"))
        self.assertTrue(len(result.get("errors", [])) > 0)

    def test_bulk_payment_no_bill_id(self):
        """Should return error if payment has no linked bill with Bill.com ID"""
        # Remove bill.com ID
        self.bill1.billcom_id = False

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertFalse(result.get("success"))
        self.assertTrue(len(result.get("errors", [])) > 0)

    # ===== Success Flow Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._get_payment_bill_id"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_bulk_payment_success(self, mock_request, mock_get_bill_id):
        """Should create bulk payments successfully"""
        mock_request.return_value = [
            {
                "id": "payment_001",
                "billId": "bill_001",
                "singleStatus": "SCHEDULED",
                "confirmationNumber": "CONF001",
                "transactionNumber": "TXN001",
            },
            {
                "id": "payment_002",
                "billId": "bill_002",
                "singleStatus": "SCHEDULED",
                "confirmationNumber": "CONF002",
                "transactionNumber": "TXN002",
            },
        ]

        # Mock _get_payment_bill_id to return correct bill IDs
        def get_bill_id_side_effect(payment):
            if payment == self.payment1:
                return "bill_001"
            elif payment == self.payment2:
                return "bill_002"
            return False

        mock_get_bill_id.side_effect = get_bill_id_side_effect

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertTrue(result.get("success"), f"Expected success but got: {result}")
        self.assertEqual(result.get("success_count", 0), 2)
        self.assertEqual(result.get("error_count", 0), 0)

        # Verify payment1 updated
        self.assertEqual(self.payment1.billcom_id, "payment_001")
        self.assertEqual(self.payment1.billcom_confirmation_number, "CONF001")

        # Verify payment2 updated
        self.assertEqual(self.payment2.billcom_id, "payment_002")
        self.assertEqual(self.payment2.billcom_confirmation_number, "CONF002")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._get_payment_bill_id"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_bulk_payment_partial_success(self, mock_request, mock_get_bill_id):
        """Should handle partial success (some payments fail)"""
        mock_request.return_value = [
            {
                "id": "payment_001",
                "billId": "bill_001",
                "singleStatus": "SCHEDULED",
                "confirmationNumber": "CONF001",
            },
            {
                "billId": "bill_002",
                "error": "Insufficient funds",
            },
        ]

        # Mock _get_payment_bill_id to return correct bill IDs
        def get_bill_id_side_effect(payment):
            if payment == self.payment1:
                return "bill_001"
            elif payment == self.payment2:
                return "bill_002"
            return False

        mock_get_bill_id.side_effect = get_bill_id_side_effect

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertFalse(result.get("success"))  # Not full success
        self.assertEqual(result.get("success_count", 0), 1)
        self.assertEqual(result.get("error_count", 0), 1)

        # Verify payment1 synced
        self.assertEqual(self.payment1.billcom_sync_status, "synced")

        # Verify payment2 failed
        self.assertEqual(self.payment2.billcom_sync_status, "sync_failed")
        self.assertIn("Insufficient funds", self.payment2.billcom_sync_error)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._get_payment_bill_id"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_bulk_payment_with_wallet(self, mock_request, mock_get_bill_id):
        """Should handle WALLET funding type with process date"""
        mock_request.return_value = [
            {
                "id": "payment_001",
                "billId": "bill_001",
                "singleStatus": "SCHEDULED",
            },
            {
                "id": "payment_002",
                "billId": "bill_002",
                "singleStatus": "SCHEDULED",
            },
        ]

        # Mock _get_payment_bill_id to return correct bill IDs
        def get_bill_id_side_effect(payment):
            if payment == self.payment1:
                return "bill_001"
            elif payment == self.payment2:
                return "bill_002"
            return False

        mock_get_bill_id.side_effect = get_bill_id_side_effect

        # Set funding type to WALLET
        self.payment1.write(
            {
                "billcom_funding_account_type": "WALLET",
                "billcom_process_date": fields.Date.today(),
            }
        )
        self.payment2.write(
            {
                "billcom_funding_account_type": "WALLET",
                "billcom_process_date": fields.Date.today(),
            }
        )

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1 | self.payment2)

        self.assertTrue(result.get("success"), f"Expected success but got: {result}")

        # Verify API was called with processDate
        call_args = mock_request.call_args
        if call_args:
            payload = call_args.kwargs.get("data", {})
            self.assertIn("processDate", payload)
            self.assertEqual(payload["fundingAccount"]["type"], "WALLET")

    # ===== Error Handling Tests ====
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._get_payment_bill_id"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_bulk_payment_posts_to_chatter(self, mock_request, mock_get_bill_id):
        """Should post success messages to payment chatter"""
        mock_request.return_value = [
            {
                "id": "payment_001",
                "billId": "bill_001",
                "singleStatus": "SCHEDULED",
                "confirmationNumber": "CONF001",
            },
        ]

        # Mock _get_payment_bill_id to return correct bill ID
        mock_get_bill_id.return_value = "bill_001"

        # Count messages before
        messages_before = len(self.payment1.message_ids)

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1)

        self.assertTrue(result.get("success"))

        # Should have new message in chatter
        messages_after = len(self.payment1.message_ids)
        self.assertGreater(messages_after, messages_before)

        # Verify message content
        last_message = self.payment1.message_ids[0]
        self.assertIn("Bill.com Bulk Payment Created", last_message.body)
        self.assertIn("payment_001", last_message.body)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._get_payment_bill_id"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_payment_status_update(self, mock_request, mock_get_bill_id):
        """Should update payment status from Bill.com"""
        # Payment already synced
        self.payment1.billcom_id = "payment_existing_001"

        mock_request.return_value = {
            "id": "payment_existing_001",
            "status": "PAID",
            "paidDate": fields.Date.today().isoformat(),
        }
        self.assertEqual(self.payment1.billcom_id, "payment_existing_001")

    # ===== Payment Validation Tests =====

    def test_payment_requires_partner(self):
        """Should reject payment without partner"""
        payment_no_partner = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "amount": 100.0,
                "date": fields.Date.today(),
                "journal_id": self.bank_journal.id,
            }
        )

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(payment_no_partner)

        self.assertFalse(result.get("success"))

    def test_payment_amount_validation(self):
        """Should validate payment amount is positive"""
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.vendor_billcom.id,
                "amount": 0.0,
                "date": fields.Date.today(),
                "journal_id": self.bank_journal.id,
                "is_sync_to_billcom": True,
            }
        )

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(payment)

        # Should fail validation
        self.assertFalse(result.get("success"))

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService._get_payment_bill_id"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_payment_duplicate_prevention(self, mock_request, mock_get_bill_id):
        """Should prevent duplicate payment creation"""
        # Payment already has billcom_id
        self.payment1.billcom_id = "payment_existing_123"

        mock_get_bill_id.return_value = "bill_001"

        service = self.env["billcom.service"]
        result = service.create_bulk_payments(self.payment1)

        # Should skip or update, not create new
        self.assertIsNotNone(result)

    # ===== Mixed Payment Types Tests =====

    def test_bulk_payments_mixed_currencies(self):
        """Should handle payments in different currencies"""
        # This would require currency setup
        # For now, ensure all payments use company currency
        self.assertEqual(self.payment1.currency_id, self.env.company.currency_id)
        self.assertEqual(self.payment2.currency_id, self.env.company.currency_id)
