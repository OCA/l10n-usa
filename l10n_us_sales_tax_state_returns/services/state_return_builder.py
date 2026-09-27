# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Build a state-structured filing worksheet (CSV) for non-SST states.

This produces the return data organized to each state's form - the line items
and per-jurisdiction breakdown the state requires, plus its vendor collection
allowance / timely-filing discount and the net tax due. It is a filing
worksheet (the values to key or upload), not a byte-exact portal file; the
exact upload schema (e.g. Texas EDI 813, Florida DR-15 e-file) is a per-state
spec a deployer maps on top. Allowance rates/caps below are best-effort and
should be confirmed against the current state rules.
"""

import csv
import io

# state_code -> vendor collection allowance / timely-filing discount.
ALLOWANCE = {
    "FL": {"rate": 0.025, "cap": 30.0, "label": "Collection Allowance (2.5%, max $30)"},
    "TX": {"rate": 0.005, "cap": None, "label": "Timely Filing Discount (0.5%)"},
    "PA": {"rate": 0.01, "cap": 25.0, "label": "Vendor Discount (1%, monthly cap $25)"},
}
FORM_NAME = {
    "FL": "Florida Sales and Use Tax Return (DR-15)",
    "TX": "Texas Sales and Use Tax Return (01-114)",
    "PA": "Pennsylvania Sales, Use and Hotel Occupancy Tax Return (PA-3)",
}
SUPPORTED = set(ALLOWANCE)


def is_supported(state_code):
    return state_code in SUPPORTED


def collection_allowance(record):
    """Vendor collection allowance / timely-filing discount for the return.

    When the remittance module is installed and a ``us.tax.authority`` is
    configured for the return's state, that record is the source of truth - so
    the worksheet and the booked remittance bill never disagree. Otherwise fall
    back to the built-in per-state table above (best-effort; confirm against
    current state rules).
    """
    currency = record.company_id.currency_id
    authority = None
    if "us.tax.authority" in record.env:
        authority = record.env["us.tax.authority"]._get_for(
            record.company_id, record.state_id
        )
    if authority and authority.allowance_rate:
        amount = authority.collection_allowance(record.total_tax)
    else:
        cfg = ALLOWANCE.get(record.state_id.code)
        if not cfg:
            return 0.0
        amount = record.total_tax * cfg["rate"]
        if cfg["cap"] is not None:
            amount = min(amount, cfg["cap"])
        amount = currency.round(amount)
    # Never exceed the tax collected, and never go negative (guards a
    # fat-fingered rate or a refund-period total).
    return min(max(amount, 0.0), max(record.total_tax, 0.0))


def build(record):
    """Return the state worksheet as CSV bytes for the return's state."""
    code = record.state_id.code
    builder = {"FL": _build_fl, "TX": _build_tx, "PA": _build_pa}.get(code)
    if not builder:
        raise ValueError(f"No state return builder for {code}")
    buf = io.StringIO()
    builder(record, csv.writer(buf))
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _lines(record, levels):
    return record.line_ids.filtered(lambda line: line.level in levels).sorted(
        lambda line: (line.sequence, line.id)
    )


def _tax(record, levels):
    return round(sum(_lines(record, levels).mapped("tax_amount")), 2)


def _rate(line):
    # Reverse-derived per-line rate for the worksheet's display column; correct
    # only when taxable_base is the jurisdiction-specific base for the line
    # (the report builder stores it per level, not the state-wide base).
    return round(line.tax_amount / line.taxable_base, 6) if line.taxable_base else 0.0


def _header(writer, record):
    writer.writerow([FORM_NAME[record.state_id.code]])
    writer.writerow(["Period", str(record.date_from), str(record.date_to)])
    writer.writerow([])


def _summary_and_net(writer, record):
    allowance = collection_allowance(record)
    writer.writerow([])
    writer.writerow(["Total Tax Collected", f"{record.total_tax:.2f}"])
    writer.writerow([ALLOWANCE[record.state_id.code]["label"], f"{allowance:.2f}"])
    writer.writerow(["Net Tax Due", f"{record.total_tax - allowance:.2f}"])


# ---------------------------------------------------------------------------
# per-state builders
# ---------------------------------------------------------------------------
def _build_fl(record, writer):
    _header(writer, record)
    writer.writerow(["Gross Sales", f"{record.total_sales:.2f}"])
    writer.writerow(["Exempt Sales", f"{record.exempt_sales:.2f}"])
    writer.writerow(["Taxable Amount", f"{record.total_taxable:.2f}"])
    writer.writerow(["State Tax (6%)", f"{_tax(record, ['state']):.2f}"])
    writer.writerow([])
    writer.writerow(["Discretionary Surtax by County"])
    writer.writerow(["County", "FIPS", "Taxable", "Surtax"])
    for line in _lines(record, ["county", "city", "district"]):
        jur = line.jurisdiction_id
        writer.writerow(
            [
                jur.complete_name or "",
                jur.fips_county or jur.fips_place or "",
                f"{line.taxable_base:.2f}",
                f"{line.tax_amount:.2f}",
            ]
        )
    _summary_and_net(writer, record)


def _build_tx(record, writer):
    _header(writer, record)
    writer.writerow(["Total Sales", f"{record.total_sales:.2f}"])
    writer.writerow(["Taxable Sales", f"{record.total_taxable:.2f}"])
    writer.writerow(["State Tax (6.25%)", f"{_tax(record, ['state']):.2f}"])
    writer.writerow([])
    writer.writerow(["Local Jurisdictions"])
    writer.writerow(["Jurisdiction", "FIPS", "Taxable", "Rate", "Tax"])
    for line in _lines(record, ["county", "city", "district"]):
        jur = line.jurisdiction_id
        writer.writerow(
            [
                jur.complete_name or "",
                jur.fips_place or jur.fips_county or "",
                f"{line.taxable_base:.2f}",
                f"{_rate(line):.6f}",
                f"{line.tax_amount:.2f}",
            ]
        )
    _summary_and_net(writer, record)


def _build_pa(record, writer):
    _header(writer, record)
    writer.writerow(["Gross Sales", f"{record.total_sales:.2f}"])
    writer.writerow(["Taxable Sales", f"{record.total_taxable:.2f}"])
    writer.writerow(["State Tax (6%)", f"{_tax(record, ['state']):.2f}"])
    writer.writerow([])
    writer.writerow(["Local Tax (Allegheny / Philadelphia)"])
    writer.writerow(["Jurisdiction", "Taxable", "Rate", "Tax"])
    for line in _lines(record, ["county", "city", "district"]):
        writer.writerow(
            [
                line.jurisdiction_id.complete_name or "",
                f"{line.taxable_base:.2f}",
                f"{_rate(line):.6f}",
                f"{line.tax_amount:.2f}",
            ]
        )
    _summary_and_net(writer, record)
