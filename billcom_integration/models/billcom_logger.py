# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import traceback
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BillcomLogger(models.Model):
    _name = "billcom.logger"
    _description = "Bill.com Integration Logger"
    _order = "create_date desc"
    _rec_name = "operation_type"

    # Basic Information
    operation_type = fields.Selection(
        [
            ("sync_vendor", "Vendor Sync"),
            ("sync_customer", "Customer Sync"),
            ("sync_bill", "Bill Sync"),
            ("sync_invoice", "Invoice Sync"),
            ("sync_payment", "Payment Sync"),
            ("sync_attachment", "Attachment Sync"),
            ("webhook", "Webhook Processing"),
            ("auth", "Authentication"),
            ("api_request", "API Request"),
            ("manual_sync", "Manual Sync"),
            ("scheduled_sync", "Scheduled Sync"),
        ],
        required=True,
    )

    level = fields.Selection(
        [
            ("debug", "Debug"),
            ("info", "Info"),
            ("warning", "Warning"),
            ("error", "Error"),
            ("critical", "Critical"),
        ],
        string="Log Level",
        required=True,
        default="info",
    )

    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("success", "Success"),
            ("warning", "Warning with Success"),
            ("error", "Error"),
            ("retry", "Retrying"),
        ],
        required=True,
        default="pending",
    )

    # Context Information
    record_model = fields.Char()
    record_id = fields.Integer()
    record_name = fields.Char()
    billcom_id = fields.Char(string="Bill.com ID")

    # Request/Response Details
    endpoint = fields.Char(string="API Endpoint")
    http_method = fields.Char()
    request_data = fields.Text()
    response_data = fields.Text()
    response_status_code = fields.Integer(string="HTTP Status Code")

    # Timing and Performance
    start_time = fields.Datetime()
    end_time = fields.Datetime()
    duration = fields.Float(
        string="Duration (seconds)", compute="_compute_duration", store=True
    )
    retry_count = fields.Integer(default=0)
    max_retries = fields.Integer(default=3)

    # Message and Error Details
    message = fields.Text()
    error_message = fields.Text()
    error_traceback = fields.Text()

    # User and Company Context
    user_id = fields.Many2one(
        "res.users", string="User", default=lambda self: self.env.user
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    config_id = fields.Many2one("billcom.config", string="Bill.com Configuration")

    # Sync Queue Reference
    sync_queue_id = fields.Many2one("billcom.sync.queue", string="Sync Queue Item")

    @api.depends("start_time", "end_time")
    def _compute_duration(self):
        for record in self:
            if record.start_time and record.end_time:
                delta = record.end_time - record.start_time
                record.duration = delta.total_seconds()
            else:
                record.duration = 0.0

    @api.model
    def log_operation(self, operation_type, level="info", status="pending", **kwargs):
        """Create a log entry for Bill.com operations"""
        values = {
            "operation_type": operation_type,
            "level": level,
            "status": status,
            "start_time": fields.Datetime.now(),
        }
        values.update(kwargs)
        return self.create(values)

    @api.model
    def log_api_request(self, endpoint, method="GET", status="pending", **kwargs):
        """Log API request details"""
        return self.log_operation(
            "api_request",
            endpoint=endpoint,
            http_method=method,
            status=status,
            **kwargs,
        )

    @api.model
    def log_sync_operation(
        self, sync_type, record_model=None, record_id=None, **kwargs
    ):
        """Log synchronization operations"""
        record_name = None
        if record_model and record_id:
            try:
                record = self.env[record_model].browse(record_id)
                record_name = (
                    record.display_name if record.exists() else f"ID {record_id}"
                )
            except Exception:
                record_name = f"ID {record_id}"

        return self.log_operation(
            sync_type,
            record_model=record_model,
            record_id=record_id,
            record_name=record_name,
            **kwargs,
        )

    @api.model
    def log_webhook(self, event_type, entity_id=None, **kwargs):
        """Log webhook processing"""
        return self.log_operation(
            "webhook", message=f"Webhook: {event_type}", billcom_id=entity_id, **kwargs
        )

    def update_status(self, status, message=None, error_message=None, **kwargs):
        """Update log entry status and end time"""
        values = {
            "status": status,
            "end_time": fields.Datetime.now(),
        }
        if message:
            values["message"] = message
        if error_message:
            values["error_message"] = error_message
        if status == "error" and not values.get("error_traceback"):
            values["error_traceback"] = traceback.format_exc()

        values.update(kwargs)
        self.write(values)

    def mark_success(self, message=None, **kwargs):
        """Mark operation as successful"""
        self.update_status("success", message=message, **kwargs)

    def mark_error(self, error_message, **kwargs):
        """Mark operation as failed"""
        self.update_status("error", error_message=error_message, **kwargs)

    def mark_retry(self, retry_count=None, **kwargs):
        """Mark operation for retry"""
        if retry_count is not None:
            kwargs["retry_count"] = retry_count
        self.update_status("retry", **kwargs)

    @api.model
    def cleanup_old_logs(self, days=30):
        """Clean up old log entries"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([("create_date", "<", cutoff_date)])
        count = len(old_logs)
        old_logs.unlink()
        _logger.info(f"Cleaned up {count} old Bill.com log entries")
        return count

    def action_view_related_record(self):
        """Action to view the related record"""
        self.ensure_one()
        if not self.record_model or not self.record_id:
            return False

        return {
            "type": "ir.actions.act_window",
            "name": f"Related {self.record_model}",
            "res_model": self.record_model,
            "res_id": self.record_id,
            "view_mode": "form",
            "target": "current",
        }

    def action_retry_operation(self):
        """Retry the failed operation"""
        self.ensure_one()
        if self.sync_queue_id:
            return self.sync_queue_id.action_retry()
        return False

    @api.model
    def get_operation_stats(self, operation_type=None, days=7):
        """Get operation statistics"""
        domain = [("create_date", ">=", fields.Datetime.now() - timedelta(days=days))]
        if operation_type:
            domain.append(("operation_type", "=", operation_type))

        logs = self.search(domain)

        stats = {
            "total": len(logs),
            "success": len(logs.filtered(lambda line: line.status == "success")),
            "error": len(logs.filtered(lambda line: line.status == "error")),
            "pending": len(
                logs.filtered(
                    lambda line: line.status in ["pending", "processing", "retry"]
                )
            ),
            "avg_duration": sum(logs.mapped("duration")) / len(logs) if logs else 0,
        }

        stats["success_rate"] = (
            (stats["success"] / stats["total"] * 100) if stats["total"] else 0
        )

        return stats

    @api.model
    def get_error_summary(self, days=7, limit=10):
        """Get summary of recent errors"""
        domain = [
            ("create_date", ">=", fields.Datetime.now() - timedelta(days=days)),
            ("status", "=", "error"),
        ]

        error_logs = self.search(domain, limit=limit)

        return [
            {
                "id": log.id,
                "operation_type": log.operation_type,
                "record_name": log.record_name,
                "error_message": log.error_message,
                "create_date": log.create_date,
                "duration": log.duration,
            }
            for log in error_logs
        ]
