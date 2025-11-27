# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BillcomWebhookLog(models.Model):
    _name = "billcom.webhook.log"
    _description = "Bill.com Webhook Log"
    _order = "create_date desc"
    _rec_name = "idempotency_key"

    idempotency_key = fields.Char(
        required=True,
        index=True,
        help="Unique key to prevent duplicate webhook processing (eventType:entityId)",
    )

    event_type = fields.Char(
        required=True,
        index=True,
        help="Type of webhook event (bill.created, vendor.updated, etc.)",
    )

    entity_id = fields.Char(
        required=True,
        help="Bill.com ID of the entity affected",
    )

    webhook_data = fields.Text(
        help="Full JSON payload received from Bill.com",
    )

    state = fields.Selection(
        [
            ("received", "Received"),
            ("processing", "Processing"),
            ("success", "Success"),
            ("error", "Error"),
        ],
        default="received",
        required=True,
    )

    error_message = fields.Text(
        help="Error message if processing failed",
    )

    processed_at = fields.Datetime(
        help="When the webhook was successfully processed",
    )

    signature_valid = fields.Boolean(
        default=False,
        help="Whether the webhook signature was valid",
    )

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
    )

    @api.model
    def check_duplicate(self, idempotency_key):
        """Check if webhook with this idempotency key was already processed

        Args:
            idempotency_key (str): Idempotency key to check

        Returns:
            bool: True if already processed, False otherwise
        """
        existing = self.search([("idempotency_key", "=", idempotency_key)], limit=1)
        return bool(existing)

    @api.model
    def log_webhook(
        self,
        event_type,
        entity_id,
        webhook_data=None,
        signature_valid=False,
        idempotency_key=None,
    ):
        """Log a webhook event

        Args:
            event_type (str): Type of webhook event
            entity_id (str): Bill.com entity ID
            webhook_data (str): Full JSON payload
            signature_valid (bool): Whether signature was valid
            idempotency_key (str): Unique key for idempotency (uses eventId if available)

        Returns:
            billcom.webhook.log: Created log record
        """
        # Use provided idempotency_key or generate from event_type:entity_id
        if not idempotency_key:
            idempotency_key = f"{event_type}: {entity_id}"

        # Note: Duplicate check is done in the controller before calling this method
        # No need to check again here to avoid double verification

        return self.create(
            {
                "idempotency_key": idempotency_key,
                "event_type": event_type,
                "entity_id": entity_id,
                "webhook_data": webhook_data,
                "signature_valid": signature_valid,
                "state": "received",
            }
        )

    def mark_processing(self):
        """Mark webhook as processing"""
        self.ensure_one()
        self.write({"state": "processing"})

    def mark_success(self):
        """Mark webhook as successfully processed"""
        self.ensure_one()
        self.write(
            {
                "state": "success",
                "processed_at": fields.Datetime.now(),
            }
        )

    def mark_error(self, error_message):
        """Mark webhook processing as failed

        Args:
            error_message (str): Error message
        """
        self.ensure_one()
        self.write(
            {
                "state": "error",
                "error_message": error_message,
            }
        )

    @api.model
    def cleanup_old_logs(self, days=30):
        """Clean up old webhook logs

        Args:
            days (int): Delete logs older than this many days
        """
        cutoff_date = fields.Datetime.now() - fields.timedelta(days=days)
        old_logs = self.search(
            [("create_date", "<", cutoff_date), ("state", "=", "success")]
        )
        count = len(old_logs)
        old_logs.unlink()
        _logger.info("Cleaned up %s old webhook logs", count)
        return count
