import logging
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    billcom = fields.Char(string="Bill.com Reference")
    is_sync_to_billcom = fields.Boolean(default=True)
    last_sync_date = fields.Datetime(copy=False)
    billcom_payment_type = fields.Selection(
        selection=[
            ("ach", "ACH"),
            ("check", "Check"),
            ("virtual_card", "Virtual Card"),
            ("wire", "Wire Transfer"),
        ],
        string="Bill.com Payment Type",
        default="ach",
    )
    billcom_process_date = fields.Date(string="Process Date")
    billcom_payment_status = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("processing", "Processing"),
            ("processed", "Processed"),
            ("sent", "Sent"),
            ("canceled", "Canceled"),
            ("failed", "Failed"),
        ],
        string="Bill.com Payment Status",
        readonly=True,
        copy=False,
        default="draft",
    )
    is_international_payment = fields.Boolean(
        string="International Payment",
        compute="_compute_is_international_payment",
        store=True,
    )
    billcom_confirmation_number = fields.Char(
        string="Bill.com Confirmation Number", readonly=True, copy=False
    )
    billcom_transaction_number = fields.Char(
        string="Bill.com Transaction Number", readonly=True, copy=False
    )
    billcom_exchange_rate = fields.Float(
        string="Exchange Rate", digits=(16, 6), readonly=True
    )
    billcom_funding_amount = fields.Monetary(
        string="Funding Amount (USD)", readonly=True
    )

    @api.depends("partner_id", "partner_id.country_id")
    def _compute_is_international_payment(self):
        """Determine if payment is international based on vendor country"""
        company_country = self.env.company.country_id
        for payment in self:
            if payment.partner_id and payment.partner_id.country_id:
                payment.is_international_payment = (
                    payment.partner_id.country_id.id != company_country.id
                )
            else:
                payment.is_international_payment = False

    def _prepare_payment_data(self):
        """Prepare payment data for Bill.com API"""
        self.ensure_one()
        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.payment_type != "outbound" or self.partner_type != "supplier":
            return False

        # Get the bill ID if this payment is linked to a bill
        bill_id = False
        if self.reconciled_bill_ids:
            for bill in self.reconciled_bill_ids:
                if bill.billcom:
                    bill_id = bill.billcom
                    break

        # Determine payment method
        if self.billcom_payment_type == "check":
            pass
        elif self.billcom_payment_type == "virtual_card":
            pass
        elif self.billcom_payment_type == "wire":
            pass

        # Get bank account information
        bank_account_id = False
        if self.journal_id.bank_account_id:
            # Check if the bank account is already synced with Bill.com
            if (
                hasattr(self.journal_id.bank_account_id, "billcom")
                and self.journal_id.bank_account_id.billcom
            ):
                bank_account_id = self.journal_id.bank_account_id.billcom

        # Prepare payment data
        payment_data = {
            "vendorId": self.partner_id.billcom,
            "processDate": self.billcom_process_date.isoformat()
            if self.billcom_process_date
            else fields.Date.today().isoformat(),
            "amount": self.amount,
            "description": self.ref or f"Payment {self.name}",
            "fundingAccount": {"type": "BANK_ACCOUNT", "id": bank_account_id},
            "processingOptions": {
                "requestPayFaster": False,
                "createBill": False,
                "requestCheckDeliveryType": "STANDARD",
            },
        }

        # Add bill ID if available
        if bill_id:
            payment_data["billId"] = bill_id

        # Add international payment options if needed
        if self.is_international_payment and self.billcom_payment_type == "wire":
            payment_data["internationalOptions"] = {
                "paymentCurrency": self.currency_id.name,
                "wireInstructions": self.partner_id.bank_ids[0].bank_id.bic
                if self.partner_id.bank_ids
                else "",
            }

        return payment_data

    def button_sync_to_billcom(self):
        """Sync payment to Bill.com"""
        self.ensure_one()
        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.payment_type != "outbound" or self.partner_type != "supplier":
            return False

        try:
            # Prepare payment data
            payment_data = self._prepare_payment_data()
            if not payment_data:
                return False

            # Make API request
            if self.billcom:
                # For existing payments, we can only get the status
                # Bill.com API v3 doesn't support updating payments via PUT
                result = self.env["billcom.service"]._make_request(
                    f"payments/{self.billcom}", method="GET"
                )

                # Log that we can't update the payment
                _logger.info(
                    "Payment %s already exists in Bill.com (ID: %s). Bill.com API does not support updating existing payments.",
                    self.name,
                    self.billcom,
                )

                # Update local status from Bill.com
                if result and result.get("id"):
                    self.with_context(skip_billcom_sync=True).write(
                        {
                            "billcom_payment_status": self._map_billcom_status(
                                result.get("singleStatus")
                            ),
                            "last_sync_date": fields.Datetime.now(),
                        }
                    )
            else:
                # Create new payment
                result = self.env["billcom.service"]._make_request(
                    "payments", method="POST", data=payment_data
                )

            if result and result.get("id"):
                # Update payment with Bill.com data
                update_vals = {
                    "billcom": result.get("id"),
                    "last_sync_date": fields.Datetime.now(),
                    "billcom_payment_status": self._map_billcom_status(
                        result.get("singleStatus")
                    ),
                    "billcom_confirmation_number": result.get("confirmationNumber", ""),
                    "billcom_transaction_number": result.get("transactionNumber", ""),
                }

                # Update exchange rate and funding amount for international payments
                if result.get("exchangeRate"):
                    update_vals["billcom_exchange_rate"] = result.get("exchangeRate")
                if result.get("fundingAmount"):
                    update_vals["billcom_funding_amount"] = result.get("fundingAmount")

                self.with_context(skip_billcom_sync=True).write(update_vals)
                _logger.info("Successfully synced payment %s with Bill.com", self.name)
                return result
            return False
        except Exception as e:
            _logger.error("Error syncing payment %s to Bill.com: %s", self.name, str(e))
            return False

    def _map_billcom_status(self, billcom_status):
        """Map Bill.com payment status to Odoo status"""
        status_map = {
            "SCHEDULED": "scheduled",
            "PROCESSING": "processing",
            "PROCESSED": "processed",
            "SENT": "sent",
            "CANCELED": "canceled",
            "FAILED": "failed",
        }
        return status_map.get(billcom_status, "draft")

    def write(self, vals):
        """Override write to sync changes to Bill.com"""
        res = super().write(vals)
        if self.env.context.get("skip_billcom_sync"):
            return res

        for record in self:
            if (
                record.is_sync_to_billcom
                and record.partner_id.is_sync_to_billcom
                and record.payment_type == "outbound"
                and record.partner_type == "supplier"
            ):
                try:
                    record.with_context(skip_billcom_sync=True).button_sync_to_billcom()
                except Exception as e:
                    _logger.error("Error syncing payment to Bill.com: %s", str(e))

        return res

    def action_get_payment_status(self):
        """Get payment status from Bill.com"""
        self.ensure_one()
        if not self.billcom:
            raise UserError(_("This payment has not been synced with Bill.com yet."))

        try:
            result = self.env["billcom.service"]._make_request(
                f"payments/{self.billcom}", method="GET"
            )

            if result and result.get("id"):
                # Update payment with Bill.com data
                self.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_payment_status": self._map_billcom_status(
                            result.get("singleStatus")
                        ),
                        "last_sync_date": fields.Datetime.now(),
                    }
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Success"),
                        "message": _("Payment status updated from Bill.com: %s")
                        % result.get("singleStatus"),
                        "type": "success",
                        "sticky": False,
                    },
                }

            return False
        except Exception as e:
            _logger.error("Error getting payment status from Bill.com: %s", str(e))
            raise UserError(
                _("Error getting payment status from Bill.com: %s") % str(e)
            )

    def action_cancel_billcom_payment(self):
        """Cancel payment in Bill.com"""
        self.ensure_one()
        if not self.billcom:
            raise UserError(_("This payment has not been synced with Bill.com yet."))

        if self.billcom_payment_status not in ["draft", "scheduled"]:
            raise UserError(_("Only draft or scheduled payments can be canceled."))

        try:
            result = self.env["billcom.service"]._make_request(
                f"payments/{self.billcom}/cancel", method="POST"
            )

            if result and result.get("id"):
                # Update payment with Bill.com data
                self.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_payment_status": "canceled",
                        "last_sync_date": fields.Datetime.now(),
                    }
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Success"),
                        "message": _("Payment successfully canceled in Bill.com"),
                        "type": "success",
                        "sticky": False,
                    },
                }

            return False
        except Exception as e:
            _logger.error("Error canceling payment in Bill.com: %s", str(e))
            raise UserError(_("Error canceling payment in Bill.com: %s") % str(e))

    @api.model
    def update_billcom_payment_status(self):
        """Update payment status from Bill.com for all pending payments
        This method is called by the scheduled action

        Enhanced with:
        - Retry logic for failed API calls
        - Better error handling and logging
        - Prioritization based on payment age
        """
        # Get configuration for sync settings
        try:
            config = self.env["billcom.config"].sudo().get_config()
            if not config.sync_payments:
                _logger.info("Payment synchronization is disabled in configuration")
                return False

            max_retries = (
                config.api_max_retries if hasattr(config, "api_max_retries") else 3
            )
            retry_delay = (
                config.api_retry_delay if hasattr(config, "api_retry_delay") else 5
            )
        except Exception as e:
            _logger.error("Error getting Bill.com configuration: %s", str(e))
            return False

        # Get all payments that have been synced with Bill.com and are not in a final state
        # Order by last_sync_date to prioritize payments that haven't been updated recently
        payments = self.search(
            [
                ("billcom", "!=", False),
                (
                    "billcom_payment_status",
                    "not in",
                    ["processed", "sent", "canceled", "failed"],
                ),
            ],
            order="last_sync_date asc, create_date asc",
        )

        if not payments:
            _logger.info("No pending payments found for status update")
            return True

        _logger.info("Found %s payments to update status from Bill.com", len(payments))

        updated_count = 0
        error_count = 0
        skipped_count = 0

        for payment in payments:
            # Skip payments updated recently (within last hour) unless in processing state
            if (
                payment.last_sync_date
                and payment.billcom_payment_status != "processing"
            ):
                last_update_age = fields.Datetime.now() - payment.last_sync_date
                # Skip if updated in the last hour (3600 seconds)
                if last_update_age.total_seconds() < 3600:
                    _logger.debug(
                        "Skipping recent payment %s (updated %s ago)",
                        payment.name,
                        last_update_age,
                    )
                    skipped_count += 1
                    continue

            # Implement retry logic
            retry_count = 0
            success = False
            last_error = None

            while not success and retry_count < max_retries:
                try:
                    # Add detailed logging
                    _logger.debug(
                        "Requesting status for payment %s (ID: %s, attempt %s/%s)",
                        payment.name,
                        payment.billcom,
                        retry_count + 1,
                        max_retries,
                    )

                    result = self.env["billcom.service"]._make_request(
                        f"payments/{payment.billcom}", method="GET"
                    )

                    if result and result.get("id"):
                        # Get the new status
                        new_status = payment._map_billcom_status(
                            result.get("singleStatus")
                        )
                        old_status = payment.billcom_payment_status

                        # Update payment with Bill.com data
                        payment.with_context(skip_billcom_sync=True).write(
                            {
                                "billcom_payment_status": new_status,
                                "last_sync_date": fields.Datetime.now(),
                                "billcom_confirmation_number": result.get(
                                    "confirmationNumber",
                                    payment.billcom_confirmation_number or "",
                                ),
                                "billcom_transaction_number": result.get(
                                    "transactionNumber",
                                    payment.billcom_transaction_number or "",
                                ),
                                "billcom_exchange_rate": result.get(
                                    "exchangeRate", payment.billcom_exchange_rate or 0.0
                                ),
                                "billcom_funding_amount": result.get(
                                    "fundingAmount",
                                    payment.billcom_funding_amount or 0.0,
                                ),
                            }
                        )

                        # Log status change if it occurred
                        if old_status != new_status:
                            _logger.info(
                                "Payment %s status changed: %s -> %s",
                                payment.name,
                                old_status,
                                new_status,
                            )

                            # Create a note on the payment for audit trail
                            payment.message_post(
                                body=_("Bill.com payment status changed from %s to %s")
                                % (old_status, new_status),
                                subtype_id=self.env.ref("mail.mt_note").id,
                            )

                        updated_count += 1
                        success = True
                    else:
                        _logger.warning(
                            "No valid response for payment %s (attempt %s/%s)",
                            payment.name,
                            retry_count + 1,
                            max_retries,
                        )
                        retry_count += 1
                        time.sleep(retry_delay)  # Wait before retrying

                except Exception as e:
                    last_error = str(e)
                    _logger.warning(
                        "Error updating payment %s (attempt %s/%s): %s",
                        payment.name,
                        retry_count + 1,
                        max_retries,
                        last_error,
                    )
                    retry_count += 1
                    time.sleep(retry_delay)  # Wait before retrying

            # If all retries failed, log the error
            if not success:
                error_count += 1
                _logger.error(
                    "Failed to update payment %s after %s attempts: %s",
                    payment.name,
                    max_retries,
                    last_error or "Unknown error",
                )

                # Create a note on the payment for audit trail
                payment.message_post(
                    body=_("Failed to update payment status from Bill.com: %s")
                    % (last_error or "Unknown error"),
                    subtype_id=self.env.ref("mail.mt_note").id,
                )

        _logger.info(
            "Bill.com payment status update complete: %s updated, %s errors, %s skipped",
            updated_count,
            error_count,
            skipped_count,
        )
        return True

    @api.model
    def process_billcom_payment_webhook(self, payment_data):
        """Process payment status update from Bill.com webhook

        Args:
            payment_data (dict): Payment data from Bill.com webhook

        Returns:
            bool: True if successful, False otherwise
        """
        if not payment_data or not isinstance(payment_data, dict):
            _logger.error("Invalid payment data received from webhook")
            return False

        payment_id = payment_data.get("id")
        if not payment_id:
            _logger.error("No payment ID in webhook data")
            return False

        # Find the payment in Odoo
        payment = self.search([("billcom", "=", payment_id)], limit=1)
        if not payment:
            _logger.warning("Payment with Bill.com ID %s not found in Odoo", payment_id)
            return False

        try:
            # Get the new status
            new_status = payment._map_billcom_status(payment_data.get("singleStatus"))
            old_status = payment.billcom_payment_status

            # Update payment with Bill.com data
            payment.with_context(skip_billcom_sync=True).write(
                {
                    "billcom_payment_status": new_status,
                    "last_sync_date": fields.Datetime.now(),
                    "billcom_confirmation_number": payment_data.get(
                        "confirmationNumber", payment.billcom_confirmation_number or ""
                    ),
                    "billcom_transaction_number": payment_data.get(
                        "transactionNumber", payment.billcom_transaction_number or ""
                    ),
                    "billcom_exchange_rate": payment_data.get(
                        "exchangeRate", payment.billcom_exchange_rate or 0.0
                    ),
                    "billcom_funding_amount": payment_data.get(
                        "fundingAmount", payment.billcom_funding_amount or 0.0
                    ),
                }
            )

            # Log status change if it occurred
            if old_status != new_status:
                _logger.info(
                    "Payment %s status changed via webhook: %s -> %s",
                    payment.name,
                    old_status,
                    new_status,
                )

                # Create a note on the payment for audit trail
                payment.message_post(
                    body=_(
                        "Bill.com payment status changed from %s to %s (via webhook)"
                    )
                    % (old_status, new_status),
                    subtype_id=self.env.ref("mail.mt_note").id,
                )

            return True
        except Exception as e:
            _logger.error(
                "Error processing payment webhook for %s: %s", payment.name, str(e)
            )
            return False

    @api.model
    def update_billcom_payment_status_cron(self):
        # Get configuration
        try:
            config = self.env['billcom.config'].sudo().get_config()
            # Only run if the interval is greater than 0 and payment sync is enabled
            if hasattr(config, 'payment_status_check_interval') and config.payment_status_check_interval > 0 and config.sync_payments:
                self.update_billcom_payment_status()
            else:
                _logger.info('Bill.com payment status check is disabled')
        except Exception as e:
            _logger.error('Error in Bill.com payment status update: %s', str(e))
