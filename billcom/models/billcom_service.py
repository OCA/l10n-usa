import logging
import time

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomService(models.AbstractModel):
    _name = "billcom.service"
    _description = "Bill.com Integration Service"
    _inherit = ["billcom.service.abstract"]

    @api.model
    def full_sync_billcom(self):
        # Get configuration
        try:
            config = self.env['billcom.config'].sudo().get_config()
            # Only run if the interval is greater than 0
            if hasattr(config, 'full_sync_interval') and config.full_sync_interval > 0:
                self.sync_all()
            else:
                _logger.info('Bill.com full synchronization is disabled (interval set to 0)')
        except Exception as e:
            _logger.error('Error in Bill.com full synchronization: %s', str(e))

    @api.model
    def sync_billcom_payments(self):
        # Get configuration
        try:
            config = self.env['billcom.config'].sudo().get_config()
            # Only run if the interval is greater than 0 and payment sync is enabled
            if hasattr(config, 'payment_sync_interval') and config.payment_sync_interval > 0 and config.sync_payments:
                self.sync_payments()
            else:
                _logger.info('Bill.com payment synchronization is disabled')
        except Exception as e:
            _logger.error('Error in Bill.com payment synchronization: %s', str(e))

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
                "stateOrProvince": partner.state_id.code if partner.state_id else "",
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
            if partner.billcom:
                # Update existing partner
                _logger.info(
                    "Updating existing %s with ID %s in Bill.com",
                    partner_type,
                    partner.billcom,
                )
                result = self._make_request(
                    f"{endpoint}/{partner.billcom}", method="PATCH", data=partner_data
                )
            else:
                # Create new partner
                _logger.info("Creating new %s in Bill.com", partner_type)
                result = self._make_request(endpoint, method="POST", data=partner_data)

            # Log the result for debugging
            _logger.debug(
                "Bill.com API response for %s %s: %s",
                partner_type,
                partner.name,
                result,
            )

            # Handle response
            if result and result.get("id"):
                # Use context to prevent triggering sync again
                partner.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom": result.get("id"),
                        "last_sync_date": fields.Datetime.now(),
                    }
                )
                _logger.info(
                    "Successfully synced %s %s with Bill.com",
                    partner_type,
                    partner.name,
                )

                # If this is a vendor and it has bank accounts, sync them separately
                if partner_type == "vendor" and partner.bank_ids:
                    _logger.info("Syncing bank account for vendor %s", partner.name)
                    # Wait a moment to ensure the vendor is fully created in Bill.com
                    time.sleep(1)
                    # Create a new instance to call the method
                    service_instance = self.env["billcom.service"].create({})
                    service_instance.sync_vendor_bank_account(partner)

                return result
            return False
        except Exception as e:
            _logger.error(
                "%s sync failed for %s: %s", partner_type.title(), partner.name, str(e)
            )
            raise

    @api.model
    def sync_all(self):
        """Synchronize all entities with Bill.com"""
        try:
            config = self._get_config()
            if not config.auto_sync_enabled:
                _logger.info("Automatic sync is disabled in configuration")
                return {}
        except UserError as e:
            _logger.warning(str(e))
            return {}

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

    def sync_vendor_bank_account(self, partner):
        """Sync vendor bank account to Bill.com using dedicated endpoints

        According to Bill.com API v3 documentation, vendor bank accounts must be managed
        with dedicated endpoints:
        - POST /v3/vendors/{vendorId}/bank-account (create)
        - GET /v3/vendors/{vendorId}/bank-account (get)
        - DELETE /v3/vendors/{vendorId}/bank-account (delete)

        To update a bank account, we must first delete the existing one and then create a new one.
        """
        # Ensure we have a singleton
        if not self.ids:
            _logger.error("sync_vendor_bank_account called on empty recordset")
            return False

        # Validate partner
        if not partner:
            _logger.error("No partner provided to sync_vendor_bank_account")
            return False

        # Get configuration
        try:
            config = self._get_config()
            if not config:
                _logger.error("No active Bill.com configuration found")
                return False
        except Exception as e:
            _logger.error("Error getting Bill.com configuration: %s", str(e))
            return False

        if not partner.billcom:
            _logger.warning(
                "Cannot sync bank account: Partner %s has no Bill.com ID", partner.name
            )
            return False

        # Check if partner is a vendor (supplier)
        if not partner.supplier_rank:
            _logger.warning(
                "Cannot sync bank account: Partner %s is not a vendor", partner.name
            )
            return False

        if not partner.bank_ids:
            _logger.info("Vendor %s has no bank accounts to sync", partner.name)
            return False

        # Get the first bank account
        bank = partner.bank_ids[0]

        # Variable to track if we need to delete an existing bank account
        has_bank_account = False

        # Check if vendor already has a bank account in Bill.com
        try:
            # Try to get existing bank account
            try:
                result = self._make_request(
                    f"vendors/{partner.billcom}/bank-account", method="GET"
                )

                # If we get here, the request was successful
                # Handle different response formats
                if isinstance(result, list):
                    _logger.info(
                        "Received list response for bank account check: %s", result
                    )
                    # Assume no bank account if we get a list (usually an error response)
                    has_bank_account = False
                elif isinstance(result, dict) and result.get("id"):
                    has_bank_account = True
                    _logger.info(
                        "Found existing bank account for vendor %s in Bill.com",
                        partner.name,
                    )
                else:
                    has_bank_account = False
                    _logger.info(
                        "No bank account found for vendor %s in Bill.com", partner.name
                    )
            except Exception as e:
                # If error is 404, it means bank account doesn't exist, which is fine
                if "404" in str(e):
                    _logger.info(
                        "No bank account found for vendor %s in Bill.com (404 response)",
                        partner.name,
                    )
                    has_bank_account = False
                else:
                    # For other errors, log and continue with creation
                    _logger.warning(
                        "Error checking vendor bank account, will try to create: %s",
                        str(e),
                    )
                    has_bank_account = False

            # If bank account exists, delete it first
            if has_bank_account:
                _logger.info(
                    "Deleting existing bank account for vendor %s in Bill.com",
                    partner.name,
                )
                try:
                    self._make_request(
                        f"vendors/{partner.billcom}/bank-account", method="DELETE"
                    )
                    _logger.info(
                        "Successfully deleted bank account for vendor %s in Bill.com",
                        partner.name,
                    )
                except Exception as e:
                    _logger.warning(
                        "Error deleting bank account, will try to create anyway: %s",
                        str(e),
                    )

            # Create bank account data
            # Ensure we have valid account number and routing number
            account_number = bank.acc_number
            routing_number = bank.aba_routing

            if not account_number or account_number == "":
                _logger.error(
                    "Cannot create bank account: Missing account number for vendor %s",
                    partner.name,
                )
                return False

            if not routing_number or routing_number == "":
                _logger.error(
                    "Cannot create bank account: Missing routing number for vendor %s",
                    partner.name,
                )
                return False

            # Prepare bank account data according to Bill.com API v3 documentation
            # Reference: https://developer.bill.com/reference/createvendorbankaccount
            bank_data = {
                "nameOnAccount": bank.acc_holder_name or partner.name,
                "accountNumber": account_number,
                "routingNumber": routing_number,
                "type": "CHECKING",  # Default to checking account
                "ownerType": "BUSINESS"
                if partner.company_type == "company"
                else "PERSONAL",
                "bankCountry": bank.bank_id.country.code
                if bank.bank_id and bank.bank_id.country
                else "US",
                "paymentCurrency": bank.currency_id.code if bank.currency_id else "USD",
            }
            # Create new bank account
            _logger.info(
                "Creating bank account for vendor %s in Bill.com", partner.name
            )
            try:
                result = self._make_request(
                    f"vendors/{partner.billcom}/bank-account",
                    method="POST",
                    data=bank_data,
                )

                # Handle different response formats
                if isinstance(result, dict) and result.get("id"):
                    _logger.info(
                        "Successfully created bank account for vendor %s in Bill.com",
                        partner.name,
                    )
                    return True
                elif isinstance(result, list) and len(result) > 0:
                    # Extract error message from list response
                    error_messages = []
                    for item in result:
                        if isinstance(item, dict) and item.get("message"):
                            error_messages.append(item.get("message"))

                    error_str = (
                        ", ".join(error_messages) if error_messages else str(result)
                    )
                    _logger.error(
                        "Failed to create bank account for vendor %s in Bill.com: %s",
                        partner.name,
                        error_str,
                    )
                    return False
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

            # Now, process partners from Odoo to Bill.com
            # Only sync partners that have been updated since the last sync
            for partner in partners_to_sync:
                # Skip partners that already have a Bill.com ID and haven't been updated since last sync
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

                # Sync the partner to Bill.com
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
        # Skip if document or partner is not marked for sync
        if (
            not document.is_sync_to_billcom
            or not document.partner_id.is_sync_to_billcom
        ):
            _logger.info(
                "%s %s not marked for sync to BillCom", doc_type, document.name
            )
            return False

        try:
            # Get config and check if sync is enabled
            config = self._get_config()

            # Check if sync is enabled for this document type
            if doc_type == "bill" and not config.sync_bills:
                _logger.info("Vendor bill synchronization is disabled")
                return False
            elif doc_type == "invoice" and not config.sync_invoices:
                _logger.info("Customer invoice synchronization is disabled")
                return False

            # Sync partner first if needed
            partner_type = "vendor" if doc_type == "bill" else "customer"
            if not document.partner_id.billcom:
                partner_result = self.sync_partner(document.partner_id, partner_type)
                if not partner_result:
                    _logger.warning(
                        "Cannot sync %s %s: Partner sync failed",
                        doc_type,
                        document.name,
                    )
                    return False

            # Use the document's method to prepare data - this delegates to the model that knows its structure best
            # This avoids duplication of data preparation logic
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

                    # Create bill in Odoo
                    bill_vals = {
                        "partner_id": vendor.id,
                        "move_type": "in_invoice",
                        "invoice_date": bill_data.get("invoiceDate"),
                        "invoice_date_due": bill_data.get("dueDate"),
                        "ref": bill_data.get("invoiceNumber", ""),
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
                            "price_unit": line_data.get("price", 0.0),
                        }

                        # Find product if available
                        if line_data.get("itemId"):
                            product = self.env["product.product"].search(
                                [("billcom", "=", line_data["itemId"])], limit=1
                            )
                            if product:
                                line_vals["product_id"] = product.id

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
                    "Skipping invoice %s due to error: %s", invoice.name, str(e)
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

                    # Create invoice in Odoo
                    invoice_vals = {
                        "partner_id": customer.id,
                        "move_type": "out_invoice",
                        "invoice_date": invoice_data.get("invoiceDate"),
                        "invoice_date_due": invoice_data.get("dueDate"),
                        "ref": invoice_data.get("invoiceNumber", ""),
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
                        }

                        # Find product if available
                        if line_data.get("itemId"):
                            product = self.env["product.product"].search(
                                [("billcom", "=", line_data["itemId"])], limit=1
                            )
                            if product:
                                line_vals["product_id"] = product.id

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
