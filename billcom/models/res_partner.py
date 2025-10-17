# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "billcom.abstract.model"]

    billcom_res_currency_id = fields.Many2one(
        "res.currency",
        string="Bill.com Currency",
        default=lambda self: self.env.company.currency_id,
    )

    billcom_sync_state = fields.Selection(
        [
            ("pending", "Pending Sync"),
            ("synced", "Synced"),
            ("error", "Sync Error"),
        ],
        default="pending",
        string="Bill.com Sync State",
    )

    billcom_payment_purpose_id = fields.Many2one(
        "billcom.payment.purpose",
        string="Bill.com Payment Purpose",
        help="Payment purpose for international vendors (non-US) in Bill.com",
        domain="[('country_id', '=', country_id)]",
    )

    def _prepare_partner_data(self, partner_type="vendor"):  # noqa: C901
        """Prepare partner data for Bill.com API v3"""
        self.ensure_one()
        if not self.is_sync_to_billcom:
            return False

        # Get billing and shipping addresses
        billing_address = self
        shipping_address = self

        # If this is a contact with a parent company, use parent for some fields
        # parent_company = (
        #     self.parent_id if self.parent_id and self.parent_id.is_company else False
        # )

        # Check for specific address types in child contacts
        if self.child_ids:
            for child in self.child_ids:
                if child.type == "invoice":
                    billing_address = child
                elif child.type == "delivery":
                    shipping_address = child

        # Common data for both vendor and customer (only valid API v3 fields)
        common_data = {
            "name": self.name or "Unknown",  # Required field
            "shortName": self.ref
            or (self.name[:40] if self.name else "Unknown")[:40],  # Max 40 chars
        }

        # Add optional fields only if they have values
        if self.email:
            common_data["email"] = self.email
        if self.phone:
            common_data["phone"] = self.phone
        if self.ref:
            common_data["accountNumber"] = self.ref
        if self.billcom_res_currency_id and self.country_id.code != "US":
            common_data["billCurrency"] = self.billcom_res_currency_id.name

        # Log the common data for debugging
        _logger.info("Common data prepared: %s", common_data)

        # Address format for Bill.com API v3
        def format_address(addr):
            # Bill.com API v3 required address fields: line1, city, zipOrPostalCode, country
            address_data = {
                "line1": addr.street or "N/A",  # Required: line1 cannot be empty
                "city": addr.city or "N/A",  # Required: city cannot be empty
                "zipOrPostalCode": addr.zip or "00000",  # Required: cannot be empty
                "country": (
                    addr.country_id.code if addr.country_id else "US"
                ),  # Required: default to US
            }

            # Optional fields - only add if they have values
            if addr.street2:
                address_data["line2"] = addr.street2
            if addr.state_id and addr.state_id.code:
                address_data["stateOrProvince"] = addr.state_id.code

            # Log the address data for debugging
            _logger.info("Formatted address data: %s", address_data)

            return address_data

        if partner_type == "vendor":
            vendor_data = common_data.copy()

            # Add required fields for vendor
            vendor_data["accountType"] = "BUSINESS" if self.is_company else "PERSON"
            vendor_data["address"] = format_address(self)  # Required field

            # Add paymentInformation if vendor has bank account
            # This is required for enabling electronic payments to vendors
            # For child partners, use parent's bank accounts (parent-child structure)
            bank_partner = self.parent_id if self.parent_id else self
            if bank_partner.bank_ids:
                bank = bank_partner.bank_ids.filtered(
                    lambda r: r.billcom_vendor_id.id == self.id
                )  # Use first bank account
                if not bank:
                    bank = bank_partner.bank_ids[0]  # Fallback to first bank account

                # Check if we have minimum required bank information
                # Get routing number with priority
                routing_number = bank.aba_routing or (
                    bank.bank_id.routing_number if bank.bank_id else None
                )

                if bank.acc_number and routing_number:
                    payment_info = {
                        "payeeName": bank.acc_holder_name or self.name,
                        "payByType": bank.billcom_pay_by_type or "CHECK",
                        "payBySubType": bank.billcom_pay_by_subtype or "NONE",
                        "bankAccount": {
                            "nameOnAccount": bank.acc_holder_name or self.name,
                            "accountNumber": bank.acc_number,
                            "type": bank.billcom_account_type or "CHECKING",
                            "ownerType": bank.billcom_owner_type
                            or ("BUSINESS" if self.is_company else "PERSONAL"),
                        },
                    }

                    # Add international vendor fields if applicable
                    # Check if vendor is international (not US)
                    if self.country_id and self.country_id.code == "US":
                        payment_info["bankAccount"].update(
                            {"routingNumber": routing_number}
                        )
                    else:
                        payment_info["bankCountry"] = self.country_id.code
                        if bank.currency_id:
                            payment_info["paymentCurrency"] = bank.currency_id.name

                        payment_info.setdefault("bankInfo", {}).update(
                            {
                                "countryISO": self.country_id.code,
                            }
                        )

                        if bank.bank_id:
                            payment_info["bankInfo"].update(
                                {
                                    "branchName": "",
                                }
                            )
                            if bank.bank_id.name:
                                payment_info["bankInfo"].update(
                                    {
                                        "institutionName": bank.bank_id.name,
                                    }
                                )
                            if bank.bank_id.bic:
                                payment_info["bankInfo"].update(
                                    {
                                        "swiftBIC": bank.bank_id.bic,
                                    }
                                )
                            if bank.bank_id.street:
                                payment_info["bankInfo"].setdefault(
                                    "address", {}
                                ).update({"line1": bank.bank_id.street})
                            if bank.bank_id.city:
                                payment_info["bankInfo"].setdefault(
                                    "address", {}
                                ).update({"city": bank.bank_id.city})
                            if bank.bank_id.state:
                                payment_info["bankInfo"].setdefault("address", {})[
                                    "stateOrProvince"
                                ] = bank.bank_id.state.code
                            if bank.bank_id.zip:
                                payment_info["bankInfo"].setdefault("address", {})[
                                    "zipOrPostalCode"
                                ] = bank.bank_id.zip
                            if bank.bank_id.country:
                                payment_info["bankInfo"].setdefault("address", {})[
                                    "country"
                                ] = bank.bank_id.country.name

                    vendor_data["paymentInformation"] = payment_info
                    if bank_partner != self:
                        _logger.info(
                            "Added paymentInformation for vendor %s from parent %s: %s",
                            self.name,
                            bank_partner.name,
                            payment_info,
                        )
                    else:
                        _logger.info(
                            "Added paymentInformation for vendor %s: %s",
                            self.name,
                            payment_info,
                        )
                else:
                    _logger.info(
                        f"Vendor {self.name} (using {bank_partner.name} for banks) "
                        f"has bank account but missing account number or routing number"
                    )
            else:
                if bank_partner != self:
                    _logger.info(
                        "Vendor %s: parent %s has no bank accounts",
                        self.name,
                        bank_partner.name,
                    )
                else:
                    _logger.info("Vendor %s has no bank accounts", self.name)

            # Log final vendor data
            _logger.info("Final vendor data for Bill.com: %s", vendor_data)

            # Note: paymentTermId requires a Bill.com payment term ID (format: pte01XXXXXX)
            # not the Odoo payment term name. Omitting this field for now.
            # TODO: Implement payment term mapping between Odoo and Bill.com if needed

            return vendor_data
        else:  # customer
            customer_data = common_data.copy()

            # Add required fields for customer
            customer_data["accountType"] = "BUSINESS" if self.is_company else "PERSON"
            customer_data["billingAddress"] = format_address(billing_address)
            customer_data["shippingAddress"] = format_address(shipping_address)

            # Add optional language field if available
            if self.lang:
                customer_data["language"] = self.lang

            # Log final customer data
            _logger.info("Final customer data for Bill.com: %s", customer_data)

            # Note: paymentTermId requires a Bill.com payment term ID (format: pte01XXXXXX)
            # not the Odoo payment term name. Omitting this field for now.
            # TODO: Implement payment term mapping between Odoo and Bill.com if needed

            return customer_data

    def sync_to_billcom(self, partner_type="vendor"):
        """Sync partner to Bill.com - delegates to service"""
        self.ensure_one()
        if not self.is_sync_to_billcom:
            return False

        try:
            service = self.env["billcom.service"]
            return service.sync_partner(self, partner_type)
        except Exception as e:
            _logger.error(
                f"Error syncing partner {self.name} " f"to Bill.com: {str(e)}"
            )
            raise UserError(_(f"Error syncing to Bill.com: {e}")) from e

    def sync_to_billcom_vendor(self):
        """Sync as vendor - delegates to service"""
        return self.sync_to_billcom(partner_type="vendor")

    def sync_to_billcom_customer(self):
        """Sync as customer - delegates to service"""
        return self.sync_to_billcom(partner_type="customer")

    @api.model
    def sync_from_billcom(self, partner_type="vendor"):
        """Sync partners from Bill.com to Odoo - delegates to service"""
        service = self.env["billcom.service"]
        return service.sync_partners_from_billcom(partner_type=partner_type)

    @api.model
    def _sync_partners_cron(self):
        """Cron job to sync partners from Bill.com - delegates to service"""
        service = self.env["billcom.service"]
        return service.sync_partners_cron()

    @api.model
    def sync_from_billcom_by_id(self, billcom_id, partner_type="vendor"):
        """Sync a specific partner from Bill.com by ID - delegates to service"""
        service = self.env["billcom.service"]
        return service.sync_partner_from_billcom_by_id(
            billcom_id, partner_type=partner_type
        )

    def action_fetch_payment_purposes(self):
        """Fetch payment purposes from Bill.com for international vendor

        This button appears only for international vendors (non-US) that have
        a currency configured.
        """
        self.ensure_one()

        # Validation
        if not self.country_id:
            raise UserError(_("Please set the country for this partner first"))

        if self.country_id.code == "US":
            raise UserError(
                _(
                    "Payment purposes are only required for international (non-US) vendors"
                )
            )

        if not self.billcom_res_currency_id:
            raise UserError(
                _("Please set the Bill.com Currency for this partner first")
            )

        # Get account type from bank account if exists, otherwise use NONE
        account_type = "NONE"
        if self.bank_ids:
            bank = self.bank_ids[0]
            account_type = bank.billcom_account_type

        try:
            # Fetch payment purposes from API
            payment_purposes = self.env[
                "billcom.payment.purpose"
            ].fetch_payment_purposes_for_config(
                country_id=self.country_id.id,
                currency_id=self.billcom_res_currency_id.id,
                account_type=account_type,
            )

            if not payment_purposes:
                raise UserError(
                    _(
                        f"No payment purposes found for country {self.country_id.name}, "
                        f"currency {self.billcom_res_currency_id.name}, "
                        f"account type {account_type}"
                    )
                )

            # Show notification with count
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Payment Purposes Fetched"),
                    "message": _(
                        "%d payment purpose(s) loaded from Bill.com. You can now select one."
                    )
                    % len(payment_purposes),
                    "type": "success",
                    "sticky": False,
                    "next": {
                        "type": "ir.actions.act_window",
                        "res_model": "res.partner",
                        "res_id": self.id,
                        "view_mode": "form",
                        "target": "current",
                    },
                },
            }
        except Exception as e:
            _logger.error(f"Error fetching payment purposes: {e}")
            raise

    # Backwards compatibility
    _sync_vendors_cron = _sync_partners_cron


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    # Bill.com Funding Account (organization's bank account for payments)
    billcom_funding_account_id = fields.Many2one(
        "billcom.funding.account",
        string="Bill.com Funding Account",
        help="Link to the Bill.com funding account (organization bank account). "
        "This is used when creating payments to specify which account to pay from.",
        copy=False,
        domain=[("status", "=", "VERIFIED")],
        ondelete="restrict",
    )
    billcom_vendor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Bill.com Vendor",
        help="Link to the Bill.com vendor (partner) associated with this bank account",
        copy=False,
    )
    # Bill.com Vendor Bank Account Fields (vendor/customer's bank account)
    billcom_vendor_bank_id = fields.Char(
        string="Bill.com Vendor Bank ID",
        help="Bill.com vendor bank account ID",
        copy=False,
        readonly=True,
    )
    billcom_pay_by_type = fields.Selection(
        [
            ("ACH", "ACH"),
            ("WALLET", "Wallet"),
            ("CHECK", "Check"),
            ("VIRTUAL_CARD", "VIRTUAL CARD"),
            ("UNDEFINED", "UNDEFINED"),
            ("RPPS", "RPPS"),
            ("INTERNATIONAL_E_PAYMENT", "INTERNATIONAL EPAYMENT"),
            ("OFFLINE", "OFFLINE"),
        ],
        string="Bill.com Pay By Type",
        help="Default payment method for this vendor in Bill.com",
        copy=False,
    )
    billcom_pay_by_subtype = fields.Selection(
        [
            ("NONE", "None"),
            ("ACH", "ACH"),
            ("WIRE", "International Wire"),
            ("IACH", "IACH"),
            ("LOCAL", "LOCAL"),
            ("MULTIPLE", "MULTIPLE"),
            ("UNDEFINED", "UNDEFINED"),
        ],
        string="Bill.com Pay By Subtype",
        help="Payment subtype in Bill.com",
        copy=False,
    )
    billcom_account_type = fields.Selection(
        [
            ("CHECKING", "Checking"),
            ("SAVINGS", "Savings"),
        ],
        string="Bill.com Account Type",
        help="Bank account type in Bill.com",
        copy=False,
    )
    billcom_owner_type = fields.Selection(
        [
            ("BUSINESS", "Business"),
            ("PERSONAL", "Personal"),
        ],
        string="Bill.com Owner Type",
        help="Bank account owner type in Bill.com",
        copy=False,
    )
    billcom_account_status = fields.Char(
        string="Bill.com Account Status",
        help="Status of bank account in Bill.com (e.g., NET_LINKED_ACCOUNT, VERIFIED)",
        readonly=True,
        copy=False,
    )
    billcom_last_sync_date = fields.Datetime(
        string="Last Synced",
        help="Last synchronization date with Bill.com",
        readonly=True,
        copy=False,
    )

    def sync_bank_account_to_billcom(self):
        """Sync bank account to Bill.com when created/updated

        IMPORTANT: This method should only be used when vendor does NOT already
        have paymentInformation in Bill.com. If vendor already has payment info,
        you must re-sync the entire vendor to update bank account.

        Bill.com error BDC_1233 will occur if:
        - Vendor has pending invite
        - Vendor has pending bank account
        - Vendor already has epayment setup
        - Vendor is international
        """
        self.ensure_one()

        # Skip if context flag is set (to prevent circular sync)
        if self.env.context.get("skip_billcom_sync"):
            return

        # Only sync if partner is synced to Bill.com and has a Bill.com ID
        if (
            not self.billcom_vendor_id.billcom_id
            or not self.billcom_vendor_id.is_sync_to_billcom
        ):
            _logger.info(
                f"Skipping bank account sync: partner {self.billcom_vendor_id.name} "
                f"not synced to Bill.com"
            )
            return

        # Only sync if we have required bank information
        # Get routing number with priority
        routing_number = self.aba_routing or (
            self.bank_id.routing_number if self.bank_id else None
        )
        if not self.acc_number or not routing_number:
            _logger.warning(
                f"Cannot sync bank account: missing account number or routing number "
                f"for partner {self.partner_id.name}"
            )
            return

        # Check if this bank account was already synced
        if self.billcom_vendor_bank_id:
            raise UserError(
                _(
                    "This bank account is already synced to Bill.com (ID: %s).\n\n"
                    "To update bank account information:\n"
                    "1. Update the fields in Odoo\n"
                    "2. Re-sync the entire vendor (recommended)\n"
                    "   OR\n"
                    "3. Contact Bill.com support to update payment information"
                )
                % self.billcom_vendor_bank_id
            )

        try:
            service = self.env["billcom.service"]
            vendor_id = self.billcom_vendor_id.billcom_id

            # Prepare bank account data for Bill.com API v3
            # Endpoint: POST /v3/vendors/:vendorId/bank-account

            routing_number = self.aba_routing or (
                self.bank_id.routing_number if self.bank_id else None
            )
            bank_account_data = {
                "bankName": self.bank_id.name if self.bank_id else "Unknown",
                "accountNumber": self.acc_number,
                "type": self.billcom_account_type or "CHECKING",
                "ownerType": self.billcom_owner_type
                or (
                    "BUSINESS"
                    if self.partner_id.company_type == "company"
                    else "PERSONAL"
                ),
                "paymentCurrency": self.currency_id.name if self.currency_id else "USD",
            }

            if self.bank_id.country.code == "US":
                bank_account_data["routingNumber"] = routing_number

            # Add name on account if available
            if self.acc_holder_name:
                bank_account_data["nameOnAccount"] = self.acc_holder_name
            elif self.partner_id.name:
                # Fallback to partner name if no holder name specified
                bank_account_data["nameOnAccount"] = self.partner_id.name

            _logger.info(
                f"Syncing bank account to Bill.com for vendor {self.partner_id.name}"
            )
            _logger.debug(f"Bank account payload: {bank_account_data}")

            # Create or update bank account in Bill.com
            if self.billcom_vendor_bank_id:
                # Update existing bank account
                # Note: Bill.com may use PATCH or PUT for updates
                endpoint = (
                    f"vendors/{vendor_id}/bank-account/{self.billcom_vendor_bank_id}"
                )
                method = "PATCH"
                _logger.info(
                    f"Updating existing Bill.com bank account {self.billcom_vendor_bank_id}"
                )
            else:
                # Create new bank account
                endpoint = f"vendors/{vendor_id}/bank-account"
                method = "POST"
                _logger.info("Creating new Bill.com bank account")

            response = service._make_request(
                endpoint, method=method, data=bank_account_data
            )

            if response and response.get("id"):
                # Update Odoo record with Bill.com ID and status
                self.with_context(skip_billcom_sync=True).write(
                    {
                        "billcom_vendor_bank_id": response["id"],
                        "billcom_account_status": response.get("status", ""),
                        "billcom_last_sync_date": fields.Datetime.now(),
                    }
                )

                _logger.info(
                    f"Successfully synced bank account to Bill.com. "
                    f"Bill.com ID: {response['id']}"
                )

                # Post message to partner's chatter
                self.partner_id.message_post(
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
                        "bank": self.bank_id.name,
                        "account": (
                            self.acc_number[-4:]
                            if len(self.acc_number) >= 4
                            else "****"
                        ),
                        "id": response["id"],
                        "status": response.get("status", "Unknown"),
                    },
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )
            else:
                _logger.error(
                    "No valid response from Bill.com when syncing bank account"
                )

        except Exception as e:
            error_msg = str(e)
            _logger.error(
                f"Error syncing bank account to Bill.com "
                f"for {self.partner_id.name}: {error_msg}"
            )

            # Handle specific Bill.com error BDC_1233
            if "BDC_1233" in error_msg or "already setup for epayment" in error_msg:
                raise UserError(
                    _(
                        "Cannot sync bank account using separate endpoint.\n\n"
                        "Bill.com Error: Vendor already has payment information configured.\n\n"
                        "To update bank account:\n"
                        "1. Update bank account fields in Odoo\n"
                        "2. Re-sync the entire vendor to Bill.com\n"
                        "   (This will update paymentInformation in vendor data)\n\n"
                        "Note: The separate bank account endpoint can only be used for vendors "
                        "without existing payment configuration."
                    )
                ) from e

            # Generic error
            raise UserError(
                _(f"Error syncing bank account to Bill.com: {error_msg}")
            ) from e

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to sync bank account to Bill.com after creation"""
        records = super().create(vals_list)

        # DO NOT auto-sync bank accounts on create
        # They should be synced via paymentInformation when vendor is synced
        # or manually via "Sync to Bill.com" button if vendor already exists
        _logger.info(
            "Bank account created. Will sync via vendor paymentInformation "
            "or use manual 'Sync to Bill.com' button if vendor already exists in Bill.com"
        )

        return records

    def write(self, vals):
        """Override write to sync bank account changes to Bill.com"""
        result = super().write(vals)

        # DO NOT auto-sync bank accounts on write
        # Bill.com error BDC_1233 occurs if vendor already has paymentInformation
        # User must re-sync entire vendor to update bank account via paymentInformation
        _logger.info(
            "Bank account updated. To sync changes: "
            "1) Re-sync vendor (recommended) or 2) Use manual 'Sync to Bill.com' button"
        )

        return result
