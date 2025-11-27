# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomFundingAccount(models.Model):
    _name = "billcom.funding.account"
    _description = "Bill.com Funding Account"
    _order = "is_default_payables desc, is_default_receivables desc, name"
    _rec_name = "name"

    # Basic Information
    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    billcom_id = fields.Char(
        string="Bill.com ID",
        required=True,
        index=True,
        readonly=True,
        help="Unique identifier from Bill.com API",
    )
    bank_name = fields.Char(
        readonly=True,
    )
    name_on_account = fields.Char(
        readonly=True,
    )
    account_number = fields.Char(
        readonly=True,
        help="Masked account number from Bill.com",
    )
    routing_number = fields.Char(
        readonly=True,
    )

    # Account Details
    funding_type = fields.Selection(
        [
            ("BANK_ACCOUNT", "Bank Account"),
            ("CARD_ACCOUNT", "Credit/Debit Card"),
            ("WALLET", "BILL Balance"),
            ("AP_CARD", "AP Card"),
        ],
        readonly=True,
        help="Type of funding account for Bill.com API",
    )
    account_type = fields.Selection(
        [
            ("CHECKING", "Checking"),
            ("SAVINGS", "Savings"),
        ],
        readonly=True,
    )
    owner_type = fields.Selection(
        [
            ("BUSINESS", "Business"),
            ("PERSONAL", "Personal"),
        ],
        readonly=True,
    )
    status = fields.Selection(
        [
            ("VERIFIED", "Verified"),
            ("PENDING", "Pending"),
            ("UNVERIFIED", "Unverified"),
            ("FAILED", "Failed"),
        ],
        readonly=True,
    )

    # Default Settings
    is_default_payables = fields.Boolean(
        string="Default for Payables",
        readonly=True,
        help=(
            "This is the default funding account for payables "
            "(vendor payments) in Bill.com"
        ),
    )
    is_default_receivables = fields.Boolean(
        string="Default for Receivables",
        readonly=True,
        help=(
            "This is the default funding account for receivables "
            "(customer invoices) in Bill.com"
        ),
    )

    # System Fields
    active = fields.Boolean(
        default=True,
    )

    access_to_admins = fields.Boolean(
        string="Access to Admins Only",
        readonly=True,
    )
    created_by = fields.Char(
        string="Created By (Bill.com User ID)",
        readonly=True,
    )

    # Timestamps
    billcom_created_time = fields.Datetime(
        string="Created in Bill.com",
        readonly=True,
    )
    billcom_updated_time = fields.Datetime(
        string="Updated in Bill.com",
        readonly=True,
    )
    last_sync_date = fields.Datetime(
        readonly=True,
    )

    # Relations
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    _sql_constraints = [
        (
            "billcom_id_company_uniq",
            "unique(billcom_id, company_id)",
            "Bill.com funding account must be unique per company!",
        )
    ]

    @api.depends("bank_name", "name_on_account", "account_number")
    def _compute_name(self):
        """Compute display name from bank name and account details"""
        for record in self:
            parts = []
            if record.bank_name:
                parts.append(record.bank_name)
            if record.name_on_account:
                parts.append(f"({record.name_on_account})")
            if record.account_number:
                parts.append(f"[{record.account_number}]")

            record.name = " ".join(parts) if parts else "Bill.com Funding Account"

    @api.model
    def sync_funding_accounts_from_billcom(self):
        """
        Import/update funding accounts from Bill.com API

        Returns:
            dict: Statistics about the sync operation
        """
        try:
            _logger.info("Starting funding accounts sync from Bill.com")

            service = self.env["billcom.service"]
            funding_accounts_data = service.get_funding_accounts()

            created = 0
            updated = 0
            errors = 0

            for account_data in funding_accounts_data:
                billcom_id = None
                try:
                    billcom_id = account_data.get("id")
                    if not billcom_id:
                        _logger.warning("Funding account without ID, skipping")
                        errors += 1
                        continue

                    # Check if funding account already exists
                    existing = self.search(
                        [
                            ("billcom_id", "=", billcom_id),
                            ("company_id", "=", self.env.company.id),
                        ],
                        limit=1,
                    )

                    # Prepare values
                    vals = self._prepare_funding_account_vals(account_data)

                    if existing:
                        existing.write(vals)
                        updated += 1
                        _logger.info(
                            f"Updated funding account: {vals.get('bank_name')}"
                        )
                    else:
                        self.create(vals)
                        created += 1
                        _logger.info(
                            f"Created funding account: {vals.get('bank_name')}"
                        )

                except Exception as e:
                    _logger.error(f"Error processing funding account {billcom_id}: {e}")
                    errors += 1

            result = {
                "created": created,
                "updated": updated,
                "errors": errors,
                "total": len(funding_accounts_data),
            }

            _logger.info(
                "Funding accounts sync completed: %s created, %s updated, %s errors",
                created,
                updated,
                errors,
            )

            return result

        except Exception as e:
            _logger.error(f"Error syncing funding accounts from Bill.com: {e}")
            raise UserError(
                f"Failed to sync funding accounts from Bill.com: {str(e)}"
            ) from e

    @api.model
    def _prepare_funding_account_vals(self, account_data):
        """
        Prepare values for creating/updating funding account from Bill.com data

        Args:
            account_data: Dictionary from Bill.com API

        Returns:
            dict: Values for create/write
        """
        # Extract default settings
        default_settings = account_data.get("default", {})

        vals = {
            "billcom_id": account_data.get("id"),
            "bank_name": account_data.get("bankName"),
            "name_on_account": account_data.get("nameOnAccount"),
            "account_number": account_data.get("accountNumber"),
            "routing_number": account_data.get("routingNumber"),
            "account_type": account_data.get("type"),
            "owner_type": account_data.get("ownerType"),
            "status": account_data.get("status"),
            "active": not account_data.get("archived", False),
            "access_to_admins": account_data.get("accessToAdmins", False),
            "created_by": account_data.get("createdBy"),
            "is_default_payables": default_settings.get("payables", False),
            "is_default_receivables": default_settings.get("receivables", False),
            "last_sync_date": fields.Datetime.now(),
        }

        # Parse timestamps
        # created_time = account_data.get("createdTime")
        # if created_time:
        #     vals["billcom_created_time"] = created_time

        # updated_time = account_data.get("updatedTime")
        # if updated_time:
        #     vals["billcom_updated_time"] = updated_time

        return vals

    def action_sync_from_billcom(self):
        """Action to sync funding accounts from Bill.com (can be called from UI)"""
        result = self.sync_funding_accounts_from_billcom()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Funding Accounts Synced",
                "message": (
                    f"Created: {result['created']}, Updated: {result['updated']}, "
                    f"Errors: {result['errors']}"
                ),
                "type": "success" if result["errors"] == 0 else "warning",
                "sticky": False,
            },
        }
