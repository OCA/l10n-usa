# Copyright 2025 Binhex - Simple Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomConfig(models.Model):
    _name = "billcom.config"
    _description = "Bill.com API Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, default="Bill.com Configuration", tracking=True)
    environment = fields.Selection(
        [("sandbox", "Sandbox"), ("production", "Production")],
        required=True,
        default="sandbox",
        tracking=True,
    )
    username = fields.Char(required=True, tracking=True)
    password = fields.Char(required=True)
    user_id = fields.Many2one("res.users", required=True, tracking=True)
    organization_id = fields.Char(
        string="Organization ID", required=True, tracking=True
    )
    dev_key = fields.Char(string="Developer Key", required=True)

    # MFA Configuration
    enable_mfa = fields.Boolean(
        default=False,
        help="Enable Multi-Factor Authentication for Bill.com login",
        tracking=True,
    )
    mfa_device_id = fields.Char(
        string="MFA Device ID",
        help="Trusted Device ID from Bill.com for MFA-free payment creation. "
        "Required for creating payments via API. "
        "See MFA_PAYMENT_ISSUE.md for setup instructions.",
        tracking=True,
    )
    mfa_remember_me_id = fields.Char(
        string="MFA Remember Me ID",
        help="30-day MFA ID for step-up authentication. "
        "Generated from MFA challenge/validate with rememberMe=true. "
        "Use 'Setup MFA' button to obtain this automatically.",
        tracking=True,
    )
    mfa_device_name = fields.Char(
        default="Odoo Integration",
        help="Friendly name for this integration device used in MFA step-up",
    )

    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [
            ("draft", "Not Connected"),
            ("connected", "Connected"),
            ("error", "Connection Error"),
        ],
        string="Connection Status",
        default="draft",
        tracking=True,
        readonly=True,
    )
    last_connection_test = fields.Datetime(readonly=True)
    last_error_message = fields.Text(readonly=True)
    last_sync_date = fields.Datetime(
        string="Last Synchronization", readonly=True, tracking=True
    )

    # Sync Configuration
    sync_invoices = fields.Boolean(
        string="Sync Customer Invoices",
        default=True,
        help="Enable synchronization of customer invoices to Bill.com",
    )
    sync_bills = fields.Boolean(
        string="Sync Vendor Bills",
        default=True,
        help="Enable synchronization of vendor bills to Bill.com",
    )
    sync_customers = fields.Boolean(
        default=True,
        help="Enable synchronization of customers to Bill.com",
    )
    sync_vendors = fields.Boolean(
        default=True,
        help="Enable synchronization of vendors to Bill.com",
    )
    sync_payments = fields.Boolean(
        string="Sync Vendor Payments",
        default=True,
        help="Enable synchronization of vendor payments to Bill.com",
    )

    # Webhook Configuration
    enable_webhooks = fields.Boolean(
        default=False,
        help="Enable webhook integration with Bill.com for real-time updates",
    )
    webhook_secret = fields.Char(
        help="Secret key for validating incoming webhooks from Bill.com",
    )
    webhook_subscription_id = fields.Char(
        string="Webhook Subscription ID",
        readonly=True,
        help="Bill.com webhook subscription ID (auto-filled when subscribed)",
    )
    webhook_url = fields.Char(
        compute="_compute_webhook_url",
        store=True,
        help="URL where Bill.com will send webhook notifications",
    )
    webhook_subscription_state = fields.Selection(
        [
            ("not_subscribed", "Not Subscribed"),
            ("subscribed", "Subscribed"),
            ("error", "Error"),
        ],
        default="not_subscribed",
        readonly=True,
    )
    webhook_last_error = fields.Text(
        readonly=True,
    )

    # Webhook Events Selection - Only enabled events
    webhook_event_bills = fields.Boolean(
        string="Bill Events",
        default=True,
        help="Subscribe to bill.created, bill.updated, bill.archived, bill.restored",
    )
    webhook_event_vendors = fields.Boolean(
        string="Vendor Events",
        default=True,
        help="Subscribe to vendor.created, vendor.updated, vendor.archived, vendor.restored",
    )
    webhook_event_payments = fields.Boolean(
        string="Payment Events",
        default=True,
        help="Subscribe to payment.updated, payment.failed",
    )
    webhook_event_bank_accounts = fields.Boolean(
        string="Bank Account Events",
        default=True,
        help="Subscribe to bank-account.created, bank-account.updated",
    )

    # API Configuration
    api_max_retries = fields.Integer(
        default=3,
        help="Maximum number of retry attempts for failed API calls",
    )
    api_retry_delay = fields.Integer(
        string="Retry Delay (seconds)",
        default=5,
        help="Delay in seconds between retry attempts",
    )

    # Scheduled Actions Configuration
    full_sync_interval = fields.Integer(
        string="Full Sync Interval (hours)",
        default=1,
        help="Interval in hours between full synchronization with Bill.com",
    )
    payment_sync_interval = fields.Integer(
        string="Payment Sync Interval (minutes)",
        default=15,
        help="Interval in minutes between payment synchronization with Bill.com",
    )
    payment_status_check_interval = fields.Integer(
        string="Payment Status Check Interval (minutes)",
        default=60,
        help="Interval in minutes between payment status checks (0 to disable)",
    )
    default_payment_type = fields.Selection(
        [
            ("ach", "ACH"),
            ("check", "Check"),
            ("virtual_card", "Virtual Card"),
            ("wire", "Wire Transfer"),
        ],
        default="ach",
        help="Default payment type for Bill.com payments",
    )

    # Funding Account Configuration
    default_funding_account_id = fields.Char(
        string="Default Funding Account ID",
        help="Bill.com ID of the default funding account for payments",
        tracking=True,
    )
    default_funding_account_type = fields.Selection(
        [
            ("BANK_ACCOUNT", "Bank Account"),
            ("CARD_ACCOUNT", "Credit/Debit Card"),
            ("WALLET", "BILL Balance"),
            ("AP_CARD", "AP Card"),
        ],
        string="Funding Account Type",
        default="BANK_ACCOUNT",
        help="Type of funding account for Bill.com API",
        tracking=True,
    )
    token = fields.Char(string="API Token", copy=False, readonly=True)
    token_expiry = fields.Datetime(copy=False, readonly=True)
    auto_sync_enabled = fields.Boolean(
        string="Enable Automatic Sync",
        default=True,
        help="Enable automatic synchronization via scheduled actions",
    )
    sync_interval = fields.Integer(
        string="Sync Interval (minutes)",
        default=60,
        help="Interval in minutes between automatic synchronizations",
    )
    api_url = fields.Char(compute="_compute_api_url", store=True, readonly=False)

    # Dashboard computed fields
    kanban_dashboard = fields.Text(compute="_compute_kanban_dashboard")
    kanban_dashboard_graph = fields.Text(compute="_compute_kanban_dashboard_graph")
    color = fields.Integer(string="Color Index", compute="_compute_color")

    # Dashboard metrics
    total_partners = fields.Integer(compute="_compute_dashboard_metrics")
    synced_vendors = fields.Integer(compute="_compute_dashboard_metrics")
    synced_customers = fields.Integer(compute="_compute_dashboard_metrics")
    pending_partners = fields.Integer(
        compute="_compute_dashboard_metrics",
    )

    total_bills = fields.Integer(compute="_compute_dashboard_metrics")
    synced_bills = fields.Integer(compute="_compute_dashboard_metrics")
    pending_bills = fields.Integer(compute="_compute_dashboard_metrics")

    total_payments = fields.Integer(compute="_compute_dashboard_metrics")
    synced_payments = fields.Integer(compute="_compute_dashboard_metrics")
    pending_payments = fields.Integer(compute="_compute_dashboard_metrics")

    total_invoices = fields.Integer(compute="_compute_dashboard_metrics")
    synced_invoices = fields.Integer(compute="_compute_dashboard_metrics")
    pending_invoices = fields.Integer(compute="_compute_dashboard_metrics")

    queue_pending = fields.Integer(compute="_compute_dashboard_metrics")
    queue_processing = fields.Integer(compute="_compute_dashboard_metrics")
    queue_completed = fields.Integer(compute="_compute_dashboard_metrics")
    queue_failed = fields.Integer(compute="_compute_dashboard_metrics")

    log_today = fields.Integer(
        compute="_compute_dashboard_metrics", string="Logs Today"
    )
    log_errors_today = fields.Integer(
        compute="_compute_dashboard_metrics", string="Errors Today"
    )
    log_warnings_today = fields.Integer(
        compute="_compute_dashboard_metrics", string="Warnings Today"
    )

    last_sync_date_dashboard = fields.Datetime(
        compute="_compute_dashboard_metrics", string="Last Sync Dashboard"
    )

    @api.depends("environment")
    def _compute_api_url(self):
        for record in self:
            if record.environment == "sandbox":
                record.api_url = "https://gateway.stage.bill.com/connect"
            else:
                record.api_url = "https://gateway.prod.bill.com/connect"

    def test_connection(self):
        """Test the connection to Bill.com API"""
        self.ensure_one()
        try:
            service = self.env["billcom.service"].sudo()
            result = service._get_token()

            if result:
                self.write(
                    {
                        "state": "connected",
                        "last_connection_test": fields.Datetime.now(),
                        "last_error_message": False,
                    }
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Success"),
                        "message": _("Successfully connected to Bill.com API"),
                        "type": "success",
                        "sticky": False,
                    },
                }
        except Exception as e:
            error_msg = str(e)
            _logger.error("Bill.com connection test failed: %s", error_msg)

            self.write(
                {
                    "state": "error",
                    "last_connection_test": fields.Datetime.now(),
                    "last_error_message": error_msg,
                }
            )

            raise UserError(_("Connection test failed: %s") % error_msg) from e

    def action_setup_mfa(self):
        """Initiate MFA setup process - generates challenge and opens wizard"""
        self.ensure_one()

        try:
            service = self.env["billcom.service"].sudo()

            # Generate MFA challenge
            challenge_data = service.generate_mfa_challenge(self)

            # Create wizard with challenge data
            wizard = self.env["billcom.mfa.wizard"].create(
                {
                    "config_id": self.id,
                    "challenge_id": challenge_data["challenge_id"],
                    "session_id": challenge_data["session_id"],
                    "phone_number": challenge_data.get("phone_number", "****"),
                }
            )

            return {
                "type": "ir.actions.act_window",
                "name": _("Enter MFA Code"),
                "res_model": "billcom.mfa.wizard",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
                "context": {"active_id": self.id},
            }

        except Exception as e:
            _logger.error("Failed to initiate MFA setup: %s", str(e))
            raise UserError(_("Failed to initiate MFA setup: %s") % str(e)) from e

    def button_sync_primary_data(self):
        """Synchronize primary data from Bill.com (funding accounts, taxes/items, etc.)"""
        self.ensure_one()

        try:
            _logger.info("Starting sync of primary data from Bill.com")

            # Sync funding accounts from Bill.com
            _logger.info("Syncing funding accounts from Bill.com...")
            funding_account_model = self.env["billcom.funding.account"]
            funding_result = funding_account_model.sync_funding_accounts_from_billcom()

            funding_synced = funding_result.get("synced", 0)
            funding_total = funding_result.get("total", 0)

            # Import items from Bill.com (all types)
            _logger.info("Importing items from Bill.com...")
            item_model = self.env["billcom.item"]
            import_result = item_model.sync_items_from_billcom()

            items_created = import_result.get("created", 0)
            items_updated = import_result.get("updated", 0)
            items_errors = import_result.get("errors", 0)
            items_total = import_result.get("total", 0)

            # Sync Odoo taxes to Bill.com as items (SALES_TAX type)
            _logger.info("Syncing Odoo taxes to Bill.com as items...")
            tax_result = item_model.sync_from_odoo_taxes()

            tax_synced = tax_result.get("synced", 0)
            tax_total = tax_result.get("total", 0)
            tax_errors = tax_result.get("errors", 0)

            # Build summary message
            message_parts = []
            message_parts.append(
                _("✓ Funding Accounts: %(synced)d of %(total)d synchronized")
                % {"synced": funding_synced, "total": funding_total}
            )
            message_parts.append(
                _(
                    f"✓ Items from Bill.com: {items_created} created, "
                    f"{items_updated} updated (total: {items_total})"
                )
            )
            if items_errors > 0:
                message_parts.append(_("⚠ Items Import Errors: %d") % items_errors)
            message_parts.append(
                _("✓ Tax Items to Bill.com: %(synced)d of %(total)d synchronized")
                % {"synced": tax_synced, "total": tax_total}
            )
            if tax_errors > 0:
                message_parts.append(_("⚠ Tax Export Errors: %d") % tax_errors)

            message = "\n".join(message_parts)
            has_errors = items_errors > 0 or tax_errors > 0

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Primary Data Sync Complete"),
                    "message": message,
                    "type": "success" if not has_errors else "warning",
                    "sticky": False,
                },
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error("Primary data sync failed: %s", error_msg)
            raise UserError(_("Primary data sync failed: %s") % error_msg) from e

    @api.model
    def get_config(self):
        """Get the active configuration for the current company"""
        config = self.search(
            [("active", "=", True), ("company_id", "=", self.env.company.id)], limit=1
        )

        if not config:
            raise UserError(
                _("No active Bill.com configuration found for company %s")
                % self.env.company.name
            )

        return config

    def update_scheduled_actions(self):
        """Update scheduled actions with the intervals defined in the configuration"""
        self.ensure_one()

        # Get the scheduled actions
        ir_cron_obj = self.env["ir.cron"]
        full_sync_cron = ir_cron_obj.search(
            [("id", "=", self.env.ref("billcom.ir_cron_sync_billcom").id)]
        )
        payment_sync_cron = ir_cron_obj.search(
            [("id", "=", self.env.ref("billcom.ir_cron_sync_billcom_payments").id)]
        )
        payment_status_cron = ir_cron_obj.search(
            [("id", "=", self.env.ref("billcom.ir_cron_update_payment_status").id)]
        )

        # Update full sync cron
        if full_sync_cron:
            full_sync_cron.write(
                {
                    "interval_number": self.full_sync_interval,
                    "interval_type": "hours",
                    "active": self.full_sync_interval > 0,
                }
            )

        # Update payment sync cron
        if payment_sync_cron:
            payment_sync_cron.write(
                {
                    "interval_number": self.payment_sync_interval,
                    "interval_type": "minutes",
                    "active": self.payment_sync_interval > 0 and self.sync_payments,
                }
            )

        # Update payment status cron
        if payment_status_cron:
            payment_status_cron.write(
                {
                    "interval_number": self.payment_status_check_interval,
                    "interval_type": "minutes",
                    "active": self.payment_status_check_interval > 0
                    and self.sync_payments,
                }
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Scheduled actions updated successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    def refresh_token(self):
        """Refresh the API token"""
        self.ensure_one()
        service = self.env["billcom.service"].sudo()
        return service._get_token()

    @api.depends("state")
    def _compute_color(self):
        for config in self:
            if config.state == "connected":
                config.color = 10  # Green
            elif config.state == "error":
                config.color = 1  # Red
            else:
                config.color = 7  # Gray

    @api.depends(
        "state", "total_partners", "synced_vendors", "pending_partners", "queue_failed"
    )
    def _compute_dashboard_metrics(self):
        for config in self:
            # Partners metrics
            partners = self.env["res.partner"].search(
                [("company_id", "=", config.company_id.id)]
            )
            config.total_partners = len(partners)
            config.synced_vendors = len(
                partners.filtered(lambda p: p.supplier_rank > 0 and p.billcom_id)
            )
            config.synced_customers = len(
                partners.filtered(lambda p: p.customer_rank > 0 and p.billcom_id)
            )
            config.pending_partners = len(
                partners.filtered(
                    lambda p: (p.supplier_rank > 0 or p.customer_rank > 0)
                    and not p.billcom_id
                )
            )

            # Bills metrics
            bills = self.env["account.move"].search(
                [
                    ("company_id", "=", config.company_id.id),
                    ("move_type", "=", "in_invoice"),
                ]
            )
            config.total_bills = len(bills)
            config.synced_bills = len(bills.filtered(lambda b: b.billcom_id))
            config.pending_bills = len(bills.filtered(lambda b: not b.billcom_id))

            # Payments metrics
            payments = self.env["account.payment"].search(
                [
                    ("company_id", "=", config.company_id.id),
                    ("payment_type", "=", "outbound"),
                ]
            )
            config.total_payments = len(payments)
            config.synced_payments = len(payments.filtered(lambda p: p.billcom_id))
            config.pending_payments = len(payments.filtered(lambda p: not p.billcom_id))

            # Invoices metrics
            invoices = self.env["account.move"].search(
                [
                    ("company_id", "=", config.company_id.id),
                    ("move_type", "=", "out_invoice"),
                ]
            )
            config.total_invoices = len(invoices)
            config.synced_invoices = len(invoices.filtered(lambda inv: inv.billcom_id))
            config.pending_invoices = len(
                invoices.filtered(lambda inv: not inv.billcom_id)
            )

            # Queue metrics
            queue_items = self.env["billcom.sync.queue"].search(
                [("config_id", "=", config.id)]
            )
            config.queue_pending = len(
                queue_items.filtered(lambda q: q.state == "queued")
            )
            config.queue_processing = len(
                queue_items.filtered(lambda q: q.state == "processing")
            )
            config.queue_completed = len(
                queue_items.filtered(lambda q: q.state == "success")
            )
            config.queue_failed = len(
                queue_items.filtered(lambda q: q.state == "error")
            )

            # Logs metrics
            today = fields.Date.today()
            logs_today = self.env["billcom.logger"].search(
                [("config_id", "=", config.id), ("create_date", ">=", today)]
            )
            config.log_today = len(logs_today)
            config.log_errors_today = len(
                logs_today.filtered(lambda l: l.level == "error")
            )
            config.log_warnings_today = len(
                logs_today.filtered(lambda l: l.level == "warning")
            )

            # Last sync date
            last_queue = queue_items.filtered(lambda q: q.state == "success").sorted(
                "write_date", reverse=True
            )
            config.last_sync_date_dashboard = (
                last_queue[0].write_date if last_queue else False
            )

    def _compute_kanban_dashboard(self):
        for config in self:
            config.kanban_dashboard = json.dumps(
                {
                    "state": config.state,
                    "total_partners": config.total_partners,
                    "synced_vendors": config.synced_vendors,
                    "synced_customers": config.synced_customers,
                    "pending_partners": config.pending_partners,
                    "total_bills": config.total_bills,
                    "synced_bills": config.synced_bills,
                    "pending_bills": config.pending_bills,
                    "total_payments": config.total_payments,
                    "synced_payments": config.synced_payments,
                    "pending_payments": config.pending_payments,
                    "total_invoices": config.total_invoices,
                    "synced_invoices": config.synced_invoices,
                    "pending_invoices": config.pending_invoices,
                    "queue_pending": config.queue_pending,
                    "queue_processing": config.queue_processing,
                    "queue_completed": config.queue_completed,
                    "queue_failed": config.queue_failed,
                    "log_today": config.log_today,
                    "log_errors_today": config.log_errors_today,
                    "log_warnings_today": config.log_warnings_today,
                    "last_sync_date": (
                        config.last_sync_date_dashboard.strftime("%Y-%m-%d %H:%M:%S")
                        if config.last_sync_date_dashboard
                        else False
                    ),
                }
            )

    def _compute_kanban_dashboard_graph(self):
        for config in self:
            # Compute graph data for sync activity over the last 7 days
            data = []
            for i in range(6, -1, -1):
                date = fields.Date.today() - timedelta(days=i)
                completed_count = self.env["billcom.sync.queue"].search_count(
                    [
                        ("config_id", "=", config.id),
                        ("state", "=", "success"),
                        ("write_date", ">=", date),
                        ("write_date", "<", date + timedelta(days=1)),
                    ]
                )
                data.append({"label": date.strftime("%m/%d"), "value": completed_count})

            config.kanban_dashboard_graph = json.dumps(
                [
                    {
                        "values": data,
                        "title": "Sync Activity (7 days)",
                        "key": "Completed Syncs",
                    }
                ]
            )

    def action_refresh_dashboard(self):
        """Refresh dashboard data"""
        self._compute_dashboard_metrics()
        self._compute_kanban_dashboard()
        self._compute_kanban_dashboard_graph()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def action_open_sync_wizard(self):
        """Open synchronization wizard"""
        return {
            "type": "ir.actions.act_window",
            "name": "Bill.com Synchronization",
            "res_model": "billcom.sync.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_config_id": self.id},
        }

    def action_open_configurations(self):
        """Open configurations list"""
        return {
            "type": "ir.actions.act_window",
            "name": "Bill.com Configurations",
            "res_model": "billcom.config",
            "view_mode": "tree,form",
            "target": "current",
        }

    def action_open_sync_queue(self):
        """Open sync queue for this configuration"""
        return {
            "type": "ir.actions.act_window",
            "name": "Sync Queue",
            "res_model": "billcom.sync.queue",
            "view_mode": "tree,form",
            "domain": [("config_id", "=", self.id)],
            "target": "current",
        }

    def action_open_logs(self):
        """Open logs for this configuration"""
        return {
            "type": "ir.actions.act_window",
            "name": "Bill.com Logs",
            "res_model": "billcom.logger",
            "view_mode": "tree,form",
            "domain": [("config_id", "=", self.id)],
            "target": "current",
        }

    def action_quick_sync(self):
        """Perform quick synchronization"""
        try:
            # Create sync wizard and execute
            wizard = self.env["billcom.sync.wizard"].create(
                {
                    "config_id": self.id,
                    "sync_vendors": True,
                    "sync_customers": False,
                    "sync_bills": True,
                    "sync_payments": True,
                }
            )
            wizard.action_sync()

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Quick Sync Started",
                    "message": "Quick synchronization has been initiated",
                    "type": "success",
                },
            }
        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Sync Error",
                    "message": f"Error starting sync: {str(e)}",
                    "type": "danger",
                },
            }

    def action_open_partners(self):
        """Open partners list"""
        return {
            "type": "ir.actions.act_window",
            "name": "Partners",
            "res_model": "res.partner",
            "view_mode": "tree,form",
            "domain": [("company_id", "=", self.company_id.id)],
            "target": "current",
        }

    def action_open_bills(self):
        """Open bills list"""
        return {
            "type": "ir.actions.act_window",
            "name": "Vendor Bills",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "in_invoice"),
            ],
            "target": "current",
        }

    def action_open_payments(self):
        """Open payments list"""
        return {
            "type": "ir.actions.act_window",
            "name": "Vendor Payments",
            "res_model": "account.payment",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("payment_type", "=", "outbound"),
            ],
            "target": "current",
        }

    def action_open_invoices(self):
        """Open invoices list"""
        return {
            "type": "ir.actions.act_window",
            "name": "Customer Invoices",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "out_invoice"),
            ],
            "target": "current",
        }

    def action_open_vendors_from_billcom(self):
        """Open vendors synced from Bill.com"""
        return {
            "type": "ir.actions.act_window",
            "name": "Vendors from Bill.com",
            "res_model": "res.partner",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("supplier_rank", ">", 0),
                ("billcom_id", "!=", False),
            ],
            "target": "current",
            "context": {"default_supplier_rank": 1},
        }

    def action_open_customers_from_billcom(self):
        """Open customers synced from Bill.com"""
        return {
            "type": "ir.actions.act_window",
            "name": "Customers from Bill.com",
            "res_model": "res.partner",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("customer_rank", ">", 0),
                ("billcom_id", "!=", False),
            ],
            "target": "current",
            "context": {"default_customer_rank": 1},
        }

    def action_open_bills_from_billcom(self):
        """Open bills synced from Bill.com"""
        return {
            "type": "ir.actions.act_window",
            "name": "Bills from Bill.com",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "in_invoice"),
                ("billcom_id", "!=", False),
            ],
            "target": "current",
        }

    def action_open_invoices_from_billcom(self):
        """Open invoices synced from Bill.com"""
        return {
            "type": "ir.actions.act_window",
            "name": "Invoices from Bill.com",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "out_invoice"),
                ("billcom_id", "!=", False),
            ],
            "target": "current",
        }

    def action_open_payments_from_billcom(self):
        """Open payments synced from Bill.com"""
        return {
            "type": "ir.actions.act_window",
            "name": "Payments from Bill.com",
            "res_model": "account.payment",
            "view_mode": "tree,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("payment_type", "=", "outbound"),
                ("billcom_id", "!=", False),
            ],
            "target": "current",
        }

    @api.depends("company_id")
    def _compute_webhook_url(self):
        """Compute the webhook URL for Bill.com

        Bill.com requires HTTPS URLs for webhooks
        """
        for config in self:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            # Force HTTPS as Bill.com requires it for webhooks
            if base_url.startswith("http://"):
                base_url = base_url.replace("http://", "https://")
            config.webhook_url = f"{base_url}/billcom/webhook"

    def _get_webhook_events(self):
        """Get list of webhook events based on selected checkboxes

        Only enabled event types: bills, vendors, payments, bank-accounts
        """
        self.ensure_one()
        events = []

        if self.webhook_event_bills:
            events.extend(
                [
                    "bill.created",
                    "bill.updated",
                    "bill.archived",
                    "bill.restored",
                ]
            )

        if self.webhook_event_vendors:
            events.extend(
                [
                    "vendor.created",
                    "vendor.updated",
                    "vendor.archived",
                    "vendor.restored",
                ]
            )

        if self.webhook_event_payments:
            events.extend(
                [
                    "payment.updated",
                    "payment.failed",
                ]
            )

        if self.webhook_event_bank_accounts:
            events.extend(
                [
                    "bank-account.created",
                    "bank-account.updated",
                ]
            )

        return events

    def _get_webhook_event_objects(self):
        """Get list of webhook event objects with type and version for Bill.com API v3

        Only enabled event types: bills, vendors, payments, bank-accounts
        """
        self.ensure_one()
        event_objects = []

        # Bill.com API v3 requires events in format: [{"type": "...", "version": "..."}]
        # Using version "1" as per Bill.com API documentation

        if self.webhook_event_bills:
            event_objects.extend(
                [
                    {"type": "bill.created", "version": "1"},
                    {"type": "bill.updated", "version": "1"},
                    {"type": "bill.archived", "version": "1"},
                    {"type": "bill.restored", "version": "1"},
                ]
            )

        if self.webhook_event_vendors:
            event_objects.extend(
                [
                    {"type": "vendor.created", "version": "1"},
                    {"type": "vendor.updated", "version": "1"},
                    {"type": "vendor.archived", "version": "1"},
                    {"type": "vendor.restored", "version": "1"},
                ]
            )

        if self.webhook_event_payments:
            event_objects.extend(
                [
                    {"type": "payment.updated", "version": "1"},
                    {"type": "payment.failed", "version": "1"},
                ]
            )

        if self.webhook_event_bank_accounts:
            event_objects.extend(
                [
                    {"type": "bank-account.created", "version": "1"},
                    {"type": "bank-account.updated", "version": "1"},
                ]
            )

        return event_objects

    def button_subscribe_webhooks(self):
        """Subscribe to Bill.com webhooks using API v3 format"""
        self.ensure_one()

        if not self.enable_webhooks:
            raise UserError(_("Please enable webhooks first"))

        if not self.webhook_url:
            raise UserError(_("Webhook URL not configured"))

        try:
            # Get selected events in Bill.com API v3 format
            event_objects = self._get_webhook_event_objects()

            if not event_objects:
                raise UserError(_("Please select at least one webhook event type"))

            # Generate idempotency key (UUID4)
            import uuid

            idempotency_key = str(uuid.uuid4())

            # Call Bill.com API to create subscription
            service = self.env["billcom.service"].sudo()

            # Bill.com API v3 subscription format (correct format from API docs)
            subscription_data = {
                "name": f"Odoo Webhook - {self.company_id.name}",
                "status": {"enabled": True},
                "events": event_objects,
                "notificationUrl": self.webhook_url,
            }

            _logger.info(
                "Creating webhook subscription with %s events", len(event_objects)
            )

            # Make request with idempotency key header
            # Note: Webhook API uses different base path (connect-events instead of connect)
            # Use webhook: prefix to signal _build_api_url to use connect-events base
            response = service._make_request(
                "webhook:subscriptions",
                method="POST",
                data=subscription_data,
                extra_headers={"X-Idempotent-Key": idempotency_key},
            )

            if response and response.get("id"):
                # Bill.com generates the securityKey (not we send it)
                security_key = response.get("securityKey")

                self.write(
                    {
                        "webhook_subscription_id": response.get("id"),
                        "webhook_secret": security_key,  # Store Bill.com's security key
                        "webhook_subscription_state": "subscribed",
                        "webhook_last_error": False,
                    }
                )

                _logger.info(
                    "Webhook subscription created successfully: %s", response.get("id")
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Success"),
                        "message": _(
                            "Successfully subscribed to Bill.com webhooks. "
                            "Security key has been stored."
                        ),
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                raise UserError(_("No subscription ID received from Bill.com"))

        except Exception as e:
            error_msg = str(e)
            _logger.error("Error subscribing to webhooks: %s", error_msg)

            self.write(
                {
                    "webhook_subscription_state": "error",
                    "webhook_last_error": error_msg,
                }
            )

            raise UserError(_("Failed to subscribe to webhooks: %s") % error_msg) from e

    def button_unsubscribe_webhooks(self):
        """Unsubscribe from Bill.com webhooks"""
        self.ensure_one()

        if not self.webhook_subscription_id:
            raise UserError(_("No active webhook subscription found"))

        try:
            # Call Bill.com API to delete subscription
            service = self.env["billcom.service"].sudo()

            service._make_request(
                f"webhook: subscriptions/{self.webhook_subscription_id}",
                method="DELETE",
            )

            self.write(
                {
                    "webhook_subscription_id": False,
                    "webhook_subscription_state": "not_subscribed",
                    "webhook_last_error": False,
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Success"),
                    "message": _("Successfully unsubscribed from Bill.com webhooks"),
                    "type": "success",
                    "sticky": False,
                },
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error("Error unsubscribing from webhooks: %s", error_msg)

            self.write(
                {
                    "webhook_subscription_state": "error",
                    "webhook_last_error": error_msg,
                }
            )

            raise UserError(
                _("Failed to unsubscribe from webhooks: %s") % error_msg
            ) from e

    def button_test_webhook(self):
        """Send a test webhook from Bill.com"""
        self.ensure_one()

        if not self.webhook_subscription_id:
            raise UserError(_("Please subscribe to webhooks first"))

        try:
            # Call Bill.com API to send test webhook
            service = self.env["billcom.service"].sudo()

            test_data = {
                "eventType": "bill.updated",  # Example event type
            }

            service._make_request(
                f"webhook:subscriptions/{self.webhook_subscription_id}/test",  # noqa E231
                method="POST",
                data=test_data,
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Test Sent"),
                    "message": _(
                        "Test webhook sent. Check webhook logs for the result."
                    ),
                    "type": "info",
                    "sticky": False,
                },
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error("Error sending test webhook: %s", error_msg)
            raise UserError(_("Failed to send test webhook: %s") % error_msg) from e

    def button_sync_webhook_status(self):
        """Sync webhook subscription status with Bill.com"""
        self.ensure_one()

        try:
            service = self.env["billcom.service"].sudo()

            # Get all subscriptions from Bill.com
            # Note: Webhook API uses different base path (connect-events instead of connect)
            # Use webhook: prefix to signal _build_api_url to use connect-events base
            response = service._make_request(
                "webhook:subscriptions",
                method="GET",
                params={"max": 100},  # Get up to 100 subscriptions
            )

            if not response or not isinstance(response, dict):
                raise UserError(_("Invalid response from Bill.com"))

            results = response.get("results", [])

            if not results:
                # No subscriptions in Bill.com
                if self.webhook_subscription_id:
                    # We think we have a subscription but Bill.com doesn't
                    _logger.warning(
                        "Subscription %s not found in Bill.com - marking as error",
                        self.webhook_subscription_id,
                    )
                    self.write(
                        {
                            "webhook_subscription_state": "error",
                            "webhook_last_error": "Subscription not found in Bill.com. "
                            "It may have been deleted manually.",
                        }
                    )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("No Subscriptions"),
                        "message": _("No webhook subscriptions found in Bill.com"),
                        "type": "warning",
                        "sticky": False,
                    },
                }

            # Find our subscription in the list
            our_subscription = None
            if self.webhook_subscription_id:
                for sub in results:
                    if sub.get("id") == self.webhook_subscription_id:
                        our_subscription = sub
                        break

            if self.webhook_subscription_id and not our_subscription:
                # Our subscription ID doesn't exist in Bill.com
                self.write(
                    {
                        "webhook_subscription_state": "error",
                        "webhook_last_error": "Subscription ID not found in Bill.com. "
                        "It may have been deleted. Please unsubscribe and re-subscribe.",
                    }
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Subscription Not Found"),
                        "message": _(
                            "Your subscription was not found in Bill.com. "
                            "Please unsubscribe and re-subscribe."
                        ),
                        "type": "warning",
                        "sticky": True,
                    },
                }

            if our_subscription:
                # Verify subscription details match
                billcom_url = our_subscription.get("notificationUrl", "")

                # Check if URL matches
                if billcom_url != self.webhook_url:
                    _logger.warning(
                        "Webhook URL mismatch. Odoo: %s, Bill.com: %s",
                        self.webhook_url,
                        billcom_url,
                    )

                # Update state to subscribed if everything is OK
                self.write(
                    {
                        "webhook_subscription_state": "subscribed",
                        "webhook_last_error": False,
                    }
                )

                message = _("Subscription verified successfully in Bill.com")
            else:
                # Check for orphaned subscriptions (URL matches but different ID)
                orphaned = []
                for sub in results:
                    if sub.get("notificationUrl") == self.webhook_url:
                        orphaned.append(sub)

                if orphaned:
                    # Found subscription(s) with our URL
                    if len(orphaned) == 1:
                        orphan = orphaned[0]
                        _logger.info(
                            "Found orphaned subscription %s with our URL - adopting it",
                            orphan.get("id"),
                        )

                        self.write(
                            {
                                "webhook_subscription_id": orphan.get("id"),
                                "webhook_subscription_state": "subscribed",
                                "webhook_last_error": False,
                            }
                        )

                        message = _(
                            "Found and adopted orphaned subscription: %s"
                        ) % orphan.get("id")
                    else:
                        message = _(
                            "Found %s orphaned subscriptions with this URL. "
                            "Please clean them up manually in Bill.com."
                        ) % len(orphaned)
                else:
                    message = _(
                        "No subscription found for this configuration. "
                        "Please subscribe to webhooks."
                    )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sync Complete"),
                    "message": message,
                    "type": "success",
                    "sticky": False,
                },
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error("Error syncing webhook status: %s", error_msg)

            self.write(
                {
                    "webhook_subscription_state": "error",
                    "webhook_last_error": error_msg,
                }
            )

            raise UserError(_("Failed to sync webhook status: %s") % error_msg) from e

    def button_view_all_subscriptions(self):
        """View all webhook subscriptions from Bill.com"""
        self.ensure_one()

        try:
            service = self.env["billcom.service"].sudo()

            # Get all subscriptions
            # Note: Webhook API uses different base path (connect-events instead of connect)
            # Use webhook: prefix to signal _build_api_url to use connect-events base
            response = service._make_request(
                "webhook:subscriptions",
                method="GET",
                params={"max": 100},
            )

            if not response or not isinstance(response, dict):
                raise UserError(_("Invalid response from Bill.com"))

            results = response.get("results", [])

            if not results:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("No Subscriptions"),
                        "message": _("No webhook subscriptions found in Bill.com"),
                        "type": "info",
                        "sticky": False,
                    },
                }

            # Format subscriptions for display
            message_lines = [
                _("Found %s webhook subscription(s) in Bill.com:") % len(results),
                "",
            ]

            for idx, sub in enumerate(results, 1):
                sub_id = sub.get("id", "Unknown")
                sub_name = sub.get("name", "Unnamed")
                sub_url = sub.get("notificationUrl", "No URL")
                events = sub.get("events", [])
                event_count = len(events) if isinstance(events, list) else 0

                is_ours = sub_id == self.webhook_subscription_id
                marker = "✓ (OURS)" if is_ours else ""

                message_lines.append(
                    f"{idx}. {sub_name} {marker}\n"
                    f"   ID: {sub_id}\n"
                    f"   URL: {sub_url}\n"
                    f"   Events: {event_count}\n"
                )

            message = "\n".join(message_lines)

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Bill.com Webhook Subscriptions"),
                    "message": message,
                    "type": "info",
                    "sticky": True,
                },
            }

        except Exception as e:
            error_msg = str(e)
            _logger.error("Error viewing subscriptions: %s", error_msg)
            raise UserError(_("Failed to get subscriptions: %s") % error_msg) from e
