# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomSyncQueue(models.Model):
    _name = "billcom.sync.queue"
    _description = "Bill.com Synchronization Queue"
    _order = "create_date desc"
    _rec_name = "display_name"

    # Basic Information
    display_name = fields.Char(compute="_compute_display_name", store=True)

    sync_type = fields.Selection(
        [
            ("vendor", "Vendor Sync"),
            ("customer", "Customer Sync"),
            ("bill", "Bill Sync"),
            ("invoice", "Invoice Sync"),
            ("payment", "Payment Sync"),
            ("attachment", "Attachment Sync"),
        ],
        required=True,
    )

    direction = fields.Selection(
        [
            ("odoo_to_billcom", "Odoo → Bill.com"),
            ("billcom_to_odoo", "Bill.com → Odoo"),
            ("bidirectional", "Bidirectional"),
        ],
        required=True,
        default="odoo_to_billcom",
    )

    operation = fields.Selection(
        [
            ("create", "Create"),
            ("update", "Update"),
            ("delete", "Delete"),
            ("sync", "Synchronize"),
        ],
        required=True,
        default="sync",
    )

    # Status and Priority
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("processing", "Processing"),
            ("success", "Success"),
            ("error", "Error"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
    )

    priority = fields.Selection(
        [
            ("0", "Low"),
            ("1", "Normal"),
            ("2", "High"),
            ("3", "Critical"),
        ],
        default="1",
    )

    # Record References
    record_model = fields.Char()
    record_id = fields.Integer()
    record_name = fields.Char()
    billcom_id = fields.Char(string="Bill.com ID")

    # Sync Data
    sync_data = fields.Text(string="Sync Data (JSON)")
    response_data = fields.Text()

    # Execution Details
    scheduled_date = fields.Datetime(default=fields.Datetime.now)
    started_date = fields.Datetime()
    completed_date = fields.Datetime()

    # Retry Logic
    retry_count = fields.Integer(default=0)
    max_retries = fields.Integer(default=3)
    next_retry_date = fields.Datetime()

    # Error Handling
    error_message = fields.Text()
    error_traceback = fields.Text()

    # User and Company Context
    user_id = fields.Many2one(
        "res.users", string="Created by", default=lambda self: self.env.user
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    config_id = fields.Many2one("billcom.config", string="Bill.com Configuration")

    # Related Logs
    logger_ids = fields.One2many("billcom.logger", "sync_queue_id", string="Logs")

    @api.depends("sync_type", "operation", "record_name", "billcom_id")
    def _compute_display_name(self):
        for record in self:
            parts = [record.sync_type.title() if record.sync_type else "Sync"]
            if record.operation:
                parts.append(record.operation.title())
            if record.record_name:
                parts.append(f"'{record.record_name}'")
            elif record.billcom_id:
                parts.append(f"[{record.billcom_id}]")
            record.display_name = " ".join(parts)

    @api.model
    def create_sync_item(
        self,
        sync_type,
        record_model=None,
        record_id=None,
        direction="odoo_to_billcom",
        operation="sync",
        priority="1",
        sync_data=None,
        billcom_id=None,
        **kwargs,
    ):
        """Create a new sync queue item"""

        record_name = None
        if record_model and record_id:
            try:
                record = self.env[record_model].browse(record_id)
                if record.exists():
                    record_name = record.display_name
                    # Get billcom_id from record if not provided
                    if not billcom_id and hasattr(record, "billcom_id"):
                        billcom_id = record.billcom_id
                    elif not billcom_id and hasattr(record, "billcom"):
                        billcom_id = record.billcom
            except Exception as e:
                _logger.warning(
                    f"Could not get record info for {record_model}: {record_id}: {e}"
                )

        values = {
            "sync_type": sync_type,
            "direction": direction,
            "operation": operation,
            "priority": priority,
            "record_model": record_model,
            "record_id": record_id,
            "record_name": record_name,
            "billcom_id": billcom_id,
            "state": "queued",
        }

        if sync_data:
            values["sync_data"] = (
                json.dumps(sync_data) if isinstance(sync_data, dict) else sync_data
            )

        values.update(kwargs)

        # Check for duplicates
        existing = self._find_duplicate(values)
        if existing:
            _logger.info(
                f"Sync item already exists for {sync_type} {record_model}: {record_id}"
            )
            return existing

        sync_item = self.create(values)

        # Create initial log entry
        self.env["billcom.logger"].log_operation(
            f"sync_{sync_type}",
            status="pending",
            record_model=record_model,
            record_id=record_id,
            record_name=record_name,
            billcom_id=billcom_id,
            sync_queue_id=sync_item.id,
            message=f"Queued {operation} operation for {sync_type}",
        )

        return sync_item

    def _find_duplicate(self, values):
        """Find duplicate sync items"""
        domain = [
            ("sync_type", "=", values["sync_type"]),
            ("operation", "=", values["operation"]),
            ("state", "in", ["draft", "queued", "processing"]),
        ]

        if values.get("record_model") and values.get("record_id"):
            domain.extend(
                [
                    ("record_model", "=", values["record_model"]),
                    ("record_id", "=", values["record_id"]),
                ]
            )
        elif values.get("billcom_id"):
            domain.append(("billcom_id", "=", values["billcom_id"]))

        return self.search(domain, limit=1)

    def action_process(self):
        """Process the sync queue item"""
        self.ensure_one()

        if self.state != "queued":
            raise UserError(_("Only queued items can be processed"))

        # Update state and start time
        self.write(
            {
                "state": "processing",
                "started_date": fields.Datetime.now(),
            }
        )

        # Create processing log
        log_entry = self.env["billcom.logger"].log_operation(
            f"sync_{self.sync_type}",
            status="processing",
            record_model=self.record_model,
            record_id=self.record_id,
            record_name=self.record_name,
            billcom_id=self.billcom_id,
            sync_queue_id=self.id,
            message=f"Processing {self.operation} operation for {self.sync_type}",
        )

        try:
            # Process based on sync type and direction
            result = self._execute_sync()

            # Mark as successful
            self.write(
                {
                    "state": "success",
                    "completed_date": fields.Datetime.now(),
                    "response_data": (
                        json.dumps(result) if isinstance(result, dict) else str(result)
                    ),
                }
            )

            log_entry.mark_success(
                f"Successfully processed {self.sync_type} {self.operation}"
            )

            return result

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Error processing sync queue item {self.id}: {error_msg}")

            # Update retry logic
            if self.retry_count < self.max_retries:
                self._schedule_retry(error_msg)
                log_entry.mark_retry(
                    retry_count=self.retry_count + 1, error_message=error_msg
                )
            else:
                self.write(
                    {
                        "state": "error",
                        "completed_date": fields.Datetime.now(),
                        "error_message": error_msg,
                    }
                )
                log_entry.mark_error(error_msg)

            raise

    def _execute_sync(self):
        """Execute the actual synchronization"""
        if self.direction == "odoo_to_billcom":
            return self._sync_odoo_to_billcom()
        elif self.direction == "billcom_to_odoo":
            return self._sync_billcom_to_odoo()
        elif self.direction == "bidirectional":
            result1 = self._sync_odoo_to_billcom()
            result2 = self._sync_billcom_to_odoo()
            return {"odoo_to_billcom": result1, "billcom_to_odoo": result2}

    def _sync_odoo_to_billcom(self):
        """Sync from Odoo to Bill.com"""
        if not self.record_model or not self.record_id:
            raise UserError(_("Missing record information for sync"))

        record = self.env[self.record_model].browse(self.record_id)
        if not record.exists():
            raise UserError(
                _("Record not found: %(model)s[%(id)s]")
                % {"model": self.record_model, "id": self.record_id}
            )

        # Call appropriate sync method based on type
        if self.sync_type == "vendor":
            return record.sync_to_billcom("vendor")
        elif self.sync_type == "customer":
            return record.sync_to_billcom("customer")
        elif self.sync_type == "bill":
            return record.button_sync_to_billcom()
        elif self.sync_type == "invoice":
            return record.button_sync_to_billcom()
        elif self.sync_type == "payment":
            return record.button_sync_to_billcom()
        else:
            raise UserError(_("Unsupported sync type: %s") % self.sync_type)

    def _sync_billcom_to_odoo(self):
        """Sync from Bill.com to Odoo"""
        if not self.billcom_id:
            raise UserError(_("Missing Bill.com ID for sync"))

        # Use the billcom_service to process the queue item
        service = self.env["billcom.service"]

        # If sync_data is not available, fetch it from BILL API first
        if not self.sync_data:
            self._fetch_billcom_data()

        # Process the queue item using the service
        return service.process_queue_item_from_billcom(self)

    def _fetch_billcom_data(self):
        """Fetch data from BILL API for this queue item"""
        if not self.billcom_id:
            raise UserError(_("Missing Bill.com ID to fetch data"))

        service = self.env["billcom.service"]

        # Determine endpoint based on sync type
        endpoint_map = {
            "vendor": f"vendors/{self.billcom_id}",
            "customer": f"customers/{self.billcom_id}",
            "bill": f"bills/{self.billcom_id}",
            "payment": f"payments/{self.billcom_id}",
        }

        endpoint = endpoint_map.get(self.sync_type)
        if not endpoint:
            raise UserError(
                _("Unsupported sync type for fetching data: %s") % self.sync_type
            )

        try:
            _logger.info(
                f"Fetching {self.sync_type} data from BILL API: {self.billcom_id}"
            )
            response = service._make_request(endpoint, method="GET")

            # Store the response data
            if response:
                self.sync_data = str(response)
                _logger.info(f"Successfully fetched {self.sync_type} data from BILL")
            else:
                raise UserError(_("No data returned from BILL API"))

        except Exception as e:
            _logger.error(f"Error fetching data from BILL API: {e}")
            raise UserError(_(f"Failed to fetch data from Bill.com: {e}")) from e

    def _schedule_retry(self, error_message):
        """Schedule a retry for failed sync"""
        self.retry_count += 1

        # Exponential backoff: 2^retry_count minutes
        delay_minutes = 2**self.retry_count
        next_retry = fields.Datetime.now() + timedelta(minutes=delay_minutes)

        self.write(
            {
                "state": "queued",
                "next_retry_date": next_retry,
                "error_message": error_message,
            }
        )

    def action_retry(self):
        """Manually retry a failed sync"""
        self.ensure_one()

        if self.state not in ["error", "queued"]:
            raise UserError(_("Only failed or queued items can be retried"))

        # Reset state
        self.write(
            {
                "state": "queued",
                "next_retry_date": fields.Datetime.now(),
                "error_message": False,
                "started_date": False,
                "completed_date": False,
            }
        )

        return self.action_process()

    def action_cancel(self):
        """Cancel the sync item"""
        self.ensure_one()

        if self.state == "processing":
            raise UserError(_("Cannot cancel item that is currently processing"))

        self.write(
            {
                "state": "cancelled",
                "completed_date": fields.Datetime.now(),
            }
        )

    @api.model
    def process_queue(self, limit=50):
        """Process queued sync items"""
        # Get items that are ready to process
        domain = [
            ("state", "=", "queued"),
            "|",
            ("next_retry_date", "=", False),
            ("next_retry_date", "<=", fields.Datetime.now()),
        ]

        items = self.search(
            domain, limit=limit, order="priority desc, scheduled_date asc"
        )

        processed = 0
        errors = 0

        for item in items:
            try:
                item.action_process()
                processed += 1
            except Exception as e:
                errors += 1
                _logger.error(f"Failed to process sync queue item {item.id}: {e}")

        _logger.info(f"Processed {processed} sync items, {errors} errors")

        return {
            "processed": processed,
            "errors": errors,
            "total": len(items),
        }

    @api.model
    def cleanup_completed_items(self, days=7):
        """Clean up old completed sync items"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_items = self.search(
            [
                ("state", "in", ["success", "cancelled"]),
                ("completed_date", "<", cutoff_date),
            ]
        )
        count = len(old_items)
        old_items.unlink()
        _logger.info(f"Cleaned up {count} completed sync queue items")
        return count

    def action_view_logs(self):
        """View related logs"""
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Sync Logs",
            "res_model": "billcom.logger",
            "view_mode": "tree,form",
            "domain": [("sync_queue_id", "=", self.id)],
            "context": {"default_sync_queue_id": self.id},
        }

    def action_view_record(self):
        """View the synced record (partner, bill, invoice, etc.)"""
        self.ensure_one()

        if not self.record_model or not self.record_id:
            raise UserError(_("No record associated with this sync item"))

        # Check if record still exists
        record = self.env[self.record_model].browse(self.record_id)
        if not record.exists():
            raise UserError(_("The associated record no longer exists"))

        # Get appropriate view mode based on model
        view_mode = "form,tree"
        if self.record_model == "ir.attachment":
            view_mode = "form"

        return {
            "type": "ir.actions.act_window",
            "name": self.record_name or "Record",
            "res_model": self.record_model,
            "view_mode": view_mode,
            "res_id": self.record_id,
            "target": "current",
        }
