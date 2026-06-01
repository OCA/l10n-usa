# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Threshold at which the "approaching limit" warning is triggered (80%)
LIMIT_WARNING_THRESHOLD = 0.80


class UsTaxProvider(models.Model):
    _name = "us.tax.provider"
    _description = "US Tax External Provider"
    _order = "priority, name"

    code = fields.Char(
        required=True,
        size=32,
        index=True,
        help="Unique provider code (e.g. 'local'; external providers "
        "define their own code in their own addon).",
    )
    name = fields.Char(required=True)
    active = fields.Boolean(default=False)
    is_paid = fields.Boolean(
        default=False,
        help="Mark if this provider requires payment after trial/free tier ends.",
    )
    priority = fields.Integer(
        default=10,
        help="Lower number = higher priority in fallback chain. "
        "Engine tries providers in ascending priority order.",
    )
    sandbox_mode = fields.Boolean(
        default=True,
        help="Use sandbox/test endpoints. Disable for production.",
    )
    timeout = fields.Integer(default=5, help="API request timeout in seconds.")
    supports_address_level = fields.Boolean(
        default=False,
        help="Provider can resolve by full address (not just ZIP).",
    )
    supports_zip_level = fields.Boolean(
        default=True,
        help="Provider can resolve by ZIP code.",
    )
    # ── Call limit management ─────────────────────────────────────────────────
    monthly_call_limit = fields.Integer(
        default=0,
        help="Monthly API call limit. 0 = unlimited (paid/enterprise plans).",
    )
    calls_this_month = fields.Integer(
        default=0,
        readonly=True,
        help="Calls made this month. Reset by monthly cron.",
    )
    limit_status = fields.Selection(
        [
            ("ok", "OK"),
            ("warning", "Warning (>80%)"),
            ("exceeded", "Limit Exceeded"),
            ("unlimited", "Unlimited"),
        ],
        compute="_compute_limit_status",
    )
    limit_usage_pct = fields.Float(
        compute="_compute_limit_status",
        help="Percentage of monthly limit used.",
    )
    limit_alert_sent = fields.Boolean(
        default=False,
        help="Whether the 80% warning has been sent this month.",
    )

    description = fields.Text()
    # Credential parameter keys — values stored in ir.config_parameter
    api_key_param = fields.Char(
        help="ir.config_parameter key for API Key.",
    )
    account_id_param = fields.Char(
        help="ir.config_parameter key for Account ID (if required).",
    )

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Provider code must be unique."),
    ]

    # ── Computed fields ───────────────────────────────────────────────────────

    @api.depends("monthly_call_limit", "calls_this_month")
    def _compute_limit_status(self):
        for rec in self:
            if rec.monthly_call_limit == 0:
                rec.limit_status = "unlimited"
                rec.limit_usage_pct = 0.0
            else:
                pct = rec.calls_this_month / rec.monthly_call_limit
                rec.limit_usage_pct = round(pct * 100, 1)
                if pct >= 1.0:
                    rec.limit_status = "exceeded"
                elif pct >= LIMIT_WARNING_THRESHOLD:
                    rec.limit_status = "warning"
                else:
                    rec.limit_status = "ok"

    # ── Limit checks ──────────────────────────────────────────────────────────

    def is_limit_reached(self):
        """Return True if this provider has reached its monthly call limit."""
        self.ensure_one()
        if self.monthly_call_limit == 0:
            return False  # 0 = unlimited
        return self.calls_this_month >= self.monthly_call_limit

    def is_limit_warning(self):
        """Return True if this provider is at ≥80% of its monthly limit."""
        self.ensure_one()
        if self.monthly_call_limit == 0:
            return False
        return self.calls_this_month >= (
            self.monthly_call_limit * LIMIT_WARNING_THRESHOLD
        )

    def increment_call_counter(self):
        """Increment monthly call counter and send alert if threshold reached."""
        self.ensure_one()
        new_count = self.calls_this_month + 1
        self.sudo().calls_this_month = new_count

        if self.monthly_call_limit > 0:
            pct = new_count / self.monthly_call_limit
            # Send 80% warning once per month
            if pct >= LIMIT_WARNING_THRESHOLD and not self.limit_alert_sent:
                self.sudo().limit_alert_sent = True
                self._send_limit_warning_notification(new_count)
            # Log when limit is exactly reached
            if new_count >= self.monthly_call_limit:
                _logger.warning(
                    'US Tax Engine: provider "%s" has reached its monthly limit '
                    "(%d/%d calls). Engine will skip this provider until reset.",
                    self.name,
                    new_count,
                    self.monthly_call_limit,
                )

    def _send_limit_warning_notification(self, current_count):
        """Post a message in the chatter/activity for Tax Managers."""
        pct = round(current_count / self.monthly_call_limit * 100)
        remaining = self.monthly_call_limit - current_count
        message = (
            f"⚠️ API Limit Warning — {self.name}\n"
            f"You have used {pct}% of your monthly API limit "
            f"({current_count}/{self.monthly_call_limit} calls). "
            f"Only {remaining} calls remaining this month.\n\n"
            f"Options:\n"
            f"• Upgrade your {self.name} plan\n"
            f"• Ensure local DB covers your main customers's ZIP codes\n"
            f"• Enable a secondary provider with available quota"
        )
        _logger.warning("US Tax: %s", message)
        # Post as Odoo internal notification to Tax Manager group
        try:
            group = self.env.ref(
                "l10n_us_sales_tax_engine.group_us_tax_manager",
                raise_if_not_found=False,
            )
            if group:
                partners = group.users.mapped("partner_id")
                if partners:
                    self.env["mail.message"].sudo().create(
                        {
                            "message_type": "notification",
                            "subtype_id": self.env.ref("mail.mt_note").id,
                            "body": message.replace("\n", "<br/>"),
                            "partner_ids": partners.ids,
                            "author_id": self.env.ref("base.user_root").partner_id.id,
                        }
                    )
        except Exception as exc:
            _logger.debug("Could not send limit notification: %s", exc)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_validate_credentials(self):
        self.ensure_one()
        try:
            engine_cls = self._get_provider_service()
            valid = engine_cls(self).validate_credentials()
            if valid:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "type": "success",
                        "message": f"{self.name}: credentials are valid ✓",
                    },
                }
            raise UserError(self.env._("%s: credentials invalid.", self.name))
        except Exception as exc:
            raise UserError(str(exc)) from exc

    def action_reset_monthly_counter(self):
        self.write({"calls_this_month": 0, "limit_alert_sent": False})

    # ── Provider service lookup ───────────────────────────────────────────────

    def _provider_service_classes(self):
        """Return the {code: service class} registry.

        This is the extension point: an addon adds (or swaps) a provider by
        overriding this method and updating the dict from ``super()`` — no edit
        to the engine is needed.
        """
        from ..services import provider_local  # noqa: PLC0415

        return {
            "local": provider_local.ProviderLocal,
        }

    def _get_provider_service(self):
        """Return the Python service class for this provider's code."""
        cls = self._provider_service_classes().get(self.code)
        if not cls:
            raise UserError(
                self.env._('No service class found for provider code "%s".', self.code)
            )
        return cls

    def get_api_key(self):
        """Safely retrieve API key from ir.config_parameter."""
        self.ensure_one()
        if not self.api_key_param:
            return ""
        return self.env["ir.config_parameter"].sudo().get_param(self.api_key_param, "")
