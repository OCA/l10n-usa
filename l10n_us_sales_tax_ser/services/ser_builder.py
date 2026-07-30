# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Build a Streamlined Sales Tax Simplified Electronic Return (SER) as XML.

Element names follow the SST Technology Guide (Oct 2022, Ch. 6-9) and the
``SSTSER2025V01`` schema family. The amounts come from a generated
``us.tax.return``; the per-jurisdiction breakdown (``JurisdictionDetail``) is
keyed by FIPS code, which is why this can only be produced once SST Rate &
Boundary data has tagged the booked taxes with named jurisdictions.

NOTE: the canonical XSD lives at FTA E-Standards (statemef.com) and must be
confirmed before transmitting to a state; the version + a couple of element
names are kept as constants here so they are trivial to align.
"""

import xml.etree.ElementTree as ET

TRANSMISSION_VERSION = "SSTSER2025V01"


def _money(value):
    return f"{value:.2f}"


def _sub(parent, tag, text=None, attrib=None):
    el = ET.SubElement(parent, tag, attrib or {})
    if text is not None:
        el.text = str(text)
    return el


def _state_fips(tax_return):
    """2-digit state FIPS the return is filed to."""
    state_line = tax_return.line_ids.filtered(lambda line: line.level == "state")
    fips = state_line[:1].jurisdiction_id.fips_state
    if not fips:
        any_jur = tax_return.env["us.tax.jurisdiction"].search(
            [
                ("state_id", "=", tax_return.state_id.id),
                ("fips_state", "!=", False),
            ],
            limit=1,
        )
        fips = any_jur.fips_state
    return fips


def _line_fips(line):
    """The FIPS / composite code a non-state jurisdiction line reports under."""
    jur = line.jurisdiction_id
    return (
        jur.composite_ser_code
        or jur.fips_place
        or jur.fips_county
        or jur.district_code
        or jur.fips_state
        or ""
    )


def build_ser(tax_return):
    """Return the SER XML for ``tax_return`` as bytes (with declaration)."""
    company = tax_return.company_id
    sstpid = company.sst_id
    state_id_value = tax_return.state_registration_id
    state_fips = _state_fips(tax_return)
    version = company.sst_transmission_version or TRANSMISSION_VERSION
    process_type = "T" if company.sst_test_mode else "P"

    root = ET.Element(
        "SSTSimplifiedReturnTransmission",
        {"transmissionVersion": version},
    )

    header = _sub(root, "TransmissionHeader")
    _sub(
        header,
        "TransmissionId",
        f"{company.sst_transmitter_id or 'TEST'}{tax_return.id:011d}",
    )
    _sub(header, "ProcessType", process_type)
    _sub(header, "DocumentCount", "1")

    document = _sub(
        root,
        "SimplifiedReturnDocument",
        attrib={"DocumentId": str(tax_return.id), "DocumentType": "SEROnly"},
    )

    filing = _sub(document, "SSTPFilingHeader")
    _sub(filing, "FilingType", "SEROnly")
    _sub(filing, "TaxPeriodStartDate", tax_return.date_from)
    _sub(filing, "TaxPeriodEndDate", tax_return.date_to)
    # SSTPID for SST-registered sellers, otherwise the state-issued StateID.
    if sstpid:
        _sub(filing, "SSTPID", sstpid)
    elif state_id_value:
        _sub(filing, "StateID", state_id_value)
    tin = _sub(filing, "TIN")
    _sub(tin, "FedTIN", company.sst_fein, attrib={"TypeTIN": "FEIN"})
    _sub(filing, "FIPSCode", state_fips)

    ser = _sub(document, "SimplifiedElectronicReturn")
    _sub(ser, "ReturnType", "O")
    _sub(ser, "TotalSales", _money(tax_return.total_sales))
    _sub(ser, "ExemptionsDeductions", _money(tax_return.exempt_sales))
    _sub(ser, "TaxableSales", _money(tax_return.total_taxable))

    state_lines = tax_return.line_ids.filtered(lambda line: line.level == "state")
    _sub(
        ser,
        "StateTaxDueSalesInState",
        _money(sum(state_lines.mapped("tax_amount"))),
    )
    # Mandatory in the schema. We are destination-based and don't separately
    # track out-of-state-origin sales, consumer-use withdrawals, or a reduced
    # state food/drug rate, so these are reported as zero.
    _sub(ser, "StateTaxDueSalesOrigOutOfState", _money(0.0))
    _sub(ser, "StateTaxDueOwnPurchWithdraw", _money(0.0))
    _sub(ser, "StateTaxDueFoodDrug", _money(0.0))

    for line in tax_return.line_ids.sorted(lambda r: (r.sequence, r.id)):
        if line.level == "state":
            continue
        detail = _sub(ser, "JurisdictionDetail")
        _sub(detail, "JurisdictionCode", _line_fips(line))
        _sub(detail, "JurisTaxDueSalesInState", _money(line.tax_amount))
        _sub(detail, "JurisTaxDueSalesOrigOutOfState", _money(0.0))
        _sub(detail, "JurisTaxDueOwnPurchWithdraw", _money(0.0))

    _sub(ser, "TotalTaxDue", _money(tax_return.total_tax))
    _sub(ser, "AmountDueOrRefund", _money(tax_return.total_tax))

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
