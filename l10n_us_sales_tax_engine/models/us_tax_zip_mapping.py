# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxZipMapping(models.Model):
    _name = "us.tax.zip.mapping"
    _description = "US Tax ZIP to Jurisdiction Mapping"
    _order = "zip, confidence desc"
    _rec_name = "zip"

    zip = fields.Char(
        string="ZIP Code",
        size=5,
        required=True,
        index=True,
    )
    zip4 = fields.Char(string="ZIP+4", size=4)
    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        required=True,
        index=True,
    )
    jurisdiction_id = fields.Many2one(
        "us.tax.jurisdiction",
        required=True,
        index=True,
        ondelete="restrict",
    )
    county = fields.Char()
    city = fields.Char()
    confidence = fields.Float(
        default=1.0,
        help="Confidence 0.0-1.0. Highest wins when ZIP has multiple jurisdictions.",
    )
    source = fields.Char(
        default="manual",
        help="Data origin: florida_dor, texas_open_data, api_ziptax, manual",
    )
    imported_at = fields.Datetime(default=fields.Datetime.now)
    import_batch_id = fields.Many2one("us.tax.import.batch")
    address_key = fields.Char(
        default="",
        index=True,
        help="Normalized full-address key for a rooftop-specific mapping. "
        "Empty for a ZIP-level (fallback) mapping.",
    )
    verified = fields.Boolean(
        help="The jurisdiction was confirmed by an authoritative source "
        "(an address-level provider or geocode), not just a ZIP guess. "
        "Verified rooftop mappings win over ZIP-level confidence.",
    )

    _sql_constraints = [
        (
            "zip_jurisdiction_unique",
            "UNIQUE(zip, jurisdiction_id, address_key)",
            "This ZIP + Jurisdiction + address combination already exists.",
        ),
    ]

    @api.model
    def get_best_jurisdiction(self, zip_code, state_code=None, confidence_min=0.7):
        """Return the best jurisdiction for a ZIP code.

        Args:
            zip_code: 5-digit ZIP string
            state_code: Optional 2-letter state code to narrow down
            confidence_min: Minimum confidence threshold
        Returns:
            us.tax.jurisdiction record or empty recordset
        """
        domain = [
            ("zip", "=", zip_code),
            ("confidence", ">=", confidence_min),
        ]
        if state_code:
            domain += [("state_id.code", "=", state_code)]

        mapping = self.search(domain, order="confidence desc", limit=1)
        return mapping.jurisdiction_id if mapping else self.env["us.tax.jurisdiction"]

    @api.model
    def _address_key(self, address):
        """Normalized rooftop key from an address dict, or '' when there is no
        street detail (in which case only ZIP-level resolution is possible).

        The address dict carries a formatted ``address`` string built as
        ``"<street>, <city>, <state> <zip>"`` (see address_resolver).
        """
        full = (address.get("address") or "").strip()
        if not full or not full.split(",")[0].strip():
            return ""  # no street -> ZIP-level only
        return " ".join(full.upper().split())

    @api.model
    def resolve_jurisdiction(self, address, confidence_min=0.7):
        """Resolve a jurisdiction from a full address, ZIP being the fallback.

        A verified rooftop (address-level) mapping wins; otherwise the ZIP-level
        confidence pick. This makes a straddling ZIP resolve correctly once the
        address has been learned.
        """
        key = self._address_key(address)
        if key:
            m = self.search(
                [("address_key", "=", key)],
                order="verified desc, confidence desc",
                limit=1,
            )
            if m:
                return m.jurisdiction_id
            # No learned rooftop yet: let a geocode bridge resolve and teach it
            # (free, address-accurate) before falling back to the ZIP guess.
            jurisdiction = self._geocode_jurisdiction(address)
            if jurisdiction:
                self.learn_jurisdiction(address, jurisdiction, source="geocode")
                return jurisdiction
        return self.get_best_jurisdiction(
            (address.get("zip") or "")[:5], address.get("state"), confidence_min
        )

    @api.model
    def _geocode_jurisdiction(self, address):
        """Hook: resolve a jurisdiction from a rooftop geocode (e.g. address ->
        county FIPS -> jurisdiction), or an empty recordset. No-op in the
        engine; a geocode bridge (property_data) overrides it to populate the
        learned cache without a paid provider."""
        return self.env["us.tax.jurisdiction"]

    @api.model
    def learn_jurisdiction(self, address, jurisdiction, source="api"):
        """Persist the address -> jurisdiction assignment an authoritative
        source resolved, so it is reused locally and the upstream provider is
        not called again for the same rooftop.

        Address -> jurisdiction is permanent (a rooftop does not change tax
        jurisdiction), unlike the rate, so this is cached without a TTL.
        """
        key = self._address_key(address)
        if not key or not jurisdiction:
            return self.browse()
        vals = {
            "zip": (address.get("zip") or "")[:5],
            "state_id": jurisdiction.state_id.id,
            "jurisdiction_id": jurisdiction.id,
            "address_key": key,
            "confidence": 1.0,
            "verified": True,
            "source": source,
        }
        existing = self.search([("address_key", "=", key)], limit=1)
        if existing:
            existing.write(vals)
            return existing
        return self.create(vals)
