# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

_logger = logging.getLogger(__name__)


class CacheManager:
    """Handles cache lookups and writes for the tax engine."""

    def __init__(self, env, ttl_hours: int = 720):
        self.env = env
        self.ttl_hours = ttl_hours
        # sudo: caching is an internal engine detail, not a permission a
        # calling user should need (group_us_tax_technical only gates
        # manual access to the cache screen, not the engine's own writes).
        self.Cache = env["us.tax.api.cache"].sudo()

    def get(self, address_hash: str, provider_id: int = None):
        """Return cached rate dict or None if cache miss/expired."""
        entry = self.Cache.get_valid_entry(address_hash, provider_id=provider_id)
        if not entry:
            return None
        _logger.debug("Cache HIT for hash=%s", address_hash[:12])
        return {
            "state_rate": entry.state_rate,
            "county_rate": entry.county_rate,
            "city_rate": entry.city_rate,
            "district_rate": entry.district_rate,
            "total_rate": entry.total_rate,
            "source_date": str(entry.source_date) if entry.source_date else None,
            "from_cache": True,
            "cached_at": str(entry.cached_at),
        }

    def set(
        self,
        address_hash: str,
        provider_id: int,
        rates: dict,
        zip_code: str = None,
        state_id: int = None,
        request_payload: dict = None,
        response_payload: dict = None,
    ):
        """Save rates to cache."""
        try:
            self.Cache.create_or_update(
                address_hash=address_hash,
                provider_id=provider_id,
                rates=rates,
                ttl_hours=self.ttl_hours,
                request_payload=request_payload,
                response_payload=response_payload,
                zip_code=zip_code,
                state_id=state_id,
            )
            _logger.debug(
                "Cache SET for hash=%s, TTL=%sh", address_hash[:12], self.ttl_hours
            )
        except Exception as exc:
            _logger.warning("Cache write failed: %s", exc)

    def build_hash(
        self, zip_code: str, state_code: str, product_category_code: str, date
    ) -> str:
        date_month = str(date)[:7] if date else "nodate"  # 'YYYY-MM'
        return self.Cache.build_hash(
            zip_code, state_code, product_category_code, date_month
        )
