# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import hashlib
import hmac
import json
import logging

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class BillComController(http.Controller):
    def _handle_error(self, error):
        """Common error handler for endpoints"""
        _logger.error(str(error))
        return {"success": False, "error": str(error)}

    def _validate_webhook_signature(self, payload, signature, secret):
        """Validate webhook signature from Bill.com

        Bill.com signature validation process:
        1. HMAC-SHA256 hash of minified JSON payload
        2. Encode hash as base64 (NOT hexadecimal)
        3. Compare with x-bill-sha-signature header

        Reference: https://developer.bill.com/docs/test-with-webhook-security

        Args:
            payload (bytes): Raw webhook payload (minified JSON)
            signature (str): Value from x-bill-sha-signature header
            secret (str): securityKey from subscription response

        Returns:
            bool: True if signature is valid, False otherwise
        """
        if not secret:
            _logger.warning(
                "No webhook secret configured - skipping signature validation. "
                "Configure webhook_secret in Bill.com settings for security."
            )
            return True

        if not signature:
            _logger.error("Missing x-bill-sha-signature header in webhook request")
            return False

        try:
            # Ensure payload is bytes
            if isinstance(payload, str):
                payload = payload.encode("utf-8")

            # Compute HMAC-SHA256 hash and encode as base64
            hash_digest = hmac.new(
                secret.encode("utf-8"), payload, hashlib.sha256
            ).digest()

            expected_signature = base64.b64encode(hash_digest).decode("utf-8")

            # Secure comparison
            is_valid = hmac.compare_digest(expected_signature, signature)

            if not is_valid:
                _logger.error(
                    "⚠️  Webhook signature validation FAILED!\n"
                    "Expected (base64): %s...\n"
                    "Received: %s...\n"
                    "This may indicate a security issue or \
                        incorrect webhook_secret configuration.",
                    expected_signature[:30],
                    signature[:30],
                )
            else:
                _logger.info("✓ Webhook signature validated successfully")

            return is_valid

        except Exception as e:
            _logger.error(
                "Error validating webhook signature: %s", str(e), exc_info=True
            )
            return False

    def _get_config_from_organization_id(self, organization_id):
        """Get Bill.com configuration by organization ID from webhook metadata"""
        if not organization_id:
            return None

        config = (
            request.env["billcom.config"]
            .sudo()
            .search(
                [
                    ("organization_id", "=", organization_id),
                    ("active", "=", True),
                    ("enable_webhooks", "=", True),
                ],
                limit=1,
            )
        )

        return config

    def _extract_webhook_data(self, data):
        """Extract metadata and entity data from Bill.com webhook payload

        Bill.com API v3 webhook format:
        {
            "metadata": {
                "eventId": "...",
                "subscriptionId": "...",
                "organizationId": "...",
                "eventType": "bill.created",
                "version": "1"
            },
            "bill": { ... } / "vendor": { ... } / "payment": { ... }
        }
        """
        if not isinstance(data, dict):
            raise ValueError("Invalid webhook data format")

        # Extract metadata
        metadata = data.get("metadata", {})
        event_type = metadata.get("eventType")
        organization_id = metadata.get("organizationId")
        event_id = metadata.get("eventId")

        if not event_type:
            raise ValueError("No event type in metadata")
        if not organization_id:
            raise ValueError("No organization ID in metadata")

        # Extract entity data based on event type
        entity_data = None
        entity_id = None

        if event_type.startswith("bill."):
            entity_data = data.get("bill", {})
            entity_id = entity_data.get("id")
        elif event_type.startswith("vendor."):
            entity_data = data.get("vendor", {})
            entity_id = entity_data.get("id")
        elif event_type.startswith("payment.") or event_type.startswith("autopay."):
            entity_data = data.get("payment", {})
            entity_id = entity_data.get("id")
        elif event_type.startswith("bank-account."):
            entity_data = data.get("bankAccount", {})
            entity_id = entity_data.get("id")
        elif event_type.startswith("card-account."):
            entity_data = data.get("cardAccount", {})
            entity_id = entity_data.get("id")

        if not entity_id and entity_data:
            # For some events like payment.failed, entity_id might be in different location
            # or might not exist (bulk operations, failed operations, etc.)
            # In these cases, use a combination of event metadata for idempotency
            entity_id = f"event-{event_id}"
            _logger.warning(
                "No entity ID in payload for %s, using event_id: %s",
                event_type,
                event_id,
            )

        # Use event_id as idempotency key
        idempotency_key = event_id or f"{event_type}: {entity_id}"

        return {
            "event_type": event_type,
            "organization_id": organization_id,
            "entity_id": entity_id,
            "entity_data": entity_data,
            "idempotency_key": idempotency_key,
            "metadata": metadata,
        }

    def _handle_bill_webhook(self, event_type, entity_id, entity_data, config):
        """Handle bill-related webhook events"""
        if not config.sync_bills:
            _logger.warning("Bill sync disabled, ignoring webhook")
            return

        if event_type == "bill.archived":
            move = (
                request.env["account.move"]
                .sudo()
                .search(
                    ["|", ("billcom_id", "=", entity_id), ("billcom", "=", entity_id)],
                    limit=1,
                )
            )
            if move:
                move.with_context(skip_billcom_sync=True).write({"active": False})
                _logger.info("Archived bill %s in Odoo", entity_id)

        elif event_type == "bill.restored":
            move = (
                request.env["account.move"]
                .sudo()
                .with_context(active_test=False)
                .search(
                    ["|", ("billcom_id", "=", entity_id), ("billcom", "=", entity_id)],
                    limit=1,
                )
            )
            if move:
                move.with_context(skip_billcom_sync=True).write({"active": True})
                _logger.info("Restored bill %s in Odoo", entity_id)

        else:
            # For created/updated events, sync from Bill.com
            request.env["account.move"].sudo().sync_from_billcom(entity_id)
            _logger.info("Synced bill %s from Bill.com", entity_id)

    def _handle_vendor_webhook(self, event_type, entity_id, entity_data, config):
        """Handle vendor-related webhook events

        Vendor webhook includes complete vendor data:
        - Basic info: name, email, phone, address
        - Network info: networkStatus, paymentNetworkId, rppsId
        - Payment info: payByType, payeeName
        - Financial: balance, autoPay
        """
        if not config.sync_vendors:
            _logger.warning("Vendor sync disabled, ignoring webhook")
            return

        if event_type == "vendor.archived":
            partner = (
                request.env["res.partner"]
                .sudo()
                .search(
                    ["|", ("billcom_id", "=", entity_id), ("billcom", "=", entity_id)],
                    limit=1,
                )
            )
            if partner:
                partner.with_context(skip_billcom_sync=True).write({"active": False})
                _logger.info("Archived vendor %s in Odoo", entity_id)

        elif event_type == "vendor.restored":
            partner = (
                request.env["res.partner"]
                .sudo()
                .with_context(active_test=False)
                .search(
                    ["|", ("billcom_id", "=", entity_id), ("billcom", "=", entity_id)],
                    limit=1,
                )
            )
            if partner:
                partner.with_context(skip_billcom_sync=True).write({"active": True})
                _logger.info("Restored vendor %s in Odoo", entity_id)

        else:
            # For created/updated events, use the webhook entity data
            # This is more efficient than fetching from API again
            partner_model = request.env["res.partner"].sudo()

            # Find existing partner
            existing_partner = partner_model.search(
                ["|", ("billcom_id", "=", entity_id), ("billcom", "=", entity_id)],
                limit=1,
            )

            # Prepare partner values from webhook data
            address = entity_data.get("address", {})
            entity_data.get("paymentInformation", {})
            entity_data.get("additionalInfo", {})

            partner_vals = {
                "name": entity_data.get("name", "Unknown"),
                "email": entity_data.get("email", ""),
                "phone": entity_data.get("phone", ""),
                "street": address.get("line1", ""),
                "street2": address.get("line2", ""),
                "city": address.get("city", ""),
                "zip": address.get("zipOrPostalCode", ""),
                "billcom_id": entity_id,
                "billcom": entity_id,
                "last_sync_date": fields.Datetime.now(),
                "ref": entity_data.get("accountNumber")
                or entity_data.get("shortName", ""),
                "is_sync_to_billcom": True,
                "billcom_sync_state": "synced",
                "supplier_rank": 1,
                "customer_rank": 0,
                # Store additional Bill.com specific info in comment
                "comment": self._format_vendor_comment(entity_data),
            }

            # Set state/country
            if address.get("stateOrProvince"):
                state = (
                    request.env["res.country.state"]
                    .sudo()
                    .search([("code", "=", address["stateOrProvince"])], limit=1)
                )
                if state:
                    partner_vals["state_id"] = state.id

            if address.get("country"):
                country = (
                    request.env["res.country"]
                    .sudo()
                    .search([("code", "=", address["country"])], limit=1)
                )
                if country:
                    partner_vals["country_id"] = country.id

            if existing_partner:
                existing_partner.with_context(skip_billcom_sync=True).write(
                    partner_vals
                )
                _logger.info("Updated vendor %s from webhook", entity_data.get("name"))
            else:
                partner_model.with_context(skip_billcom_sync=True).create(partner_vals)
                _logger.info("Created vendor %s from webhook", entity_data.get("name"))

    def _format_vendor_comment(self, vendor_data):
        """Format vendor Bill.com information for comment field"""
        lines = ["=== Bill.com Vendor Info ==="]

        # Network status
        network_status = vendor_data.get("networkStatus", "NOT_CONNECTED")
        lines.append(f"Network Status: {network_status}")

        if vendor_data.get("paymentNetworkId"):
            lines.append(f"Payment Network ID: {vendor_data['paymentNetworkId']}")
        if vendor_data.get("rppsId"):
            lines.append(f"RPPS ID: {vendor_data['rppsId']}")

        # Payment information
        payment_info = vendor_data.get("paymentInformation", {})
        if payment_info:
            pay_by_type = payment_info.get("payByType", "CHECK")
            lines.append(f"Payment Type: {pay_by_type}")
            if payment_info.get("lastPaymentDate"):
                lines.append(f"Last Payment: {payment_info['lastPaymentDate'][:10]}")

        # Balance
        balance = vendor_data.get("balance", {})
        if balance and balance.get("amount") is not None:
            lines.append(f"Balance: ${balance['amount']: .2f}")
            if balance.get("lastUpdatedDate"):
                lines.append(f"Balance Updated: {balance['lastUpdatedDate'][:10]}")

        # AutoPay
        auto_pay = vendor_data.get("autoPay", {})
        if auto_pay.get("enabled"):
            lines.append("AutoPay: Enabled")

        # Additional info
        additional_info = vendor_data.get("additionalInfo", {})
        if additional_info:
            if additional_info.get("track1099"):
                lines.append("Track 1099: Yes")
            if additional_info.get("combinePayments"):
                lines.append("Combine Payments: Yes")

        return "\n".join(lines)

    def _handle_payment_webhook(self, event_type, entity_id, entity_data, config):
        """Handle payment-related webhook events

        Payment webhook includes complete payment data:
        - payment.updated: Status changes (SCHEDULED, PROCESSED, etc.)
        - payment.failed: Payment creation/processing failures
        - autopay.failed: Automatic payment failures

        Payment Status Values:
        - SCHEDULED: Payment scheduled for processing
        - PROCESSED: Payment has been processed
        - DELIVERED: Payment delivered to vendor
        - RETURNED: Payment returned/failed
        """
        if not config.sync_payments:
            _logger.warning("Payment sync disabled, ignoring webhook")
            return

        if event_type == "payment.failed":
            # Handle payment failure
            self._handle_payment_failed(entity_data)
        elif event_type == "autopay.failed":
            # Handle automatic payment failure (similar to payment.failed)
            self._handle_autopay_failed(entity_data)
        elif event_type == "payment.updated":
            # Handle payment status update using webhook data directly
            self._handle_payment_updated(entity_id, entity_data)
        else:
            _logger.warning("Unhandled payment event type: %s", event_type)

    def _handle_payment_failed(self, payment_data):
        """Handle payment.failed webhook

        Payment failed includes:
        - bills: List of bills that were in the failed payment
        - vendor: Vendor information
        - fundingAccount: Funding account used
        - errors: List of error messages

        This handler updates payment status, creates activities, and posts to chatter
        """
        vendor_info = payment_data.get("vendor", {})
        errors = payment_data.get("errors", [])
        transaction_number = payment_data.get("transactionNumber")
        bills = payment_data.get("bills", [])

        error_messages = [
            f"{err.get('message', 'Unknown error')} ({err.get('code', 'N/A')})"
            for err in errors
        ]
        error_text = "; ".join(error_messages)

        _logger.error(
            "Payment failed for vendor %s (transaction: %s). Errors: %s",
            vendor_info.get("name", "Unknown"),
            transaction_number,
            error_text,
        )

        # Find related payments by bill IDs
        if bills:
            bill_ids = [bill.get("billId") for bill in bills if bill.get("billId")]

            if bill_ids:
                # Find bills in Odoo
                moves = (
                    request.env["account.move"]
                    .sudo()
                    .search(
                        [
                            "|",
                            ("billcom_id", "in", bill_ids),
                            ("billcom", "in", bill_ids),
                        ]
                    )
                )

                for move in moves:
                    # Find related payments through reconciled move lines
                    payments = move.line_ids.filtered(
                        lambda line: line.account_id.account_type
                        in ("asset_receivable", "liability_payable")
                    ).mapped("matched_debit_ids.debit_move_id.payment_id")

                    payments |= move.line_ids.filtered(
                        lambda line: line.account_id.account_type
                        in ("asset_receivable", "liability_payable")
                    ).mapped("matched_credit_ids.credit_move_id.payment_id")

                    # Also check reconciled_bill_ids field if available
                    if hasattr(move, "payment_id") and move.payment_id:
                        payments |= move.payment_id

                    for payment in payments.filtered(
                        lambda p: p.is_sync_to_billcom
                        and p.billcom_sync_status != "sync_failed"
                    ):
                        # Update payment status to failed
                        payment.with_context(skip_billcom_sync=True).write(
                            {
                                "billcom_payment_status": "failed",
                                "billcom_sync_status": "sync_failed",
                                "billcom_sync_error": error_text,
                                "billcom_transaction_number": transaction_number or "",
                            }
                        )

                        # Post error message to payment chatter
                        payment.message_post(
                            body=(
                                f"<p><strong>Bill.com Payment Failed</strong></p>"
                                f"<p><strong>Vendor: </strong> "
                                f"{vendor_info.get('name', 'Unknown')}</p>"
                                f"<p><strong>Transaction: </strong> "
                                f"{transaction_number or 'N/A'}</p>"
                                f"<p><strong>Errors: </strong></p>"
                                f"<ul>"
                                f"{''.join([f'<li>{msg}</li>' for msg in error_messages])}"
                                f"</ul>"
                                f"<p><em>Please review and retry the payment or "
                                f"contact Bill.com support.</em></p>"
                            ),
                            message_type="notification",
                            subtype_xmlid="mail.mt_note",
                        )

                        # Create activity for payment owner or accounting manager
                        activity_user = payment.create_uid
                        if not activity_user:
                            # Fallback to first user in Invoicing group
                            invoicing_group = request.env.ref(
                                "account.group_account_invoice",
                                raise_if_not_found=False,
                            )
                            if invoicing_group and invoicing_group.users:
                                activity_user = invoicing_group.users[0]

                        if activity_user:
                            try:
                                note = f"Bill.com payment failed with transaction\
                                     number {transaction_number or 'N/A'}."
                                payment.activity_schedule(
                                    "mail.mail_activity_data_warning",
                                    summary=f"Payment failed: \
                                    {vendor_info.get('name', 'Unknown')}",
                                    note=note,
                                    user_id=activity_user.id,
                                )
                                _logger.info(
                                    "Created activity for failed payment %s (user: %s)",
                                    payment.name,
                                    activity_user.name,
                                )
                            except Exception as e:
                                _logger.warning(
                                    "Could not create activity for failed payment %s: %s",
                                    payment.name,
                                    str(e),
                                )

                        _logger.info(
                            "Updated payment %s status to failed (Bill: %s)",
                            payment.name,
                            move.name,
                        )

                    # Also post message to bill
                    move.message_post(
                        body=(
                            f"<p><strong>Bill.com Payment Failed</strong></p>"
                            f"<p><strong>Transaction: </strong> "
                            f"{transaction_number or 'N/A'}</p>"
                            f"<p><strong>Errors: </strong></p>"
                            f"<ul>{''.join([f'<li>{msg}</li>' for msg in error_messages])}</ul>"
                        ),
                        message_type="notification",
                        subtype_xmlid="mail.mt_note",
                    )
        else:
            _logger.warning(
                "No bill IDs provided in payment.failed webhook for transaction %s",
                transaction_number,
            )

    def _handle_autopay_failed(self, payment_data):
        """Handle autopay.failed webhook

        Autopay failed has similar structure to payment.failed:
        - bills: List of bills in the failed autopay request
        - vendor: Vendor information
        - errors: List of error messages

        Autopay failures are treated similarly to payment failures but with
        specific messaging about the automatic payment feature.
        """
        vendor_info = payment_data.get("vendor", {})
        errors = payment_data.get("errors", [])
        transaction_number = payment_data.get("transactionNumber")
        bills = payment_data.get("bills", [])

        error_messages = [
            f"{err.get('message', 'Unknown error')} ({err.get('code', 'N/A')})"
            for err in errors
        ]
        error_text = "; ".join(error_messages)

        _logger.error(
            "AutoPay failed for vendor %s (transaction: %s). Errors: %s",
            vendor_info.get("name", "Unknown"),
            transaction_number,
            error_text,
        )

        # Find related payments by bill IDs (same logic as payment.failed)
        if bills:
            bill_ids = [bill.get("billId") for bill in bills if bill.get("billId")]

            if bill_ids:
                # Find bills in Odoo
                moves = (
                    request.env["account.move"]
                    .sudo()
                    .search(
                        [
                            "|",
                            ("billcom_id", "in", bill_ids),
                            ("billcom", "in", bill_ids),
                        ]
                    )
                )

                for move in moves:
                    # Find related payments
                    payments = move.line_ids.filtered(
                        lambda line: line.account_id.account_type
                        in ("asset_receivable", "liability_payable")
                    ).mapped("matched_debit_ids.debit_move_id.payment_id")

                    payments |= move.line_ids.filtered(
                        lambda line: line.account_id.account_type
                        in ("asset_receivable", "liability_payable")
                    ).mapped("matched_credit_ids.credit_move_id.payment_id")

                    if hasattr(move, "payment_id") and move.payment_id:
                        payments |= move.payment_id

                    for payment in payments.filtered(
                        lambda p: p.is_sync_to_billcom
                        and p.billcom_sync_status != "sync_failed"
                    ):
                        # Update payment status to failed
                        payment.with_context(skip_billcom_sync=True).write(
                            {
                                "billcom_payment_status": "failed",
                                "billcom_sync_status": "sync_failed",
                                "billcom_sync_error": f"AutoPay Failed: {error_text}",
                                "billcom_transaction_number": transaction_number or "",
                            }
                        )

                        # Post error message to payment chatter (with AutoPay context)
                        payment.message_post(
                            body=f"<p><strong>Bill.com AutoPay Failed</strong></p>"
                            f"<p><strong>Vendor: </strong>"
                            f"{vendor_info.get('name', 'Unknown')}</p>"  # noqa: E231
                            f"<p><strong>Transaction: </strong> "
                            f"{transaction_number or 'N/A'}</p>"  # noqa: E231
                            f"<p><strong>Errors: </strong></p>"  # noqa: E231
                            f"<ul>{''.join([f'<li>{msg}</li>' for msg in error_messages])}</ul>"
                            f"<p><em>Automatic payment failed. Please review autopay settings "
                            f"or manually process the payment.</em></p>",
                            message_type="notification",
                            subtype_xmlid="mail.mt_note",
                        )

                        # Create activity for payment owner
                        activity_user = payment.create_uid
                        if not activity_user:
                            invoicing_group = request.env.ref(
                                "account.group_account_invoice",
                                raise_if_not_found=False,
                            )
                            if invoicing_group and invoicing_group.users:
                                activity_user = invoicing_group.users[0]

                        if activity_user:
                            summary = (
                                f"AutoPay failed: {vendor_info.get('name', 'Unknown')}"
                            )
                            note = f"Bill.com automatic payment failed (transaction: \
                                {transaction_number or 'N/A'})."
                            try:
                                payment.activity_schedule(
                                    "mail.mail_activity_data_warning",
                                    summary=summary,
                                    note=note,
                                    user_id=activity_user.id,
                                )
                                _logger.info(
                                    "Created activity for failed autopay %s (user: %s)",
                                    payment.name,
                                    activity_user.name,
                                )
                            except Exception as e:
                                _logger.warning(
                                    "Could not create activity for failed autopay %s: %s",
                                    payment.name,
                                    str(e),
                                )

                        _logger.info(
                            "Updated payment %s status to failed (AutoPay, Bill: %s)",
                            payment.name,
                            move.name,
                        )

                    # Post message to bill
                    move.message_post(
                        body=(
                            f"<p><strong>Bill.com AutoPay Failed</strong></p>"
                            f"<p><strong>Transaction: </strong>"
                            f"{transaction_number or 'N/A'}</p>"
                            f"<p><strong>Errors: </strong></p>"
                            f"<ul>{''.join([f'<li>{msg}</li>' for msg in error_messages])}</ul>"
                            f"<p><em>Automatic payment failed."
                            f"Manual payment may be required.</em></p>"
                        ),
                        message_type="notification",
                        subtype_xmlid="mail.mt_note",
                    )

        else:
            _logger.warning(
                "No bill IDs provided in autopay.failed webhook for transaction %s",
                transaction_number,
            )

    def _handle_payment_updated(self, entity_id, payment_data):
        """Handle payment.updated webhook

        Uses webhook data directly instead of making additional API call.
        This improves performance and ensures data accuracy.
        """
        payment_status = payment_data.get("status")
        bill_ids = payment_data.get("billIds", [])
        vendor_info = payment_data.get("vendor", {})
        funding = payment_data.get("funding", {})
        disbursement = payment_data.get("disbursement", {})

        _logger.info(
            "Payment %s updated - Status: %s, Vendor: %s, Bills: %s",
            entity_id,
            payment_status,
            vendor_info.get("name"),
            len(bill_ids),
        )

        # Log detailed payment information
        if payment_status == "SCHEDULED":
            arrives_by = disbursement.get("arrivesByDate")
            _logger.info(
                "Payment %s scheduled - Arrives by: %s, Amount: %s %s",
                entity_id,
                arrives_by,
                funding.get("amount"),
                funding.get("currency", "USD"),
            )
        elif payment_status == "PROCESSED":
            disbursement_account = disbursement.get("disbursementAccount", {})
            _logger.info(
                "Payment %s processed - Disbursement type: %s, Account: %s",
                entity_id,
                disbursement_account.get("type"),
                disbursement_account.get("accountNumber", "N/A"),
            )

        # Try to process with existing method if available
        try:
            result = (
                request.env["account.payment"]
                .sudo()
                .process_billcom_payment_webhook(payment_data)
            )
            if result:
                _logger.info(
                    "Successfully processed payment webhook for ID: %s", entity_id
                )
            else:
                _logger.warning(
                    "process_billcom_payment_webhook returned False for ID: %s",
                    entity_id,
                )
        except AttributeError:
            # Method doesn't exist yet, just log the webhook data
            _logger.info(
                "Payment webhook processed (logging only): %s - %s",
                entity_id,
                payment_status,
            )

    def _handle_card_account_webhook(self, event_type, entity_id, entity_data, config):
        """Handle card-account-related webhook events

        Card account webhook includes (for BILL Spend Cards):
        - id: Card account ID
        - status: Status of the card account
        - type: Card type
        - cardNumber: Masked card number (last 4 digits)
        - cardholder: Name on card
        - expirationDate: Card expiration date
        - default settings: Default for payables/receivables

        Events:
        - card-account.created: New card account added
        - card-account.updated: Card account modified (status, defaults, etc.)
        """
        card_account_id = entity_data.get("id")
        status = entity_data.get("status")
        card_number = entity_data.get("cardNumber", "N/A")
        cardholder = entity_data.get("cardholder", "Unknown")
        expiration = entity_data.get("expirationDate", "N/A")
        default_settings = entity_data.get("default", {})

        _logger.info(
            "Card Account webhook - Event: %s, ID: %s, Status: %s, Cardholder: %s, Card: %s",
            event_type,
            card_account_id,
            status,
            cardholder,
            card_number,
        )

        if event_type == "card-account.created":
            _logger.info(
                "New card account created - Cardholder: %s, Card: %s, Expires: %s",
                cardholder,
                card_number,
                expiration,
            )

        elif event_type == "card-account.updated":
            _logger.info(
                "Card account %s updated - Status: %s, Cardholder: %s",
                card_account_id,
                status,
                cardholder,
            )

            # Log default settings changes
            if default_settings.get("payables"):
                _logger.info(
                    "Card account %s set as DEFAULT for PAYABLES (AP)", card_account_id
                )
            if default_settings.get("receivables"):
                _logger.info(
                    "Card account %s set as DEFAULT for RECEIVABLES (AR)",
                    card_account_id,
                )

        # TODO: Optionally sync to Odoo
        # This would require:
        # 1. Create billcom.card.account model to track cards
        # 2. Store card account ID, masked number, status
        # 3. Link to company/user
        # 4. Track default settings

    def _handle_bank_account_webhook(self, event_type, entity_id, entity_data, config):
        """Handle bank-account-related webhook events

        Bank account webhook includes:
        - id: Bank account ID (starts with 'bac')
        - status: NOT_VERIFIED, VERIFIED, PENDING, BLOCKED, EXPIRED, INVALID, UNDEFINED
        - type: CHECKING or SAVINGS
        - ownerType: BUSINESS or PERSONAL
        - default.payables: Default for AP operations
        - default.receivables: Default for AR operations

        Status Rules:
        - VERIFIED + archived=false: Active verified account
        - NOT_VERIFIED/PENDING/EXPIRED/BLOCKED + archived=true: Inactive account
        """
        bank_account_id = entity_data.get("id")
        status = entity_data.get("status")
        archived = entity_data.get("archived", False)
        account_number = entity_data.get("accountNumber", "N/A")
        name_on_account = entity_data.get("nameOnAccount", "Unknown")
        bank_name = entity_data.get("bankName", "Unknown")
        account_type = entity_data.get("type", "CHECKING")
        owner_type = entity_data.get("ownerType", "BUSINESS")
        default_settings = entity_data.get("default", {})

        _logger.info(
            "Bank Account webhook - Event: %s, ID: %s, Status: %s, Archived: %s, Name: %s",
            event_type,
            bank_account_id,
            status,
            archived,
            name_on_account,
        )

        if event_type == "bank-account.created":
            _logger.info(
                "New bank account created - Bank: %s, Type: %s, Owner: %s, Account: %s",
                bank_name,
                account_type,
                owner_type,
                account_number,
            )

        elif event_type == "bank-account.updated":
            # Log status changes
            if status == "VERIFIED" and not archived:
                _logger.info(
                    "Bank account %s VERIFIED and activated - %s at %s",
                    bank_account_id,
                    name_on_account,
                    bank_name,
                )
            elif status == "NOT_VERIFIED" and archived:
                _logger.warning(
                    "Bank account %s verification FAILED - account archived",
                    bank_account_id,
                )
            elif status in ("PENDING", "EXPIRED", "BLOCKED") and archived:
                _logger.warning(
                    "Bank account %s status: %s - account archived",
                    bank_account_id,
                    status,
                )

            # Log default settings changes
            if default_settings.get("payables"):
                _logger.info(
                    "Bank account %s set as DEFAULT for PAYABLES (AP)", bank_account_id
                )
            if default_settings.get("receivables"):
                _logger.info(
                    "Bank account %s set as DEFAULT for RECEIVABLES (AR)",
                    bank_account_id,
                )

        # TODO: Optionally sync to Odoo res.partner.bank
        # This would require:
        # 1. Find/create partner bank account
        # 2. Store Bill.com bank account ID
        # 3. Update status and default settings
        # 4. Handle archived state

    @http.route("/billcom/webhook", type="json", auth="none", csrf=False)
    def webhook(self):  # noqa: C901
        """Endpoint to receive webhooks from Bill.com

        Bill.com API v3 webhook format with metadata:
        {
            "metadata": {
                "eventId": "unique-event-id",
                "organizationId": "org-id",
                "eventType": "bill.created",
                "version": "1"
            },
            "bill": { ... }
        }
        """
        webhook_log = None
        try:
            data = request.get_json_data()
            _logger.info("Received Bill.com webhook: %s", json.dumps(data, indent=2))

            # Extract webhook data (event type, organization ID, entity ID, etc.)
            webhook_info = self._extract_webhook_data(data)
            event_type = webhook_info["event_type"]
            organization_id = webhook_info["organization_id"]
            entity_id = webhook_info["entity_id"]
            idempotency_key = webhook_info["idempotency_key"]

            # Get configuration by organization ID (not company)
            config = self._get_config_from_organization_id(organization_id)
            if not config:
                error_msg = f"No active Bill.com configuration\
                     found for organization {organization_id}"
                _logger.error(error_msg)
                return {"success": False, "error": error_msg}

            # Validate webhook signature if secret is configured
            signature_valid = True
            if config.webhook_secret:
                # Bill.com uses x-bill-sha-signature header (official documentation)
                signature = request.httprequest.headers.get("x-bill-sha-signature")
                payload = request.httprequest.get_data()
                signature_valid = self._validate_webhook_signature(
                    payload, signature, config.webhook_secret
                )
                if not signature_valid:
                    _logger.error("Invalid webhook signature from Bill.com")
                    return {"success": False, "error": "Invalid signature"}

            # Check for idempotency - prevent duplicate processing
            webhook_log_model = request.env["billcom.webhook.log"].sudo()
            if webhook_log_model.check_duplicate(idempotency_key):
                _logger.info(
                    "Duplicate webhook %s - already processed", idempotency_key
                )
                return {
                    "success": True,
                    "message": f"Webhook {idempotency_key} already processed",
                }

            # Create webhook log
            webhook_log = webhook_log_model.log_webhook(
                event_type=event_type,
                entity_id=entity_id,
                webhook_data=json.dumps(data),
                signature_valid=signature_valid,
                idempotency_key=idempotency_key,
            )

            if not webhook_log:
                return {"success": True, "message": "Webhook already processed"}

            webhook_log.mark_processing()

            # Route to appropriate handler based on event type
            if event_type.startswith("bill."):
                self._handle_bill_webhook(
                    event_type, entity_id, webhook_info["entity_data"], config
                )
            elif event_type.startswith("vendor."):
                self._handle_vendor_webhook(
                    event_type, entity_id, webhook_info["entity_data"], config
                )
            elif event_type.startswith("payment.") or event_type.startswith("autopay."):
                self._handle_payment_webhook(
                    event_type, entity_id, webhook_info["entity_data"], config
                )
            elif event_type.startswith("bank-account."):
                self._handle_bank_account_webhook(
                    event_type, entity_id, webhook_info["entity_data"], config
                )
            elif event_type.startswith("card-account."):
                self._handle_card_account_webhook(
                    event_type, entity_id, webhook_info["entity_data"], config
                )
            else:
                error_msg = f"Unhandled event type: {event_type}"
                _logger.warning(error_msg)
                webhook_log.mark_error(error_msg)
                return {"success": False, "error": error_msg}

            # Mark webhook as successfully processed
            webhook_log.mark_success()
            return {"success": True, "message": f"Successfully processed {event_type}"}

        except ValidationError as ve:
            _logger.error("Validation error in webhook: %s", str(ve))
            if webhook_log:
                webhook_log.mark_error(f"Validation error: {str(ve)}")
            return self._handle_error(ve)
        except UserError as ue:
            _logger.error("User error in webhook: %s", str(ue))
            if webhook_log:
                webhook_log.mark_error(f"User error: {str(ue)}")
            return self._handle_error(ue)
        except Exception as e:
            _logger.error("Unexpected error in webhook: %s", str(e), exc_info=True)
            if webhook_log:
                webhook_log.mark_error(f"Unexpected error: {str(e)}")
            return self._handle_error(e)

    @http.route("/billcom/api/sync", type="json", auth="user")
    def sync(self):
        """Sync data with Bill.com"""
        try:
            service = request.env["billcom.service"].sudo()
            result = service.sync_all()
            return {"success": True, "results": result}
        except Exception as e:
            return self._handle_error(e)
