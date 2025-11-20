# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomSyncQueue(BillcomTestCommon):
    """Tests for billcom.sync.queue model"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        # Create test vendor bill
        cls.vendor_bill = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.vendor_billcom.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test Product",
                            "quantity": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )

    # ===== Display Name Tests =====

    def test_compute_display_name_with_all_fields(self):
        """Should compute display name with all fields"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "operation": "create",
                "record_name": "Test Vendor",
                "billcom_id": "00v123456",
            }
        )

        self.assertIn("Vendor", queue_item.display_name)
        self.assertIn("Create", queue_item.display_name)
        self.assertIn("Test Vendor", queue_item.display_name)

    def test_compute_display_name_with_billcom_id_only(self):
        """Should compute display name with billcom_id when no record_name"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "bill",
                "operation": "sync",
                "billcom_id": "00b987654",
            }
        )

        self.assertIn("Bill", queue_item.display_name)
        self.assertIn("00b987654", queue_item.display_name)

    # ===== Create Sync Item Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_logger.BillcomLogger.log_operation"
    )
    def test_create_sync_item_basic(self, mock_log):
        """Should create basic sync item"""
        mock_log.return_value = MagicMock()

        queue_item = self.env["billcom.sync.queue"].create_sync_item(
            sync_type="vendor",
            record_model="res.partner",
            record_id=self.vendor_billcom.id,
            direction="odoo_to_billcom",
            operation="create",
        )

        self.assertEqual(queue_item.sync_type, "vendor")
        self.assertEqual(queue_item.state, "queued")
        self.assertEqual(queue_item.record_model, "res.partner")
        self.assertEqual(queue_item.record_id, self.vendor_billcom.id)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_logger.BillcomLogger.log_operation"
    )
    def test_create_sync_item_with_sync_data(self, mock_log):
        """Should create sync item with JSON data"""
        mock_log.return_value = MagicMock()

        sync_data = {"name": "Test Vendor", "email": "test@example.com"}

        queue_item = self.env["billcom.sync.queue"].create_sync_item(
            sync_type="vendor",
            sync_data=sync_data,
        )

        stored_data = json.loads(queue_item.sync_data)
        self.assertEqual(stored_data["name"], "Test Vendor")
        self.assertEqual(stored_data["email"], "test@example.com")

    @patch(
        "odoo.addons.billcom_integration.models.billcom_logger.BillcomLogger.log_operation"
    )
    def test_create_sync_item_duplicate_detection(self, mock_log):
        """Should detect and return existing duplicate sync item"""
        mock_log.return_value = MagicMock()

        # Create first item
        item1 = self.env["billcom.sync.queue"].create_sync_item(
            sync_type="vendor",
            record_model="res.partner",
            record_id=self.vendor_billcom.id,
            operation="sync",
        )

        # Try to create duplicate
        item2 = self.env["billcom.sync.queue"].create_sync_item(
            sync_type="vendor",
            record_model="res.partner",
            record_id=self.vendor_billcom.id,
            operation="sync",
        )

        # Should return same item
        self.assertEqual(item1, item2)

    # ===== Find Duplicate Tests =====

    def test_find_duplicate_by_record(self):
        """Should find duplicate by record model and id"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "operation": "sync",
                "state": "queued",
                "record_model": "res.partner",
                "record_id": self.vendor_billcom.id,
            }
        )

        values = {
            "sync_type": "vendor",
            "operation": "sync",
            "record_model": "res.partner",
            "record_id": self.vendor_billcom.id,
        }

        duplicate = queue_item._find_duplicate(values)
        self.assertEqual(duplicate, queue_item)

    def test_find_duplicate_by_billcom_id(self):
        """Should find duplicate by billcom_id"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "bill",
                "operation": "sync",
                "state": "queued",
                "billcom_id": "00b123456",
            }
        )

        values = {
            "sync_type": "bill",
            "operation": "sync",
            "billcom_id": "00b123456",
        }

        duplicate = queue_item._find_duplicate(values)
        self.assertEqual(duplicate, queue_item)

    def test_find_duplicate_no_match(self):
        """Should return empty recordset when no duplicate"""
        values = {
            "sync_type": "vendor",
            "operation": "sync",
            "record_model": "res.partner",
            "record_id": 999999,
        }

        queue_item = self.env["billcom.sync.queue"]
        duplicate = queue_item._find_duplicate(values)
        self.assertFalse(duplicate)

    # ===== Action Process Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_sync_queue.BillcomSyncQueue._execute_sync"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_logger.BillcomLogger.log_operation"  # noqa B950
    )
    def test_action_process_success(self, mock_log, mock_execute):
        """Should process sync item successfully"""
        mock_log.return_value = MagicMock(mark_success=MagicMock())
        mock_execute.return_value = {"status": "success"}

        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "queued",
            }
        )

        result = queue_item.action_process()

        self.assertEqual(queue_item.state, "success")
        self.assertTrue(queue_item.completed_date)
        self.assertEqual(result, {"status": "success"})

    def test_action_process_wrong_state(self):
        """Should raise error if not in queued state"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "success",
            }
        )

        with self.assertRaises(UserError):
            queue_item.action_process()

    # ===== Sync Direction Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.res_partner.ResPartner.sync_to_billcom"
    )
    def test_sync_odoo_to_billcom_vendor(self, mock_sync):
        """Should sync vendor from Odoo to Bill.com"""
        mock_sync.return_value = {"id": "00v123"}

        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "direction": "odoo_to_billcom",
                "record_model": "res.partner",
                "record_id": self.vendor_billcom.id,
                "state": "processing",
            }
        )

        result = queue_item._sync_odoo_to_billcom()

        self.assertEqual(result, {"id": "00v123"})
        mock_sync.assert_called_once_with("vendor")

    @patch(
        "odoo.addons.billcom_integration.models.account_move.AccountMove.button_sync_to_billcom"
    )
    def test_sync_odoo_to_billcom_bill(self, mock_sync):
        """Should sync bill from Odoo to Bill.com"""
        mock_sync.return_value = {"id": "00b456"}

        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "bill",
                "direction": "odoo_to_billcom",
                "record_model": "account.move",
                "record_id": self.vendor_bill.id,
                "state": "processing",
            }
        )

        result = queue_item._sync_odoo_to_billcom()

        self.assertEqual(result, {"id": "00b456"})
        mock_sync.assert_called_once()

    def test_sync_odoo_to_billcom_missing_record(self):
        """Should raise error if record not found"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "direction": "odoo_to_billcom",
                "record_model": "res.partner",
                "record_id": 999999,
                "state": "processing",
            }
        )

        with self.assertRaises(UserError) as context:
            queue_item._sync_odoo_to_billcom()

        self.assertIn("not found", str(context.exception))

    @patch(
        "odoo.addons.billcom_integration.models.billcom_service_abstract.BillcomServiceAbstract._make_request"  # noqa B950
    )
    @patch(
        "odoo.addons.billcom_integration.models.billcom_service.BillcomService.process_queue_item_from_billcom"  # noqa B950
    )
    def test_sync_billcom_to_odoo_with_data(self, mock_process, mock_request):
        """Should sync from Bill.com to Odoo with existing data"""
        mock_process.return_value = {"status": "synced"}

        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "direction": "billcom_to_odoo",
                "billcom_id": "00v123",
                "sync_data": '{"name": "Test Vendor"}',
                "state": "processing",
            }
        )

        result = queue_item._sync_billcom_to_odoo()

        self.assertEqual(result, {"status": "synced"})
        mock_process.assert_called_once()
        mock_request.assert_not_called()  # Should not fetch if data exists

    # ===== Schedule Retry Tests =====

    def test_schedule_retry_exponential_backoff(self):
        """Should use exponential backoff for retry scheduling"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "queued",
                "retry_count": 0,
            }
        )

        queue_item._schedule_retry("Test error")

        # After 1 retry, should wait 2^1 = 2 minutes
        self.assertEqual(queue_item.retry_count, 1)
        self.assertTrue(queue_item.next_retry_date)
        self.assertEqual(queue_item.state, "queued")

        # Calculate expected delay (2^1 = 2 minutes)
        expected_delay = timedelta(minutes=2)
        actual_delay = queue_item.next_retry_date - fields.Datetime.now()

        # Allow 1 minute tolerance
        self.assertLess(abs((actual_delay - expected_delay).total_seconds()), 60)

    # ===== Action Retry Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_sync_queue.BillcomSyncQueue.action_process"  # noqa B950
    )
    def test_action_retry_success(self, mock_process):
        """Should retry failed sync item"""
        mock_process.return_value = {"status": "success"}

        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "error",
                "error_message": "Previous error",
            }
        )

        queue_item.action_retry()

        self.assertEqual(queue_item.state, "queued")
        self.assertFalse(queue_item.error_message)
        mock_process.assert_called_once()

    def test_action_retry_wrong_state(self):
        """Should raise error if not in error or queued state"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "processing",
            }
        )

        with self.assertRaises(UserError):
            queue_item.action_retry()

    # ===== Action Cancel Tests =====

    def test_action_cancel_success(self):
        """Should cancel queued sync item"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "queued",
            }
        )

        queue_item.action_cancel()

        self.assertEqual(queue_item.state, "cancelled")
        self.assertTrue(queue_item.completed_date)

    def test_action_cancel_processing(self):
        """Should raise error when canceling processing item"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "processing",
            }
        )

        with self.assertRaises(UserError):
            queue_item.action_cancel()

    # ===== Process Queue Tests =====

    @patch(
        "odoo.addons.billcom_integration.models.billcom_sync_queue.BillcomSyncQueue.action_process"  # noqa B950
    )
    def test_process_queue_batch(self, mock_process):
        """Should process multiple queued items"""
        mock_process.return_value = {"status": "success"}

        # Create 3 queued items
        for i in range(3):
            self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "vendor",
                    "state": "queued",
                    "priority": str(i),
                }
            )

        result = self.env["billcom.sync.queue"].process_queue(limit=5)

        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["errors"], 0)

    @patch(
        "odoo.addons.billcom_integration.models.billcom_sync_queue.BillcomSyncQueue.action_process"  # noqa B950
    )
    def test_process_queue_with_errors(self, mock_process):
        """Should handle errors during batch processing"""
        mock_process.side_effect = Exception("API Error")

        # Create 2 queued items
        for _ in range(2):
            self.env["billcom.sync.queue"].create(
                {
                    "sync_type": "vendor",
                    "state": "queued",
                }
            )

        result = self.env["billcom.sync.queue"].process_queue(limit=5)

        self.assertEqual(result["errors"], 2)

    # ===== Cleanup Tests =====

    def test_cleanup_completed_items(self):
        """Should cleanup old completed items"""
        # Create old completed item
        old_date = fields.Datetime.now() - timedelta(days=10)
        old_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "success",
                "completed_date": old_date,
            }
        )

        # Create recent completed item
        recent_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "state": "success",
                "completed_date": fields.Datetime.now(),
            }
        )

        count = self.env["billcom.sync.queue"].cleanup_completed_items(days=7)

        self.assertEqual(count, 1)
        self.assertFalse(old_item.exists())
        self.assertTrue(recent_item.exists())

    # ===== Action View Tests =====

    def test_action_view_logs(self):
        """Should return action to view logs"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
            }
        )

        action = queue_item.action_view_logs()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "billcom.logger")
        self.assertIn(("sync_queue_id", "=", queue_item.id), action["domain"])

    def test_action_view_record(self):
        """Should return action to view synced record"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
                "record_model": "res.partner",
                "record_id": self.vendor_billcom.id,
                "record_name": "Test Vendor",
            }
        )

        action = queue_item.action_view_record()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], self.vendor_billcom.id)

    def test_action_view_record_no_record(self):
        """Should raise error if no associated record"""
        queue_item = self.env["billcom.sync.queue"].create(
            {
                "sync_type": "vendor",
            }
        )

        with self.assertRaises(UserError):
            queue_item.action_view_record()
