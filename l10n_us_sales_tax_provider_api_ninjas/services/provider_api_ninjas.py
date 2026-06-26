# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

import requests

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import (
    ProviderBase,
    ProviderError,
)

_logger = logging.getLogger(__name__)

API_NINJAS_URL = "https://api.api-ninjas.com/v1/salestax"


class ProviderApiNinjas(ProviderBase):
    """API Ninjas Sales Tax API — ZIP-level, free tier available.

    Registration: https://api-ninjas.com/register
    Credentials: X-Api-Key header from profile
    """

    CODE = "api_ninjas"
    NAME = "API Ninjas"
    SUPPORTS_ADDRESS = False
    SUPPORTS_ZIP = True

    def validate_credentials(self) -> bool:
        try:
            key = self.get_api_key()
            resp = requests.get(
                API_NINJAS_URL,
                params={"zip_code": "33101"},
                headers={"X-Api-Key": key},
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception as exc:
            _logger.warning("API Ninjas credential validation failed: %s", exc)
            return False

    def get_rate(self, payload: dict) -> dict:
        key = self.get_api_key()
        zip_code = payload.get("zip", "").strip()
        if not zip_code:
            raise ProviderError("API Ninjas: zip code is required.")

        _logger.info(
            "API Ninjas call for ZIP=%s (key=%s)", zip_code, self._mask_key(key)
        )

        try:
            resp = requests.get(
                API_NINJAS_URL,
                params={"zip_code": zip_code},
                headers={"X-Api-Key": key},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(
                f"API Ninjas: request timed out after {self.timeout}s."
            ) from exc
        except requests.HTTPError as exc:
            raise ProviderError(f"API Ninjas HTTP error: {exc}") from exc

        self.record.increment_call_counter()
        data = resp.json()

        if not data:
            raise ProviderError(f"API Ninjas: no data for ZIP={zip_code}.")

        result = data[0] if isinstance(data, list) else data
        return self.normalize_response(result)

    def normalize_response(self, raw: dict) -> dict:
        def safe_float(val, default=0.0) -> float:
            """Convert API Ninjas value to float — free tier returns
            'This field is for premium subscribers only' for county/city."""
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        state_rate = safe_float(raw.get("state_rate", 0))
        county_rate = safe_float(raw.get("county_rate", 0))
        city_rate = safe_float(raw.get("city_rate", 0))
        district_rate = safe_float(raw.get("special_rate", 0))
        # Prefer explicit total_rate; fallback to sum of available components
        total_rate = safe_float(raw.get("total_rate", 0)) or (
            state_rate + county_rate + city_rate + district_rate
        )
        if total_rate == 0 and state_rate == 0:
            raise ProviderError(
                "API Ninjas: free tier returned no usable rate data. "
                "County/city rates require a premium subscription."
            )
        return {
            "state_rate": state_rate,
            "county_rate": county_rate,
            "city_rate": city_rate,
            "district_rate": district_rate,
            "total_rate": total_rate,
            "source_date": None,
            "raw_response": raw,
        }
