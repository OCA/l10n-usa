# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Single source of truth for the US tax jurisdiction-level taxonomy.

The state / county / city / district levels (and the ``combined`` catch-all for
a provider that returns only a total rate) drive: the Selection fields on
``account.tax``, ``us.tax.jurisdiction`` and ``us.tax.return.line``; the rate
component columns on ``us.tax.rate``; the per-level booking labels; and the
return-line ordering. Defining them once here keeps those in lock-step across
the engine, report and SST addons.
"""

# (code, label, us.tax.rate field, display sequence)
_LEVELS = [
    ("state", "State", "state_rate", 0),
    ("county", "County", "county_rate", 1),
    ("city", "City", "city_rate", 2),
    ("district", "Special District", "district_rate", 3),
    ("combined", "Combined (undetailed)", None, 4),
]

# Selection for jurisdiction.type (real levels only — no synthetic "combined").
JURISDICTION_TYPE_SELECTION = [
    (c, lbl) for c, lbl, _rf, _seq in _LEVELS if c != "combined"
]
# Selection for booked-tax / return-line level (includes "combined").
LEVEL_SELECTION = [(c, lbl) for c, lbl, _rf, _seq in _LEVELS]

LABEL_BY_LEVEL = {c: lbl for c, lbl, _rf, _seq in _LEVELS}
SEQUENCE_BY_LEVEL = {c: seq for c, _lbl, _rf, seq in _LEVELS}
RATE_FIELD_BY_LEVEL = {c: rf for c, _lbl, rf, _seq in _LEVELS if rf}

# Ordered (code, label, rate_field) for the per-level scalar booking path.
RATE_COMPONENTS = [
    (c, lbl, rf) for c, lbl, rf, _seq in _LEVELS if rf and c != "combined"
]


def level_to_rate_field(level):
    """Return the us.tax.rate component column for a level (district default)."""
    return RATE_FIELD_BY_LEVEL.get(level, "district_rate")
