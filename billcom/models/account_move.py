import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    billcom = fields.Char(string="Bill.com Reference")
    is_sync_to_billcom = fields.Boolean(string="Sync to Bill.com", default=True)
    last_sync_date = fields.Datetime()

    def _prepare_bill_data(self):
        """Prepare bill data for Bill.com API"""
        self.ensure_one()
        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.move_type != "in_invoice":
            return False

        lines = []
        for line in self.invoice_line_ids:
            line_data = {"description": line.name or "", "amount": line.price_subtotal}
            lines.append(line_data)

        payment_status_map = {
            "paid": "PAID",
            "not_paid": "UNPAID",
            "partial": "PARTIALLY_PAID",
            "in_payment": "IN_PROCESS",
        }

        return {
            "vendorId": self.partner_id.billcom,
            "invoice": {
                "invoiceNumber": self.name or "",
                "invoiceDate": self.invoice_date.isoformat()
                if self.invoice_date
                else "",
            },
            "dueDate": self.invoice_date_due.isoformat()
            if self.invoice_date_due
            else "",
            "description": self.narration or "",
            "amount": self.amount_total,
            "billLineItems": lines,
            "paymentStatus": payment_status_map.get(self.payment_state, "UNDEFINED"),
        }

    def _prepare_invoice_data(self):
        """Prepare invoice data for Bill.com API"""
        self.ensure_one()
        if not self.is_sync_to_billcom or not self.partner_id.is_sync_to_billcom:
            return False

        if self.move_type != "out_invoice":
            return False

        lines = []
        for line in self.invoice_line_ids:
            line_data = {
                "description": line.name or "",
                "quantity": line.quantity,
                "price": line.price_unit,
            }
            if (
                line.product_id
                and hasattr(line.product_id, "billcom")
                and line.product_id.billcom
            ):
                line_data["itemId"] = line.product_id.billcom

            lines.append(line_data)

        status_map = {
            "paid": "PAID_IN_FULL",
            "not_paid": "OPEN",
            "partial": "PARTIAL_PAYMENT",
            "in_payment": "SCHEDULED",
        }

        return {
            "customerId": self.partner_id.billcom,
            "invoiceNumber": self.name or "",
            "invoiceDate": self.invoice_date.isoformat() if self.invoice_date else "",
            "dueDate": self.invoice_date_due.isoformat()
            if self.invoice_date_due
            else "",
            "description": self.narration or "",
            "amount": self.amount_total,
            "invoiceLineItems": lines,
            "status": status_map.get(self.payment_state, "UNDEFINED"),
        }

    def button_sync_to_billcom(self):
        """Sync document to Bill.com"""
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

            if self.billcom:
                # Update existing document
                result = self.env["billcom.service"]._make_request(
                    f"{endpoint}/{self.billcom}", method="PUT", data=data
                )
            else:
                # Create new document
                result = self.env["billcom.service"]._make_request(
                    endpoint, method="POST", data=data
                )

            if result and result.get("id"):
                self.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom": result.get("id"),
                        "last_sync_date": fields.Datetime.now(),
                    }
                )
                _logger.info("Successfully synced %s with Bill.com", self.name)
                return result
            return False
        except Exception as e:
            _logger.error("Error syncing %s to Bill.com: %s", self.name, str(e))
            return False

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

    def write(self, vals):
        """Override write to sync changes to Bill.com"""
        res = super().write(vals)
        if self.env.context.get("skip_billcom_sync"):
            return res

        for record in self:
            if (
                record.is_sync_to_billcom
                and record.partner_id.is_sync_to_billcom
                and record.move_type in ["in_invoice", "out_invoice"]
            ):
                try:
                    record.with_context(skip_billcom_sync=True).button_sync_to_billcom()
                except Exception as e:
                    _logger.error("Error syncing document to Bill.com: %s", str(e))

        return res
