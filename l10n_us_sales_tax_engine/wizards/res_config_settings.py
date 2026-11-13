# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Engine core ───────────────────────────────────────────────────────────
    us_tax_engine_active = fields.Boolean(
        string="Enable US Sales Tax Engine",
        config_parameter="l10n_us_tax.engine_active",
        help="Activate hybrid US Sales Tax calculation for US customer addresses.",
    )
    us_tax_auto_calculate = fields.Boolean(
        string="Automatic Tax Calculation",
        config_parameter="l10n_us_tax.auto_calculate",
        help=(
            "When enabled, US Sales Tax is recalculated automatically as the "
            "document changes (lines, partner, address, dates) and on "
            "confirmation/posting. A recalculation that is not already cached "
            "consumes external API calls."
        ),
    )
    us_tax_engine_mode = fields.Selection(
        [
            ("local", "Local Database Only"),
            ("api", "External API Only"),
            ("hybrid", "Hybrid (Local First, API Fallback)"),
        ],
        string="Engine Mode",
        config_parameter="l10n_us_tax.engine_mode",
        default="hybrid",
        help="How the engine selects the tax rate source.",
    )
    us_tax_fail_policy = fields.Selection(
        [
            ("block", "Block — prevent document confirmation"),
            ("warn", "Warn — proceed with $0 tax + warning"),
            ("last_cache", "Use Last Cache — use expired cache if available"),
            ("manual", "Manual — let user enter rate"),
        ],
        string="API Failure Policy",
        config_parameter="l10n_us_tax.fail_policy",
        default="warn",
        help="What happens when all configured API providers fail.",
    )
    us_tax_cache_ttl_hours = fields.Integer(
        string="Cache TTL (hours)",
        config_parameter="l10n_us_tax.cache_ttl_hours",
        default=720,
        help="Hours to keep API responses in cache. Default: 720 (30 days).",
    )
    us_tax_confidence_threshold = fields.Float(
        string="ZIP Confidence Threshold",
        config_parameter="l10n_us_tax.confidence_threshold",
        default=0.7,
        help="Minimum ZIP-to-jurisdiction confidence to use local data (0.0–1.0).",
    )

    @api.onchange("us_tax_engine_active")
    def _onchange_us_tax_engine_active(self):
        """Keep the automation subordinated to the engine.

        Turning the engine off also turns the automation off, so the stored
        parameter never contradicts the engine once the engine is re-enabled.
        """
        for settings in self:
            if not settings.us_tax_engine_active:
                settings.us_tax_auto_calculate = False

    def _sync_provider_active(self, code, enabled):
        provider = (
            self.env["us.tax.provider"].sudo().search([("code", "=", code)], limit=1)
        )
        if provider:
            provider.active = bool(enabled)
