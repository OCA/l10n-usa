# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

import requests

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import (
    ProviderBase,
    ProviderError,
)

_logger = logging.getLogger(__name__)

ZIPTAX_BASE_URL = "https://api.zip-tax.com/request/v40"


class ProviderZipTax(ProviderBase):
    """ZipTax (zip.tax) API provider — ZIP-level lookup.

    Registration: https://www.zip.tax/register
    Credentials: API key from dashboard
    Free tier: 100 calls/month
    """

    CODE = "ziptax"
    NAME = "ZipTax"
    SUPPORTS_ADDRESS = False
    SUPPORTS_ZIP = True

    def validate_credentials(self) -> bool:
        try:
            key = self.get_api_key()
            resp = requests.get(
                ZIPTAX_BASE_URL,
                params={"key": key, "postalcode": "33101", "country": "US"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return False
            raw = resp.json()
            return raw.get("rCode") == 100 and bool(raw.get("results"))
        except Exception as exc:
            _logger.warning("ZipTax credential validation failed: %s", exc)
            return False

    def get_rate(self, payload: dict) -> dict:
        key = self.get_api_key()
        zip_code = payload.get("zip", "").strip()
        if not zip_code:
            raise ProviderError("ZipTax: zip code is required.")

        _logger.info(
            "ZipTax API call for ZIP=%s (key=%s)", zip_code, self._mask_key(key)
        )

        try:
            resp = requests.get(
                ZIPTAX_BASE_URL,
                params={"key": key, "postalcode": zip_code, "country": "US"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(
                f"ZipTax: request timed out after {self.timeout}s."
            ) from exc
        except requests.HTTPError as exc:
            raise ProviderError(f"ZipTax HTTP error: {exc}") from exc

        self.record.increment_call_counter()
        raw = resp.json()

        if not raw.get("results"):
            raise ProviderError(
                f'ZipTax: no results for ZIP={zip_code}. rCode={raw.get("rCode")}'
            )

        return self.normalize_response(raw["results"][0])

    def normalize_response(self, raw: dict) -> dict:
        # Field names per the real zip.tax v40 response (confirmed against
        # a live call) — not the names a v60-style docs page suggests.
        return {
            "state_rate": float(raw.get("stateSalesTax", 0)),
            "county_rate": float(raw.get("countySalesTax", 0)),
            "city_rate": float(raw.get("citySalesTax", 0)),
            "district_rate": float(raw.get("districtSalesTax", 0)),
            "total_rate": float(raw.get("taxSales", 0)),
            "source_date": None,
            "raw_response": raw,
        }
