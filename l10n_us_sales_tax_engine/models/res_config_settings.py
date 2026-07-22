# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Engine core ───────────────────────────────────────────────────────────
    us_tax_engine_active = fields.Boolean(
        string="Enable US Sales Tax Engine",
        config_parameter="l10n_us_tax.engine_active",
        help="Activate hybrid US Sales Tax calculation for US customer addresses.",
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

    def _sync_provider_active(self, code, enabled):
        provider = (
            self.env["us.tax.provider"].sudo().search([("code", "=", code)], limit=1)
        )
        if provider:
            provider.active = bool(enabled)
