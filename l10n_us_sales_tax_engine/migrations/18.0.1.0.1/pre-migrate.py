# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Pre-migration: clean XML control characters from ir_ui_view.arch_db.

Some view records in the database contain XML-invalid control characters
(0x01-0x08, 0x0B, 0x0C, 0x0E-0x1F) that cause lxml to fail when Odoo
scans all views for i18n terms during --update.

This script removes those characters before the module update proceeds,
allowing the update to complete cleanly.
"""

import logging
import re

_logger = logging.getLogger(__name__)

# XML-valid control characters are only: TAB (0x09), LF (0x0A), CR (0x0D)
# All others in range 0x01-0x1F are invalid in XML and must be removed.
_CONTROL_CHAR_RE = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f]")


def migrate(cr, version):
    """Remove XML-invalid control characters from all view arch_db columns."""
    _logger.info(
        "l10n_us_sales_tax_engine pre-migrate: "
        "scanning views for XML-invalid control characters..."
    )

    cr.execute("SELECT id, name::text FROM ir_ui_view ORDER BY id")
    views = cr.fetchall()

    fixed = 0
    for view_id, view_name in views:
        try:
            cr.execute("SELECT arch_db::text FROM ir_ui_view WHERE id = %s", (view_id,))
            row = cr.fetchone()
            if not row or not row[0]:
                continue

            arch_str = row[0]
            # Check for XML-invalid control characters
            if _CONTROL_CHAR_RE.search(arch_str):
                cleaned = _CONTROL_CHAR_RE.sub("", arch_str)
                cr.execute(
                    "UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s",
                    (cleaned, view_id),
                )
                fixed += 1
                _logger.debug(
                    "Cleaned control characters from view id=%s name=%s",
                    view_id,
                    (view_name or "")[:60],
                )
        except Exception as exc:
            _logger.warning("Could not clean view id=%s: %s", view_id, exc)

    if fixed:
        _logger.info(
            "l10n_us_sales_tax_engine pre-migrate: "
            "cleaned %d views with XML-invalid control characters.",
            fixed,
        )
    else:
        _logger.info(
            "l10n_us_sales_tax_engine pre-migrate: "
            "no views with control characters found."
        )
