# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "billcom.abstract.model"]

    # Bill.com specific fields for bills/invoices
    billcom_status = fields.Char(
        string="Bill.com Status",
        help="Payment status from Bill.com (PAID, UNPAID, PARTIALLY_PAID, etc.)",
        readonly=True,
    )
    billcom_document_ids = fields.One2many(
        "billcom.document",
        "bill_id",
        string="Bill.com Documents",
        help="Documents attached to this bill in Bill.com",
    )
    billcom_invoice_number = fields.Char(
        string="Bill.com Invoice Number",
    )
    billcom_payment_link = fields.Char(
        string="Bill.com Payment Link",
        help="Payment link for customer to pay invoice online",
        readonly=True,
        copy=False,
    )

    active = fields.Boolean()

    def _prepare_bill_data(self, for_bulk=False):
        """Prepare bill data for Bill.com API

        Args:
            for_bulk: If True, includes additional fields required for bulk endpoint
        """
        self.ensure_one()
        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.move_type != "in_invoice":
            return False

        # Get billcom.item model for tax mapping
        item_model = self.env["billcom.item"]

        # Prepare line items
        lines = []
        for line in self.invoice_line_ids:
            line_data = {
                "description": line.name or "",
                "amount": line.price_total,  # Tax included in amount
            }

            # Add tax items if line has taxes
            if line.tax_ids:
                for tax in line.tax_ids:
                    # Get or create Bill.com item for this tax
                    tax_item_id = item_model.get_item_for_tax(tax)
                    if tax_item_id:
                        line_data["itemId"] = tax_item_id
                        _logger.info(
                            "Added tax item %s to bill line for tax %s",
                            tax_item_id,
                            tax.name,
                        )
                        break  # Use first tax item found

            lines.append(line_data)

        # Build bill data according to Bill.com API v3 format
        bill_data = {
            "vendorId": self.partner_id.billcom_id or self.partner_id.billcom,
            "billLineItems": lines,
            "invoice": {
                "invoiceNumber": self.billcom_invoice_number or self.name or "",
                "purchaseOrderNumber": self.invoice_origin or "",
                "invoiceDate": (
                    self.invoice_date.isoformat() if self.invoice_date else ""
                ),
            },
        }

        # Add dueDate if available
        if self.invoice_date_due:
            bill_data["dueDate"] = self.invoice_date_due.isoformat()

        # For bulk endpoint, add required fields
        if for_bulk:
            billcom_id = self.billcom_id or self.billcom
            if not billcom_id:
                return False  # Bulk only supports existing bills

            bill_data["id"] = billcom_id
            bill_data["archived"] = False  # Default to not archived

        return bill_data

    def _prepare_invoice_data(self):
        """Prepare invoice data for Bill.com API"""
        self.ensure_one()
        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.move_type != "out_invoice":
            return False

        # Get billcom.item model for tax mapping
        item_model = self.env["billcom.item"]

        # Prepare line items
        lines = []
        for line in self.invoice_line_ids:
            line_data = {
                "description": line.name or "",
                "quantity": line.quantity,
                "price": line.price_unit,
            }

            # Priority 1: include itemId if product has Bill.com reference
            if (
                line.product_id
                and hasattr(line.product_id, "billcom_id")
                and line.product_id.billcom_id
            ):
                line_data["itemId"] = line.product_id.billcom_id
            # Priority 2: Add tax items if line has taxes and no product item
            elif line.tax_ids:
                for tax in line.tax_ids:
                    # Get or create Bill.com item for this tax
                    tax_item_id = item_model.get_item_for_tax(tax)
                    if tax_item_id:
                        line_data["itemId"] = tax_item_id
                        _logger.info(
                            "Added tax item %s to invoice line for tax %s",
                            tax_item_id,
                            tax.name,
                        )
                        break  # Use first tax item found

            lines.append(line_data)

        # Build invoice data according to Bill.com API v3 format
        # Only include required fields - API calculates totalAmount and assigns status
        invoice_data = {
            "customer": {"id": self.partner_id.billcom_id or self.partner_id.billcom},
            "invoiceLineItems": lines,
            "invoiceNumber": self.name or "",
            "processingOptions": {"sendEmail": False},  # Don't send email by default
        }

        # Add dueDate if available
        if self.invoice_date_due:
            invoice_data["dueDate"] = self.invoice_date_due.isoformat()

        return invoice_data

    def _find_existing_billcom_document(self, endpoint, document_number):
        """Search Bill.com for existing document by number

        Args:
            endpoint: 'invoices' or 'bills'
            document_number: The invoice/bill number to search for

        Returns:
            Bill.com ID if found, None otherwise
        """
        try:
            # Build search parameters based on endpoint type
            if endpoint == "invoices":
                params = {"invoiceNumber": document_number}
            elif endpoint == "bills":
                params = {"invoiceNumber": document_number}
            else:
                return None

            # Search for existing document
            result = self.env["billcom.service"]._make_request(
                endpoint, method="GET", params=params
            )

            # Check if we found any results
            if result and isinstance(result, list) and len(result) > 0:
                return result[0].get("id")
            elif result and isinstance(result, dict) and result.get("id"):
                return result.get("id")

            return None

        except Exception as e:
            _logger.warning(
                "Error searching for existing %s with number %s: %s",
                endpoint,
                document_number,
                str(e),
            )
            return None

    def button_sync_to_billcom(self):
        """Sync document(s) to Bill.com - supports single and bulk operations"""
        # Handle multiple records with bulk endpoint
        if len(self) > 1:
            return self._sync_bulk_to_billcom()

        # Single record sync
        self.ensure_one()

        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.move_type not in ["in_invoice", "out_invoice"]:
            return False

        try:
            endpoint = ""
            data = {}

            if self.move_type == "in_invoice":
                endpoint = "bills"
                data = self._prepare_bill_data()
            else:
                endpoint = "invoices"
                data = self._prepare_invoice_data()

            if not data:
                return False

            # Determine if we should update or create
            existing_id = self.billcom_id or self.billcom

            # If no ID in Odoo, check if document exists in Bill.com by number
            if not existing_id:
                existing_id = self._find_existing_billcom_document(endpoint, self.name)
                if existing_id:
                    _logger.info(
                        "Found existing %s in Bill.com with number %s (ID: %s)",
                        endpoint,
                        self.name,
                        existing_id,
                    )

            if existing_id:
                # Update existing document
                _logger.info(
                    "Updating existing %s with ID %s in Bill.com", endpoint, existing_id
                )
                result = self.env["billcom.service"]._make_request(
                    f"{endpoint}/{existing_id}", method="PUT", data=data
                )
            else:
                # Create new document
                _logger.info("Creating new %s in Bill.com", endpoint)
                result = self.env["billcom.service"]._make_request(
                    endpoint, method="POST", data=data
                )

            if result and result.get("id"):
                action = "updated" if existing_id else "created"
                doc_type = "Bill" if self.move_type == "in_invoice" else "Invoice"

                self.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom": result.get("id"),
                        "billcom_id": result.get("id"),
                        "last_sync_date": fields.Datetime.now(),
                        "billcom_sync_status": "synced",
                        "billcom_sync_error": False,
                    }
                )
                _logger.info("Successfully synced %s with Bill.com", self.name)

                # Post success message to chatter
                self.message_post(
                    body=f"<p><strong>Bill.com Sync Successful</strong></p>"
                    f"<ul>"
                    f"<li>Type: {doc_type}</li>"
                    f"<li>Action: {action.title()}</li>"
                    f"<li>Bill.com ID: {result.get('id')}</li>"
                    f"<li>Document Number: {self.name}</li>"
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
                body=f"<p><strong>Bill.com Sync Failed</strong></p>"
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

            _logger.error("Error syncing %s to Bill.com: %s", self.name, error_detail)

            # Set sync status to failed
            self.with_context(skip_billcom_sync=True).write(
                {
                    "billcom_sync_status": "sync_failed",
                    "billcom_sync_error": friendly_message,
                }
            )

            # Post detailed error to chatter
            self.message_post(
                body=f"<p><strong>Bill.com Sync Error</strong></p>"
                f"<p>Failed to sync document to Bill.com</p>"
                f"<p><strong>Error:</strong></p>"  # noqa: E231
                f"<pre>{friendly_message}</pre>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            # Raise user-friendly error
            raise UserError(
                _("Failed to sync document to Bill.com:\n\n%s") % friendly_message
            ) from e

    def _sync_bulk_to_billcom(self):  # noqa: C901
        """Sync multiple documents to Bill.com

        - Bills (in_invoice) with billcom_id: Use bulk endpoint for updates
        - Bills (in_invoice) without billcom_id: Create individually
        - Invoices (out_invoice): Always sync individually (no bulk support)
        """
        # Separate bills and invoices
        bills = self.filtered(lambda m: m.move_type == "in_invoice")
        invoices = self.filtered(lambda m: m.move_type == "out_invoice")

        total_success = 0
        total_errors = 0

        # Process invoices individually (no bulk support)
        if invoices:
            _logger.info(
                "Syncing %d invoice(s) individually (bulk not supported for invoices)...",
                len(invoices),
            )
            for invoice in invoices:
                try:
                    invoice.button_sync_to_billcom()
                    total_success += 1
                except Exception as e:
                    total_errors += 1
                    _logger.error("Error syncing invoice %s: %s", invoice.name, str(e))

        if not bills:
            # Only invoices were processed
            if total_errors > 0:
                raise UserError(
                    _(
                        "Invoice sync completed with errors:\n\n"
                        "✓ Succeeded: %(success)d\n"
                        "✗ Failed: %(errors)d"
                    )
                    % {"success": total_success, "errors": total_errors}
                )
            return True

        # Filter bills that should be synced
        bills_to_sync = bills.filtered(
            lambda b: b.is_sync_to_billcom and b.partner_id.is_sync_to_billcom
        )

        if not bills_to_sync:
            if invoices:
                # Already processed invoices
                return True
            raise UserError(_("No documents selected for synchronization to Bill.com"))

        # Separate existing bills (for bulk update) from new bills (for individual creation)
        existing_bills = bills_to_sync.filtered(lambda b: b.billcom_id or b.billcom)
        new_bills = bills_to_sync - existing_bills

        _logger.info(
            "Processing %d bill(s): %d existing (bulk), %d new (individual)",
            len(bills_to_sync),
            len(existing_bills),
            len(new_bills),
        )

        # Process new bills individually
        if new_bills:
            _logger.info("Creating %d new bill(s) individually...", len(new_bills))
            for bill in new_bills:
                try:
                    bill.button_sync_to_billcom()
                    total_success += 1
                except Exception as e:
                    total_errors += 1
                    _logger.error("Error creating bill %s: %s", bill.name, str(e))

        # Process existing bills in bulk
        if existing_bills:
            try:
                bulk_success, bulk_errors = self._sync_existing_bills_bulk(
                    existing_bills
                )
                total_success += bulk_success
                total_errors += bulk_errors
            except Exception as e:
                _logger.error("Error in bulk update: %s", str(e))
                total_errors += len(existing_bills)

        # Summary notification
        _logger.info(
            "Sync completed: %d succeeded, %d failed", total_success, total_errors
        )

        if total_errors > 0:
            raise UserError(
                _(
                    "Sync completed with errors:\n\n"
                    "✓ Succeeded: %(success)d\n"
                    "✗ Failed: %(errors)d\n\n"
                    "Check individual document notes for details."
                )
                % {"success": total_success, "errors": total_errors}
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Successful"),
                "message": _("Successfully synced %d document(s) to Bill.com")
                % total_success,
                "type": "success",
                "sticky": False,
            },
        }

    def _sync_existing_bills_bulk(self, bills):
        """Sync existing bills using bulk endpoint

        Args:
            bills: Recordset of bills with billcom_id (existing in Bill.com)

        Returns:
            tuple: (success_count, error_count)
        """

        _logger.info("Starting bulk update of %d existing bill(s)", len(bills))

        # Prepare bulk data with required fields
        bulk_data = []
        bill_mapping = {}  # Map array index to bill record

        for idx, bill in enumerate(bills):
            data = bill._prepare_bill_data(for_bulk=True)
            if data:
                bulk_data.append(data)
                bill_mapping[idx] = bill
            else:
                _logger.warning(
                    "Bill %s skipped from bulk (missing billcom_id or invalid data)",
                    bill.name,
                )

        if not bulk_data:
            _logger.warning("No valid bill data for bulk update")
            return (0, len(bills))

        try:
            # Make bulk request
            _logger.info("Sending %d bill(s) to Bill.com bulk endpoint", len(bulk_data))
            results = self.env["billcom.service"]._make_request(
                "bills/bulk", method="POST", data=bulk_data
            )

            if not results or not isinstance(results, list):
                _logger.error(
                    "Unexpected response from bulk API. Expected list, got: %s",
                    type(results),
                )
                return (0, len(bulk_data))

            # Process results
            success_count = 0
            error_count = 0

            for idx, result in enumerate(results):
                bill = bill_mapping.get(idx)
                if not bill:
                    continue

                try:
                    if result and result.get("id"):
                        # Successful sync
                        bill.with_context(skip_billcom_sync=True).write(
                            {
                                "billcom": result.get("id"),
                                "billcom_id": result.get("id"),
                                "last_sync_date": fields.Datetime.now(),
                                "billcom_sync_status": "synced",
                                "billcom_sync_error": False,
                            }
                        )

                        bill.message_post(
                            body=f"<p><strong>Bill.com Bulk Update Successful</strong></p>"
                            f"<ul>"
                            f"<li>Bill.com ID: {result.get('id')}</li>"
                            f"<li>Document Number: {bill.name}</li>"
                            f"</ul>",
                            message_type="notification",
                            subtype_xmlid="mail.mt_note",
                        )

                        success_count += 1
                        _logger.info("Successfully updated bill %s via bulk", bill.name)
                    else:
                        # Failed sync
                        error_msg = f"No ID in bulk response: {result}"
                        bill.with_context(skip_billcom_sync=True).write(
                            {
                                "billcom_sync_status": "sync_failed",
                                "billcom_sync_error": error_msg,
                            }
                        )

                        bill.message_post(
                            body=f"<p><strong>Bill.com Bulk Update Failed</strong></p>"
                            f"<p>No ID returned in response</p>"
                            f"<p><em>Response: {result}</em></p>",
                            message_type="notification",
                            subtype_xmlid="mail.mt_note",
                        )

                        error_count += 1
                        _logger.error(
                            "Failed to update bill %s: %s", bill.name, error_msg
                        )

                except Exception as e:
                    error_msg = str(e)
                    bill.with_context(skip_billcom_sync=True).write(
                        {
                            "billcom_sync_status": "sync_failed",
                            "billcom_sync_error": error_msg,
                        }
                    )

                    bill.message_post(
                        body=f"<p><strong>Bill.com Bulk Update Error</strong></p>"
                        f"<p>{error_msg}</p>",
                        message_type="notification",
                        subtype_xmlid="mail.mt_note",
                    )

                    error_count += 1
                    _logger.error(
                        "Error processing bulk result for bill %s: %s",
                        bill.name,
                        error_msg,
                    )

            return (success_count, error_count)

        except Exception as e:
            error_detail = str(e)
            service = self.env["billcom.service"]
            friendly_message = service._extract_friendly_error(e)

            _logger.error("Error in bulk update: %s", error_detail)

            # Mark all bills as failed
            for bill in bills:
                bill.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_sync_status": "sync_failed",
                        "billcom_sync_error": friendly_message,
                    }
                )

            return (0, len(bills))

    @api.model
    def _sync_documents_cron(self):
        """Cron job to sync documents from Bill.com"""
        try:
            config = (
                self.env["billcom.config"]
                .sudo()
                .search(
                    [("active", "=", True), ("company_id", "=", self.env.company.id)],
                    limit=1,
                )
            )
            if not config or not config.auto_sync_enabled:
                _logger.info(
                    "Automatic sync is disabled or no active configuration found"
                )
                return

            service = self.env["billcom.service"].sudo()
            # Sync both invoices and bills
            service.sync_invoices()
            service.sync_bills()
        except Exception as e:
            _logger.error("Error in document sync cron: %s", str(e))

    # def write(self, vals):
    #     """Override write to sync changes to Bill.com"""
    #     res = super().write(vals)
    #     if self.name == '/' or self.env.context.get("skip_billcom_sync"):
    #         return res

    #     for record in self:
    #         # Only sync if record was created in Odoo (not from Bill.com)
    #         # Records from Bill.com have billcom_id set
    #         if (
    #             record.is_sync_to_billcom
    #             and record.partner_id.is_sync_to_billcom
    #             and record.move_type in ["in_invoice", "out_invoice"]
    #             and not record.billcom_id  # Skip if already synced from Bill.com
    #         ):
    #             try:
    #                 record.with_context(skip_billcom_sync=True).button_sync_to_billcom()
    #             except Exception as e:
    #                 _logger.error("Error syncing document to Bill.com: %s", str(e))

    def button_sync_attachments_to_billcom(self):
        """Create billcom.document records from existing ir.attachment records

        This button finds all attachments linked to this bill and creates
        corresponding billcom.document records that can be uploaded to Bill.com
        """
        self.ensure_one()

        if self.move_type != "in_invoice":
            raise UserError(_("This action is only available for vendor bills"))

        # Find all attachments for this bill
        attachments = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", self.id),
            ]
        )

        if not attachments:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Attachments Found"),
                    "message": _("This bill has no attachments to sync"),
                    "type": "info",
                    "sticky": False,
                },
            }

        # Create billcom.document records for each attachment
        created_count = 0
        existing_count = 0

        for attachment in attachments:
            try:
                document = self.env["billcom.document"].create_from_attachment(
                    attachment
                )
                if document:
                    # Check if it was newly created or already existed
                    if document.create_date == fields.Datetime.now():
                        created_count += 1
                    else:
                        existing_count += 1
            except Exception as e:
                _logger.warning(
                    "Failed to create document from attachment %d: %s",
                    attachment.id,
                    str(e),
                )

        # Post to chatter
        if created_count > 0 or existing_count > 0:
            self.message_post(
                body=f"<p><strong>Attachments Synced to Bill.com Documents</strong></p>"
                f"<ul>"
                f"<li>New documents created: {created_count}</li>"
                f"<li>Documents already existed: {existing_count}</li>"
                f"<li>Total attachments: {len(attachments)}</li>"
                f"</ul>"
                f"<p><em>Use 'Upload to Bill.com' button on each\
                     document to complete upload</em></p>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Attachments Synced"),
                "message": _(
                    "Created %(created)d new Bill.com document(s) from %(total)d attachment(s)"
                )
                % {"created": created_count, "total": len(attachments)},
                "type": "success",
                "sticky": False,
            },
        }

    def button_send_invoice_payment_reminder(self):
        """Send invoice payment reminder to customer via Bill.com

        This button:
        1. Validates the invoice is ready (posted, synced, has customer email)
        2. Gets payment link from Bill.com API
        3. Sends payment reminder email via Bill.com
        4. Stores payment link in invoice record
        """
        self.ensure_one()

        # Validation: Must be customer invoice
        if self.move_type != "out_invoice":
            raise UserError(
                _("This action is only available for customer invoices (out_invoice)")
            )

        # Validation: Must be posted
        if self.state != "posted":
            raise UserError(_("Invoice must be posted before sending payment reminder"))

        # Validation: Must be synced to Bill.com
        if not self.billcom_id and not self.billcom:
            raise UserError(
                _(
                    "Invoice must be synced to Bill.com first.\n\n"
                    "Please click 'Sync to Bill.com' button to sync this invoice."
                )
            )

        # Validation: Must not be fully paid
        if self.payment_state == "paid":
            raise UserError(
                _(
                    "Cannot send payment reminder for fully paid invoice.\n\n"
                    "Payment Status: %s"
                )
                % self.payment_state
            )

        # Validation: Partner must have email
        if not self.partner_id.email:
            raise UserError(
                _(
                    "Customer must have an email address configured.\n\n"
                    "Customer: %s\n"
                    "Please add an email address to this customer's contact information."
                )
                % self.partner_id.name
            )

        # Validation: Partner must be synced to Bill.com
        if not self.partner_id.billcom_id and not self.partner_id.billcom:
            raise UserError(
                _(
                    "Customer must be synced to Bill.com first.\n\n"
                    "Customer: %s\n"
                    "Please sync the customer to Bill.com before sending payment reminder."
                )
                % self.partner_id.name
            )

        try:
            service = self.env["billcom.service"]
            billcom_invoice_id = self.billcom_id or self.billcom
            billcom_customer_id = self.partner_id.billcom_id or self.partner_id.billcom
            customer_email = self.partner_id.email

            _logger.info(
                "Sending payment reminder for invoice %s (Bill.com ID: %s)",
                self.name,
                billcom_invoice_id,
            )

            # Step 1: Get payment link from Bill.com
            payment_link = service.get_invoice_payment_link(
                invoice_id=billcom_invoice_id,
                customer_id=billcom_customer_id,
                customer_email=customer_email,
            )

            # Step 2: Send invoice email via Bill.com
            # Bill.com will use default customer email if not specified
            service.send_invoice_email(
                invoice_id=billcom_invoice_id, recipient_emails=[customer_email]
            )

            # Step 3: Store payment link in invoice record
            self.with_context(skip_billcom_sync=True).write(
                {"billcom_payment_link": payment_link}
            )

            # Post success message to chatter
            self.message_post(
                body=f"<p><strong>Payment Reminder Sent Successfully</strong></p>"  # noqa: E231
                f"<ul>"  # noqa: E231
                f"<li><strong>Customer:</strong> {self.partner_id.name}</li>"  # noqa: E231
                f"<li><strong>Email:</strong> {customer_email}</li>"  # noqa: E231
                f"<li><strong>Invoice:</strong> {self.name}</li>"  # noqa: E231
                f"<li><strong>Amount Due:</strong>\
                {self.currency_id.symbol}{self.amount_residual:.2f}</li>"  # noqa: E231, E501
                f"</ul>"  # noqa: E231
                f"<p><strong>Payment Link:</strong></p>"  # noqa: E231
                f"<p><a href='{payment_link}' \
                    target='_blank'>{payment_link}</a></p>",  # noqa: E231, E501
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            _logger.info("Successfully sent payment reminder for invoice %s", self.name)

            # Return success notification
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Payment Reminder Sent"),
                    "message": _("Payment reminder email sent successfully to %s")
                    % customer_email,
                    "type": "success",
                    "sticky": False,
                },
            }

        except Exception as e:
            error_detail = str(e)

            # Extract user-friendly error message
            service = self.env["billcom.service"]
            friendly_message = service._extract_friendly_error(e)

            _logger.error(
                "Error sending payment reminder for invoice %s: %s",
                self.name,
                error_detail,
            )

            # Post error to chatter
            self.message_post(
                body=f"<p><strong>Payment Reminder Failed</strong></p>"  # noqa: E231
                f"<p>Failed to send payment reminder via Bill.com</p>"  # noqa: E231
                f"<p><strong>Error:</strong></p>"  # noqa: E231
                f"<pre>{friendly_message}</pre>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            # Raise user-friendly error
            raise UserError(
                _("Failed to send payment reminder:\n\n%s") % friendly_message
            ) from e

    @api.model
    def sync_from_billcom(self, billcom_id):  # noqa: C901
        """Sync a bill/invoice from Bill.com by ID (called by webhook)

        Args:
            billcom_id (str): Bill.com ID of the document to sync

        Returns:
            bool: True if successful, False otherwise
        """
        if not billcom_id:
            _logger.error("No Bill.com ID provided for sync")
            return False

        move = False
        move_type = False

        try:
            # Search for existing document with this Bill.com ID
            move = self.search(
                ["|", ("billcom_id", "=", billcom_id), ("billcom", "=", billcom_id)],
                limit=1,
            )

            # Determine if it's a bill or invoice by trying both endpoints
            service = self.env["billcom.service"].sudo()
            document_data = None
            endpoint = None

            # Try bills endpoint first
            try:
                document_data = service._make_request(
                    f"bills/{billcom_id}", method="GET"
                )
                if document_data and document_data.get("id"):
                    endpoint = "bills"
                    move_type = "in_invoice"
            except Exception as e:
                _logger.debug(
                    "Document %s not found in bills endpoint: %s", billcom_id, str(e)
                )

            # If not a bill, try invoices endpoint
            if not document_data:
                try:
                    document_data = service._make_request(
                        f"invoices/{billcom_id}", method="GET"
                    )
                    if document_data and document_data.get("id"):
                        endpoint = "invoices"
                        move_type = "out_invoice"
                except Exception as e:
                    _logger.debug(
                        "Document %s not found in invoices endpoint: %s",
                        billcom_id,
                        str(e),
                    )

            if not document_data:
                _logger.error(
                    "Could not fetch document %s from\
                    Bill.com - tried both bills and\
                    invoices endpoints",
                    billcom_id,
                )
                return False

            _logger.info("Syncing %s %s from Bill.com", endpoint, billcom_id)

            # Extract partner information
            partner_id = None
            if endpoint == "bills":
                vendor_id = document_data.get("vendorId")
                if vendor_id:
                    partner = (
                        self.env["res.partner"]
                        .sudo()
                        .search(
                            [
                                "|",
                                ("billcom_id", "=", vendor_id),
                                ("billcom", "=", vendor_id),
                            ],
                            limit=1,
                        )
                    )
                    if partner:
                        partner_id = partner.id
            elif endpoint == "invoices":
                customer_id = document_data.get("customerId")
                if customer_id:
                    partner = (
                        self.env["res.partner"]
                        .sudo()
                        .search(
                            [
                                "|",
                                ("billcom_id", "=", customer_id),
                                ("billcom", "=", customer_id),
                            ],
                            limit=1,
                        )
                    )
                    if partner:
                        partner_id = partner.id

            if not partner_id:
                _logger.warning("Partner not found for %s %s", endpoint, billcom_id)
                return False

            # Prepare values for create/update
            invoice_info = document_data.get("invoice", {})
            vals = {
                "move_type": move_type,
                "partner_id": partner_id,
                "billcom_id": billcom_id,
                "billcom": billcom_id,
                "billcom_status": document_data.get("paymentStatus"),
                "ref": invoice_info.get("invoiceNumber", ""),
                "invoice_origin": invoice_info.get("purchaseOrderNumber", ""),
                "invoice_date": invoice_info.get("invoiceDate"),
                "invoice_date_due": document_data.get("dueDate"),
                "last_sync_date": fields.Datetime.now(),
            }

            # Create or update the move
            if move:
                # Update existing move
                move.with_context(skip_billcom_sync=True).write(vals)
                _logger.info("Updated existing %s in Odoo: %s", endpoint, move.name)
                action = "updated"
            else:
                # Create new move
                vals["is_sync_to_billcom"] = False  # Prevent sync back to Bill.com
                move = self.with_context(skip_billcom_sync=True).create(vals)
                _logger.info("Created new %s in Odoo: %s", endpoint, move.name)
                action = "created"

            # Apply status mapping from Bill.com to Odoo state
            if endpoint == "bills":
                billcom_payment_status = document_data.get("paymentStatus", "UNDEFINED")
                target_state = service._map_billcom_bill_status_to_odoo_state(
                    billcom_payment_status
                )
            else:  # invoices
                billcom_status = document_data.get("status", "UNDEFINED")
                target_state = service._map_billcom_invoice_status_to_odoo_state(
                    billcom_status
                )

            if target_state == "posted" and move.state == "draft":
                # Post the move if Bill.com status requires it
                try:
                    move.with_context(skip_billcom_sync=True).action_post()
                    _logger.info(
                        "Posted %s %s based on Bill.com status (webhook sync)",
                        endpoint,
                        move.name,
                    )
                except Exception as e:
                    _logger.warning(
                        "Could not post %s %s from Bill.com status (webhook): %s",
                        endpoint,
                        move.name,
                        e,
                    )

            # Post success message to chatter
            doc_type = "Bill" if endpoint == "bills" else "Invoice"
            move.message_post(
                body=f"<p><strong>Synced from Bill.com</strong></p>"
                f"<ul>"
                f"<li>Type: {doc_type}</li>"
                f"<li>Action: {action.title()}</li>"
                f"<li>Bill.com ID: {billcom_id}</li>"
                f"<li>Source: Webhook</li>"
                f"</ul>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            return True

        except Exception as e:
            error_detail = str(e)
            _logger.error(
                "Error syncing %s from Bill.com: %s", billcom_id, error_detail
            )

            # Try to post error to existing move if found
            if move:
                move.message_post(
                    body=f"<p><strong>Bill.com Sync Error</strong></p>"
                    f"<p>Failed to sync from Bill.com</p>"
                    f"<p><strong>Bill.com ID:</strong> {billcom_id}</p>"  # noqa: E231
                    f"<p><strong>Error:</strong> {error_detail}</p>",  # noqa: E231
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

            return False
