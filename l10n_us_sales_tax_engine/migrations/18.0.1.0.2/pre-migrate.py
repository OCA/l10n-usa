# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Pre-migration for l10n_us_sales_tax_engine 18.0.1.0.2.

Removes the TaxCloud provider record and related ir.config_parameter entries.
TaxCloud was a Phase 2 placeholder that was never implemented; it is removed
in this version to avoid confusion.
"""

import logging

_logger = logging.getLogger(__name__)

TAXCLOUD_PARAMS = [
    "l10n_us_tax.taxcloud_api_key",
    "l10n_us_tax.taxcloud_login_id",
    "l10n_us_tax.enable_taxcloud",
]


def migrate(cr, version):
    if not version:
        return

    _logger.info("l10n_us_sales_tax_engine: removing TaxCloud provider...")

    cr.execute(
        "DELETE FROM us_tax_provider WHERE code = 'taxcloud'",
    )
    _logger.info("l10n_us_sales_tax_engine: deleted TaxCloud provider record.")

    for param in TAXCLOUD_PARAMS:
        cr.execute(
            "DELETE FROM ir_config_parameter WHERE key = %s",
            (param,),
        )
    _logger.info("l10n_us_sales_tax_engine: cleaned up TaxCloud config parameters.")
