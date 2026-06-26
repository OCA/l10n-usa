# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    us_tax_enable_api_ninjas = fields.Boolean(
        string="Enable API Ninjas",
        config_parameter="l10n_us_tax.enable_api_ninjas",
        help="Use API Ninjas as a secondary fallback provider (free tier available).",
    )
    us_tax_api_ninjas_key = fields.Char(
        string="API Ninjas Key",
        config_parameter="l10n_us_tax.api_ninjas_key",
        help="X-Api-Key from your api-ninjas.com profile page.",
    )

    def set_values(self):
        res = super().set_values()
        # Sync provider active state with toggle
        self._sync_provider_active("api_ninjas", self.us_tax_enable_api_ninjas)
        return res
