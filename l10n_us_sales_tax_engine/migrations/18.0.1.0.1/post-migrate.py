# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Post-migration for l10n_us_sales_tax_engine 18.0.1.0.1.

Syncs provider active/enable flags from existing ir.config_parameter values
so users who already had API keys configured keep their provider settings
after the upgrade from 18.0.1.0.0 to 18.0.1.0.1.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Sync provider enable flags from pre-existing API keys."""
    if not version:
        # Fresh install — no migration needed, defaults apply.
        return

    _logger.info(
        "l10n_us_sales_tax_engine post-migrate: "
        "syncing provider enable flags from existing API keys..."
    )

    key_to_provider = {
        "l10n_us_tax.ziptax_api_key": ("ziptax", "l10n_us_tax.enable_ziptax"),
        "l10n_us_tax.api_ninjas_key": ("api_ninjas", "l10n_us_tax.enable_api_ninjas"),
        "l10n_us_tax.taxjar_token": ("taxjar", "l10n_us_tax.enable_taxjar"),
    }

    for key_param, (provider_code, enable_param) in key_to_provider.items():
        cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (key_param,))
        row = cr.fetchone()
        if row and row[0]:
            # Key exists — activate the provider and set enable flag
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
                "l10n_us_sales_tax_engine: activated provider %s",
                provider_code,
            )
