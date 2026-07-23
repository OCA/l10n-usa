# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    us_tax_enable_ziptax = fields.Boolean(
        string="Enable ZipTax",
        config_parameter="l10n_us_tax.enable_ziptax",
        help="Use ZipTax (zip.tax) as an external fallback provider.",
    )
    us_tax_ziptax_api_key = fields.Char(
        string="ZipTax API Key",
        config_parameter="l10n_us_tax.ziptax_api_key",
        help="Register free at https://www.zip.tax/register — 100 calls/month free.",
    )

    def set_values(self):
        res = super().set_values()
        # Sync provider active state with toggle
        self._sync_provider_active("ziptax", self.us_tax_enable_ziptax)
        return res
