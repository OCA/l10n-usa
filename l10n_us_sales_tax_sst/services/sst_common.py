# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Shared constants and helpers for the SST Rate & Boundary integration."""

# Re-exported from the engine so the importer and the taxability-matrix wizard
# parse dates (incl. open-ended sentinels) identically.
from odoo.addons.l10n_us_sales_tax_engine.tools import (  # noqa: F401
    OPEN_ENDED,
    parse_sst_date,
)

# X12 Data Element 1721 "Jurisdiction Type" → engine us.tax.jurisdiction.type
# (which drives us_tax_level on the booked tax). Anything not listed is treated
# as a special district.
JTYPE_TO_LEVEL = {
    "45": "state",
    "00": "county",
    "01": "city",
    "02": "city",
    "03": "city",
    "05": "city",
    # Sub-county special jurisdictions (transit authorities, special-purpose
    # districts, local tax areas such as Washington's location codes). The
    # engine has a single "district" level, so they all land there; the rate
    # still applies per jurisdiction. Enumerated explicitly so a genuinely
    # unrecognised code is logged by the importer rather than silently bucketed.
    "26": "district",
    "49": "district",
    "63": "district",
    "69": "district",
    "79": "district",
}

# Engine product-category codes that take the SST reduced food/drug rate.
FOOD_DRUG_CATEGORIES = {"FOOD", "MEDICINE"}


def jtype_to_level(jurisdiction_type):
    """Map an X12 DE1721 jurisdiction-type code to an engine level.

    Codes are zero-padded to two digits before lookup: some states emit them
    unpadded (e.g. Tennessee writes county/city as "0"/"1", not "00"/"01"),
    which would otherwise fall through to "district".
    """
    return JTYPE_TO_LEVEL.get((jurisdiction_type or "").strip().zfill(2), "district")


def parse_sst_rate(value):
    """Parse an SST decimal-fraction rate string (e.g. '0.04875') to float."""
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0
