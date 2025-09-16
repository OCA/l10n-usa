import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BillcomConfig(models.Model):
    _name = "billcom.config"
    _description = "Bill.com API Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"

    name = fields.Char(
        string="Name", required=True, default="Bill.com Configuration", tracking=True
    )
    environment = fields.Selection(
        [("sandbox", "Sandbox"), ("production", "Production")],
        string="Environment",
        required=True,
        default="sandbox",
        tracking=True,
    )
    username = fields.Char(required=True, tracking=True)
    password = fields.Char(required=True, tracking=True)
    user_id = fields.Many2one("res.users", string="User", required=True, tracking=True)
    organization_id = fields.Char(
        string="Organization ID", required=True, tracking=True
    )
    dev_key = fields.Char(string="Developer Key", required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
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
    last_connection_test = fields.Datetime(string="Last Connection Test", readonly=True)
    last_error_message = fields.Text(string="Last Error Message", readonly=True)
    last_sync_date = fields.Datetime(
        string="Last Synchronization", readonly=True, tracking=True
    )

    # Sync Configuration
    sync_invoices = fields.Boolean(
        string="Sync Customer Invoices",
        default=False,
        help="Enable synchronization of customer invoices to Bill.com",
    )
    sync_bills = fields.Boolean(
        string="Sync Vendor Bills",
        default=True,
        help="Enable synchronization of vendor bills to Bill.com",
    )
    sync_customers = fields.Boolean(
        string="Sync Customers",
        default=False,
        help="Enable synchronization of customers to Bill.com",
    )
    sync_vendors = fields.Boolean(
        string="Sync Vendors",
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
        string="Enable Webhooks",
        default=False,
        help="Enable webhook integration with Bill.com for real-time updates",
    )
    webhook_secret = fields.Char(
        string="Webhook Secret",
        help="Secret key for validating incoming webhooks from Bill.com",
    )

    # API Configuration
    api_max_retries = fields.Integer(
        string="Max API Retries",
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
        string="Default Payment Type",
        default="ach",
        help="Default payment type for Bill.com payments",
    )
    token = fields.Char(string="API Token", copy=False, readonly=True)
    token_expiry = fields.Datetime(string="Token Expiry", copy=False, readonly=True)
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
    api_url = fields.Char(
        string="API URL", compute="_compute_api_url", store=True, readonly=True
    )

    @api.depends("environment")
    def _compute_api_url(self):
        for record in self:
            if record.environment == "sandbox":
                record.api_url = "https://gateway.stage.bill.com/connect/v3"
            else:
                record.api_url = "https://api.bill.com/api/v3"

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

            raise UserError(_("Connection test failed: %s") % error_msg)

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
