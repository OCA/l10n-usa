# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import json

from odoo import api, fields, models


class UsTaxApiCache(models.Model):
    _name = "us.tax.api.cache"
    _description = "US Tax API Response Cache"
    _order = "cached_at desc"

    address_hash = fields.Char(index=True, required=True)
    zip = fields.Char(size=5, index=True)
    state_id = fields.Many2one("res.country.state", index=True)
    provider_id = fields.Many2one("us.tax.provider", ondelete="set null")
    total_rate = fields.Float(digits=(5, 4))
    state_rate = fields.Float(digits=(5, 4))
    county_rate = fields.Float(digits=(5, 4))
    city_rate = fields.Float(digits=(5, 4))
    district_rate = fields.Float(digits=(5, 4))
    source_date = fields.Date(help="Rate effective date reported by provider.")
    cached_at = fields.Datetime(default=fields.Datetime.now)
    expires_at = fields.Datetime(index=True)
    # Payloads stored as JSON text — keys sanitized (no API credentials)
    request_payload = fields.Text()
    response_payload = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "address_provider_unique",
            "UNIQUE(address_hash, provider_id)",
            "Cache entry for this address+provider already exists.",
        ),
    ]

    @api.model
    def build_hash(self, zip_code, state_code, product_category_code, date_month):
        """Build a deterministic cache key."""
        raw = f"{zip_code}|{state_code}|{product_category_code}|{date_month}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @api.model
    def get_valid_entry(self, address_hash, provider_id=None):
        """Return a non-expired cache entry or None."""
        domain = [
            ("address_hash", "=", address_hash),
            "|",
            ("expires_at", "=", False),
            ("expires_at", ">=", fields.Datetime.now()),
        ]
        if provider_id:
            domain.append(("provider_id", "=", provider_id))
        return self.search(domain, order="cached_at desc", limit=1)

    @api.model
    def create_or_update(
        self,
        address_hash,
        provider_id,
        rates,
        ttl_hours,
        request_payload=None,
        response_payload=None,
        zip_code=None,
        state_id=None,
    ):
        """Upsert a cache entry."""
        now = fields.Datetime.now()
        expires = fields.Datetime.add(now, hours=ttl_hours) if ttl_hours else False

        existing = self.search(
            [
                ("address_hash", "=", address_hash),
                ("provider_id", "=", provider_id),
            ],
            limit=1,
        )

        vals = {
            "total_rate": rates.get("total_rate", 0.0),
            "state_rate": rates.get("state_rate", 0.0),
            "county_rate": rates.get("county_rate", 0.0),
            "city_rate": rates.get("city_rate", 0.0),
            "district_rate": rates.get("district_rate", 0.0),
            "source_date": rates.get("source_date"),
            "cached_at": now,
            "expires_at": expires,
            "request_payload": json.dumps(request_payload or {}),
            "response_payload": json.dumps(response_payload or {}),
        }
        if existing:
            existing.update(vals)
            return existing
        vals.update(
            {
                "address_hash": address_hash,
                "provider_id": provider_id,
                "zip": zip_code,
                "state_id": state_id,
                "active": True,
            }
        )
        return self.create(vals)

    @api.model
    def purge_expired(self):
        """Called by cron to archive expired entries."""
        expired = self.search(
            [
                ("expires_at", "<", fields.Datetime.now()),
            ]
        )
        expired.active = False
        return len(expired)
