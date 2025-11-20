# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def parse_billcom_datetime(date_string):
    """Parse Bill.com datetime format to Odoo datetime

    Bill.com format: 2025-10-03T06:11:24.000+00:00
    Odoo format: YYYY-MM-DD HH:MM:SS

    Args:
        date_string: ISO 8601 datetime string from Bill.com

    Returns:
        datetime: Parsed datetime object or None
    """
    if not date_string:
        return None

    try:
        # Remove milliseconds and timezone info for Odoo compatibility
        # 2025-10-03T06:11:24.000+00:00 -> 2025-10-03T06:11:24
        if "." in date_string:
            date_string = date_string.split(".")[0]
        elif "+" in date_string:
            date_string = date_string.split("+")[0]
        elif "Z" in date_string:
            date_string = date_string.replace("Z", "")

        # Parse ISO format
        return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")
    except (ValueError, AttributeError) as e:
        _logger.warning(f"Failed to parse Bill.com datetime '{date_string}': {e}")
        return None


class BillcomDocument(models.Model):
    _name = "billcom.document"
    _description = "Bill.com Document"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    active = fields.Boolean(default=True)
    name = fields.Char(string="Document Name", required=True)
    billcom_id = fields.Char(
        string="Bill.com Document ID",
        help="Bill.com ID starting with 00h (upload complete) or 0du (upload in progress)",
        readonly=True,
    )
    billcom_upload_id = fields.Char(
        string="Bill.com Upload ID",
        help="Temporary ID during upload (starts with 0du)",
        readonly=True,
    )
    bill_id = fields.Many2one(
        "account.move",
        string="Bill",
        required=True,
        domain=[("move_type", "=", "in_invoice")],
        ondelete="cascade",
    )
    billcom_bill_id = fields.Char(
        string="Bill.com Bill ID",
        related="bill_id.billcom_id",
        store=True,
        readonly=True,
    )
    file_data = fields.Binary(string="File Content", attachment=True)
    file_size = fields.Integer(readonly=True)
    download_link = fields.Char(readonly=True)
    upload_status = fields.Selection(
        [
            ("pending", "Pending Upload"),
            ("in_progress", "Upload In Progress"),
            ("uploaded", "Uploaded"),
            ("failed", "Upload Failed"),
        ],
        default="pending",
        readonly=True,
    )
    error_message = fields.Text(readonly=True)
    created_time = fields.Datetime(
        string="Bill.com Created Time",
        help="Document creation time in Bill.com",
        readonly=True,
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Odoo Attachment",
        help="Link to the ir.attachment record for this document",
        readonly=True,
    )

    @api.constrains("file_data")
    def _check_file_size(self):
        """Validate file size is within Bill.com limit (6 MB)"""
        for record in self:
            if record.file_data:
                file_size = len(base64.b64decode(record.file_data))
                if file_size > 6 * 1024 * 1024:  # 6 MB limit
                    raise UserError(
                        _(
                            "File size exceeds Bill.com limit of 6 MB. Current size: %.2f MB"
                        )
                        % (file_size / (1024 * 1024))
                    )

    def _prepare_upload_data(self):
        """Prepare document data for upload to Bill.com"""
        self.ensure_one()

        if not self.file_data:
            raise UserError(_("No file content to upload"))

        if not self.billcom_bill_id:
            raise UserError(_("Bill must be synced to Bill.com first"))

        # Decode file data to binary
        file_binary = base64.b64decode(self.file_data)

        return file_binary

    def button_upload_to_billcom(self):
        """Upload document to Bill.com"""
        self.ensure_one()

        if not self.billcom_bill_id:
            raise UserError(
                _(
                    "Cannot upload document: Bill must be synced to Bill.com first.\n\n"
                    "Please sync the bill using the 'Sync to Bill.com' button."
                )
            )

        try:
            # Update status
            self.write({"upload_status": "in_progress", "error_message": False})

            # Prepare file data
            file_binary = self._prepare_upload_data()

            # Calculate file size
            file_size = len(file_binary)
            _logger.info(
                "Uploading document '%s' (%d bytes) for bill %s",
                self.name,
                file_size,
                self.billcom_bill_id,
            )

            # Upload to Bill.com
            service = self.env["billcom.service"]
            endpoint = f"documents/bills/{self.billcom_bill_id}"

            result = service._make_request(
                endpoint,
                method="POST",
                data=file_binary,
                params={"name": self.name},
                is_file_upload=True,
            )

            if result:
                # Extract upload ID or document ID
                upload_id = result.get("uploadId") or result.get("id")
                document_id = (
                    result.get("id") if result.get("id", "").startswith("00h") else None
                )
                download_link = result.get("downloadLink")
                created_time = result.get("createdTime")

                vals = {
                    "file_size": file_size,
                    "billcom_upload_id": upload_id,
                }

                # Check upload status
                if document_id:
                    # Upload complete
                    vals.update(
                        {
                            "billcom_id": document_id,
                            "upload_status": "uploaded",
                            "download_link": download_link,
                            "created_time": parse_billcom_datetime(created_time),
                        }
                    )
                    status_msg = "completed"
                else:
                    # Upload in progress
                    vals["upload_status"] = "in_progress"
                    status_msg = "in progress"

                self.write(vals)

                # Post to chatter
                self.bill_id.message_post(
                    body=f"<p><strong>Bill.com Document Upload"
                    f" {status_msg.title()}</strong></p>"
                    f"<ul>"
                    f"<li>Document: {self.name}</li>"
                    f"<li>File Size: {file_size / 1024: .2f} KB</li>"
                    f"<li>Upload ID: {upload_id}</li>"
                    f"{f'<li>Document ID: {document_id}</li>' if document_id else ''}"
                    f"</ul>",
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

                _logger.info(
                    "Document upload %s for bill %s (Upload ID: %s)",
                    status_msg,
                    self.billcom_bill_id,
                    upload_id,
                )

                if vals.get("upload_status") == "in_progress":
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Upload In Progress"),
                            "message": _(
                                "Document upload started. Use 'Check Upload "
                                "Status' to monitor progress."
                            ),
                            "type": "info",
                            "sticky": False,
                        },
                    }
                else:
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Upload Complete"),
                            "message": _(
                                "Document uploaded successfully " "to Bill.com"
                            ),
                            "type": "success",
                            "sticky": False,
                        },
                    }

            return False

        except Exception as e:
            error_detail = str(e)

            # Extract friendly error message
            service = self.env["billcom.service"]
            friendly_message = service._extract_friendly_error(e)

            _logger.error(
                "Error uploading document '%s' to Bill.com: %s",
                self.name,
                error_detail,
            )

            # Update status
            self.write({"upload_status": "failed", "error_message": friendly_message})

            # Post error to bill chatter
            self.bill_id.message_post(
                body=f"<p><strong>Bill.com Document Upload Error</strong></p>"
                f"<p>Failed to upload document: {self.name}</p>"
                f"<p><strong>Error:</strong></p>"  # noqa: E231
                f"<pre>{friendly_message}</pre>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            # Raise user-friendly error
            raise UserError(
                _("Failed to upload document to Bill.com:\n\n%s") % friendly_message
            ) from e

    def button_check_upload_status(self):
        """Check upload status in Bill.com"""
        self.ensure_one()

        if not self.billcom_upload_id:
            raise UserError(_("No upload ID available to check status"))

        try:
            service = self.env["billcom.service"]
            result = service._make_request(
                "documents/upload-status",
                method="GET",
                params={"ids": self.billcom_upload_id},
            )

            if result and isinstance(result, list) and len(result) > 0:
                status_info = result[0]
                status = status_info.get("status")  # IN_PROGRESS or UPLOADED
                document_id = status_info.get("documentId")

                if status == "UPLOADED" and document_id:
                    # Upload complete - get document details
                    doc_result = service._make_request(
                        f"documents/{document_id}", method="GET"
                    )

                    if doc_result:
                        self.write(
                            {
                                "billcom_id": document_id,
                                "upload_status": "uploaded",
                                "download_link": doc_result.get("downloadLink"),
                                "created_time": parse_billcom_datetime(
                                    doc_result.get("createdTime")
                                ),
                            }
                        )

                        # Post to chatter
                        self.bill_id.message_post(
                            body=f"<p><strong>Bill.com Document Upload Complete</strong></p>"
                            f"<ul>"
                            f"<li>Document: {self.name}</li>"
                            f"<li>Document ID: {document_id}</li>"
                            f"</ul>",
                            message_type="notification",
                            subtype_xmlid="mail.mt_note",
                        )

                        return {
                            "type": "ir.actions.client",
                            "tag": "display_notification",
                            "params": {
                                "title": _("Upload Complete"),
                                "message": _("Document upload completed successfully"),
                                "type": "success",
                                "sticky": False,
                            },
                        }
                elif status == "IN_PROGRESS":
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Upload In Progress"),
                            "message": _(
                                "Document upload is still in progress. "
                                "Please check again in a few moments."
                            ),
                            "type": "info",
                            "sticky": False,
                        },
                    }

            return False

        except Exception as e:
            error_detail = str(e)
            service = self.env["billcom.service"]
            friendly_message = service._extract_friendly_error(e)

            _logger.error(
                "Error checking upload status for document '%s': %s",
                self.name,
                error_detail,
            )

            raise UserError(
                _("Failed to check upload status:\n\n%s") % friendly_message
            ) from e

    def _create_or_update_attachment(self, file_data_encoded):
        """Create or update ir.attachment for this document

        Args:
            file_data_encoded: Base64-encoded file data
        """
        self.ensure_one()

        # Get or determine mimetype
        import mimetypes

        mimetype = mimetypes.guess_type(self.name)[0] or "application/octet-stream"

        # Prepare attachment values
        attachment_vals = {
            "name": self.name,
            "datas": file_data_encoded,
            "res_model": "account.move",
            "res_id": self.bill_id.id,
            "mimetype": mimetype,
            "description": f'Bill.com Document: {self.billcom_id or "pending"}',
        }

        if self.attachment_id:
            # Update existing attachment
            self.attachment_id.write(attachment_vals)
            _logger.info(
                "Updated ir.attachment %d for document %s",
                self.attachment_id.id,
                self.name,
            )
        else:
            # Create new attachment
            attachment = self.env["ir.attachment"].create(attachment_vals)
            self.write({"attachment_id": attachment.id})
            _logger.info(
                "Created ir.attachment %d for document %s",
                attachment.id,
                self.name,
            )

    def button_download_from_billcom(self):
        """Download document from Bill.com"""
        self.ensure_one()

        if not self.download_link:
            raise UserError(
                _(
                    "No download link available. Document may not be uploaded yet.\n\n"
                    "Use 'Check Upload Status' if upload is in progress."
                )
            )

        try:
            service = self.env["billcom.service"]

            # Download file
            file_data = service._download_document(self.download_link)

            if file_data:
                # Update file content
                file_data_encoded = base64.b64encode(file_data)
                self.write({"file_data": file_data_encoded})

                # Create or update ir.attachment
                self._create_or_update_attachment(file_data_encoded)

                _logger.info(
                    "Downloaded document '%s' from Bill.com (%d bytes)",
                    self.name,
                    len(file_data),
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Download Complete"),
                        "message": _(
                            "Document downloaded successfully from " "Bill.com"
                        ),
                        "type": "success",
                        "sticky": False,
                    },
                }

            return False

        except Exception as e:
            error_detail = str(e)
            service = self.env["billcom.service"]
            friendly_message = service._extract_friendly_error(e)

            _logger.error(
                "Error downloading document '%s' from Bill.com: %s",
                self.name,
                error_detail,
            )

            raise UserError(
                _("Failed to download document from Bill.com:\n\n%s") % friendly_message
            ) from e

    @api.model
    def create_from_attachment(self, attachment):
        """Create a billcom.document from an ir.attachment

        Args:
            attachment: ir.attachment record

        Returns:
            billcom.document: Created document record
        """
        if not attachment.res_model == "account.move":
            raise UserError(
                _("Attachment must be linked to a vendor bill (account.move)")
            )

        bill = self.env["account.move"].browse(attachment.res_id)
        if not bill.exists() or bill.move_type != "in_invoice":
            raise UserError(_("Attachment must be linked to a valid vendor bill"))

        # Check if document already exists for this attachment
        existing = self.search(
            [("attachment_id", "=", attachment.id), ("bill_id", "=", bill.id)], limit=1
        )

        if existing:
            _logger.info(
                "Document already exists for attachment %d: %s",
                attachment.id,
                existing.name,
            )
            return existing

        # Create new document
        vals = {
            "name": attachment.name,
            "bill_id": bill.id,
            "file_data": attachment.datas,
            "attachment_id": attachment.id,
            "upload_status": "pending",
        }

        document = self.create(vals)
        _logger.info(
            "Created document from attachment %d: %s",
            attachment.id,
            document.name,
        )

        return document

    @api.model
    def sync_documents_from_billcom(self, bill):
        """Sync all documents for a bill from Bill.com

        Args:
            bill: account.move record (vendor bill)

        Returns:
            int: Number of documents synced
        """
        if not bill.billcom_id:
            _logger.warning("Cannot sync documents: Bill not synced to Bill.com")
            return 0

        try:
            service = self.env["billcom.service"]
            result = service._make_request(
                f"documents/bills/{bill.billcom_id}", method="GET"
            )

            if not result or not isinstance(result, list):
                _logger.info("No documents found for bill %s", bill.billcom_id)
                return 0

            synced_count = 0
            for doc_data in result:
                doc_id = doc_data.get("id")
                if not doc_id:
                    continue

                # Check if document already exists
                existing = self.search(
                    [("billcom_id", "=", doc_id), ("bill_id", "=", bill.id)], limit=1
                )

                vals = {
                    "name": doc_data.get("name", "Unknown"),
                    "bill_id": bill.id,
                    "billcom_id": doc_id,
                    "download_link": doc_data.get("downloadLink"),
                    "created_time": parse_billcom_datetime(doc_data.get("createdTime")),
                    "upload_status": "uploaded",
                }

                if existing:
                    existing.write(vals)
                    _logger.info("Updated document %s", doc_id)
                else:
                    document = self.create(vals)
                    _logger.info("Created document %s", doc_id)

                    # Auto-download and create attachment for newly synced documents
                    try:
                        if document.download_link:
                            file_data = service._download_document(
                                document.download_link
                            )
                            if file_data:
                                file_data_encoded = base64.b64encode(file_data)
                                document.write({"file_data": file_data_encoded})
                                document._create_or_update_attachment(file_data_encoded)
                                _logger.info(
                                    "Auto-downloaded and attached document %s (%d bytes)",
                                    doc_id,
                                    len(file_data),
                                )
                    except Exception as e:
                        _logger.warning(
                            "Failed to auto-download document %s: %s", doc_id, str(e)
                        )

                synced_count += 1

            # Post to chatter
            if synced_count > 0:
                bill.message_post(
                    body=f"<p><strong>Synced {synced_count} document(s) "
                    f"from Bill.com</strong></p>",
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

            return synced_count

        except Exception as e:
            error_detail = str(e)
            _logger.error(
                "Error syncing documents for bill %s: %s", bill.billcom_id, error_detail
            )
            return 0
