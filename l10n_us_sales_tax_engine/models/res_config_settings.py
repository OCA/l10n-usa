# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Engine core ───────────────────────────────────────────────────────────
    us_tax_engine_active = fields.Boolean(
        string='Enable US Sales Tax Engine',
        config_parameter='l10n_us_tax.engine_active',
        help='Activate hybrid US Sales Tax calculation for US customer addresses.',
    )
    us_tax_engine_mode = fields.Selection([
        ('local',  'Local Database Only'),
        ('api',    'External API Only'),
        ('hybrid', 'Hybrid (Local First, API Fallback)'),
    ],
        string='Engine Mode',
        config_parameter='l10n_us_tax.engine_mode',
        default='hybrid',
        help='How the engine selects the tax rate source.',
    )
    us_tax_fail_policy = fields.Selection([
        ('block',      'Block — prevent document confirmation'),
        ('warn',       'Warn — proceed with $0 tax + warning'),
        ('last_cache', 'Use Last Cache — use expired cache if available'),
        ('manual',     'Manual — let user enter rate'),
    ],
        string='API Failure Policy',
        config_parameter='l10n_us_tax.fail_policy',
        default='warn',
        help='What happens when all configured API providers fail.',
    )
    us_tax_cache_ttl_hours = fields.Integer(
        string='Cache TTL (hours)',
        config_parameter='l10n_us_tax.cache_ttl_hours',
        default=720,
        help='Hours to keep API responses in cache. Default: 720 (30 days).',
    )
    us_tax_confidence_threshold = fields.Float(
        string='ZIP Confidence Threshold',
        config_parameter='l10n_us_tax.confidence_threshold',
        default=0.7,
        help='Minimum ZIP-to-jurisdiction confidence to use local data (0.0–1.0).',
    )

    # ── Provider toggles — show credential only when provider is enabled ──────
    us_tax_enable_ziptax = fields.Boolean(
        string='Enable ZipTax',
        config_parameter='l10n_us_tax.enable_ziptax',
        help='Use ZipTax (zip.tax) as an external fallback provider.',
    )
    us_tax_ziptax_api_key = fields.Char(
        string='ZipTax API Key',
        help='Register free at https://www.zip.tax/register — 100 calls/month free.',
    )

    us_tax_enable_api_ninjas = fields.Boolean(
        string='Enable API Ninjas',
        config_parameter='l10n_us_tax.enable_api_ninjas',
        help='Use API Ninjas as a secondary fallback provider (free tier available).',
    )
    us_tax_api_ninjas_key = fields.Char(
        string='API Ninjas Key',
        help='X-Api-Key from your api-ninjas.com profile page.',
    )

    us_tax_enable_taxjar = fields.Boolean(
        string='Enable TaxJar',
        config_parameter='l10n_us_tax.enable_taxjar',
        help='Use TaxJar for address-level accuracy (paid plan required).',
    )
    us_tax_taxjar_token = fields.Char(
        string='TaxJar API Token',
        help='Bearer token from TaxJar account → Integrations → TaxJar API.',
    )

    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res.update({
            'us_tax_ziptax_api_key': ICP.get_param('l10n_us_tax.ziptax_api_key', ''),
            'us_tax_api_ninjas_key': ICP.get_param('l10n_us_tax.api_ninjas_key', ''),
            'us_tax_taxjar_token':   ICP.get_param('l10n_us_tax.taxjar_token', ''),
        })
        return res

    def set_values(self):
        res = super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('l10n_us_tax.ziptax_api_key', self.us_tax_ziptax_api_key or '')
        ICP.set_param('l10n_us_tax.api_ninjas_key', self.us_tax_api_ninjas_key or '')
        ICP.set_param('l10n_us_tax.taxjar_token',   self.us_tax_taxjar_token or '')

        # Sync provider active state with toggles
        self._sync_provider_active('ziptax',    self.us_tax_enable_ziptax)
        self._sync_provider_active('api_ninjas', self.us_tax_enable_api_ninjas)
        self._sync_provider_active('taxjar',    self.us_tax_enable_taxjar)
        return res

    def _sync_provider_active(self, code, enabled):
        provider = self.env['us.tax.provider'].sudo().search(
            [('code', '=', code)], limit=1
        )
        if provider:
            provider.write({'active': bool(enabled)})
