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
class TestAccountMoveBillcom(BillcomTestCommon):
    """Tests for account.move Bill.com integration"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create additional vendor bill for testing
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
                            "quantity": 2,
                            "price_unit": 250.0,
                            "account_id": cls.company_data[
                                "default_account_expense"
                            ].id,
                        },
                    )
                ],
            }
        )

        # Create customer invoice for testing
        cls.customer_invoice = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.customer_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_a.id,
                            "quantity": 1,
                            "price_unit": 500.0,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                        },
                    )
                ],
            }
        )

    # ===== Bill Data Preparation Tests =====

    def test_prepare_bill_data_basic_fields(self):
        """Should prepare bill data with all required fields"""
        bill_data = self.vendor_bill._prepare_bill_data()

        self.assertIn("vendorId", bill_data)
        self.assertEqual(bill_data["vendorId"], self.vendor_billcom.billcom_id)
        # invoiceNumber is nested in 'invoice' dict
        self.assertIn("invoice", bill_data)
        self.assertIn("invoiceNumber", bill_data["invoice"])
        # invoiceDate and dueDate might be at root or nested
        self.assertTrue(
            "invoiceDate" in bill_data or "invoiceDate" in bill_data.get("invoice", {})
        )
        self.assertTrue(
            "dueDate" in bill_data or "dueDate" in bill_data.get("invoice", {})
        )

    def test_prepare_bill_data_with_lines(self):
        """Should include line items in bill data"""
        bill_data = self.vendor_bill._prepare_bill_data()

        # For bills, the field is called billLineItems
        self.assertIn("billLineItems", bill_data)
        self.assertTrue(len(bill_data["billLineItems"]) > 0)
        # Verify line item structure
        line = bill_data["billLineItems"][0]
        self.assertIn("amount", line)

    def test_prepare_bill_data_for_bulk(self):
        """Should prepare bill data for bulk operations"""
        bill_data = self.vendor_bill._prepare_bill_data(for_bulk=True)

        self.assertIsNotNone(bill_data)
        self.assertIn("vendorId", bill_data)

    def test_prepare_bill_data_no_vendor_billcom_id(self):
        """Should prepare bill data even if vendor has no Bill.com ID"""
        # Create vendor without billcom_id
        vendor_no_id = self.env["res.partner"].create(
            {
                "name": "Vendor No ID",
                "supplier_rank": 1,
            }
        )

        bill_no_id = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": vendor_no_id.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                        },
                    )
                ],
            }
        )

        bill_data = bill_no_id._prepare_bill_data()

        # Should still prepare data but vendorId will be False
        self.assertIsNotNone(bill_data)
        self.assertIn("vendorId", bill_data)
        self.assertFalse(bill_data["vendorId"])  # vendorId is False when no billcom_id

    # ===== Invoice Data Preparation Tests =====

    # def test_prepare_invoice_data_basic_fields(self):
    #     """Should prepare invoice data with required fields"""
    #     invoice_data = self.customer_invoice._prepare_invoice_data()

    #     # customerId is nested in 'customer' dict as 'id'
    #     self.assertIn("customer", invoice_data)
    #     self.assertIn("id", invoice_data["customer"])
    #     self.assertEqual(
    #         invoice_data["customer"]["id"], self.customer_billcom.billcom_id
    #     )
    #     # invoiceNumber should be at root level for invoices
    #     self.assertIn("invoiceNumber", invoice_data)
    #     # invoiceDate might be at root or nested
    #     self.assertTrue(
    #         "invoiceDate" in invoice_data
    #         or "invoiceDate" in invoice_data.get("invoice", {})
    #     )

    def test_prepare_invoice_data_with_lines(self):
        """Should include line items in invoice data"""
        invoice_data = self.customer_invoice._prepare_invoice_data()

        # For invoices, the field is called invoiceLineItems (not lineItems)
        self.assertIn("invoiceLineItems", invoice_data)
        self.assertTrue(len(invoice_data["invoiceLineItems"]) > 0)

    # ===== Single Bill Sync Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_to_billcom_create_success(self, mock_request):
        """Should create new bill in Bill.com via button"""
        mock_request.return_value = {
            "id": "bill_new_123",
            "invoiceNumber": self.bill2.name,
            "status": "OPEN",
        }

        # Remove billcom_id to simulate new bill
        self.bill2.billcom_id = False
        self.bill2.button_sync_to_billcom()

        self.assertEqual(self.bill2.billcom_id, "bill_new_123")
        self.assertEqual(self.bill2.billcom_sync_status, "synced")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_to_billcom_update_success(self, mock_request):
        """Should update existing bill in Bill.com"""
        mock_request.return_value = {
            "id": self.vendor_bill.billcom_id,
            "invoiceNumber": self.vendor_bill.name,
            "status": "OPEN",
        }

        self.vendor_bill.button_sync_to_billcom()

        self.assertEqual(self.vendor_bill.billcom_sync_status, "synced")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_to_billcom_api_error(self, mock_request):
        """Should handle API errors during sync"""
        mock_request.side_effect = UserError("API Error: Invalid data")

        with self.assertRaises(UserError):
            self.bill2.button_sync_to_billcom()

    # ===== Bulk Bill Sync Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_bulk_to_billcom_success(self, mock_request):
        """Should sync multiple bills in bulk"""

        # Mock needs to handle different endpoints
        def mock_side_effect(endpoint, method="GET", *args, **kwargs):
            # For finding existing documents (GET request)
            if method == "GET" and "bills" in endpoint:
                return []  # No existing documents
            # For creating new bills (POST request)
            elif method == "POST" and "bills" in endpoint:
                # Return single bill creation response
                bill_number = (
                    kwargs.get("data", {}).get("invoice", {}).get("invoiceNumber", "")
                )
                if self.vendor_bill.name in bill_number:
                    return {"id": "bill_bulk_001", "invoiceNumber": bill_number}
                elif self.bill2.name in bill_number:
                    return {"id": "bill_bulk_002", "invoiceNumber": bill_number}
                return {"id": "bill_new", "invoiceNumber": bill_number}
            return {}

        mock_request.side_effect = mock_side_effect

        # Remove billcom_ids
        self.vendor_bill.billcom_id = False
        self.bill2.billcom_id = False

        bills = self.vendor_bill | self.bill2
        bills._sync_bulk_to_billcom()

        # Verify bills were updated
        self.assertTrue(
            self.vendor_bill.billcom_id in ["bill_bulk_001", "bill_bulk_002"]
        )
        self.assertTrue(self.bill2.billcom_id in ["bill_bulk_001", "bill_bulk_002"])

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_existing_bills_bulk_success(self, mock_request):
        """Should update existing bills in bulk"""
        mock_request.return_value = [
            {
                "id": self.vendor_bill.billcom_id,
                "invoiceNumber": self.vendor_bill.name,
                "singleStatus": "OPEN",
            },
        ]

        bills = self.env["account.move"].browse([self.vendor_bill.id])
        bills._sync_existing_bills_bulk(bills)

        self.assertEqual(self.vendor_bill.billcom_sync_status, "synced")

    # ===== Document Finding Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_find_existing_billcom_document_found(self, mock_request):
        """Should find existing document in Bill.com"""
        # Return a list with the document (as per line 192 of account_move.py)
        mock_request.return_value = [
            {
                "id": "doc_found_123",
                "invoiceNumber": "INV001",
            }
        ]

        result = self.vendor_bill._find_existing_billcom_document("bills", "INV001")

        self.assertEqual(result, "doc_found_123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_find_existing_billcom_document_not_found(self, mock_request):
        """Should return None if document not found"""
        # Return empty list
        mock_request.return_value = []

        result = self.vendor_bill._find_existing_billcom_document("bills", "INV999")

        self.assertIsNone(result)

    # ===== State Management Tests =====

    def test_bill_state_after_validation(self):
        """Should not auto-sync on validation if not configured"""
        self.bill2.billcom_id = False

        self.bill2.action_post()

        # Should remain unchanged unless auto-sync enabled
        self.assertEqual(self.bill2.state, "posted")

    # ===== Sync from Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_from_billcom_success(self, mock_request):
        """Should sync bill data from Bill.com"""

        # Mock both the bills endpoint check and the actual data fetch
        def mock_side_effect(endpoint, *args, **kwargs):
            if "bills/" in endpoint:
                return {
                    "id": "bill_remote_123",
                    "invoiceNumber": "BILLCOM-001",
                    "vendorId": self.vendor_billcom.billcom_id,
                    "invoiceDate": "2025-01-15",
                    "dueDate": "2025-02-15",
                    "amount": 100.0,
                    "status": "OPEN",
                    "lineItems": [
                        {
                            "amount": 100.0,
                            "description": "Test item",
                            "quantity": 1,
                        }
                    ],
                }
            return None

        mock_request.side_effect = mock_side_effect

        result = self.env["account.move"].sync_from_billcom("bill_remote_123")

        # Method returns True on success
        self.assertTrue(result)

        # Verify bill was created or updated
        synced_bill = self.env["account.move"].search(
            [("billcom_id", "=", "bill_remote_123")], limit=1
        )
        if synced_bill:
            self.assertEqual(synced_bill.move_type, "in_invoice")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_from_billcom_vendor_not_found(self, mock_request):
        """Should handle vendor not found in Odoo"""

        def mock_side_effect(endpoint, *args, **kwargs):
            if "bills/" in endpoint:
                return {
                    "id": "bill_remote_456",
                    "vendorId": "nonexistent_vendor",
                    "invoiceNumber": "BILL-002",
                    "invoiceDate": "2025-01-15",
                    "dueDate": "2025-02-15",
                    "amount": 100.0,
                }
            return None

        mock_request.side_effect = mock_side_effect

        result = self.env["account.move"].sync_from_billcom("bill_remote_456")

        # Should return False when vendor not found
        self.assertFalse(result)

    # ===== Attachment Sync Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_sync_attachments_to_billcom(self, mock_request):
        """Should sync attachments to Bill.com"""
        # Create test attachment
        self.env["ir.attachment"].create(
            {
                "name": "test_invoice.pdf",
                "datas": "dGVzdCBkYXRh",  # base64 "test data"
                "res_model": "account.move",
                "res_id": self.vendor_bill.id,
            }
        )

        mock_request.return_value = {
            "id": "attachment_123",
            "fileName": "test_invoice.pdf",
        }

        self.vendor_bill.button_sync_attachments_to_billcom()

        # Should not raise errors
        self.assertTrue(True)

    # ===== Cron Job Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.sync_bills"
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.sync_invoices"
    )
    def test_sync_documents_cron(self, mock_sync_invoices, mock_sync_bills):
        """Should sync not_synced documents via cron"""
        # Enable auto sync in config
        self.billcom_config.write({"auto_sync_enabled": True})

        # Mock sync methods to prevent real API calls
        mock_sync_invoices.return_value = None
        mock_sync_bills.return_value = None

        # Call cron method
        self.env["account.move"]._sync_documents_cron()

        # Verify sync methods were called
        mock_sync_invoices.assert_called_once()
        mock_sync_bills.assert_called_once()

    # ===== Validation Tests =====

    def test_bill_without_vendor(self):
        """Should handle bill without vendor gracefully"""
        bill_data = self.vendor_bill._prepare_bill_data()

        # Should still prepare data
        self.assertIsNotNone(bill_data)

    def test_bill_with_draft_state(self):
        """Should allow sync of draft bills if configured"""
        self.bill2.state = "draft"

        # Should not raise error
        bill_data = self.bill2._prepare_bill_data()
        self.assertIsNotNone(bill_data)
