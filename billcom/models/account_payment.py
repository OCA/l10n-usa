# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import time
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "billcom.abstract.model"]

    billcom_funding_account_type = fields.Selection(
        selection=[
            ("BANK_ACCOUNT", "Bank Account"),
            ("CARD_ACCOUNT", "Credit/Debit Card"),
            ("WALLET", "BILL Balance"),
            ("AP_CARD", "AP Card"),
        ],
        string="Funding Account Type",
        default="BANK_ACCOUNT",
        help="Type of funding account for Bill.com payment",
    )
    billcom_process_date = fields.Date(
        string="Process Date",
        help=(
            "Date when Bill.com will process this payment (format: YYYY-MM-DD). "
            "Required for WALLET and AP_CARD funding types. "
            "For new vendor bank accounts, must be at least 2 business days from today."
        ),
    )
    is_process_date_sync = fields.Boolean(compute="_compute_process_sync_date")
    billcom_pay_faster = fields.Boolean(
        string="Pay Faster",
        default=False,
        help="Enable Pay Faster for expedited payment delivery",
    )
    billcom_check_delivery_type = fields.Selection(
        selection=[
            ("STANDARD", "Standard"),
            ("RTP_DELIVERY", "Real-Time Payment (ACH)"),
            ("UPS_1DAY", "UPS 1-Day Delivery"),
            ("UPS_2DAY", "UPS 2-Days Delivery"),
            ("UPS_3DAY", "UPS 3-Days Delivery"),
            ("USPS_PRIORITY", "USPS Priority"),
        ],
        string="Check Delivery Type",
        default="STANDARD",
        help="Delivery method for check payments",
    )
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
    reconciled_bill_ids = fields.Many2many(
        comodel_name="account.move",
        relation="account_payment_bill_rel",
        column1="payment_id",
        column2="bill_id",
        string="Reconciled Bills",
        help="Bills reconciled with this payment for Bill.com sync",
        domain="[('move_type', '=', 'in_invoice')]",
    )

    @api.depends("partner_bank_id.billcom_last_sync_date")
    def _compute_process_sync_date(self):
        for rec in self:
            if self.partner_bank_id.billcom_last_sync_date:
                diff = (
                    fields.Datetime.today()
                    - self.partner_bank_id.billcom_last_sync_date
                )
                rec.is_process_date_sync = diff >= timedelta(days=1)
            else:
                rec.is_process_date_sync = True

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

    def _calculate_business_days_ahead(self, days=2):
        """Calculate a date N business days from today (excluding weekends)

        Args:
            days (int): Number of business days to add (default: 2)

        Returns:
            date: Date N business days from today

        Note: This is a simple calculation that only excludes weekends.
        For accurate business day calculation with holidays, consider using
        a proper business day calendar library.
        """
        current_date = fields.Date.today()
        business_days_added = 0

        while business_days_added < days:
            current_date += timedelta(days=1)
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5:
                business_days_added += 1

        return current_date

    def action_set_process_date_for_new_vendor(self):
        """Set process date to 2 business days ahead for new vendor bank accounts

        Use this action when paying a vendor for the first time with a bank account,
        as Bill.com requires 2 business days for verification.
        """
        self.ensure_one()
        min_process_date = self._calculate_business_days_ahead(days=2)
        self.billcom_process_date = min_process_date

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Process Date Updated"),
                "message": _(
                    "Process date set to %s (2 business days ahead for new vendor verification)"
                )
                % min_process_date,
                "type": "success",
                "sticky": False,
            },
        }

    def _prepare_payment_data(self):  # noqa: C901
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
                if bill.billcom_id or bill.billcom:
                    bill_id = bill.billcom_id or bill.billcom
                    break

        # Get funding account - REQUIRED for payment
        funding_account = False
        funding_account_id = False

        # Try to get funding account from journal's bank account
        if (
            self.journal_id.bank_account_id
            and self.journal_id.bank_account_id.billcom_funding_account_id
        ):
            funding_account = self.journal_id.bank_account_id.billcom_funding_account_id
            funding_account_id = funding_account.billcom_id
            _logger.info(
                "Using funding account from journal: %s (%s)",
                funding_account.name,
                funding_account_id,
            )
        # If no funding account configured, try to get the default one
        if not funding_account_id:
            _logger.info(
                "No funding account configured in journal, attempting to use default"
            )

            # Search for default payables funding account in database
            funding_account = self.env["billcom.funding.account"].search(
                [
                    ("is_default_payables", "=", True),
                    ("status", "=", "VERIFIED"),
                    ("company_id", "=", self.env.company.id),
                ],
                limit=1,
            )

            if funding_account:
                funding_account_id = funding_account.billcom_id
                _logger.info(
                    "Using default payables funding account: %s (%s)",
                    funding_account.name,
                    funding_account_id,
                )

        # Validate funding account configuration
        funding_type = self.billcom_funding_account_type or "BANK_ACCOUNT"

        # For WALLET type, id is not required
        if funding_type != "WALLET" and not funding_account_id:
            raise UserError(
                _(
                    "No Bill.com funding account configured. "
                    "Please link a funding account in the journal's bank account, "
                    "or sync funding accounts from Bill.com (Configuration > Funding Accounts)."
                )
            )

        # Build fundingAccount object
        funding_account_data = {"type": funding_type}
        if funding_type != "WALLET":
            funding_account_data["id"] = funding_account_id

        # Determine process date
        # WALLET and AP_CARD types REQUIRE processDate
        # BANK_ACCOUNT and CHECK: DO NOT send processDate (Bill.com sets it automatically)
        # Format: "YYYY-MM-DD" (e.g., "2025-12-31")
        #
        # Important: Bill.com automatically calculates next available payment date
        # considering bank verification times (2 business days for new accounts)

        process_date = None
        requires_process_date = funding_type in ["WALLET", "AP_CARD"]

        # ONLY process date for WALLET and AP_CARD (required)
        # For BANK_ACCOUNT and CHECK, let Bill.com set the date automatically
        if requires_process_date or not self.is_process_date_sync:
            # Use user-specified date or calculate default
            if self.billcom_process_date:
                date_obj = self.billcom_process_date
            else:
                # For WALLET/AP_CARD, default to today
                # For new vendor bank accounts, should be +2 business days but we'll
                # let Bill.com validate this (they return error if too soon)
                date_obj = fields.Date.today()

            # Convert to string format "YYYY-MM-DD"
            # CRITICAL: Bill.com requires exact format "YYYY-MM-DD"
            if isinstance(date_obj, str):
                # Already a string, validate format
                process_date = date_obj
            elif hasattr(date_obj, "strftime"):
                # Date/datetime object, convert to string
                process_date = date_obj.strftime("%Y-%m-%d")
            else:
                # Use Odoo's date conversion
                process_date = fields.Date.to_string(date_obj)

            # Validate the format
            if not process_date or not isinstance(process_date, str):
                raise UserError(
                    _(
                        "Invalid process date format. Expected YYYY-MM-DD string, got: %s"
                    )
                    % str(process_date)
                )

            _logger.info(
                "Payment processDate set to '%s' (type: %s) "
                "(funding_type=%s, required=%s)",
                process_date,
                type(process_date).__name__,
                funding_type,
                requires_process_date,
            )
        # Determine if we should create a bill or pay an existing one
        # If there's a linked bill with Bill.com ID, we pay it
        # Otherwise, Bill.com will create the bill automatically
        create_bill = not bill_id

        # Build payment data according to Bill.com API v3 format
        payment_data = {
            "vendorId": self.partner_id.billcom_id or self.partner_id.billcom,
            "amount": self.amount,
            "fundingAccount": funding_account_data,
            "processingOptions": {
                "createBill": create_bill,
                "requestPayFaster": self.billcom_pay_faster or False,
                "requestCheckDeliveryType": self.billcom_check_delivery_type
                or "STANDARD",
            },
        }

        # Add processDate if set (CRITICAL: Must be string in YYYY-MM-DD format)
        if process_date and isinstance(process_date, str) and len(process_date) == 10:
            payment_data["processDate"] = process_date
            _logger.info(f"Adding processDate to payment payload: '{process_date}'")
        elif requires_process_date:
            # WALLET and AP_CARD REQUIRE processDate
            raise UserError(
                _(
                    "Process date is required for %s funding type but was not set correctly. "
                    "Please set a valid process date (YYYY-MM-DD format)."
                )
                % funding_type
            )

        # Add bill ID if available (only when createBill is False)
        if bill_id:
            payment_data["billId"] = bill_id

        _logger.info(
            "Preparing payment: createBill=%s, billId=%s, vendor=%s, amount=%s",
            create_bill,
            bill_id or "None",
            self.partner_id.name,
            self.amount,
        )

        # Add optional description
        if self.ref:
            payment_data["description"] = self.ref

        # Add international payment options if needed
        if self.is_international_payment:
            payment_data["internationalOptions"] = {
                "paymentCurrency": self.currency_id.name,
            }
            # Add wire instructions if available
            if self.partner_id.bank_ids and self.partner_id.bank_ids[0].bank_id.bic:
                payment_data["internationalOptions"][
                    "wireInstructions"
                ] = self.partner_id.bank_ids[0].bank_id.bic

        # Final validation and logging
        _logger.info("=" * 80)
        _logger.info("FINAL PAYMENT DATA TO BILL.COM:")
        _logger.info(f"Payment: {self.name}")
        _logger.info(f"Vendor: {self.partner_id.name}")
        _logger.info(f"Amount: {self.amount}")
        _logger.info(f"Funding Type: {funding_type}")
        _logger.info(f"Process Date: {payment_data.get('processDate', 'NOT SET')}")
        _logger.info(f"Full payload: {payment_data}")
        _logger.info("=" * 80)

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
            if self.billcom_id or self.billcom:
                # For existing payments, we can only get the status
                # Bill.com API v3 doesn't support updating payments via PUT
                payment_id = self.billcom_id or self.billcom
                result = self.env["billcom.service"]._make_request(
                    f"payments/{payment_id}", method="GET"
                )

                # Log that we can't update the payment
                _logger.info(
                    "Payment %s already exists in Bill.com (ID: %s). "
                    "Bill.com API does not support updating existing payments.",
                    self.name,
                    payment_id,
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

                    # Post info message to chatter
                    self.message_post(
                        body=(
                            f"<p><strong>Bill.com Payment Status Updated</strong></p>"
                            f"<ul>"
                            f"<li>Bill.com ID: {payment_id}</li>"
                            f"<li>Status: {result.get('singleStatus')}</li>"
                            f"<li>Note: Payment already exists in Bill.com. "
                            f"API does not support updates.</li>"
                            f"</ul>"
                        ),
                        message_type="notification",
                        subtype_xmlid="mail.mt_note",
                    )
            else:
                # Create new payment
                result = self.env["billcom.service"]._make_request(
                    "payments", method="POST", data=payment_data
                )

            if result and result.get("id"):
                is_new = not (self.billcom_id or self.billcom)

                # Update payment with Bill.com data
                update_vals = {
                    "billcom": result.get("id"),
                    "billcom_id": result.get("id"),
                    "last_sync_date": fields.Datetime.now(),
                    "billcom_payment_status": self._map_billcom_status(
                        result.get("singleStatus")
                    ),
                    "billcom_confirmation_number": result.get("confirmationNumber", ""),
                    "billcom_transaction_number": result.get("transactionNumber", ""),
                    "billcom_sync_status": "synced",
                    "billcom_sync_error": False,  # Clear any previous error
                }

                # Update exchange rate and funding amount for international payments
                if result.get("exchangeRate"):
                    update_vals["billcom_exchange_rate"] = result.get("exchangeRate")
                if result.get("fundingAmount"):
                    update_vals["billcom_funding_amount"] = result.get("fundingAmount")

                self.with_context(skip_billcom_sync=True).write(update_vals)
                _logger.info("Successfully synced payment %s with Bill.com", self.name)

                # Post success message to chatter (only for new payments)
                if is_new:
                    self.message_post(
                        body=f"<p><strong>Bill.com Payment Created</strong></p>"
                        f"<ul>"
                        f"<li>Bill.com ID: {result.get('id')}</li>"
                        f"<li>Status: {result.get('singleStatus')}</li>"
                        f"<li>Confirmation #: {result.get('confirmationNumber', 'N/A')}</li>"
                        f"<li>Transaction #: {result.get('transactionNumber', 'N/A')}</li>"
                        f"</ul>",
                        message_type="notification",
                        subtype_xmlid="mail.mt_note",
                    )

                return result

            # Post error if no ID in response
            error_msg = (
                f"Unexpected response format from Bill.com API. Response: {result}"
            )
            self.with_context(skip_billcom_sync=True).write(
                {
                    "billcom_sync_status": "sync_failed",
                    "billcom_sync_error": error_msg,
                }
            )
            self.message_post(
                body=f"<p><strong>Bill.com Payment Sync Failed</strong></p>"
                f"<p>Unexpected response format from Bill.com API</p>"
                f"<p><em>Response: {result}</em></p>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )
            return False
        except Exception as e:
            error_detail = str(e)

            # Try to extract user-friendly error message
            service = self.env["billcom.service"]
            friendly_message = service._extract_friendly_error(e)

            _logger.error(
                "Error syncing payment %s to Bill.com: %s", self.name, error_detail
            )

            # Set sync status to failed
            self.with_context(skip_billcom_sync=True).write(
                {
                    "billcom_sync_status": "sync_failed",
                    "billcom_sync_error": friendly_message,
                }
            )

            # Post detailed error to chatter
            self.message_post(
                body=f"<p><strong>Bill.com Payment Sync Error</strong></p>"
                f"<p>Failed to sync payment to Bill.com</p>"
                f"<p><strong>Error:</strong></p>"  # noqa: E231
                f"<pre>{friendly_message}</pre>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            # Raise user-friendly error
            raise UserError(
                _("Failed to sync payment to Bill.com:\n\n%s") % friendly_message
            ) from e

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

    # def write(self, vals):
    #     """Override write to sync changes to Bill.com"""
    #     res = super().write(vals)
    #     if self.env.context.get("skip_billcom_sync"):
    #         return res

    #     for record in self:
    #         # Only sync if payment was created in Odoo (not from Bill.com)
    #         # Payments from Bill.com have billcom_id set
    #         if (
    #             record.is_sync_to_billcom
    #             and record.partner_id.is_sync_to_billcom
    #             and record.payment_type == "outbound"
    #             and record.partner_type == "supplier"
    #             and not record.billcom_id  # Skip if already synced from Bill.com
    #         ):
    #             try:
    #                 record.with_context(skip_billcom_sync=True).button_sync_to_billcom()
    #             except Exception as e:
    #                 _logger.error("Error syncing payment to Bill.com: %s", str(e))

    #     return res

    def action_get_payment_status(self):
        """Get payment status from Bill.com"""
        self.ensure_one()
        payment_id = self.billcom_id or self.billcom
        if not payment_id:
            raise UserError(_("This payment has not been synced with Bill.com yet."))

        try:
            result = self.env["billcom.service"]._make_request(
                f"payments/{payment_id}", method="GET"
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
            ) from e

    def action_cancel_billcom_payment(self):
        """Cancel payment in Bill.com"""
        self.ensure_one()
        payment_id = self.billcom_id or self.billcom
        if not payment_id:
            raise UserError(_("This payment has not been synced with Bill.com yet."))

        if self.billcom_payment_status not in ["draft", "scheduled"]:
            raise UserError(_("Only draft or scheduled payments can be canceled."))

        try:
            result = self.env["billcom.service"]._make_request(
                f"payments/{payment_id}/cancel", method="POST"
            )

            if result and result.get("id"):
                # Update payment with Bill.com data
                self.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_payment_status": "canceled",
                        "last_sync_date": fields.Datetime.now(),
                    }
                )
                # Cancel payment
                self.action_cancel()

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
            raise UserError(
                _("Error canceling payment in Bill.com: %s") % str(e)
            ) from e

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
                                body=_(
                                    "Bill.com payment status changed from %(old)s to %(new)s"
                                )
                                % {"old": old_status, "new": new_status},
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

        # Find the payment in Odoo (check billcom_id first, then billcom)
        payment = self.search([("billcom_id", "=", payment_id)], limit=1)
        if not payment:
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

            # Apply status mapping from Bill.com to Odoo state
            billcom_payment_status = payment_data.get("paymentStatus", "UNDEFINED")
            service = self.env["billcom.service"].sudo()
            target_state = service._map_billcom_payment_status_to_odoo_state(
                billcom_payment_status
            )

            if target_state == "posted" and payment.state == "draft":
                # Post the payment if Bill.com status requires it
                try:
                    payment.with_context(skip_billcom_sync=True).action_post()
                    _logger.info(
                        "Posted payment %s based on Bill.com status: %s (webhook)",
                        payment.name,
                        billcom_payment_status,
                    )
                except Exception as e:
                    _logger.warning(
                        "Could not post payment %s from Bill.com status %s "
                        "(webhook): %s",
                        payment.name,
                        billcom_payment_status,
                        e,
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
                        "Bill.com payment status changed from %(old)s to %(new)s (via webhook)"
                    )
                    % {"old": old_status, "new": new_status},
                    subtype_id=self.env.ref("mail.mt_note").id,
                )

            return True
        except Exception as e:
            _logger.error(
                "Error processing payment webhook for %s: %s", payment.name, str(e)
            )
            return False

    @api.model
    def sync_payment_status(self):
        # Get configuration
        try:
            config = self.env["billcom.config"].sudo().get_config()
            # Only run if the interval is greater than 0 and payment sync is enabled
            if (
                hasattr(config, "payment_status_check_interval")
                and config.payment_status_check_interval > 0
                and config.sync_payments
            ):
                self.update_billcom_payment_status()
            else:
                _logger.info("Bill.com payment status check is disabled")
        except Exception as e:
            _logger.error("Error in Bill.com payment status update: %s", str(e))

    def action_bulk_sync_to_billcom(self):
        if not self:
            raise UserError(_("No payments selected"))

        # Validate all payments before processing
        for payment in self:
            if (
                not payment.is_sync_to_billcom
                or not payment.partner_id.is_sync_to_billcom
            ):
                raise UserError(
                    _(
                        f"Payment {payment.name}s or vendor {payment.partner_id.name}s"
                        f"is not marked for Bill.com synchronization"
                    )
                )

            if payment.payment_type != "outbound" or payment.partner_type != "supplier":
                raise UserError(
                    _(
                        f"Payment {payment.name} is not a vendor payment"
                        f" (must be outbound supplier payment)"
                    )
                )

            # Check if payment has linked bill with Bill.com ID
            has_billcom_bill = False
            if payment.reconciled_bill_ids:
                for bill in payment.reconciled_bill_ids:
                    if bill.billcom_id or bill.billcom:
                        has_billcom_bill = True
                        break

            if not has_billcom_bill:
                raise UserError(
                    _(
                        "Payment %s does not have a linked bill with Bill.com ID. "
                        "Bulk payments can only pay existing bills. "
                        "Please sync the bill to Bill.com first or use single payment creation."
                    )
                    % payment.name
                )

        # Call bulk payment creation
        try:
            result = self.env["billcom.service"].create_bulk_payments(self)

            if result.get("success"):
                success_count = result.get("success_count", 0)
                error_count = result.get("error_count", 0)

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Bulk Payment Success"),
                        "message": _(
                            "Successfully processed %(success)d payments to Bill.com. "
                            "Errors: %(errors)d"
                        )
                        % {"success": success_count, "errors": error_count},
                        "type": "success" if error_count == 0 else "warning",
                        "sticky": False,
                    },
                }
            else:
                errors = result.get("errors", ["Unknown error"])
                error_message = "\n".join(errors)
                raise UserError(_("Bulk payment failed:\n\n%s") % error_message)

        except Exception as e:
            _logger.error("Bulk payment action error: %s", str(e))
            raise UserError(_("Bulk payment failed: %s") % str(e)) from e
