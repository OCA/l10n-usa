# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Shared helpers for effective-dated US tax data (rates, rules, boundaries)."""

from datetime import date, timedelta

# Open-ended effective-date sentinels. The SST spec documents 29991231, but real
# state files (e.g. Wyoming) use 99991231 — treat any far-future date as open.
OPEN_ENDED = {"29991231", "99991231"}

# States that source an INTRASTATE sale to the seller's location (ship-from)
# rather than the customer's (ship-to). Interstate sales are always destination.
# (California is a hybrid — state/county origin, district destination — and is
# intentionally not listed; it is rated destination-based until modelled.)
ORIGIN_BASED_STATES = {
    "AZ",
    "IL",
    "MS",
    "MO",
    "NM",
    "OH",
    "PA",
    "TN",
    "TX",
    "UT",
    "VA",
}


def parse_sst_date(value):
    """Parse a CCYYMMDD or YYYY-MM-DD string into a date; open-ended/blank → None."""
    value = (value or "").strip()
    if not value:
        return None
    if "-" in value:
        value = value.replace("-", "")
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"Invalid date {value!r} (expected CCYYMMDD or YYYY-MM-DD)")
    if value in OPEN_ENDED or value[:4] >= "2999":
        return None
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def close_superseded_periods(model, base_domain, effective_date):
    """Close open prior periods when a newer effective-dated row starts.

    Sets ``end_date`` = ``effective_date`` − 1 day on every record matching
    ``base_domain`` that is still open (``end_date`` unset) and started earlier,
    so exactly one period is active on any date. Used by both the rate importer
    (``us.tax.rate``) and the taxability-matrix importer (``us.tax.rule``).
    """
    if not effective_date:
        return
    model.search(
        base_domain
        + [("end_date", "=", False), ("effective_date", "<", effective_date)]
    ).write({"end_date": effective_date - timedelta(days=1)})
