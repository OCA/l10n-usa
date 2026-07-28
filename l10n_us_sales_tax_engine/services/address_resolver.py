# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import re


def normalize_zip(zip_code: str) -> str:
    """Extract and validate 5-digit US ZIP from any input."""
    if not zip_code:
        return ""
    cleaned = re.sub(r"[^0-9]", "", str(zip_code).strip())
    return cleaned[:5] if len(cleaned) >= 5 else ""


def _partner_to_address(partner: object) -> dict:
    """Extract address dict from a res.partner record."""
    zip_code = normalize_zip(partner.zip or "")
    state_code = partner.state_id.code if partner.state_id else ""
    country_code = partner.country_id.code if partner.country_id else ""
    return {
        "zip": zip_code,
        "state": state_code,
        "city": (partner.city or "").strip().upper(),
        "county": "",
        "address": f'{partner.street or ""}, {partner.city or ""}, '
        f"{state_code} {zip_code}",
        "country_code": country_code,
        "partner_id": partner.id,
    }


def resolve_shipping_address(record):
    """Extract shipping address from sale.order or account.move.

    Priority: explicit shipping partner > delivery child > invoice address
    Returns: dict with zip, state_code, city, county, full_address
    """
    partner = None

    if hasattr(record, "partner_shipping_id") and record.partner_shipping_id:
        partner = record.partner_shipping_id
    elif hasattr(record, "partner_id") and record.partner_id:
        # Look for child delivery address
        delivery = record.partner_id.child_ids.filtered(lambda p: p.type == "delivery")
        partner = delivery[0] if delivery else record.partner_id

    if not partner:
        return {}

    return _partner_to_address(partner)


def resolve_invoice_address(record):
    """Extract billing/invoice address from sale.order or account.move.

    Used when us_tax_based_on_shipping is False on the sale order.
    Priority: partner_invoice_id > partner_id
    """
    partner = None

    if hasattr(record, "partner_invoice_id") and record.partner_invoice_id:
        partner = record.partner_invoice_id
    elif hasattr(record, "partner_id") and record.partner_id:
        partner = record.partner_id

    if not partner:
        return {}

    return _partner_to_address(partner)


def is_us_address(address_dict: dict) -> bool:
    """Return True if address is within the United States."""
    code = address_dict.get("country_code", "")
    return code in ("US", "USA") if code else True
