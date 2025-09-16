import json
import logging

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class BillComController(http.Controller):
    def _handle_error(self, error):
        """Common error handler for endpoints"""
        _logger.error(str(error))
        return {"success": False, "error": str(error)}

    @http.route("/billcom/webhook", type="json", auth="none", csrf=False)
    def webhook(self):
        """Endpoint to receive webhooks from Bill.com"""
        try:
            # Get config to check if webhooks are enabled
            config = request.env["billcom.config"].sudo().get_config()
            if not hasattr(config, "enable_webhooks") or not config.enable_webhooks:
                return {"success": False, "error": "Webhooks are disabled"}

            data = request.jsonrequest
            _logger.info("Received Bill.com webhook: %s", json.dumps(data))

            # Validate webhook data
            if not isinstance(data, dict):
                return {"success": False, "error": "Invalid webhook data format"}

            event_type = data.get("eventType")
            if not event_type:
                return {"success": False, "error": "No event type provided"}

            entity_id = data.get("entityId")
            if not entity_id:
                return {"success": False, "error": "No entity ID provided"}

            # Handle different event types based on configuration
            if event_type.startswith("bill."):
                if config.sync_bills:
                    request.env["account.move"].sudo().sync_from_billcom(entity_id)
                else:
                    _logger.warning("Bill sync disabled, ignoring webhook")

            elif event_type.startswith("invoice."):
                if config.sync_invoices:
                    request.env["account.move"].sudo().sync_from_billcom(entity_id)
                else:
                    _logger.warning("Invoice sync disabled, ignoring webhook")

            elif event_type.startswith("vendor."):
                if config.sync_vendors:
                    request.env["res.partner"].sudo().sync_from_billcom(entity_id)
                else:
                    _logger.warning("Vendor sync disabled, ignoring webhook")

            elif event_type.startswith("customer."):
                if config.sync_customers:
                    request.env["res.partner"].sudo().sync_from_billcom(entity_id)
                else:
                    _logger.warning("Customer sync disabled, ignoring webhook")

            elif event_type.startswith("payment."):
                if config.sync_payments:
                    # Get the full payment data from Bill.com
                    try:
                        payment_data = (
                            request.env["billcom.service"]
                            .sudo()
                            ._make_request(f"payments/{entity_id}", method="GET")
                        )

                        if payment_data and payment_data.get("id"):
                            # Process the payment webhook
                            result = (
                                request.env["account.payment"]
                                .sudo()
                                .process_billcom_payment_webhook(payment_data)
                            )
                            if result:
                                _logger.info(
                                    "Successfully processed payment webhook for ID: %s",
                                    entity_id,
                                )
                            else:
                                _logger.warning(
                                    "Failed to process payment webhook for ID: %s",
                                    entity_id,
                                )
                        else:
                            _logger.warning(
                                "Could not retrieve payment data for ID: %s", entity_id
                            )
                    except Exception as e:
                        _logger.error("Error processing payment webhook: %s", str(e))
                        return {
                            "success": False,
                            "error": f"Error processing payment webhook: {str(e)}",
                        }
                else:
                    _logger.warning("Payment sync disabled, ignoring webhook")

            else:
                _logger.warning("Unhandled event type: %s", event_type)
                return {
                    "success": False,
                    "error": f"Unhandled event type: {event_type}",
                }

            return {"success": True, "message": f"Successfully processed {event_type}"}

        except ValidationError as ve:
            _logger.error("Validation error in webhook: %s", str(ve))
            return self._handle_error(ve)
        except UserError as ue:
            _logger.error("User error in webhook: %s", str(ue))
            return self._handle_error(ue)
        except Exception as e:
            _logger.error("Unexpected error in webhook: %s", str(e), exc_info=True)
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
