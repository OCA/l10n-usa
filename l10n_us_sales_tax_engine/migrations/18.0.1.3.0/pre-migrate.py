# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Pre-migration for l10n_us_sales_tax_engine 18.0.1.3.0.

Carries l10n_us_tax.engine_active over to l10n_us_tax.auto_calculate on a
database that already had the engine on. Before this version the engine was
gated by engine_active alone; from here on the automatic recalculation needs
both parameters, and nothing but the settings form ever writes the new one,
so an upgraded database would silently stop calculating tax and under-collect.

Only runs on an upgrade, and only when the engine was already enabled: a
database that never turned it on is left untouched. Enabling it costs no
provider call during the upgrade itself, because the new columns are
initialised through _write_multi, which does not re-enter write().

Carrying the flag over also switches on the new write()/create() triggers
and the daily cron, which consume more provider quota than 18.0.1.2.0 did.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = 'l10n_us_tax.engine_active'"
    )
    row = cr.fetchone()
    if not row or row[0] != "True":
        return

    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_uid, write_uid,
                                         create_date, write_date)
        VALUES ('l10n_us_tax.auto_calculate', 'True', 1, 1, NOW(), NOW())
        ON CONFLICT (key) DO NOTHING
        """
    )
    _logger.info(
        "l10n_us_sales_tax_engine: automatic US tax calculation enabled, "
        "inherited from l10n_us_tax.engine_active."
    )
