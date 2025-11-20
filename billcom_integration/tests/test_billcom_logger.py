# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import BillcomTestCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "billcom")
class TestBillcomLogger(BillcomTestCommon):
    """Tests for billcom.logger model"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

    # ===== Compute Duration Tests =====

    def test_compute_duration_with_times(self):
        """Should compute duration from start and end times"""
        start = fields.Datetime.now()
        end = start + timedelta(seconds=10)

        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "success",
                "start_time": start,
                "end_time": end,
            }
        )

        self.assertEqual(log.duration, 10.0)

    def test_compute_duration_no_end_time(self):
        """Should return 0 if no end time"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "pending",
                "start_time": fields.Datetime.now(),
            }
        )

        self.assertEqual(log.duration, 0.0)

    # ===== Log Operation Tests =====

    def test_log_operation_basic(self):
        """Should create log entry with basic info"""
        log = self.env["billcom.logger"].log_operation(
            "sync_vendor", level="info", status="pending"
        )

        self.assertEqual(log.operation_type, "sync_vendor")
        self.assertEqual(log.level, "info")
        self.assertEqual(log.status, "pending")
        self.assertTrue(log.start_time)

    def test_log_operation_with_context(self):
        """Should create log with context information"""
        log = self.env["billcom.logger"].log_operation(
            "sync_vendor",
            record_model="res.partner",
            record_id=self.vendor_billcom.id,
            billcom_id="00v123",
        )

        self.assertEqual(log.record_model, "res.partner")
        self.assertEqual(log.record_id, self.vendor_billcom.id)
        self.assertEqual(log.billcom_id, "00v123")

    # ===== Log API Request Tests =====

    def test_log_api_request_get(self):
        """Should log GET API request"""
        log = self.env["billcom.logger"].log_api_request(
            "/vendors/00v123", method="GET"
        )

        self.assertEqual(log.operation_type, "api_request")
        self.assertEqual(log.endpoint, "/vendors/00v123")
        self.assertEqual(log.http_method, "GET")

    def test_log_api_request_post(self):
        """Should log POST API request with data"""
        log = self.env["billcom.logger"].log_api_request(
            "/vendors",
            method="POST",
            request_data='{"name": "Test Vendor"}',
            status="processing",
        )

        self.assertEqual(log.http_method, "POST")
        self.assertTrue(log.request_data)
        self.assertEqual(log.status, "processing")

    # ===== Log Sync Operation Tests =====

    def test_log_sync_operation_with_record(self):
        """Should log sync operation with record name"""
        log = self.env["billcom.logger"].log_sync_operation(
            "sync_vendor", record_model="res.partner", record_id=self.vendor_billcom.id
        )

        self.assertEqual(log.operation_type, "sync_vendor")
        self.assertEqual(log.record_model, "res.partner")
        self.assertEqual(log.record_id, self.vendor_billcom.id)
        self.assertTrue(log.record_name)

    def test_log_sync_operation_no_record(self):
        """Should log sync without record"""
        log = self.env["billcom.logger"].log_sync_operation("sync_vendor")

        self.assertEqual(log.operation_type, "sync_vendor")
        self.assertFalse(log.record_model)
        self.assertFalse(log.record_name)

    def test_log_sync_operation_invalid_record(self):
        """Should handle invalid record ID"""
        log = self.env["billcom.logger"].log_sync_operation(
            "sync_vendor", record_model="res.partner", record_id=999999
        )

        self.assertEqual(log.record_model, "res.partner")
        self.assertTrue(log.record_name)  # Should have fallback ID name

    # ===== Log Webhook Tests =====

    def test_log_webhook_basic(self):
        """Should log webhook event"""
        log = self.env["billcom.logger"].log_webhook(
            "vendor.updated", entity_id="00v123"
        )

        self.assertEqual(log.operation_type, "webhook")
        self.assertIn("Webhook", log.message)
        self.assertEqual(log.billcom_id, "00v123")

    def test_log_webhook_with_details(self):
        """Should log webhook with details"""
        log = self.env["billcom.logger"].log_webhook(
            "payment.sent",
            entity_id="00p456",
            response_data='{"status": "sent"}',
        )

        self.assertEqual(log.billcom_id, "00p456")
        self.assertTrue(log.response_data)

    # ===== Update Status Tests =====

    def test_update_status_success(self):
        """Should update status to success"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "pending",
                "start_time": fields.Datetime.now(),
            }
        )

        log.update_status("success", message="Sync completed")

        self.assertEqual(log.status, "success")
        self.assertEqual(log.message, "Sync completed")
        self.assertTrue(log.end_time)

    def test_update_status_error(self):
        """Should update status to error with traceback"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "processing",
                "start_time": fields.Datetime.now(),
            }
        )

        log.update_status("error", error_message="API Error")

        self.assertEqual(log.status, "error")
        self.assertEqual(log.error_message, "API Error")
        self.assertTrue(log.end_time)

    # ===== Mark Success Tests =====

    def test_mark_success_basic(self):
        """Should mark log as successful"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "processing",
                "start_time": fields.Datetime.now(),
            }
        )

        log.mark_success("Vendor synced successfully")

        self.assertEqual(log.status, "success")
        self.assertEqual(log.message, "Vendor synced successfully")

    def test_mark_success_with_response(self):
        """Should mark success with response data"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "api_request",
                "level": "info",
                "status": "processing",
                "start_time": fields.Datetime.now(),
            }
        )

        log.mark_success(response_data='{"id": "00v123"}', response_status_code=200)

        self.assertEqual(log.status, "success")
        self.assertEqual(log.response_status_code, 200)

    # ===== Mark Error Tests =====

    def test_mark_error_basic(self):
        """Should mark log as error"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "processing",
                "start_time": fields.Datetime.now(),
            }
        )

        log.mark_error("Connection timeout")

        self.assertEqual(log.status, "error")
        self.assertEqual(log.error_message, "Connection timeout")

    def test_mark_error_with_code(self):
        """Should mark error with response code"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "api_request",
                "level": "info",
                "status": "processing",
                "start_time": fields.Datetime.now(),
            }
        )

        log.mark_error("Unauthorized", response_status_code=401)

        self.assertEqual(log.status, "error")
        self.assertEqual(log.response_status_code, 401)

    # ===== Mark Retry Tests =====

    def test_mark_retry_basic(self):
        """Should mark log for retry"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "error",
                "retry_count": 0,
            }
        )

        log.mark_retry(retry_count=1)

        self.assertEqual(log.status, "retry")
        self.assertEqual(log.retry_count, 1)

    # ===== Cleanup Old Logs Tests =====

    def test_cleanup_old_logs_basic(self):
        """Should delete old log entries"""
        # Create old log
        old_date = fields.Datetime.now() - timedelta(days=40)
        old_log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "success",
                "start_time": old_date,
            }
        )
        # Force old create_date
        self.env.cr.execute(
            "UPDATE billcom_logger SET create_date = %s WHERE id = %s",
            (old_date, old_log.id),
        )

        # Create recent log
        recent_log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "level": "info",
                "status": "success",
            }
        )

        count = self.env["billcom.logger"].cleanup_old_logs(days=30)

        self.assertGreater(count, 0)
        self.assertFalse(old_log.exists())
        self.assertTrue(recent_log.exists())

    # ===== Action View Related Record Tests =====

    def test_action_view_related_record_success(self):
        """Should return action to view related record"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
                "record_model": "res.partner",
                "record_id": self.vendor_billcom.id,
            }
        )

        result = log.action_view_related_record()

        self.assertEqual(result["type"], "ir.actions.act_window")
        self.assertEqual(result["res_model"], "res.partner")
        self.assertEqual(result["res_id"], self.vendor_billcom.id)

    def test_action_view_related_record_no_record(self):
        """Should return False if no related record"""
        log = self.env["billcom.logger"].create(
            {
                "operation_type": "sync_vendor",
            }
        )

        result = log.action_view_related_record()

        self.assertFalse(result)

    # ===== Get Operation Stats Tests =====

    def test_get_operation_stats_basic(self):
        """Should calculate operation statistics"""
        # Create test logs
        for _ in range(5):
            self.env["billcom.logger"].create(
                {
                    "operation_type": "sync_vendor",
                    "level": "info",
                    "status": "success",
                    "start_time": fields.Datetime.now(),
                    "end_time": fields.Datetime.now() + timedelta(seconds=5),
                }
            )

        for _ in range(2):
            self.env["billcom.logger"].create(
                {
                    "operation_type": "sync_vendor",
                    "level": "error",
                    "status": "error",
                    "start_time": fields.Datetime.now(),
                    "end_time": fields.Datetime.now() + timedelta(seconds=5),
                }
            )

        stats = self.env["billcom.logger"].get_operation_stats("sync_vendor", days=7)

        self.assertGreaterEqual(stats["total"], 7)
        self.assertGreaterEqual(stats["success"], 5)
        self.assertGreaterEqual(stats["error"], 2)
        self.assertGreater(stats["success_rate"], 0)

    def test_get_operation_stats_no_logs(self):
        """Should return zeros for no logs"""
        stats = self.env["billcom.logger"].get_operation_stats("sync_bill", days=1)

        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["success_rate"], 0)
        self.assertEqual(stats["avg_duration"], 0)

    # ===== Get Error Summary Tests =====

    def test_get_error_summary_basic(self):
        """Should return error summary"""
        # Create error logs
        for i in range(3):
            self.env["billcom.logger"].create(
                {
                    "operation_type": "sync_vendor",
                    "level": "error",
                    "status": "error",
                    "record_name": f"Vendor {i}",
                    "error_message": f"Error {i}",
                }
            )

        errors = self.env["billcom.logger"].get_error_summary(days=7, limit=10)

        self.assertGreaterEqual(len(errors), 3)
        self.assertTrue(all("error_message" in err for err in errors))

    def test_get_error_summary_with_limit(self):
        """Should respect limit parameter"""
        # Create many error logs
        for i in range(15):
            self.env["billcom.logger"].create(
                {
                    "operation_type": "sync_vendor",
                    "level": "error",
                    "status": "error",
                    "error_message": f"Error {i}",
                }
            )

        errors = self.env["billcom.logger"].get_error_summary(days=7, limit=5)

        self.assertLessEqual(len(errors), 5)
