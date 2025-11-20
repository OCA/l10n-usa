# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging
from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.billcom_integration.models.billcom_document import (
    parse_billcom_datetime,
)

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomDocument(BillcomTestCommon):
    """Tests for billcom.document model"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create test document
        cls.test_file_data = base64.b64encode(b"Test file content")
        cls.test_document = cls.env["billcom.document"].create(
            {
                "name": "test_document.pdf",
                "bill_id": cls.vendor_bill.id,
                "file_data": cls.test_file_data,
            }
        )

    # ===== Helper Function Tests =====

    def test_parse_billcom_datetime_with_milliseconds(self):
        """Should parse datetime with milliseconds"""

        date_string = "2025-10-03T06:11:24.000+00:00"
        result = parse_billcom_datetime(date_string)

        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 10)
        self.assertEqual(result.day, 3)

    def test_parse_billcom_datetime_with_timezone(self):
        """Should parse datetime with timezone"""
        date_string = "2025-10-03T06:11:24+00:00"
        result = parse_billcom_datetime(date_string)

        self.assertIsInstance(result, datetime)

    def test_parse_billcom_datetime_with_z(self):
        """Should parse datetime with Z timezone"""
        date_string = "2025-10-03T06:11:24Z"
        result = parse_billcom_datetime(date_string)

        self.assertIsInstance(result, datetime)

    def test_parse_billcom_datetime_invalid(self):
        """Should return None for invalid datetime"""
        result = parse_billcom_datetime("invalid_date")
        self.assertIsNone(result)

    def test_parse_billcom_datetime_none(self):
        """Should return None for None input"""
        result = parse_billcom_datetime(None)
        self.assertIsNone(result)

    # ===== File Size Validation Tests =====

    def test_check_file_size_valid(self):
        """Should accept files under 6 MB"""
        # 1 MB file
        small_file = base64.b64encode(b"x" * (1024 * 1024))
        doc = self.env["billcom.document"].create(
            {
                "name": "small.pdf",
                "bill_id": self.vendor_bill.id,
                "file_data": small_file,
            }
        )

        # Should not raise error
        self.assertTrue(doc)

    def test_check_file_size_too_large(self):
        """Should reject files over 6 MB"""
        # 7 MB file
        large_file = base64.b64encode(b"x" * (7 * 1024 * 1024))

        with self.assertRaises(UserError) as context:
            self.env["billcom.document"].create(
                {
                    "name": "large.pdf",
                    "bill_id": self.vendor_bill.id,
                    "file_data": large_file,
                }
            )

        self.assertIn("exceeds Bill.com limit", str(context.exception))

    # ===== Prepare Upload Data Tests =====

    def test_prepare_upload_data_success(self):
        """Should prepare file data for upload"""
        self.vendor_bill.billcom_id = "bill_123"
        result = self.test_document._prepare_upload_data()

        self.assertEqual(result, b"Test file content")

    def test_prepare_upload_data_no_file(self):
        """Should raise error if no file data"""
        doc = self.env["billcom.document"].create(
            {
                "name": "empty.pdf",
                "bill_id": self.vendor_bill.id,
            }
        )

        with self.assertRaises(UserError) as context:
            doc._prepare_upload_data()

        self.assertIn("No file content", str(context.exception))

    def test_prepare_upload_data_no_billcom_id(self):
        """Should raise error if bill not synced"""
        self.vendor_bill.billcom_id = False

        with self.assertRaises(UserError) as context:
            self.test_document._prepare_upload_data()

        self.assertIn("must be synced", str(context.exception))

    # ===== Upload to Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_upload_to_billcom_success_complete(self, mock_request):
        """Should upload document successfully (complete)"""
        self.vendor_bill.billcom_id = "bill_123"

        mock_request.return_value = {
            "id": "00hdocument123",
            "uploadId": "upload_456",
            "downloadLink": "https://bill.com/download/doc123",
            "createdTime": "2025-10-03T06:11:24.000+00:00",
        }

        result = self.test_document.button_upload_to_billcom()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(self.test_document.upload_status, "uploaded")
        self.assertEqual(self.test_document.billcom_id, "00hdocument123")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_upload_to_billcom_in_progress(self, mock_request):
        """Should handle upload in progress"""
        self.vendor_bill.billcom_id = "bill_123"

        mock_request.return_value = {
            "uploadId": "0duupload789",  # Upload ID, not document ID
        }

        result = self.test_document.button_upload_to_billcom()

        self.assertEqual(self.test_document.upload_status, "in_progress")
        self.assertEqual(self.test_document.billcom_upload_id, "0duupload789")
        self.assertIn("Upload In Progress", result["params"]["title"])

    def test_button_upload_to_billcom_no_billcom_id(self):
        """Should raise error if bill not synced"""
        self.vendor_bill.billcom_id = False

        with self.assertRaises(UserError) as context:
            self.test_document.button_upload_to_billcom()

        self.assertIn("must be synced", str(context.exception))

    # ===== Check Upload Status Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_check_upload_status_completed(self, mock_request):
        """Should check upload status and update when complete"""
        self.test_document.billcom_upload_id = "upload_123"

        # Mock status check response
        def mock_request_side_effect(endpoint, method="GET", params=None):
            if "upload-status" in endpoint:
                return [
                    {
                        "status": "UPLOADED",
                        "documentId": "00hdoc456",
                    }
                ]
            elif "documents/" in endpoint:
                return {
                    "id": "00hdoc456",
                    "downloadLink": "https://bill.com/download/doc456",
                    "createdTime": "2025-10-03T06:11:24.000+00:00",
                }
            return {}

        mock_request.side_effect = mock_request_side_effect

        result = self.test_document.button_check_upload_status()

        self.assertEqual(self.test_document.upload_status, "uploaded")
        self.assertEqual(self.test_document.billcom_id, "00hdoc456")
        self.assertIn("Upload Complete", result["params"]["title"])

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_button_check_upload_status_in_progress(self, mock_request):
        """Should show in progress status"""
        self.test_document.billcom_upload_id = "upload_123"

        mock_request.return_value = [
            {
                "status": "IN_PROGRESS",
            }
        ]

        result = self.test_document.button_check_upload_status()

        self.assertIn("Upload In Progress", result["params"]["title"])

    def test_button_check_upload_status_no_upload_id(self):
        """Should raise error if no upload ID"""
        self.test_document.billcom_upload_id = False

        with self.assertRaises(UserError) as context:
            self.test_document.button_check_upload_status()

        self.assertIn("No upload ID", str(context.exception))

    # ===== Download from Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._download_document"  # noqa B950
    )
    def test_button_download_from_billcom_success(self, mock_download):
        """Should download document successfully"""
        self.test_document.download_link = "https://bill.com/download/doc123"

        mock_download.return_value = b"Downloaded content"

        result = self.test_document.button_download_from_billcom()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(
            base64.b64decode(self.test_document.file_data), b"Downloaded content"
        )
        self.assertTrue(self.test_document.attachment_id)

    def test_button_download_from_billcom_no_link(self):
        """Should raise error if no download link"""
        self.test_document.download_link = False

        with self.assertRaises(UserError) as context:
            self.test_document.button_download_from_billcom()

        self.assertIn("No download link", str(context.exception))

    # ===== Create from Attachment Tests =====

    def test_create_from_attachment_success(self):
        """Should create document from attachment"""
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test_attach.pdf",
                "datas": self.test_file_data,
                "res_model": "account.move",
                "res_id": self.vendor_bill.id,
            }
        )

        doc = self.env["billcom.document"].create_from_attachment(attachment)

        self.assertEqual(doc.name, "test_attach.pdf")
        self.assertEqual(doc.bill_id, self.vendor_bill)
        self.assertEqual(doc.attachment_id, attachment)

    def test_create_from_attachment_duplicate(self):
        """Should return existing document if already exists"""
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test_attach.pdf",
                "datas": self.test_file_data,
                "res_model": "account.move",
                "res_id": self.vendor_bill.id,
            }
        )

        # Create first document
        doc1 = self.env["billcom.document"].create_from_attachment(attachment)

        # Try to create again
        doc2 = self.env["billcom.document"].create_from_attachment(attachment)

        self.assertEqual(doc1, doc2)

    def test_create_from_attachment_wrong_model(self):
        """Should raise error if attachment not for account.move"""
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.pdf",
                "datas": self.test_file_data,
                "res_model": "res.partner",
                "res_id": self.vendor_billcom.id,
            }
        )

        with self.assertRaises(UserError) as context:
            self.env["billcom.document"].create_from_attachment(attachment)

        self.assertIn("must be linked to a vendor bill", str(context.exception))

    # ===== Sync Documents from Bill.com Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._download_document"  # noqa B950
    )
    def test_sync_documents_from_billcom_success(self, mock_download, mock_request):
        """Should sync documents from Bill.com"""
        self.vendor_bill.billcom_id = "bill_123"

        mock_request.return_value = [
            {
                "id": "00hdoc1",
                "name": "invoice.pdf",
                "downloadLink": "https://bill.com/download/doc1",
                "createdTime": "2025-10-03T06:11:24.000+00:00",
            },
            {
                "id": "00hdoc2",
                "name": "receipt.pdf",
                "downloadLink": "https://bill.com/download/doc2",
                "createdTime": "2025-10-03T07:11:24.000+00:00",
            },
        ]

        mock_download.return_value = b"File content"

        count = self.env["billcom.document"].sync_documents_from_billcom(
            self.vendor_bill
        )

        self.assertEqual(count, 2)

        # Verify documents were created
        docs = self.env["billcom.document"].search(
            [("bill_id", "=", self.vendor_bill.id)]
        )
        self.assertGreaterEqual(len(docs), 2)

    def test_sync_documents_from_billcom_no_billcom_id(self):
        """Should return 0 if bill not synced"""
        self.vendor_bill.billcom_id = False

        count = self.env["billcom.document"].sync_documents_from_billcom(
            self.vendor_bill
        )

        self.assertEqual(count, 0)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    def test_sync_documents_from_billcom_no_documents(self, mock_request):
        """Should handle no documents returned"""
        self.vendor_bill.billcom_id = "bill_123"

        mock_request.return_value = []

        count = self.env["billcom.document"].sync_documents_from_billcom(
            self.vendor_bill
        )

        self.assertEqual(count, 0)

    # ===== Create/Update Attachment Tests =====

    def test_create_or_update_attachment_create_new(self):
        """Should create new attachment"""
        doc = self.env["billcom.document"].create(
            {
                "name": "new_doc.pdf",
                "bill_id": self.vendor_bill.id,
                "file_data": self.test_file_data,
            }
        )

        doc._create_or_update_attachment(self.test_file_data)

        self.assertTrue(doc.attachment_id)
        self.assertEqual(doc.attachment_id.name, "new_doc.pdf")
        self.assertEqual(doc.attachment_id.res_model, "account.move")
        self.assertEqual(doc.attachment_id.res_id, self.vendor_bill.id)

    def test_create_or_update_attachment_update_existing(self):
        """Should update existing attachment"""
        # Create attachment first
        attachment = self.env["ir.attachment"].create(
            {
                "name": "old_name.pdf",
                "datas": self.test_file_data,
                "res_model": "account.move",
                "res_id": self.vendor_bill.id,
            }
        )

        doc = self.env["billcom.document"].create(
            {
                "name": "updated_doc.pdf",
                "bill_id": self.vendor_bill.id,
                "file_data": self.test_file_data,
                "attachment_id": attachment.id,
            }
        )

        new_data = base64.b64encode(b"Updated content")
        doc._create_or_update_attachment(new_data)

        # Should update existing, not create new
        self.assertEqual(doc.attachment_id, attachment)
        self.assertEqual(doc.attachment_id.name, "updated_doc.pdf")
