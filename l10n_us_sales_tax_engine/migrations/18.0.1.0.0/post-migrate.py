# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Post-migration script for l10n_us_sales_tax_engine 18.0.1.0.0.

Ensures provider enable flags are synced from existing ir.config_parameter
values on first install / upgrade, so users who configured providers before
this version keep their settings.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Sync enable flags with existing API keys in ir.config_parameter."""
    _logger.info("l10n_us_sales_tax_engine: syncing provider enable flags...")

    key_to_provider = {
        "l10n_us_tax.ziptax_api_key": ("ziptax", "l10n_us_tax.enable_ziptax"),
        "l10n_us_tax.api_ninjas_key": ("api_ninjas", "l10n_us_tax.enable_api_ninjas"),
        "l10n_us_tax.taxjar_token": ("taxjar", "l10n_us_tax.enable_taxjar"),
    }

    for key_param, (provider_code, enable_param) in key_to_provider.items():
        # Check if an API key already exists
        cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (key_param,))
        row = cr.fetchone()
        if row and row[0]:
            # Key exists → enable the provider and set the flag
            cr.execute(
                """
                INSERT INTO ir_config_parameter (key, value)
                VALUES (%s, 'True')
                ON CONFLICT (key) DO UPDATE SET value = 'True'
                """,
                (enable_param,),
            )
            cr.execute(
                "UPDATE us_tax_provider SET active = TRUE WHERE code = %s",
                (provider_code,),
            )
            _logger.info(
                "l10n_us_sales_tax_engine: enabled provider %s (key found)",
                provider_code,
            )
