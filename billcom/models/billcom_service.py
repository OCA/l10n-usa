# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .billcom_document import parse_billcom_datetime

_logger = logging.getLogger(__name__)


class BillcomService(models.AbstractModel):
    _name = "billcom.service"
    _description = "Bill.com Integration Service"
    _inherit = ["billcom.service.abstract"]

    @api.model
    def sync_partner(self, partner, partner_type="vendor"):
        """Sync single partner to Bill.com"""
        # Check if sync is enabled for this partner type
        config = self._get_config()
        if partner_type == "vendor" and not config.sync_vendors:
            _logger.info("Vendor synchronization is disabled")
            return False
        elif partner_type == "customer" and not config.sync_customers:
            _logger.info("Customer synchronization is disabled")
            return False

        # Skip if partner is not marked for sync
        if not partner.is_sync_to_billcom:
            _logger.info(
                "%s %s not marked for sync to BillCom", partner_type, partner.name
            )
            return False

        # Use context to prevent infinite loops
        if self.env.context.get("skip_billcom_sync"):
            _logger.info(
                "Skipping sync for %s %s due to context", partner_type, partner.name
            )
            return False

        # Prepare partner data
        partner_data = partner._prepare_partner_data(partner_type)
        _logger.info(
            "Partner data prepared for %s %s: %s",
            partner_type,
            partner.name,
            partner_data,
        )
        if not partner_data:
            _logger.warning("No data prepared for %s %s", partner_type, partner.name)
            return False

        # Verify required fields are present and not null
        if not partner_data.get("name"):
            _logger.warning(
                "Name is missing or blank for %s %s", partner_type, partner.name
            )
            partner_data["name"] = partner.name or "Unknown"

        if partner_type == "vendor" and not partner_data.get("address"):
            _logger.warning("Address is missing or null for vendor %s", partner.name)
            # Create a default address if missing
            partner_data["address"] = {
                "line1": partner.street or "Unknown",
                "city": partner.city or "Unknown",
                "stateOrProvince": partner.state_id.name if partner.state_id else "",
                "zipOrPostalCode": partner.zip or "",
                "country": partner.country_id.code if partner.country_id else "US",
            }

        # Log the final data structure being sent
        _logger.info(
            "Final %s data being sent to Bill.com: %s", partner_type, partner_data
        )

        # Set endpoint based on partner type
        endpoint = "vendors" if partner_type == "vendor" else "customers"

        # Make request to Bill.com API
        try:
            existing_id = partner.billcom_id or partner.billcom

            if existing_id:
                if (
                    partner.country_id.code != "US"
                    and partner.billcom_payment_purpose_id
                ):
                    partner_data.setdefault("paymentInformation", {}).update(
                        {
                            "paymentPurpose": {
                                "code": {
                                    "name": partner.billcom_payment_purpose_id.code,
                                    "value": partner.billcom_payment_purpose_id.description,
                                }
                            }
                        }
                    )

                _logger.info(
                    "Updating partner_data %s with paymentPurpose in Bill.com",
                    partner_data,
                )

                _logger.info(
                    "Updating existing %s with ID %s in Bill.com",
                    partner_type,
                    existing_id,
                )

                result = self._make_request(
                    f"{endpoint}/{existing_id}", method="PATCH", data=partner_data
                )
            else:
                _logger.info("Creating new %s in Bill.com", partner_type)
                result = self._make_request(endpoint, method="POST", data=partner_data)

            _logger.debug(
                "Bill.com API response for %s %s: %s",
                partner_type,
                partner.name,
                result,
            )

            if result and result.get("id"):
                partner_id = result.get("id")
                action = "updated" if existing_id else "created"

                partner.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom": partner_id,
                        "billcom_id": partner_id,
                        "last_sync_date": fields.Datetime.now(),
                        "billcom_sync_status": "synced",
                        "billcom_sync_error": False,
                    }
                )

                _logger.info(
                    "Successfully synced %s %s to Bill.com with ID: %s",
                    partner_type,
                    partner.name,
                    partner_id,
                )

                partner.message_post(
                    body=f"<p><strong>Bill.com Sync Successful</strong></p>"
                    f"<ul>"
                    f"<li>Type: {partner_type.title()}</li>"
                    f"<li>Action: {action.title()}</li>"
                    f"<li>Bill.com ID: {partner_id}</li>"
                    f"</ul>",
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

                if partner_type == "vendor" and partner.bank_ids:
                    _logger.info(
                        "Bank account for vendor %s included in paymentInformation",
                        partner.name,
                    )
                    if result.get("paymentInformation"):
                        bank = partner.bank_ids[0]
                        bank.with_context(skip_billcom_sync=True).write(
                            {
                                "billcom_last_sync_date": fields.Datetime.now(),
                            }
                        )

                return partner_id
            else:
                error_msg = (
                    f"Unexpected response format from Bill.com API. Response: {result}"
                )
                _logger.warning(
                    "%s for %s %s: %s",
                    error_msg,
                    partner_type,
                    partner.name,
                    result,
                )
                partner.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_sync_status": "sync_failed",
                        "billcom_sync_error": error_msg,
                    }
                )
                partner.message_post(
                    body=f"<p><strong>Bill.com Sync Failed</strong></p>"
                    f"<p>{error_msg}</p>"
                    f"<p><em>Response: {result}</em></p>",
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )
                return False
        except Exception as e:
            error_detail = str(e)

            friendly_message = self._extract_friendly_error(e)

            _logger.error(
                "%s sync failed for %s: %s",
                partner_type.title(),
                partner.name,
                error_detail,
            )

            partner.with_context(skip_billcom_sync=True).write(
                {
                    "billcom_sync_status": "sync_failed",
                    "billcom_sync_error": friendly_message,
                }
            )

            partner.message_post(
                body=f"<p><strong>Bill.com Sync Error</strong></p>"
                f"<p>Failed to sync {partner_type} to Bill.com</p>"
                f"<p><strong>Error: </strong> {friendly_message}</p>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            raise UserError(
                _("Failed to sync %(type)s to Bill.com:\n\n%(message)s")
                % {"type": partner_type, "message": friendly_message}
            ) from e

    def sync_item(self, item):
        if not item.is_sync_to_billcom:
            _logger.info("Item %s not marked for sync to Bill.com", item.name)
            return False

        if self.env.context.get("skip_billcom_sync"):
            _logger.info("Skipping sync for item %s due to context", item.name)
            return False

        item_data = item._prepare_item_data()
        _logger.info("Item data prepared for %s: %s", item.name, item_data)

        if not item_data:
            _logger.warning("No data prepared for item %s", item.name)
            return False

        try:
            existing_id = item.billcom_id or item.billcom

            if existing_id:
                _logger.info(
                    "Updating existing item with ID %s in Bill.com", existing_id
                )
                result = self._make_request(
                    f"classifications/items/{existing_id}",
                    method="PATCH",
                    data=item_data,
                )
            else:
                _logger.info("Creating new item in Bill.com")
                result = self._make_request(
                    "classifications/items", method="POST", data=item_data
                )

            _logger.debug("Bill.com API response for item %s: %s", item.name, result)

            if result and result.get("id"):
                item_id = result.get("id")
                action = "updated" if existing_id else "created"

                update_vals = {
                    "billcom": item_id,
                    "billcom_id": item_id,
                    "last_sync_date": fields.Datetime.now(),
                    "billcom_sync_status": "synced",
                    "billcom_sync_error": False,
                }

                if result.get("createdTime"):
                    created_dt = parse_billcom_datetime(result.get("createdTime"))
                    if created_dt:
                        update_vals["created_time"] = created_dt

                if result.get("updatedTime"):
                    updated_dt = parse_billcom_datetime(result.get("updatedTime"))
                    if updated_dt:
                        update_vals["updated_time"] = updated_dt

                item.with_context(skip_billcom_sync=True).write(update_vals)

                _logger.info(
                    "Successfully synced item %s to Bill.com with ID: %s",
                    item.name,
                    item_id,
                )

                item.message_post(
                    body=f"<p><strong>Bill.com Sync Successful</strong></p>"
                    f"<ul>"
                    f"<li>Type: {item.type}</li>"
                    f"<li>Action: {action.title()}</li>"
                    f"<li>Bill.com ID: {item_id}</li>"
                    f"</ul>",
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

                return item_id
            else:
                error_msg = (
                    f"Unexpected response format from Bill.com API. Response: {result}"
                )
                _logger.warning("%s for item %s", error_msg, item.name)
                item.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_sync_status": "sync_failed",
                        "billcom_sync_error": error_msg,
                    }
                )
                item.message_post(
                    body=f"<p><strong>Bill.com Sync Failed</strong></p>"
                    f"<p>{error_msg}</p>",
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )
                return False
        except Exception as e:
            error_detail = str(e)

            friendly_message = self._extract_friendly_error(e)

            _logger.error("Item sync failed for %s: %s", item.name, error_detail)

            item.with_context(skip_billcom_sync=True).write(
                {
                    "billcom_sync_status": "sync_failed",
                    "billcom_sync_error": friendly_message,
                }
            )

            item.message_post(
                body=f"<p><strong>Bill.com Sync Error</strong></p>"
                f"<p>Failed to sync item to Bill.com</p>"
                f"<p><strong>Error: </strong> {friendly_message}</p>",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            raise UserError(
                _("Failed to sync item to Bill.com:\n\n%s") % friendly_message
            ) from e

    def get_items(self, item_type=None):
        try:
            _logger.info("Fetching items from Bill.com (type: %s)", item_type or "all")

            # Build query parameters
            params = {}
            if item_type:
                params["type"] = item_type

            # Make API request - GET /v3/classifications/items
            result = self._make_request(
                "classifications/items", method="GET", params=params
            )

            if result and isinstance(result, list):
                _logger.info("Retrieved %d items from Bill.com", len(result))
                return result
            elif result and isinstance(result, dict) and "items" in result:
                # Some APIs return {items: [...]}
                items = result.get("items", [])
                _logger.info("Retrieved %d items from Bill.com", len(items))
                return items
            else:
                _logger.warning(
                    "Unexpected response format from Bill.com items API: %s", result
                )
                return []

        except Exception as e:
            _logger.error("Error fetching items from Bill.com: %s", str(e))
            raise

    @api.model
    def full_sync(self):
        # Get configuration
        try:
            config = self.env["billcom.config"].sudo().get_config()
            # Only run if the interval is greater than 0
            if hasattr(config, "full_sync_interval") and config.full_sync_interval > 0:
                self.sync_all()
            else:
                _logger.info(
                    "Bill.com full synchronization is disabled " "(interval set to 0)"
                )
        except Exception as e:
            _logger.error("Error in Bill.com full synchronization: %s", str(e))

    @api.model
    def payment_sync(self):
        # Get configuration
        try:
            config = self.env["billcom.config"].sudo().get_config()
            # Only run if the interval is greater than 0 and payment sync is enabled
            if (
                hasattr(config, "payment_sync_interval")
                and config.payment_sync_interval > 0
                and config.sync_payments
            ):
                self.sync_payments()
            else:
                _logger.info("Bill.com payment synchronization is disabled")
        except Exception as e:
            _logger.error("Error in Bill.com payment synchronization: %s", str(e))

    @api.model
    def sync_all(self):  # noqa: C901
        """Synchronize all entities with Bill.com"""
        try:
            config = self._get_config()
            if not config.auto_sync_enabled:
                _logger.info("Automatic sync is disabled in configuration")
                return {}
        except UserError as e:
            _logger.warning(str(e))
            return 0

        results = {}

        # Sync partners based on configuration
        if config.sync_vendors:
            try:
                results["vendors"] = self.sync_partners("vendor")
                _logger.info("Synced vendors with Bill.com")
            except Exception as e:
                _logger.error("Error syncing vendors: %s", str(e))
                results["vendors_error"] = str(e)

        if config.sync_customers:
            try:
                results["customers"] = self.sync_partners("customer")
                _logger.info("Synced customers with Bill.com")
            except Exception as e:
                _logger.error("Error syncing customers: %s", str(e))
                results["customers_error"] = str(e)

        # Sync documents based on configuration
        if config.sync_bills:
            try:
                results["bills"] = self.sync_bills()
                _logger.info("Synced bills with Bill.com")
            except Exception as e:
                _logger.error("Error syncing bills: %s", str(e))
                results["bills_error"] = str(e)

        if config.sync_invoices:
            try:
                results["invoices"] = self.sync_invoices()
                _logger.info("Synced invoices with Bill.com")
            except Exception as e:
                _logger.error("Error syncing invoices: %s", str(e))
                results["invoices_error"] = str(e)

        # Sync payments if enabled
        if config.sync_payments:
            try:
                results["payments"] = self.sync_payments()
                _logger.info("Synced payments with Bill.com")
            except Exception as e:
                _logger.error("Error syncing payments: %s", str(e))
                results["payments_error"] = str(e)

        # Update last sync date
        config.sudo().write({"last_sync_date": fields.Datetime.now()})

        return results

    def _validate_bank_sync_prerequisites(self, partner):
        """Validate all prerequisites for bank account sync."""
        if not partner:
            _logger.error("No partner provided to sync_vendor_bank_account")
            return False, None, None

        try:
            config = self._get_config()
            if not config:
                _logger.error("No active Bill.com configuration found")
                return False, None, None
        except Exception as e:
            _logger.error("Error getting Bill.com configuration: %s", str(e))
            return False, None, None

        partner_billcom_id = partner.billcom_id or partner.billcom

        if not partner_billcom_id:
            _logger.warning(
                "Cannot sync bank account: Partner %s has no Bill.com ID",
                partner.name,
            )
            return False, None, None

        if not partner.supplier_rank:
            _logger.warning(
                "Cannot sync bank account: Partner %s is not a vendor", partner.name
            )
            return False, None, None

        if not partner.bank_ids:
            _logger.info("Vendor %s has no bank accounts to sync", partner.name)
            return False, None, None

        bank = partner.bank_ids[0]

        # Validate account number
        if not bank.acc_number or bank.acc_number == "":
            _logger.error(
                "Cannot sync bank account: Missing account number for vendor %s",
                partner.name,
            )
            return False, None, None

        # Validate routing number for US accounts
        if partner.country_id and partner.country_id.code == "US":
            routing_number = bank.aba_routing or (
                bank.bank_id.routing_number if bank.bank_id else None
            )
            if not routing_number or routing_number == "":
                _logger.error(
                    "Cannot sync bank account: Missing routing number for US vendor %s",
                    partner.name,
                )
                return False, None, None

        return True, partner_billcom_id, bank

    def _check_existing_bank_account(self, partner_billcom_id, partner_name):
        """Check if vendor has existing bank account in Bill.com."""
        try:
            result = self._make_request(
                f"vendors/{partner_billcom_id}/bank-account", method="GET"
            )

            if isinstance(result, list):
                _logger.info(
                    "Received list response for bank account check: %s", result
                )
                return False
            elif isinstance(result, dict) and result.get("id"):
                _logger.info(
                    "Found existing bank account for vendor %s in Bill.com",
                    partner_name,
                )
                return True
            else:
                _logger.info(
                    "No bank account found for vendor %s in Bill.com", partner_name
                )
                return False
        except Exception as e:
            if "404" in str(e):
                _logger.info(
                    "No bank account found for vendor %s in Bill.com (404 response)",
                    partner_name,
                )
            else:
                _logger.warning(
                    "Error checking vendor bank account, will try to create: %s",
                    str(e),
                )
            return False

    def _delete_existing_bank_account(self, partner_billcom_id, partner_name):
        """Delete existing bank account from Bill.com."""
        _logger.info(
            "Deleting existing bank account for vendor %s in Bill.com",
            partner_name,
        )
        try:
            self._make_request(
                f"vendors/{partner_billcom_id}/bank-account", method="DELETE"
            )
            _logger.info(
                "Successfully deleted bank account for vendor %s in Bill.com",
                partner_name,
            )
        except Exception as e:
            _logger.warning(
                "Error deleting bank account, will try to create anyway: %s",
                str(e),
            )

    def _build_bank_account_payload(self, bank, partner):
        """Build bank account payload for Bill.com API."""
        account_number = bank.acc_number
        if not account_number or account_number == "":
            _logger.error(
                "Cannot create bank account: Missing account number for vendor %s",
                partner.name,
            )
            return None

        bank_data = {
            "nameOnAccount": bank.acc_holder_name or partner.name,
            "accountNumber": account_number,
            "type": bank.billcom_account_type or "CHECKING",
            "ownerType": bank.billcom_owner_type
            or ("BUSINESS" if partner.company_type == "company" else "PERSONAL"),
            "paymentCurrency": bank.currency_id.name if bank.currency_id else "USD",
        }

        routing_number = bank.aba_routing or (
            bank.bank_id.routing_number if bank.bank_id else None
        )

        if partner.country_id and partner.country_id.code == "US":
            if not routing_number or routing_number == "":
                _logger.error(
                    "Cannot create bank account: Missing routing number for vendor %s",
                    partner.name,
                )
                return None
            bank_data.update({"routingNumber": routing_number})
        else:
            if not bank.bank_id.bic:
                bank_data.update({"routingNumber": routing_number})

            bank_data.setdefault("bankInfo", {}).update(
                {"countryISO": partner.country_id.code}
            )

            if bank.bank_id:
                self._add_international_bank_info(bank_data, bank)

        return bank_data

    def _add_international_bank_info(self, bank_data, bank):
        """Add international bank information to payload."""
        bank_data["bankInfo"].update({"branchName": ""})

        if bank.bank_id.name:
            bank_data["bankInfo"]["institutionName"] = bank.bank_id.name
        if bank.bank_id.bic:
            bank_data["bankInfo"]["swiftBIC"] = bank.bank_id.bic

        if bank.bank_id.street:
            bank_data["bankInfo"].setdefault("address", {})[
                "line1"
            ] = bank.bank_id.street
        if bank.bank_id.city:
            bank_data["bankInfo"].setdefault("address", {})["city"] = bank.bank_id.city
        if bank.bank_id.state_id:
            bank_data["bankInfo"].setdefault("address", {})[
                "stateOrProvince"
            ] = bank.bank_id.state_id.code
        if bank.bank_id.zip:
            bank_data["bankInfo"].setdefault("address", {})[
                "zipOrPostalCode"
            ] = bank.bank_id.zip
        if bank.bank_id.country_id:
            bank_data["bankInfo"].setdefault("address", {})[
                "country"
            ] = bank.bank_id.country_id.name

    def _create_bank_account_in_billcom(
        self, partner_billcom_id, bank_data, bank, partner
    ):
        """Create bank account in Bill.com and process response."""
        _logger.debug("Bank account data payload: %s", bank_data)
        _logger.info("Creating bank account for vendor %s in Bill.com", partner.name)

        try:
            result = self._make_request(
                f"vendors/{partner_billcom_id}/bank-account",
                method="POST",
                data=bank_data,
            )

            if isinstance(result, dict) and result.get("id"):
                return self._handle_successful_creation(result, bank, partner)
            elif isinstance(result, list) and len(result) > 0:
                return self._handle_error_response(result, partner.name)
            else:
                _logger.error(
                    "Failed to create bank account for vendor %s in Bill.com: %s",
                    partner.name,
                    result,
                )
                return False
        except Exception as e:
            _logger.error(
                "Error creating bank account for vendor %s: %s",
                partner.name,
                str(e),
            )
            return False

    def _handle_successful_creation(self, result, bank, partner):
        """Handle successful bank account creation."""
        _logger.info(
            "Successfully created bank account for vendor %s in Bill.com. ID: %s",
            partner.name,
            result.get("id"),
        )

        bank.with_context(skip_billcom_sync=True).write(
            {
                "billcom_vendor_bank_id": result.get("id"),
                "billcom_account_status": result.get("status", ""),
                "billcom_last_sync_date": fields.Datetime.now(),
            }
        )

        account_number = bank.acc_number
        partner.message_post(
            body=_(
                "<p><strong>Bank Account Synced to Bill.com</strong></p>"
                "<ul>"
                "<li>Bank: %(bank)s</li>"
                "<li>Account: ****%(account)s</li>"
                "<li>Bill.com ID: %(id)s</li>"
                "<li>Status: %(status)s</li>"
                "</ul>"
            )
            % {
                "bank": bank.bank_id.name if bank.bank_id else "Unknown",
                "account": (
                    account_number[-4:] if len(account_number) >= 4 else "****"
                ),
                "id": result.get("id"),
                "status": result.get("status", "Unknown"),
            },
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )

        return True

    def _handle_error_response(self, result, partner_name):
        """Handle error response from Bill.com API."""
        error_messages = []
        for item in result:
            if isinstance(item, dict) and item.get("message"):
                error_messages.append(item.get("message"))

        error_str = ", ".join(error_messages) if error_messages else str(result)
        _logger.error(
            "Failed to create bank account for vendor %s in Bill.com: %s",
            partner_name,
            error_str,
        )
        return False

    def sync_vendor_bank_account(self, partner):
        """Synchronize vendor bank account with Bill.com."""
        # Validate prerequisites
        is_valid, partner_billcom_id, bank = self._validate_bank_sync_prerequisites(
            partner
        )
        if not is_valid:
            return False

        try:
            # Check and delete existing bank account if needed
            has_bank_account = self._check_existing_bank_account(
                partner_billcom_id, partner.name
            )
            if has_bank_account:
                self._delete_existing_bank_account(partner_billcom_id, partner.name)

            # Build payload
            bank_data = self._build_bank_account_payload(bank, partner)
            if not bank_data:
                return False

            # Create bank account
            return self._create_bank_account_in_billcom(
                partner_billcom_id, bank_data, bank, partner
            )

        except Exception as e:
            _logger.error("Error syncing vendor bank account: %s", str(e))
            return False

    @api.model
    def sync_partners(self, partner_type="vendor"):
        """Synchronize partners with Bill.com

        Args:
            partner_type (str): Type of partner to sync ('vendor' or 'customer')

        Returns:
            list: List of partner IDs that were synced
        """
        try:
            config = self._get_config()
            if not config:
                return []

            # Determine if sync is enabled for this partner type
            if partner_type == "vendor" and not config.sync_vendors:
                _logger.info("Vendor synchronization is disabled")
                return []
            elif partner_type == "customer" and not config.sync_customers:
                _logger.info("Customer synchronization is disabled")
                return []

            # Set parameters based on partner type
            if partner_type == "vendor":
                endpoint = "vendors"
                rank_field = "supplier_rank"
                other_rank_field = "customer_rank"
                rank_value = 1
                other_rank_value = 0
            else:  # customer
                endpoint = "customers"
                rank_field = "customer_rank"
                other_rank_field = "supplier_rank"
                rank_value = 1
                other_rank_value = 0

            # Get partners from Bill.com API
            _logger.info("Fetching %ss from Bill.com", partner_type)
            partners_data = self._make_request(
                endpoint,
                method="GET",
                params={"isActive": True, "start": 0, "max": 100},
            )

            # Get partners from Odoo that need to be synced to Bill.com
            # For vendors, we only sync those that have been updated since the last sync
            domain = [("is_sync_to_billcom", "=", True), (rank_field, ">", 0)]

            # Get all partners that need to be synced
            partners_to_sync = self.env["res.partner"].search(domain)
            _logger.info(
                "Found %d %ss in Odoo marked for sync",
                len(partners_to_sync),
                partner_type,
            )

            synced_partners = []

            # First, process partners from Bill.com to Odoo
            for partner_data in partners_data.get("data", []):
                # Skip if no ID
                if not partner_data.get("id"):
                    continue

                # Check if partner already exists
                existing_partner = (
                    self.env["res.partner"]
                    .with_context(active_test=False)
                    .search(
                        [("billcom", "=", partner_data["id"]), (rank_field, ">", 0)],
                        limit=1,
                    )
                )

                # Prepare common partner data
                partner_vals = {
                    "name": partner_data.get("name", ""),
                    "email": partner_data.get("email", ""),
                    "phone": partner_data.get("phone", ""),
                    "street": partner_data.get("address1", ""),
                    "street2": partner_data.get("address2", ""),
                    "city": partner_data.get("city", ""),
                    "state_id": self._get_state_id(partner_data.get("state", "")),
                    "zip": partner_data.get("zip", ""),
                    "country_id": self._get_country_id(partner_data.get("country", "")),
                    "website": partner_data.get("website", ""),
                    "last_sync_date": fields.Datetime.now(),
                    "active": True,
                }

                if existing_partner:
                    # Update existing partner
                    _logger.info(
                        "Updating %s %s from Bill.com", partner_type, partner_data["id"]
                    )
                    existing_partner.with_context(skip_billcom_sync=True).write(
                        partner_vals
                    )
                    synced_partners.append(existing_partner.id)
                    _logger.info(
                        "Updated %s %s from Bill.com", partner_type, partner_data["id"]
                    )
                else:
                    # Create new partner
                    _logger.info(
                        "Creating %s %s from Bill.com", partner_type, partner_data["id"]
                    )
                    partner_vals.update(
                        {
                            rank_field: rank_value,
                            other_rank_field: other_rank_value,
                            "billcom": partner_data["id"],
                            "is_sync_to_billcom": True,
                        }
                    )
                    new_partner = (
                        self.env["res.partner"]
                        .with_context(skip_billcom_sync=True)
                        .create(partner_vals)
                    )
                    synced_partners.append(new_partner.id)
                    _logger.info(
                        "Created %s %s from Bill.com", partner_type, partner_data["id"]
                    )

            for partner in partners_to_sync:
                if (
                    partner.billcom
                    and partner.last_sync_date
                    and partner.write_date <= partner.last_sync_date
                ):
                    _logger.info(
                        "Skipping %s %s - no changes since last sync",
                        partner_type,
                        partner.name,
                    )
                    continue

                _logger.info(
                    "Syncing %s %s to Bill.com (write_date: %s, last_sync_date: %s)",
                    partner_type,
                    partner.name,
                    partner.write_date,
                    partner.last_sync_date,
                )
                try:
                    result = self.sync_partner(partner, partner_type)
                    if result:
                        synced_partners.append(partner.id)
                        _logger.info(
                            "Successfully synced %s %s to Bill.com",
                            partner_type,
                            partner.name,
                        )
                except Exception as e:
                    _logger.error(
                        "Error syncing %s %s to Bill.com: %s",
                        partner_type,
                        partner.name,
                        str(e),
                    )

            _logger.info(
                "Successfully synced %d %ss with Bill.com",
                len(synced_partners),
                partner_type,
            )
            return synced_partners
        except Exception as e:
            _logger.error("Error syncing %ss with Bill.com: %s", partner_type, str(e))
            return []

    @api.model
    def sync_document(self, document, doc_type="invoice"):
        """Sync single document to Bill.com"""
        if (
            not document.is_sync_to_billcom
            or not document.partner_id.is_sync_to_billcom
        ):
            _logger.info(
                "%s %s not marked for sync to BillCom", doc_type, document.name
            )
            return False

        try:
            config = self._get_config()

            if doc_type == "bill" and not config.sync_bills:
                _logger.info("Vendor bill synchronization is disabled")
                return False
            elif doc_type == "invoice" and not config.sync_invoices:
                _logger.info("Customer invoice synchronization is disabled")
                return False

            partner_type = "vendor" if doc_type == "bill" else "customer"
            if not (document.partner_id.billcom_id or document.partner_id.billcom):
                partner_result = self.sync_partner(document.partner_id, partner_type)
                if not partner_result:
                    _logger.warning(
                        f"Cannot sync {doc_type} {document.name}: Partner sync failed"
                    )
                    return False

            return document.button_sync_to_billcom()
        except Exception as e:
            _logger.error(
                "%s sync failed for %s: %s", doc_type.title(), document.name, str(e)
            )
            raise

    @api.model
    def sync_bills(self):
        """Synchronize vendor bills with Bill.com

        This method has two functions:
        1. Push Odoo bills to Bill.com that are marked for sync
        2. Pull bills from Bill.com API if configured

        Returns:
            list: List of synced bill IDs
        """
        # Get config and check if sync is enabled
        try:
            config = self._get_config()
            if not config.sync_bills:
                _logger.info("Vendor bill synchronization is disabled")
                return []
        except UserError:
            return []

        # Find bills marked for sync that haven't been synced yet
        bills = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("is_sync_to_billcom", "=", True),
                ("last_sync_date", "=", False),
                ("partner_id.is_sync_to_billcom", "=", True),
            ]
        )

        synced_bills = []
        for bill in bills:
            try:
                result = self.sync_document(bill, "bill")
                if result:
                    synced_bills.append(bill.id)
                    _logger.info("Synced bill %s to Bill.com", bill.name)
            except Exception as e:
                _logger.error("Skipping bill %s due to error: %s", bill.name, str(e))

        # Also get bills from Bill.com API if configured
        if config.import_bills:
            try:
                # Get bills from Bill.com using v3 API
                bills_data = self._make_request(
                    "bills",
                    method="GET",
                    params={"isActive": True, "start": 0, "max": 100},
                )

                for bill_data in bills_data.get("data", []):
                    # Check if bill already exists in Odoo
                    existing_bill = self.env["account.move"].search(
                        [
                            ("billcom", "=", bill_data["id"]),
                            ("move_type", "=", "in_invoice"),
                        ],
                        limit=1,
                    )

                    if existing_bill:
                        _logger.info("Bill %s already exists in Odoo", bill_data["id"])
                        continue

                    # Find vendor
                    vendor = self.env["res.partner"].search(
                        [("billcom", "=", bill_data.get("vendorId"))], limit=1
                    )

                    if not vendor:
                        _logger.warning(
                            "Vendor not found for Bill.com bill %s", bill_data["id"]
                        )
                        continue

                    # Get default vendor bill journal
                    company = vendor.company_id or self.env.company
                    journal = self.env["account.journal"].search(
                        [
                            ("type", "=", "purchase"),
                            ("company_id", "=", company.id),
                        ],
                        limit=1,
                    )

                    if not journal:
                        _logger.error(
                            "No purchase journal found for company %s, skipping bill %s",
                            company.name,
                            bill_data["id"],
                        )
                        continue

                    # Create bill in Odoo
                    bill_vals = {
                        "partner_id": vendor.id,
                        "move_type": "in_invoice",
                        "journal_id": journal.id,
                        "invoice_date": bill_data.get("invoiceDate"),
                        "invoice_date_due": bill_data.get("dueDate"),
                        "ref": bill_data.get("invoiceNumber", ""),
                        "invoice_origin": bill_data.get("purchaseOrderNumber", ""),
                        "billcom_invoice_number": bill_data.get("invoiceNumber", ""),
                        "billcom": bill_data["id"],
                        "last_sync_date": fields.Datetime.now(),
                        "narration": bill_data.get("description", ""),
                        "is_sync_to_billcom": True,
                    }

                    # Create bill
                    bill = self.env["account.move"].create(bill_vals)
                    synced_bills.append(bill.id)

                    # Create bill lines
                    for line_data in bill_data.get("billLineItems", []):
                        line_vals = {
                            "move_id": bill.id,
                            "name": line_data.get("description", ""),
                            "quantity": line_data.get("quantity", 1.0),
                            "price_unit": line_data.get("amount", 0.0),
                        }

                        self.env["account.move.line"].create(line_vals)

                    _logger.info("Created bill %s from Bill.com", bill_data["id"])
            except Exception as e:
                _logger.error("Error importing bills from Bill.com: %s", str(e))

        return synced_bills

    @api.model
    def sync_invoices(self):
        """Synchronize customer invoices with Bill.com

        This method has two functions:
        1. Push Odoo invoices to Bill.com that are marked for sync
        2. Pull invoices from Bill.com API if configured

        Returns:
            list: List of synced invoice IDs
        """
        # Get config and check if sync is enabled
        try:
            config = self._get_config()
            if not config.sync_invoices:
                _logger.info("Customer invoice synchronization is disabled")
                return []
        except UserError:
            return []

        # Find invoices marked for sync that haven't been synced yet
        invoices = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("is_sync_to_billcom", "=", True),
                ("last_sync_date", "=", False),
                ("partner_id.is_sync_to_billcom", "=", True),
            ]
        )

        synced_invoices = []
        for invoice in invoices:
            try:
                result = self.sync_document(invoice, "invoice")
                if result:
                    synced_invoices.append(invoice.id)
                    _logger.info("Synced invoice %s to Bill.com", invoice.name)
            except Exception as e:
                _logger.error(
                    "Skipping invoice %s due to error: %s",
                    invoice.name,
                    str(e),
                )

        # Also get invoices from Bill.com API if configured
        if config.import_invoices:
            try:
                # Get invoices from Bill.com using v3 API
                invoices_data = self._make_request(
                    "invoices",
                    method="GET",
                    params={"isActive": True, "start": 0, "max": 100},
                )

                for invoice_data in invoices_data.get("data", []):
                    # Check if invoice already exists in Odoo
                    existing_invoice = self.env["account.move"].search(
                        [
                            ("billcom", "=", invoice_data["id"]),
                            ("move_type", "=", "out_invoice"),
                        ],
                        limit=1,
                    )

                    if existing_invoice:
                        _logger.info(
                            "Invoice %s already exists in Odoo", invoice_data["id"]
                        )
                        continue

                    # Find customer
                    customer = self.env["res.partner"].search(
                        [("billcom", "=", invoice_data.get("customerId"))], limit=1
                    )

                    if not customer:
                        _logger.warning(
                            "Customer not found for Bill.com invoice %s",
                            invoice_data["id"],
                        )
                        continue

                    # Get default customer invoice journal
                    company = customer.company_id or self.env.company
                    journal = self.env["account.journal"].search(
                        [
                            ("type", "=", "sale"),
                            ("company_id", "=", company.id),
                        ],
                        limit=1,
                    )

                    if not journal:
                        _logger.error(
                            "No sale journal found for company %s, skipping invoice %s",
                            company.name,
                            invoice_data["id"],
                        )
                        continue

                    # Create invoice in Odoo
                    invoice_vals = {
                        "partner_id": customer.id,
                        "move_type": "out_invoice",
                        "journal_id": journal.id,
                        "invoice_date": invoice_data.get("invoiceDate"),
                        "invoice_date_due": invoice_data.get("dueDate"),
                        "ref": invoice_data.get("invoiceNumber", ""),
                        "billcom_invoice_number": invoice_data.get("invoiceNumber", ""),
                        "billcom": invoice_data["id"],
                        "last_sync_date": fields.Datetime.now(),
                        "narration": invoice_data.get("description", ""),
                        "is_sync_to_billcom": True,
                    }

                    # Create invoice
                    invoice = self.env["account.move"].create(invoice_vals)
                    synced_invoices.append(invoice.id)

                    # Create invoice lines
                    for line_data in invoice_data.get("invoiceLineItems", []):
                        line_vals = {
                            "move_id": invoice.id,
                            "name": line_data.get("description", ""),
                            "quantity": line_data.get("quantity", 1.0),
                            "price_unit": line_data.get("price", 0.0),
                            "tax_ids": [(6, 0, [])],  # No taxes by default
                        }

                        self.env["account.move.line"].create(line_vals)

                    _logger.info("Created invoice %s from Bill.com", invoice_data["id"])
            except Exception as e:
                _logger.error("Error importing invoices from Bill.com: %s", str(e))

        return synced_invoices

    @api.model
    def sync_payment(self, payment):
        """Sync single payment to Bill.com"""
        # Skip if payment is not marked for sync
        if not payment.is_sync_to_billcom or not payment.partner_id.is_sync_to_billcom:
            _logger.info("Payment %s not marked for sync to BillCom", payment.name)
            return False

        # Check if payment is for a vendor
        if payment.partner_type != "supplier" or payment.payment_type != "outbound":
            _logger.info("Payment %s is not a vendor payment", payment.name)
            return False

        # Use context to prevent infinite loops
        if self.env.context.get("skip_billcom_sync"):
            _logger.info("Skipping sync for payment %s due to context", payment.name)
            return False

        try:
            # Get config and check if sync is enabled
            config = self._get_config()

            # Check if sync is enabled for payments
            if not config.sync_payments:
                _logger.info("Payment synchronization is disabled")
                return False

            # Sync vendor first if needed
            if not payment.partner_id.billcom:
                partner_result = self.sync_partner(payment.partner_id, "vendor")
                if not partner_result:
                    _logger.warning(
                        "Cannot sync payment %s: Vendor sync failed", payment.name
                    )
                    return False

            # Use the payment's method to prepare data and sync
            return payment.button_sync_to_billcom()
        except Exception as e:
            _logger.error("Payment sync failed for %s: %s", payment.name, str(e))
            raise

    @api.model
    def sync_payments(self):
        """Synchronize vendor payments with Bill.com

        This method has two functions:
        1. Push Odoo payments to Bill.com that are marked for sync
        2. Pull payment status updates from Bill.com API

        Returns:
            list: List of synced payment IDs
        """
        # Get config and check if sync is enabled
        try:
            config = self._get_config()
            if not config.sync_payments:
                _logger.info("Payment synchronization is disabled")
                return []
        except UserError:
            return []

        # Find payments marked for sync that haven't been synced yet
        payments = self.env["account.payment"].search(
            [
                ("payment_type", "=", "outbound"),
                ("partner_type", "=", "supplier"),
                ("is_sync_to_billcom", "=", True),
                ("last_sync_date", "=", False),
                ("partner_id.is_sync_to_billcom", "=", True),
                ("state", "=", "posted"),
            ]
        )

        synced_payments = []
        for payment in payments:
            try:
                result = self.sync_payment(payment)
                if result:
                    synced_payments.append(payment.id)
                    _logger.info("Synced payment %s to Bill.com", payment.name)
            except Exception as e:
                _logger.error(
                    "Skipping payment %s due to error: %s", payment.name, str(e)
                )

        # Update status of existing payments in Bill.com
        existing_payments = self.env["account.payment"].search(
            [
                ("billcom", "!=", False),
                ("billcom_payment_status", "in", ["draft", "scheduled", "processing"]),
            ]
        )

        for payment in existing_payments:
            try:
                # Get payment status from Bill.com
                payment_data = self._make_request(
                    f"payments/{payment.billcom}", method="GET"
                )

                if payment_data and payment_data.get("id"):
                    # Update payment status
                    status = payment._map_billcom_status(
                        payment_data.get("singleStatus")
                    )
                    payment.with_context(skip_billcom_sync=True).write(
                        {
                            "billcom_payment_status": status,
                            "last_sync_date": fields.Datetime.now(),
                        }
                    )
                    _logger.info(
                        "Updated payment %s status to %s", payment.name, status
                    )
            except Exception as e:
                _logger.error(
                    "Error updating payment %s status: %s", payment.name, str(e)
                )

        return synced_payments

    # =========================================================================
    # WIZARD INTEGRATION METHODS
    # =========================================================================

    @api.model
    def sync_partners_by_type(self, partner_type="vendor", domain=None):
        """Sync partners by type with optional domain filter (used by wizard)"""
        if not domain:
            domain = []

        # Add partner type filter
        if partner_type == "vendor":
            domain.append(("supplier_rank", ">", 0))
        else:
            domain.append(("customer_rank", ">", 0))

        # Find partners
        partners = self.env["res.partner"].search(domain)
        synced_count = 0
        errors = []

        for partner in partners:
            try:
                result = self.sync_partner(partner, partner_type)
                if result:
                    synced_count += 1
                    _logger.info(f"Successfully synced {partner_type} {partner.name}")
            except Exception as e:
                error_msg = f"Error syncing {partner_type} {partner.name}: {str(e)}"
                _logger.error(error_msg)
                errors.append(error_msg)

        return {"synced": synced_count, "total": len(partners), "errors": errors}

    @api.model
    def sync_bills_by_domain(self, domain=None):
        """Sync bills with optional domain filter (used by wizard)"""
        if not domain:
            domain = []

        # Add bill-specific filters
        domain.extend(
            [
                ("move_type", "=", "in_invoice"),
                ("state", "in", ["draft", "posted"]),
            ]
        )

        # Find bills
        bills = self.env["account.move"].search(domain)
        synced_count = 0
        errors = []

        for bill in bills:
            try:
                result = self.sync_document(bill, "bill")
                if result:
                    synced_count += 1
                    _logger.info(f"Successfully synced bill {bill.name}")
            except Exception as e:
                error_msg = f"Error syncing bill {bill.name}: {str(e)}"
                _logger.error(error_msg)
                errors.append(error_msg)

        return {"synced": synced_count, "total": len(bills), "errors": errors}

    @api.model
    def sync_invoices_by_domain(self, domain=None):
        """Sync customer invoices with optional domain filter (used by wizard)"""
        if not domain:
            domain = []

        # Add invoice-specific filters
        domain.extend(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "in", ["draft", "posted"]),
            ]
        )

        # Find invoices
        invoices = self.env["account.move"].search(domain)
        synced_count = 0
        errors = []

        for invoice in invoices:
            try:
                result = self.sync_document(invoice, "invoice")
                if result:
                    synced_count += 1
                    _logger.info(f"Successfully synced invoice {invoice.name}")
            except Exception as e:
                error_msg = f"Error syncing invoice {invoice.name}: {str(e)}"
                _logger.error(error_msg)
                errors.append(error_msg)

        return {"synced": synced_count, "total": len(invoices), "errors": errors}

    @api.model
    def sync_payments_by_domain(self, domain=None):
        """Sync payments with optional domain filter (used by wizard)"""
        if not domain:
            domain = []

        # Add payment-specific filters
        domain.extend(
            [
                ("payment_type", "=", "outbound"),
                ("partner_type", "=", "supplier"),
                ("state", "in", ["draft", "posted"]),
            ]
        )

        # Find payments
        payments = self.env["account.payment"].search(domain)
        synced_count = 0
        errors = []

        for payment in payments:
            try:
                result = self.sync_payment(payment)
                if result:
                    synced_count += 1
                    _logger.info(f"Successfully synced payment {payment.name}")
            except Exception as e:
                error_msg = f"Error syncing payment {payment.name}: {str(e)}"
                _logger.error(error_msg)
                errors.append(error_msg)

        return {"synced": synced_count, "total": len(payments), "errors": errors}

    @api.model
    def sync_attachments_by_domain(self, domain=None):
        """Sync attachments with optional domain filter (used by wizard)"""
        if not domain:
            domain = []

        # Add attachment-specific filters
        domain.extend(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "!=", False),
            ]
        )

        # Find attachments
        attachments = self.env["ir.attachment"].search(domain)

        # Filter attachments that belong to synced bills
        filtered_attachments = attachments.filtered(
            lambda a: a.res_model == "account.move"
            and a.res_id
            and self.env["account.move"].browse(a.res_id).exists()
            and self.env["account.move"].browse(a.res_id).partner_id.is_sync_to_billcom
        )

        synced_count = 0
        errors = []

        for attachment in filtered_attachments:
            try:
                # Here you would implement attachment sync logic
                # For now, we'll just log it as a placeholder
                _logger.info(f"Attachment sync for {attachment.name} (placeholder)")
                synced_count += 1
            except Exception as e:
                error_msg = f"Error syncing attachment {attachment.name}: {str(e)}"
                _logger.error(error_msg)
                errors.append(error_msg)

        return {
            "synced": synced_count,
            "total": len(filtered_attachments),
            "errors": errors,
        }

    @api.model
    def _map_billcom_bill_status_to_odoo_state(self, paymentStatus):
        """Map Bill.com bill paymentStatus to Odoo move state

        Bill.com Bill paymentStatus:
        - UNDEFINED: Status not defined → draft
        - APPROVING: Being approved → posted
        - SCHEDULED: Payment scheduled → posted
        - PAID: Fully paid → posted
        - CANCELLED: Cancelled → posted (keep posted, just mark as paid)
        - VOID: Voided → posted
        - ESCHEATED: Escheated → posted

        Odoo States:
        - draft: Not confirmed
        - posted: Confirmed and accounting entries created
        """
        if paymentStatus == "UNDEFINED":
            return "draft"
        else:
            # All other statuses mean the bill is confirmed
            return "posted"

    @api.model
    def _map_billcom_invoice_status_to_odoo_state(self, status):
        """Map Bill.com invoice status to Odoo move state

        Bill.com Invoice Statuses (similar to bills):
        - OPEN: Invoice sent, awaiting payment
        - UNDEFINED: Status not defined → draft
        - PAID_IN_FULL: Fully paid → posted
        - PARTIAL_PAYMENT: Partially paid → posted
        - SCHEDULED: Payment scheduled → posted

        Odoo States:
        - draft: Not confirmed
        - posted: Confirmed and accounting entries created
        """
        if status in ["OPEN", "UNDEFINED"]:
            return "draft"
        else:
            return "posted"

    @api.model
    def _map_billcom_payment_status_to_odoo_state(self, paymentStatus):
        """Map Bill.com payment paymentStatus to Odoo payment state

        Bill.com Payment paymentStatus:
        - UNDEFINED: Not defined → draft
        - UNPAID: Not paid yet → draft
        - PAID: Paid → posted
        - PARTIALLY_PAID: Partially paid → posted
        - SCHEDULED: Scheduled → posted
        - IN_PROCESS: Being processed → posted

        Odoo Payment States:
        - draft: Not confirmed
        - posted: Confirmed
        - cancel: Cancelled (not used for these statuses)
        """
        if paymentStatus in ["UNDEFINED", "UNPAID"]:
            return "draft"
        else:
            # PAID, PARTIALLY_PAID, SCHEDULED, IN_PROCESS → posted
            return "posted"

    @api.model
    def process_queue_item_from_billcom(self, queue_item):
        """Process a queue item with data from BILL (BILL → Odoo)

        Args:
            queue_item: billcom.sync.queue record with sync_data from BILL

        Returns:
            bool: True if processed successfully
        """
        if not queue_item.sync_data:
            _logger.error(f"Queue item {queue_item.id} has no sync_data from BILL")
            return False

        try:
            # Parse BILL data
            import ast

            billcom_data = ast.literal_eval(queue_item.sync_data)

            # Route to appropriate handler based on sync_type
            if queue_item.sync_type == "vendor":
                return self._process_vendor_from_billcom(queue_item, billcom_data)
            elif queue_item.sync_type == "customer":
                return self._process_customer_from_billcom(queue_item, billcom_data)
            elif queue_item.sync_type == "bill":
                return self._process_bill_from_billcom(queue_item, billcom_data)
            elif queue_item.sync_type == "invoice":
                return self._process_invoice_from_billcom(queue_item, billcom_data)
            elif queue_item.sync_type == "payment":
                return self._process_payment_from_billcom(queue_item, billcom_data)
            elif queue_item.sync_type == "document":
                _logger.info(
                    "Sync from BILL not supported for type: document. "
                    "Documents are synced via sync_documents_from_billcom() method"
                )
                return False
            else:
                _logger.warning(f"Unknown sync_type: {queue_item.sync_type}")
                return False

        except Exception as e:
            _logger.error(f"Error processing queue item {queue_item.id} from BILL: {e}")
            raise

    def _process_vendor_from_billcom(self, queue_item, billcom_data):
        """Create or update vendor from BILL data

        Args:
            queue_item: billcom.sync.queue record
            billcom_data: Vendor data from BILL API

        Returns:
            bool: True if successful
        """
        billcom_vendor_id = billcom_data.get("id")

        # Check if vendor exists
        partner = self.env["res.partner"].search(
            [("billcom_id", "=", billcom_vendor_id)], limit=1
        )

        # Prepare Odoo partner values from BILL data
        vals = {
            "name": billcom_data.get("name")
            or billcom_data.get("companyName", "Unknown Vendor"),
            "supplier_rank": 1,
            "is_sync_to_billcom": True,
            "billcom": billcom_vendor_id,
            "billcom_id": billcom_vendor_id,
            "email": billcom_data.get("email"),
            "phone": billcom_data.get("phone"),
            "ref": billcom_data.get("accountNumber"),  # Account number if exists
            "vat": billcom_data.get("taxId"),
            "active": not billcom_data.get(
                "archived", False
            ),  # BILL uses 'archived' flag
            "last_sync_date": fields.Datetime.now(),
            "company_type": (
                "company" if billcom_data.get("accountType") == "BUSINESS" else "person"
            ),
        }

        # Add short name as comment if exists
        if billcom_data.get("shortName"):
            vals["comment"] = f"Short name: {billcom_data.get('shortName')}"

        # Map address - BILL API v3 uses different field names
        address_data = billcom_data.get("address", {})
        if address_data:
            vals.update(
                {
                    "street": address_data.get("line1")
                    or address_data.get("addressLine1"),
                    "street2": address_data.get("line2")
                    or address_data.get("addressLine2"),
                    "city": address_data.get("city"),
                    "zip": address_data.get("zipOrPostalCode")
                    or address_data.get("zip"),
                }
            )

            # Map state
            state_code = address_data.get("stateOrProvince") or address_data.get(
                "state"
            )
            if state_code:
                state = self.env["res.country.state"].search(
                    [("code", "=", state_code)], limit=1
                )
                if state:
                    vals["state_id"] = state.id

            # Map country
            country_code = address_data.get("country")
            if country_code:
                country = self.env["res.country"].search(
                    [("code", "=", country_code)], limit=1
                )
                if country:
                    vals["country_id"] = country.id

        # Create or update partner
        if partner:
            # Update existing
            partner.with_context(skip_billcom_sync=True).write(vals)
            _logger.info(f"Updated vendor {partner.name} from BILL")
        else:
            # Create new
            partner = (
                self.env["res.partner"]
                .with_context(skip_billcom_sync=True)
                .create(vals)
            )
            _logger.info(f"Created vendor {partner.name} from BILL")

        # Process bank account information if available
        payment_info = billcom_data.get("paymentInformation", {})

        if payment_info and payment_info.get("bankAccount"):
            self._sync_partner_bank_account(partner, payment_info)

        # Update queue item with record_id
        queue_item.record_id = partner.id

        return True

    def _sync_partner_bank_account(self, partner, payment_info):
        """Create or update partner bank account from Bill.com paymentInformation

        Args:
            partner: res.partner record
            payment_info: paymentInformation dict from Bill.com vendor data

        Structure of paymentInformation:
        {
            "payeeName": "John Doe",
            "payByType": "WALLET",  // or "CHECK", "BANK_ACCOUNT", "AP_CARD"
            "payBySubType": "NONE", // or "ACH", "INTERNATIONAL_WIRE", etc.
            "bankAccount": {
                "accountNumber": "************1111",  // Often masked
                "routingNumber": "011401533",
                "type": "CHECKING",  // or "SAVINGS"
                "ownerType": "BUSINESS"  // or "PERSONAL"
            }
        }
        """
        bank_account_data = payment_info.get("bankAccount", {})
        routing_number = bank_account_data.get("routingNumber")
        account_number = bank_account_data.get("accountNumber", False)

        # Bill.com masks account numbers, so we can only update if we have full number
        if not routing_number:
            _logger.info(
                f"No routing number in paymentInformation "
                f"for {partner.name}, skipping bank account sync"
            )
            return

        # Find bank by routing number
        bank = self.env["res.bank"].search(
            [
                ("routing_number", "=", routing_number)
            ],  # In US, routing number goes in BIC field
            limit=1,
        )

        if not bank:
            # Create bank if doesn't exist
            bank = self.env["res.bank"].create(
                {
                    "name": bank_account_data.get("bankName", f"Bank {routing_number}"),
                    "routing_number": routing_number,
                }
            )

        # Check if partner already has this bank account (by routing number)
        existing_bank_account = self.env["res.partner.bank"].search(
            [
                ("partner_id", "=", partner.id),
                ("bank_id", "=", bank.id),
            ],
            limit=1,
        )

        # Prepare bank account values
        bank_vals = {
            "partner_id": partner.id,
            "bank_id": bank.id,
            "billcom_vendor_id": partner.id,  # Link bank to vendor for parent-child sync
            # Bill.com specific fields
            "billcom_pay_by_type": payment_info.get("payByType"),
            "billcom_pay_by_subtype": payment_info.get("payBySubType", "NONE"),
            "billcom_account_type": bank_account_data.get("type"),
            "billcom_owner_type": bank_account_data.get("ownerType"),
            "billcom_last_sync_date": fields.Datetime.now(),
        }

        # Set aba_routing if available (US bank routing number field)
        if routing_number:
            bank_vals["aba_routing"] = routing_number

        # Always set account number - even if masked or missing
        # acc_number is a required field in res.partner.bank
        is_masked = account_number and "*" in account_number
        if account_number:
            # Store account number even if masked (with asterisks)
            bank_vals["acc_number"] = account_number
        else:
            # If no account number provided, use routing number as placeholder
            bank_vals["acc_number"] = (
                f"****{routing_number[-4:]}" if routing_number else "****"
            )

        if existing_bank_account:
            # Update existing bank account
            existing_bank_account.write(bank_vals)
            _logger.info(
                f"Updated bank account for {partner.name} "
                f"(type: {payment_info.get('payByType')}, routing: {routing_number})"
            )
        else:
            # Create bank account even with masked account number
            # We have routing number and Bill.com metadata which is valuable for sync
            self.env["res.partner.bank"].create(bank_vals)
            if is_masked:
                _logger.info(
                    f"Created bank account for {partner.name} with masked account number "
                    f"(type: {payment_info.get('payByType')}, routing: {routing_number})"
                )
            else:
                _logger.info(
                    f"Created bank account for {partner.name} "
                    f"(type: {payment_info.get('payByType')}, routing: {routing_number})"
                )

    def _process_customer_from_billcom(self, queue_item, billcom_data):
        """Create or update customer from BILL data"""
        billcom_customer_id = billcom_data.get("id")

        # Check if customer exists
        partner = self.env["res.partner"].search(
            [("billcom_id", "=", billcom_customer_id)], limit=1
        )

        # Prepare Odoo partner values
        # Use companyName if exists, otherwise name
        customer_name = billcom_data.get("companyName") or billcom_data.get(
            "name", "Unknown Customer"
        )

        vals = {
            "name": customer_name,
            "customer_rank": 1,
            "is_sync_to_billcom": True,
            "billcom": billcom_customer_id,
            "billcom_id": billcom_customer_id,
            "email": billcom_data.get("email"),
            "phone": billcom_data.get("phone"),
            "ref": billcom_data.get("accountNumber"),
            "vat": billcom_data.get("taxId"),
            "active": not billcom_data.get("archived", False),
            "last_sync_date": fields.Datetime.now(),
            "company_type": (
                "company" if billcom_data.get("accountType") == "BUSINESS" else "person"
            ),
        }

        # Map contact information if exists
        contact_data = billcom_data.get("contact", {})
        if contact_data:
            first_name = contact_data.get("firstName", "")
            last_name = contact_data.get("lastName", "")
            if first_name or last_name:
                # Store contact name in a note
                contact_name = f"{first_name} {last_name}".strip()
                vals["comment"] = f"Contact: {contact_name}"

        # Add short name as additional comment if exists
        if billcom_data.get("shortName"):
            existing_comment = vals.get("comment", "")
            vals[
                "comment"
            ] = f"{existing_comment}\nShort name: {billcom_data.get('shortName')}".strip()

        # Map address - Customers use 'billingAddress' instead of 'address'
        address_data = billcom_data.get("billingAddress") or billcom_data.get(
            "address", {}
        )
        if address_data:
            vals.update(
                {
                    "street": address_data.get("line1")
                    or address_data.get("addressLine1"),
                    "street2": address_data.get("line2")
                    or address_data.get("addressLine2"),
                    "city": address_data.get("city"),
                    "zip": address_data.get("zipOrPostalCode")
                    or address_data.get("zip"),
                }
            )

            state_code = address_data.get("stateOrProvince") or address_data.get(
                "state"
            )
            if state_code:
                state = self.env["res.country.state"].search(
                    [("code", "=", state_code)], limit=1
                )
                if state:
                    vals["state_id"] = state.id

            country_code = address_data.get("country")
            if country_code:
                country = self.env["res.country"].search(
                    [("code", "=", country_code)], limit=1
                )
                if country:
                    vals["country_id"] = country.id

        # Create or update
        if partner:
            partner.with_context(skip_billcom_sync=True).write(vals)
            _logger.info(f"Updated customer {partner.name} from BILL")
        else:
            partner = (
                self.env["res.partner"]
                .with_context(skip_billcom_sync=True)
                .create(vals)
            )
            _logger.info(f"Created customer {partner.name} from BILL")

        queue_item.record_id = partner.id
        return True

    def _process_bill_from_billcom(self, queue_item, billcom_data):
        """Create or update bill from BILL data"""
        billcom_bill_id = billcom_data.get("id")

        # Check if bill exists
        move = self.env["account.move"].search(
            [("billcom_id", "=", billcom_bill_id)], limit=1
        )

        # Find vendor
        vendor_billcom_id = billcom_data.get("vendorId")
        vendor = self.env["res.partner"].search(
            [("billcom_id", "=", vendor_billcom_id), ("supplier_rank", ">", 0)], limit=1
        )

        if not vendor:
            _logger.error(
                f"Vendor with BILL ID {vendor_billcom_id} not found for bill {billcom_bill_id}"
            )
            raise UserError(
                f"Vendor must be synced first. BILL Vendor ID: {vendor_billcom_id}"
            )

        # Extract invoice data from nested object
        invoice_data = billcom_data.get("invoice", {})
        invoice_number = invoice_data.get("invoiceNumber", billcom_bill_id)
        invoice_date = invoice_data.get("invoiceDate")
        invoice_origin = invoice_data.get("purchaseOrderNumber")

        # Get default vendor bill journal
        company = vendor.company_id or self.env.company
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )

        if not journal:
            raise UserError(
                f"No purchase journal found for company {company.name}. "
                f"Please configure a purchase journal."
            )

        # Prepare bill values
        vals = {
            "move_type": "in_invoice",
            "partner_id": vendor.id,
            "journal_id": journal.id,
            "ref": invoice_number,
            "billcom_invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "invoice_origin": invoice_origin,
            "invoice_date_due": billcom_data.get("dueDate"),
            "narration": billcom_data.get("description"),
            "billcom": billcom_bill_id,
            "billcom_id": billcom_bill_id,
            "billcom_status": billcom_data.get("paymentStatus"),  # UNPAID, PAID, etc.
            "last_sync_date": fields.Datetime.now(),
        }

        # Add PO number if exists
        if billcom_data.get("purchaseOrderNumber"):
            po_ref = billcom_data.get("purchaseOrderNumber")
            if vals.get("narration"):
                vals["narration"] = f"{vals['narration']}\nPO: {po_ref}"
            else:
                vals["narration"] = f"PO: {po_ref}"

        # Process line items - BILL uses 'billLineItems'
        bill_line_items = billcom_data.get("billLineItems", [])
        invoice_lines = []

        if bill_line_items:
            # Get default expense account
            default_account = self.env["account.account"].search(
                [
                    ("account_type", "=", "expense"),
                    ("company_id", "=", vendor.company_id.id or self.env.company.id),
                    ("deprecated", "=", False),
                ],
                limit=1,
            )

            for line in bill_line_items:
                line_description = line.get("description", "Bill Line Item")
                line_amount = line.get("amount", 0.0)

                line_vals = {
                    "name": line_description,
                    "quantity": 1.0,
                    "price_unit": line_amount,
                    "tax_ids": [(6, 0, [])],  # No taxes by default
                }

                # Set account (use default if not specified)
                if default_account:
                    line_vals["account_id"] = default_account.id

                invoice_lines.append((0, 0, line_vals))

        if invoice_lines:
            vals["invoice_line_ids"] = invoice_lines
        else:
            # If no line items, create a single line with the total amount
            default_account = self.env["account.account"].search(
                [
                    ("account_type", "=", "expense"),
                    ("company_id", "=", vendor.company_id.id or self.env.company.id),
                    ("deprecated", "=", False),
                ],
                limit=1,
            )

            if default_account:
                vals["invoice_line_ids"] = [
                    (
                        0,
                        0,
                        {
                            "name": billcom_data.get("description")
                            or "Bill from BILL.com",
                            "quantity": 1.0,
                            "price_unit": billcom_data.get("amount", 0.0),
                            "account_id": default_account.id,
                        },
                    )
                ]

        # Create or update
        if move:
            # Only update if in draft
            if move.state == "draft":
                move.with_context(skip_billcom_sync=True).write(vals)
                _logger.info(f"Updated bill {move.name} from BILL")
            else:
                _logger.info(f"Bill {move.name} already posted, skipping update")
        else:
            move = (
                self.env["account.move"]
                .with_context(skip_billcom_sync=True)
                .create(vals)
            )
            _logger.info(
                f"Created bill {move.name} from BILL (Invoice #: {invoice_number})"
            )

        # Map Bill.com status to Odoo state and apply if needed
        billcom_payment_status = billcom_data.get("paymentStatus", "UNDEFINED")
        target_state = self._map_billcom_bill_status_to_odoo_state(
            billcom_payment_status
        )

        if target_state == "posted" and move.state == "draft":
            # Post the bill if Bill.com status requires it
            try:
                move.with_context(skip_billcom_sync=True).action_post()
                _logger.info(
                    f"Posted bill {move.name} based on "
                    f"Bill.com status: {billcom_payment_status}"
                )
            except Exception as e:
                _logger.warning(
                    f"Could not post bill {move.name} from "
                    f"Bill.com status {billcom_payment_status}: {e}"
                )

        queue_item.record_id = move.id
        return True

    def _process_invoice_from_billcom(self, queue_item, billcom_data):  # noqa: C901
        """Create or update customer invoice from BILL data"""
        billcom_invoice_id = billcom_data.get("id")

        # Check if invoice exists
        move = self.env["account.move"].search(
            [("billcom_id", "=", billcom_invoice_id)], limit=1
        )

        # Find customer - BILL API v3 returns customerId directly (not nested)
        # Format: { "customerId": "0cu02TXNTXPYFNI16n6b", ... }
        customer_billcom_id = billcom_data.get("customerId")

        # Fallback: Try nested customer object (in case API changes or uses different format)
        customer_data = billcom_data.get("customer", {})
        if not customer_billcom_id and isinstance(customer_data, dict):
            customer_billcom_id = customer_data.get("id")

        # Try to find customer by BILL ID
        customer = None
        if customer_billcom_id:
            customer = self.env["res.partner"].search(
                [("billcom_id", "=", customer_billcom_id), ("customer_rank", ">", 0)],
                limit=1,
            )

        # If no customer ID or not found, try by email or name
        # (though invoice API doesn't typically include customer details beyond customerId)
        if not customer:
            customer_email = customer_data.get("email") if customer_data else None
            customer_name = customer_data.get("name") if customer_data else None

            if customer_email:
                customer = self.env["res.partner"].search(
                    [("email", "=", customer_email), ("customer_rank", ">", 0)], limit=1
                )

            if not customer and customer_name:
                customer = self.env["res.partner"].search(
                    [("name", "=", customer_name), ("customer_rank", ">", 0)], limit=1
                )

        if not customer:
            _logger.error(
                "Customer not found for invoice %s. "
                "BILL Customer ID: %s. "
                "Please sync customers from Bill.com first.",
                billcom_invoice_id,
                customer_billcom_id or "None",
            )
            raise UserError(
                f"Customer with Bill.com ID '{customer_billcom_id}' not found "
                f"in Odoo.\n\n"
                f"Please sync customers from Bill.com first using the sync wizard, \n"
                f"or create the customer manually and set their Bill.com ID."
            )

        # Extract invoice data - for invoices, data is at top level (not nested like bills)
        invoice_number = billcom_data.get("invoiceNumber", billcom_invoice_id)
        invoice_date = billcom_data.get("invoiceDate")
        invoice_origin = billcom_data.get("purchaseOrderNumber")

        # Get default customer invoice journal
        company = customer.company_id or self.env.company
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "sale"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )

        if not journal:
            raise UserError(
                f"No sale journal found for company {company.name}. "
                f"Please configure a sale journal."
            )

        # Prepare invoice values
        vals = {
            "move_type": "out_invoice",
            "partner_id": customer.id,
            "journal_id": journal.id,
            "ref": invoice_number,
            "invoice_origin": invoice_origin,
            "billcom_invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "invoice_date_due": billcom_data.get("dueDate"),
            "narration": billcom_data.get("description"),
            "billcom": billcom_invoice_id,
            "billcom_id": billcom_invoice_id,
            "billcom_status": billcom_data.get("status"),  # OPEN, PAID, etc.
            "last_sync_date": fields.Datetime.now(),
        }

        # Process line items - BILL uses 'invoiceLineItems' for customer invoices
        invoice_line_items = billcom_data.get("invoiceLineItems", [])
        invoice_lines = []

        if invoice_line_items:
            # Get default income account
            default_account = self.env["account.account"].search(
                [
                    ("account_type", "=", "income"),
                    ("company_id", "=", customer.company_id.id or self.env.company.id),
                    ("deprecated", "=", False),
                ],
                limit=1,
            )

            for line in invoice_line_items:
                line_description = line.get("description", "Invoice Line Item")
                line_price = line.get("price", 0.0)
                line_quantity = line.get("quantity", 1.0)

                line_vals = {
                    "name": line_description,
                    "quantity": line_quantity,
                    "price_unit": line_price,
                    "tax_ids": [(6, 0, [])],  # No taxes by default
                }

                # Set account (use default if not specified)
                if default_account:
                    line_vals["account_id"] = default_account.id

                invoice_lines.append((0, 0, line_vals))

        if invoice_lines:
            vals["invoice_line_ids"] = invoice_lines
        else:
            # If no line items, create a single line with the total amount
            default_account = self.env["account.account"].search(
                [
                    ("account_type", "=", "income"),
                    ("company_id", "=", customer.company_id.id or self.env.company.id),
                    ("deprecated", "=", False),
                ],
                limit=1,
            )

            if default_account:
                vals["invoice_line_ids"] = [
                    (
                        0,
                        0,
                        {
                            "name": billcom_data.get("description")
                            or "Invoice from " "BILL.com",
                            "quantity": 1.0,
                            "price_unit": billcom_data.get("amount", 0.0),
                            "account_id": default_account.id,
                        },
                    )
                ]

        # Create or update
        if move:
            # Only update if in draft
            if move.state == "draft":
                move.with_context(skip_billcom_sync=True).write(vals)
                _logger.info(f"Updated invoice {move.name} from BILL")
            else:
                _logger.info(f"Invoice {move.name} already posted, skipping update")
        else:
            move = (
                self.env["account.move"]
                .with_context(skip_billcom_sync=True)
                .create(vals)
            )
            _logger.info(
                f"Created invoice {move.name} from BILL (Invoice #: {invoice_number})"
            )

        # Map Bill.com status to Odoo state and apply if needed
        billcom_status = billcom_data.get("status", "UNDEFINED")
        target_state = self._map_billcom_invoice_status_to_odoo_state(billcom_status)

        if target_state == "posted" and move.state == "draft":
            # Post the invoice if Bill.com status requires it
            try:
                move.with_context(skip_billcom_sync=True).action_post()
                _logger.info(
                    f"Posted invoice {move.name} based on Bill.com status: {billcom_status}"
                )
            except Exception as e:
                _logger.warning(
                    f"Could not post invoice {move.name} from Bill.com "
                    f"status {billcom_status}: {e}"
                )

        queue_item.record_id = move.id
        return True

    def _process_payment_from_billcom(self, queue_item, billcom_data):
        """Create or update payment from BILL data"""
        billcom_payment_id = billcom_data.get("id")

        # Check if payment exists
        payment = self.env["account.payment"].search(
            [("billcom_id", "=", billcom_payment_id)], limit=1
        )

        # Find vendor
        vendor_billcom_id = billcom_data.get("vendorId")
        vendor = self.env["res.partner"].search(
            [("billcom_id", "=", vendor_billcom_id), ("supplier_rank", ">", 0)], limit=1
        )

        if not vendor:
            _logger.error(
                f"Vendor with BILL ID {vendor_billcom_id} not "
                f"found for payment {billcom_payment_id}"
            )
            raise UserError(
                f"Vendor must be synced first. BILL Vendor ID: {vendor_billcom_id}"
            )

        # Find default journal for vendor payments
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "bank"),
                ("company_id", "=", vendor.company_id.id or self.env.company.id),
            ],
            limit=1,
        )

        if not journal:
            raise UserError(_("No bank journal found for payments"))

        # Prepare payment values
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": vendor.id,
            "amount": billcom_data.get("amount", 0.0),
            "date": billcom_data.get("paymentDate") or fields.Date.today(),
            "journal_id": journal.id,
            "ref": billcom_data.get("description")
            or f"Payment from BILL {billcom_payment_id}",
            "billcom": billcom_payment_id,
            "billcom_id": billcom_payment_id,
            "billcom_status": billcom_data.get("status"),
            "last_sync_date": fields.Datetime.now(),
        }

        # Create or update
        if payment:
            # Only update if in draft
            if payment.state == "draft":
                payment.with_context(skip_billcom_sync=True).write(vals)
                _logger.info(f"Updated payment {payment.name} from BILL")
            else:
                _logger.info(f"Payment {payment.name} already posted, skipping update")
        else:
            payment = (
                self.env["account.payment"]
                .with_context(skip_billcom_sync=True)
                .create(vals)
            )
            _logger.info(f"Created payment {payment.name} from BILL")

        # Map Bill.com payment status to Odoo state and apply if needed
        billcom_payment_status = billcom_data.get("paymentStatus", "UNDEFINED")
        target_state = self._map_billcom_payment_status_to_odoo_state(
            billcom_payment_status
        )

        if target_state == "posted" and payment.state == "draft":
            # Post the payment if Bill.com status requires it
            try:
                payment.with_context(skip_billcom_sync=True).action_post()
                _logger.info(
                    f"Posted payment {payment.name} based on "
                    f"Bill.com status: {billcom_payment_status}"
                )
            except Exception as e:
                _logger.warning(
                    f"Could not post payment {payment.name} from Bill.com "
                    f"status {billcom_payment_status}: {e}"
                )

        queue_item.record_id = payment.id
        return True

    @api.model
    def get_funding_accounts(self):
        """
        Get list of funding accounts (organization bank accounts) from Bill.com

        Returns:
            list: List of funding account dictionaries with structure:
                {
                    'id': 'bac02ZTVOWXMVVAAicnz',
                    'bankName': 'Bank of America',
                    'nameOnAccount': 'bofa',
                    'accountNumber': '************0000',
                    'routingNumber': '011401533',
                    'type': 'CHECKING',
                    'status': 'VERIFIED',
                    'default': {'payables': True, 'receivables': True}
                }
        """
        try:
            _logger.info("Fetching funding accounts from Bill.com")

            # GET /v3/funding-accounts/banks
            response = self._make_request("funding-accounts/banks", method="GET")

            # Bill.com API v3 returns data in 'results' array
            funding_accounts = response.get("results", []) if response else []

            _logger.info(
                f"Retrieved {len(funding_accounts)} funding accounts from Bill.com"
            )

            return funding_accounts

        except Exception as e:
            _logger.error(f"Error fetching funding accounts from Bill.com: {e}")
            raise UserError(
                f"Failed to fetch funding accounts from Bill.com: {str(e)}"
            ) from e

    @api.model
    def get_default_funding_account(self, account_type="payables"):
        """
        Get the default funding account for payables or receivables

        Args:
            account_type: 'payables' or 'receivables'

        Returns:
            dict: Default funding account or None
        """
        try:
            funding_accounts = self.get_funding_accounts()

            # Find default account for the specified type
            for account in funding_accounts:
                if account.get("status") == "VERIFIED":
                    default_settings = account.get("default", {})
                    if default_settings.get(account_type, False):
                        _logger.info(
                            f"Found default {account_type} funding account: "
                            f"{account.get('bankName')} ({account.get('id')})"
                        )
                        return account

            # If no default found, return first verified account
            for account in funding_accounts:
                if account.get("status") == "VERIFIED":
                    _logger.warning(
                        f"No default {account_type} account found, "
                        f"using first verified: {account.get('bankName')}"
                    )
                    return account

            _logger.error("No verified funding accounts found")
            return None

        except Exception as e:
            _logger.error(f"Error getting default funding account: {e}")
            return None

    @api.model
    def generate_mfa_challenge(self, config, session_id=None):
        """Generate MFA challenge and return challenge ID

        Args:
            config: billcom.config record
            session_id: Optional existing session ID. If not provided, will login first.

        Returns:
            dict: {
                'challenge_id': str,
                'phone_number': str (masked),
                'session_id': str
            }
        """
        import requests

        challenge_url = None  # Initialize for error logging
        headers = {}  # Initialize for error logging

        try:
            # If no session_id provided, do basic login first
            if not session_id:
                session_id = self._basic_login(config)

            challenge_url = f"{config.api_url}/v3/mfa/challenge"
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "sessionId": session_id,
                "devKey": config.dev_key,
            }

            # POST with useBackup parameter
            # Set useBackup to false to use primary device (default)
            payload = {"useBackup": False}  # Use primary device

            _logger.info("Generating MFA challenge with payload: %s", payload)

            response = requests.post(
                challenge_url, json=payload, headers=headers, timeout=30
            )
            response.raise_for_status()

            result = response.json()
            challenge_id = result.get("challengeId")

            if not challenge_id:
                raise UserError(_("Failed to generate MFA challenge"))

            _logger.info("MFA challenge generated successfully: %s", challenge_id)

            # Try to get phone number info (may not be in response)
            phone_number = result.get("phoneNumber", "****")

            return {
                "challenge_id": challenge_id,
                "phone_number": phone_number,
                "session_id": session_id,
            }

        except requests.exceptions.RequestException as e:
            _logger.error("Failed to generate MFA challenge: %s", str(e))
            if challenge_url:
                _logger.error("Request URL: %s", challenge_url)
            if headers:
                _logger.error("Request headers: %s", headers)
            if hasattr(e, "response") and e.response is not None:
                _logger.error("Response status: %s", e.response.status_code)
                _logger.error("Response body: %s", e.response.text)
            raise UserError(_("Failed to generate MFA challenge: %s") % str(e)) from e

    @api.model
    def _basic_login(self, config):
        """Perform basic login without MFA handling

        Returns session ID for MFA challenge flow
        """
        import requests

        auth_url = f"{config.api_url}/v3/login"

        payload = {
            "organizationId": config.organization_id,
            "devKey": config.dev_key,
            "username": config.username,
            "password": config.password,
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }

        _logger.info("Performing basic login for MFA flow")
        response = requests.post(auth_url, json=payload, headers=headers, timeout=40)
        response.raise_for_status()

        result = response.json()
        session_id = result.get("sessionId")

        if not session_id:
            raise UserError(_("No session ID received from Bill.com API"))

        _logger.info("Basic login successful, session ID obtained")
        return session_id

    @api.model
    def validate_mfa_challenge(self, config, challenge_id, session_id, mfa_code):
        """Validate MFA challenge code and obtain Remember Me ID

        Args:
            config: billcom.config record
            challenge_id: Challenge ID from generate_mfa_challenge
            session_id: Session ID from generate_mfa_challenge
            mfa_code: 6-digit code from SMS/authenticator

        Returns:
            str: Remember Me ID (valid for 30 days)
        """
        import requests

        try:
            validate_url = f"{config.api_url}/v3/mfa/challenge/validate"

            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "sessionId": session_id,
                "devKey": config.dev_key,
            }

            # Get device name from config or use default
            device_name = config.mfa_device_name or "Odoo Integration"

            payload = {
                "challengeId": challenge_id,
                "token": mfa_code,
                "device": device_name,
                "machineName": device_name,  # Use same as device
                "rememberMe": True,  # Request Remember Me ID
            }

            _logger.info("Validating MFA code: %s", mfa_code)
            _logger.info("Challenge ID: %s", challenge_id[:30] + "...")
            _logger.info("Payload: %s", payload)

            response = requests.post(
                validate_url, json=payload, headers=headers, timeout=30
            )

            _logger.info("Response status: %s", response.status_code)
            _logger.info("Response body: %s", response.text)

            response.raise_for_status()

            result = response.json()
            remember_me_id = result.get("rememberMeId")

            if not remember_me_id:
                raise UserError(
                    _("MFA validation succeeded but no Remember Me ID received")
                )

            _logger.info(
                "MFA validated successfully. Remember Me ID obtained (valid 30 days)"
            )

            return remember_me_id

        except requests.exceptions.RequestException as e:
            _logger.error("MFA validation failed: %s", str(e))

            # Get detailed error from response
            error_detail = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_detail = (
                        error_json.get("message")
                        or error_json.get("error")
                        or str(error_json)
                    )
                    _logger.error("Bill.com error details: %s", error_json)
                except Exception:
                    error_detail = e.response.text or str(e)

            # Parse error for better user feedback
            error_msg = error_detail.lower()
            if "invalid" in error_msg or "incorrect" in error_msg:
                raise UserError(
                    _("Invalid MFA code. Please check and try again.")
                ) from e
            elif "expired" in error_msg:
                raise UserError(
                    _("MFA code expired. Please request a new code and try again.")
                ) from e
            elif "too many" in error_msg or "bdc_1358" in error_msg:
                raise UserError(
                    _(
                        "Too many MFA validation attempts.\n\n"
                        "Bill.com has temporarily blocked MFA validation.\n\n"
                        "Solutions:\n"
                        "1. Wait 5-10 minutes and try 'Setup MFA' again\n"
                        "2. Use manual Device ID method (see MFA_QUICK_GUIDE.md)\n"
                        "3. Contact Bill.com support to unlock"
                    )
                ) from e
            else:
                raise UserError(_("MFA validation failed: %s") % error_detail) from e

    # ========================================================================
    # PARTNER SYNCHRONIZATION FROM BILL.COM TO ODOO
    # ========================================================================

    @api.model
    def sync_partners_from_billcom(self, partner_type="vendor"):  # noqa: C901
        """Sync partners from Bill.com to Odoo (bulk sync)

        Args:
            partner_type (str): 'vendor' or 'customer'

        Returns:
            int: Number of partners synced
        """
        try:
            config = self._get_config()
        except UserError as e:
            _logger.warning(str(e))
            return {}

        # Check if sync is enabled for this partner type
        if partner_type == "vendor" and not config.sync_vendors:
            _logger.info("Vendor synchronization is disabled")
            return {}
        elif partner_type == "customer" and not config.sync_customers:
            _logger.info("Customer synchronization is disabled")
            return {}

        endpoint = "vendors" if partner_type == "vendor" else "customers"

        try:
            # Get partners from Bill.com API
            result = self._make_request(endpoint, method="GET")
            partners = result.get("data", [])
            synced_count = 0

            for partner_data in partners:
                try:
                    # Find existing partner in Odoo
                    existing_partner = self.env["res.partner"].search(
                        [("billcom", "=", partner_data["id"])], limit=1
                    )

                    address = partner_data.get("address", {})
                    partner_vals = {
                        "name": partner_data["name"],
                        "email": partner_data.get("email", ""),
                        "phone": partner_data.get("phone", ""),
                        "street": address.get("line1", ""),
                        "street2": address.get("line2", ""),
                        "city": address.get("city", ""),
                        "zip": address.get("zipOrPostalCode", ""),
                        "billcom": partner_data["id"],
                        "billcom_id": partner_data["id"],
                        "last_sync_date": fields.Datetime.now(),
                        "ref": partner_data.get("shortName", ""),
                        "lang": partner_data.get("language", "en_US"),
                        "is_sync_to_billcom": True,
                    }

                    # Set partner type ranks
                    if partner_type == "vendor":
                        partner_vals["supplier_rank"] = 1
                        partner_vals["customer_rank"] = 0
                    else:
                        partner_vals["supplier_rank"] = 0
                        partner_vals["customer_rank"] = 1

                    # Set state if available
                    if address.get("stateOrProvince"):
                        state = self.env["res.country.state"].search(
                            [("code", "=", address["stateOrProvince"])], limit=1
                        )
                        if state:
                            partner_vals["state_id"] = state.id

                    # Set country if available
                    if address.get("country"):
                        country = self.env["res.country"].search(
                            [("code", "=", address["country"])], limit=1
                        )
                        if country:
                            partner_vals["country_id"] = country.id

                    # Update or create partner
                    if existing_partner:
                        existing_partner.with_context(skip_billcom_sync=True).write(
                            partner_vals
                        )
                        _logger.info(
                            "Updated %s: %s from Bill.com",
                            partner_type,
                            partner_data["name"],
                        )
                        partner_to_use = existing_partner
                    else:
                        partner_to_use = (
                            self.env["res.partner"]
                            .with_context(skip_billcom_sync=True)
                            .create(partner_vals)
                        )
                        _logger.info(
                            "Created %s: %s from Bill.com",
                            partner_type,
                            partner_data["name"],
                        )

                    synced_count += 1

                    # Sync bank account for vendors
                    if partner_type == "vendor" and partner_to_use.billcom:
                        try:
                            bank_result = self._make_request(
                                f"vendors/{partner_to_use.billcom}/bank-account",
                                method="GET",
                            )

                            if bank_result and bank_result.get("bankAccount"):
                                bank_info = bank_result.get("bankAccount", {})

                                # Check if bank account already exists
                                existing_bank = False
                                if partner_to_use.bank_ids:
                                    for bank in partner_to_use.bank_ids:
                                        if bank.acc_number == bank_info.get(
                                            "accountNumber"
                                        ):
                                            existing_bank = True
                                            break

                                # Create bank account if it doesn't exist
                                if not existing_bank:
                                    bank_vals = {
                                        "acc_number": bank_info.get(
                                            "accountNumber", ""
                                        ),
                                        "aba_routing": bank_info.get(
                                            "routingNumber", ""
                                        ),
                                        "acc_holder_name": bank_info.get(
                                            "nameOnAccount", partner_to_use.name
                                        ),
                                        "partner_id": partner_to_use.id,
                                    }

                                    # Find bank by routing number
                                    if bank_info.get("routingNumber"):
                                        bank_id = self.env["res.bank"].search(
                                            [
                                                (
                                                    "aba_routing",
                                                    "=",
                                                    bank_info.get("routingNumber"),
                                                )
                                            ],
                                            limit=1,
                                        )
                                        if bank_id:
                                            bank_vals["bank_id"] = bank_id.id

                                    self.env["res.partner.bank"].create(bank_vals)
                                    _logger.info(
                                        "Created bank account for vendor %s from Bill.com",
                                        partner_to_use.name,
                                    )
                        except Exception as e:
                            # 404 means no bank account exists, which is fine
                            if "404" not in str(e):  # noqa: E713
                                _logger.warning(
                                    "Error syncing bank account for vendor %s: %s",
                                    partner_to_use.name,
                                    str(e),
                                )

                except Exception as e:
                    _logger.error(
                        "Error processing %s %s: %s",
                        partner_type,
                        partner_data.get("name", "Unknown"),
                        str(e),
                    )
                    continue

            _logger.info("Synced %d %ss from Bill.com", synced_count, partner_type)
            return synced_count

        except Exception as e:
            _logger.error("Error syncing %ss from Bill.com: %s", partner_type, str(e))
            raise UserError(
                _("Error syncing %(type)ss from Bill.com: %(error)s")
                % {"type": partner_type, "error": str(e)}
            ) from e

    @api.model
    def sync_bills_from_billcom(self):
        """Sync bills from Bill.com to Odoo (bulk sync for cron backup)

        Returns:
            int: Number of bills synced
        """
        try:
            config = self._get_config()
        except UserError as e:
            _logger.warning(str(e))
            return 0

        if not config.sync_bills:
            _logger.info("Bill synchronization is disabled")
            return 0

        try:
            # Get bills from Bill.com API with recent filter (last 30 days)
            from_date = (fields.Date.today() - timedelta(days=30)).isoformat()
            result = self._make_request(f"bills?updatedTime={from_date}", method="GET")
            bills = result.get("data", [])
            synced_count = 0

            _logger.info(f"Syncing {len(bills)} bills from Bill.com")

            for bill_data in bills:
                try:
                    # Create queue item and process
                    queue_item = type(
                        "obj",
                        (object,),
                        {
                            "entity_type": "BILL",
                            "entity_id": bill_data["id"],
                            "billcom_data": bill_data,
                        },
                    )()

                    self._process_bill_from_billcom(queue_item, bill_data)
                    synced_count += 1
                except Exception as e:
                    _logger.error(f"Error syncing bill {bill_data.get('id')}: {e}")

            _logger.info(f"Successfully synced {synced_count} bills from Bill.com")
            return synced_count

        except Exception as e:
            _logger.error(f"Error in bills sync from Bill.com: {e}")
            return 0

    @api.model
    def sync_invoices_from_billcom(self):
        """Sync invoices from Bill.com to Odoo (bulk sync for cron backup)

        Returns:
            int: Number of invoices synced
        """
        try:
            config = self._get_config()
        except UserError as e:
            _logger.warning(str(e))
            return 0

        if not config.sync_invoices:
            _logger.info("Invoice synchronization is disabled")
            return 0

        try:
            # Get invoices from Bill.com API with recent filter (last 30 days)
            from_date = (fields.Date.today() - timedelta(days=30)).isoformat()
            result = self._make_request(
                f"invoices?updatedTime={from_date}", method="GET"
            )
            invoices = result.get("data", [])
            synced_count = 0

            _logger.info(f"Syncing {len(invoices)} invoices from Bill.com")

            for invoice_data in invoices:
                try:
                    # Create queue item and process
                    queue_item = type(
                        "obj",
                        (object,),
                        {
                            "entity_type": "INVOICE",
                            "entity_id": invoice_data["id"],
                            "billcom_data": invoice_data,
                        },
                    )()

                    self._process_invoice_from_billcom(queue_item, invoice_data)
                    synced_count += 1
                except Exception as e:
                    _logger.error(
                        f"Error syncing invoice {invoice_data.get('id')}: {e}"
                    )

            _logger.info(f"Successfully synced {synced_count} invoices from Bill.com")
            return synced_count

        except Exception as e:
            _logger.error(f"Error in invoices sync from Bill.com: {e}")
            return 0

    @api.model
    def sync_payments_from_billcom(self):
        """Sync payments from Bill.com to Odoo (bulk sync for cron backup)

        Returns:
            int: Number of payments synced
        """
        try:
            config = self._get_config()
        except UserError as e:
            _logger.warning(str(e))
            return 0

        if not config.sync_payments:
            _logger.info("Payment synchronization is disabled")
            return 0

        try:
            # Get payments from Bill.com API with recent filter (last 30 days)
            from_date = (fields.Date.today() - timedelta(days=30)).isoformat()
            result = self._make_request(
                f"payments?updatedTime={from_date}", method="GET"
            )
            payments = result.get("data", [])
            synced_count = 0

            _logger.info(f"Syncing {len(payments)} payments from Bill.com")

            for payment_data in payments:
                try:
                    # Create queue item and process
                    queue_item = type(
                        "obj",
                        (object,),
                        {
                            "entity_type": "PAYMENT",
                            "entity_id": payment_data["id"],
                            "billcom_data": payment_data,
                        },
                    )()

                    self._process_payment_from_billcom(queue_item, payment_data)
                    synced_count += 1
                except Exception as e:
                    _logger.error(
                        f"Error syncing payment {payment_data.get('id')}: {e}"
                    )

            _logger.info(f"Successfully synced {synced_count} payments from Bill.com")
            return synced_count

        except Exception as e:
            _logger.error(f"Error in payments sync from Bill.com: {e}")
            return 0

    @api.model
    def sync_partners_cron(self):
        """Cron job to sync partners from Bill.com

        Returns:
            bool: True if sync completed successfully
        """
        try:
            # Get config and check if auto sync is enabled
            try:
                config = self._get_config()
                if (
                    hasattr(config, "auto_sync_enabled")
                    and not config.auto_sync_enabled
                ):
                    _logger.info("Automatic sync is disabled in configuration")
                    return False
            except UserError as e:
                _logger.warning(str(e))
                return False

            # Sync vendors if enabled
            if config.sync_vendors:
                try:
                    vendor_count = self.sync_partners_from_billcom(
                        partner_type="vendor"
                    )
                    _logger.info(
                        "Cron job synced %s vendors from Bill.com", vendor_count or 0
                    )
                except Exception as e:
                    _logger.error("Error in vendor sync cron: %s", str(e))

            # Sync customers if enabled
            if config.sync_customers:
                try:
                    customer_count = self.sync_partners_from_billcom(
                        partner_type="customer"
                    )
                    _logger.info(
                        "Cron job synced %s customers from Bill.com",
                        customer_count or 0,
                    )
                except Exception as e:
                    _logger.error("Error in customer sync cron: %s", str(e))

            return True
        except Exception as e:
            _logger.error("Error in partner sync cron: %s", str(e))
            return False

    @api.model
    def sync_partner_from_billcom_by_id(self, billcom_id, partner_type="vendor"):
        """Sync a specific partner from Bill.com by ID

        Args:
            billcom_id (str): Bill.com partner ID
            partner_type (str): 'vendor' or 'customer'

        Returns:
            res.partner: Synced partner record or False
        """
        try:
            config = self._get_config()
        except UserError as e:
            _logger.warning(str(e))
            return False

        # Check if sync is enabled for this partner type
        if partner_type == "vendor" and not config.sync_vendors:
            _logger.info("Vendor synchronization is disabled")
            return False
        elif partner_type == "customer" and not config.sync_customers:
            _logger.info("Customer synchronization is disabled")
            return False

        endpoint = (
            f"{'vendors' if partner_type == 'vendor' else 'customers'}/{billcom_id}"
        )

        try:
            # Get partner data from Bill.com
            partner_data = self._make_request(endpoint, method="GET")

            if not partner_data or partner_data.get("status") == "error":
                _logger.warning("Partner not found in Bill.com with ID: %s", billcom_id)
                return False

            # Find existing partner or create new one
            existing_partner = self.env["res.partner"].search(
                [("billcom_id", "=", billcom_id)], limit=1
            )
            if not existing_partner:
                existing_partner = self.env["res.partner"].search(
                    [("billcom", "=", billcom_id)], limit=1
                )

            address = partner_data.get("address", {})
            partner_vals = {
                "name": partner_data.get("name", "Unknown"),
                "email": partner_data.get("email", ""),
                "phone": partner_data.get("phone", ""),
                "street": address.get("line1", ""),
                "street2": address.get("line2", ""),
                "city": address.get("city", ""),
                "zip": address.get("zipOrPostalCode", ""),
                "billcom_id": billcom_id,
                "billcom": billcom_id,
                "last_sync_date": fields.Datetime.now(),
                "ref": partner_data.get("shortName", ""),
                "is_sync_to_billcom": True,
                "billcom_sync_state": "synced",
            }

            # Set partner type
            if partner_type == "vendor":
                partner_vals["supplier_rank"] = 1
                partner_vals["customer_rank"] = 0
            else:
                partner_vals["supplier_rank"] = 0
                partner_vals["customer_rank"] = 1

            # Set state/country
            if address.get("stateOrProvince"):
                state = self.env["res.country.state"].search(
                    [("code", "=", address["stateOrProvince"])], limit=1
                )
                if state:
                    partner_vals["state_id"] = state.id

            if address.get("country"):
                country = self.env["res.country"].search(
                    [("code", "=", address["country"])], limit=1
                )
                if country:
                    partner_vals["country_id"] = country.id

            if existing_partner:
                existing_partner.with_context(skip_billcom_sync=True).write(
                    partner_vals
                )
                _logger.info(
                    "Updated %s: %s from Bill.com",
                    partner_type,
                    partner_data.get("name"),
                )
                return existing_partner
            else:
                new_partner = (
                    self.env["res.partner"]
                    .with_context(skip_billcom_sync=True)
                    .create(partner_vals)
                )
                _logger.info(
                    "Created %s: %s from Bill.com",
                    partner_type,
                    partner_data.get("name"),
                )
                return new_partner

        except Exception as e:
            _logger.error(
                "Error syncing %s %s from Bill.com: %s",
                partner_type,
                billcom_id,
                str(e),
            )
            if existing_partner:
                existing_partner.billcom_sync_state = "error"
            return False

    def _validate_bulk_payment_count(self, payments):
        """Validate payment count is within Bill.com limit."""
        if not payments:
            return {"success": False, "errors": ["No payments provided"]}

        if len(payments) > 50:
            raise UserError(
                _(
                    "Bill.com bulk payment limit is 50 bills per request. "
                    "You selected %d payments. Please reduce the selection."
                )
                % len(payments)
            )

        return {"success": True}

    def _get_common_funding_account(self, first_payment):
        """Get common funding account for bulk payments."""
        common_funding_id = None
        funding_account = False

        # Try from first payment's journal
        if (
            first_payment.journal_id.bank_account_id
            and first_payment.journal_id.bank_account_id.billcom_funding_account_id
        ):
            funding_account = (
                first_payment.journal_id.bank_account_id.billcom_funding_account_id
            )
            common_funding_id = funding_account.billcom_id

        # If not found, try default
        if not common_funding_id:
            funding_account = self.env["billcom.funding.account"].search(
                [
                    ("is_default_payables", "=", True),
                    ("status", "=", "VERIFIED"),
                    ("company_id", "=", self.env.company.id),
                ],
                limit=1,
            )
            if funding_account:
                common_funding_id = funding_account.billcom_id

        common_funding_type = (
            first_payment.billcom_funding_account_type or "BANK_ACCOUNT"
        )

        # Validate funding account
        if common_funding_type != "WALLET" and not common_funding_id:
            return {
                "success": False,
                "errors": [
                    "No Bill.com funding account configured. "
                    "Please link a funding account in the journal's bank account or "
                    "configure a default payables funding account."
                ],
            }

        return {
            "success": True,
            "funding_id": common_funding_id,
            "funding_type": common_funding_type,
        }

    def _get_common_process_date(self, first_payment, funding_type):
        """Determine common process date for bulk payments."""
        requires_process_date = funding_type in ["WALLET", "AP_CARD"]
        common_process_date = None

        if requires_process_date or not first_payment.is_process_date_sync:
            if first_payment.billcom_process_date:
                date_obj = first_payment.billcom_process_date
            else:
                date_obj = fields.Date.today()

            # Convert to string format "YYYY-MM-DD"
            if isinstance(date_obj, str):
                common_process_date = date_obj
            elif hasattr(date_obj, "strftime"):
                common_process_date = date_obj.strftime("%Y-%m-%d")
            else:
                common_process_date = fields.Date.to_string(date_obj)

            # Validate format
            if not common_process_date or not isinstance(common_process_date, str):
                return {
                    "success": False,
                    "errors": [
                        f"Invalid process date format. "
                        f"Expected YYYY-MM-DD string, got: {common_process_date}"
                    ],
                }
        elif requires_process_date:
            return {
                "success": False,
                "errors": [
                    f"Process date is required for {funding_type} funding type "
                    "but was not set correctly."
                ],
            }

        return {"success": True, "process_date": common_process_date}

    def _validate_and_build_payment_items(self, payments):
        """Validate payments and build payment items list."""
        payment_items = []
        payment_mapping = {}

        for idx, payment in enumerate(payments):
            # Validate sync status
            if (
                not payment.is_sync_to_billcom
                or not payment.partner_id.is_sync_to_billcom
            ):
                return {
                    "success": False,
                    "errors": [
                        f"Payment {payment.name} or vendor {payment.partner_id.name} "
                        "is not marked for Bill.com synchronization"
                    ],
                }

            # Validate payment type
            if payment.payment_type != "outbound" or payment.partner_type != "supplier":
                return {
                    "success": False,
                    "errors": [
                        f"Payment {payment.name} is not a vendor payment "
                        "(must be outbound supplier payment)"
                    ],
                }

            # Get bill ID
            bill_id = self._get_payment_bill_id(payment)
            if not bill_id:
                return {
                    "success": False,
                    "errors": [
                        f"Payment {payment.name} does not have a linked bill with Bill.com ID. "
                        "Bulk payments can only pay existing bills. "
                        "Please sync the bill to Bill.com first or use single payment creation."
                    ],
                }

            # Build payment item
            payment_item = {
                "billId": bill_id,
                "amount": payment.amount,
            }

            payment_items.append(payment_item)
            payment_mapping[bill_id] = payment

            _logger.info(
                "Bulk Payment [%d/%d]: %s - Vendor: %s, Bill: %s, Amount: %s",
                idx + 1,
                len(payments),
                payment.name,
                payment.partner_id.name,
                bill_id,
                payment.amount,
            )

        return {
            "success": True,
            "items": payment_items,
            "mapping": payment_mapping,
        }

    def _get_payment_bill_id(self, payment):
        """Extract Bill.com bill ID from payment."""
        if payment.reconciled_bill_ids:
            for bill in payment.reconciled_bill_ids:
                if bill.billcom_id or bill.billcom:
                    return bill.billcom_id or bill.billcom
        return False

    def _build_bulk_payment_payload(
        self, funding_type, funding_id, process_date, payment_items
    ):
        """Build bulk payment payload for Bill.com API."""
        bulk_payload = {
            "fundingAccount": {
                "type": funding_type,
            },
            "payments": payment_items,
        }

        if funding_type != "WALLET":
            bulk_payload["fundingAccount"]["id"] = funding_id

        if process_date:
            bulk_payload["processDate"] = process_date

        return bulk_payload

    def _process_bulk_payment_results(self, result, payment_mapping, payment_items):
        """Process bulk payment API results."""
        if not result or not isinstance(result, list):
            return {
                "success": False,
                "errors": [f"Unexpected response format from Bill.com: {result}"],
            }

        success_count = 0
        error_count = 0
        errors = []

        for payment_result in result:
            bill_id = payment_result.get("billId")
            payment = payment_mapping.get(bill_id)

            if not payment:
                _logger.warning("No payment found for billId: %s", bill_id)
                continue

            if payment_result.get("id"):
                self._handle_bulk_payment_success(
                    payment, payment_result, bill_id, success_count, len(payment_items)
                )
                success_count += 1
            else:
                error_msg = self._handle_bulk_payment_error(
                    payment, payment_result, bill_id, error_count
                )
                errors.append(f"{payment.name}: {error_msg}")
                error_count += 1

        _logger.info("=" * 80)
        _logger.info("BULK PAYMENT COMPLETE")
        _logger.info("Success: %d, Errors: %d", success_count, error_count)
        _logger.info("=" * 80)

        return {
            "success": error_count == 0,
            "results": result,
            "errors": errors,
            "success_count": success_count,
            "error_count": error_count,
        }

    def _handle_bulk_payment_success(
        self, payment, payment_result, bill_id, success_count, total_items
    ):
        """Handle successful bulk payment result."""
        update_vals = {
            "billcom": payment_result.get("id"),
            "billcom_id": payment_result.get("id"),
            "last_sync_date": fields.Datetime.now(),
            "billcom_payment_status": payment._map_billcom_status(
                payment_result.get("singleStatus")
            ),
            "billcom_confirmation_number": payment_result.get("confirmationNumber", ""),
            "billcom_transaction_number": payment_result.get("transactionNumber", ""),
            "billcom_sync_status": "synced",
            "billcom_sync_error": False,
        }

        # Add international payment fields
        if payment_result.get("exchangeRate"):
            update_vals["billcom_exchange_rate"] = payment_result.get("exchangeRate")
        if payment_result.get("fundingAmount"):
            update_vals["billcom_funding_amount"] = payment_result.get("fundingAmount")

        payment.with_context(skip_billcom_sync=True).write(update_vals)

        # Post to chatter
        payment.message_post(
            body=f"<p><strong>Bill.com Bulk Payment Created</strong></p>"
            f"<ul>"
            f"<li>Bill.com ID: {payment_result.get('id')}</li>"
            f"<li>Bill ID: {bill_id}</li>"
            f"<li>Status: {payment_result.get('singleStatus')}</li>"
            f"<li>Confirmation #: {payment_result.get('confirmationNumber', 'N/A')}</li>"
            f"<li>Transaction #: {payment_result.get('transactionNumber', 'N/A')}</li>"
            f"<li>Bulk Request: {success_count + 1}/{total_items}</li>"
            f"</ul>",
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )

        _logger.info(
            "Bulk payment success [%d/%d]: %s - Bill.com ID: %s (Bill: %s)",
            success_count + 1,
            total_items,
            payment.name,
            payment_result.get("id"),
            bill_id,
        )

    def _handle_bulk_payment_error(self, payment, payment_result, bill_id, error_count):
        """Handle bulk payment error result."""
        error_msg = payment_result.get(
            "error", "Unknown error in bulk payment response"
        )

        payment.with_context(skip_billcom_sync=True).write(
            {
                "billcom_sync_status": "sync_failed",
                "billcom_sync_error": error_msg,
            }
        )

        _logger.error(
            "Bulk payment error [%d]: %s (Bill: %s) - Error: %s",
            error_count + 1,
            payment.name,
            bill_id,
            error_msg,
        )

        return error_msg

    @api.model
    def create_bulk_payments(self, payments):
        """Create bulk payments in Bill.com."""
        # Validate count
        validation = self._validate_bulk_payment_count(payments)
        if not validation["success"]:
            return validation

        _logger.info("=" * 80)
        _logger.info("BULK PAYMENT REQUEST - Processing %d payments", len(payments))
        _logger.info("=" * 80)

        # Get funding account
        first_payment = payments[0]
        funding_result = self._get_common_funding_account(first_payment)
        if not funding_result["success"]:
            return funding_result

        funding_id = funding_result["funding_id"]
        funding_type = funding_result["funding_type"]

        # Get process date
        date_result = self._get_common_process_date(first_payment, funding_type)
        if not date_result["success"]:
            return date_result

        process_date = date_result["process_date"]

        _logger.info("Common Funding Account: %s (type: %s)", funding_id, funding_type)
        _logger.info("Common Process Date: %s", process_date)

        # Build payment items
        items_result = self._validate_and_build_payment_items(payments)
        if not items_result["success"]:
            return items_result

        payment_items = items_result["items"]
        payment_mapping = items_result["mapping"]

        # Build payload
        bulk_payload = self._build_bulk_payment_payload(
            funding_type, funding_id, process_date, payment_items
        )

        # Log request
        _logger.info("=" * 80)
        _logger.info("SENDING BULK PAYMENT REQUEST TO BILL.COM")
        _logger.info("Total payments: %d", len(payment_items))
        _logger.info("Funding Account: %s (ID: %s)", funding_type, funding_id)
        _logger.info("Process Date: %s", process_date or "Not set")
        _logger.info("Full Payload: %s", bulk_payload)
        _logger.info("=" * 80)

        try:
            # Make API request
            result = self._make_request(
                "payments/bulk", method="POST", data=bulk_payload
            )

            _logger.info("Bulk payment response received: %s", result)

            # Process results
            return self._process_bulk_payment_results(
                result, payment_mapping, payment_items
            )

        except Exception as e:
            error_detail = str(e)
            friendly_message = self._extract_friendly_error(e)

            _logger.error("Bulk payment request failed: %s", error_detail)

            # Mark all payments as failed
            for payment in payments:
                payment.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_sync_status": "sync_failed",
                        "billcom_sync_error": friendly_message,
                    }
                )

            return {"success": False, "errors": [friendly_message]}
