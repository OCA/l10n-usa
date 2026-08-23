# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

import requests

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import (
    ProviderBase,
    ProviderError,
)

_logger = logging.getLogger(__name__)

TAXJAR_BASE = "https://api.taxjar.com/v2"
TAXJAR_SANDBOX = "https://api.sandbox.taxjar.com/v2"


class ProviderTaxJar(ProviderBase):
    """TaxJar API provider — address-level lookup (Phase 2).

    Registration: https://app.taxjar.com/sign_up
    Credentials: API Token (Bearer)
    """

    CODE = "taxjar"
    NAME = "TaxJar"
    SUPPORTS_ADDRESS = True
    SUPPORTS_ZIP = True
    COUNTY_NAME_KEY = "county"
    CITY_NAME_KEY = "city"

    def _base_url(self):
        return TAXJAR_SANDBOX if self.record.sandbox_mode else TAXJAR_BASE

    def _headers(self):
        return {"Authorization": f"Bearer {self.get_api_key()}"}

    def validate_credentials(self) -> bool:
        try:
            resp = requests.get(
                f"{self._base_url()}/categories",
                headers=self._headers(),
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception as exc:
            _logger.warning("TaxJar credential validation failed: %s", exc)
            return False

    def get_rate(self, payload: dict) -> dict:
        zip_code = payload.get("zip", "").strip()
        state = payload.get("state", "").strip()
        city = payload.get("city", "").strip()

        _logger.info("TaxJar rate lookup for ZIP=%s, state=%s", zip_code, state)

        try:
            resp = requests.get(
                f"{self._base_url()}/rates/{zip_code}",
                params={"state": state, "city": city or None},
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(
                f"TaxJar: request timed out after {self.timeout}s."
            ) from exc
        except requests.HTTPError as exc:
            raise ProviderError(f"TaxJar HTTP error: {exc}") from exc

        self.record.increment_call_counter()
        try:
            raw = resp.json().get("rate", {})
        except ValueError as exc:
            # A proxy/gateway error page is not JSON; keep it a ProviderError
            # so the engine falls through to the next provider / fail policy.
            raise ProviderError(f"TaxJar: invalid JSON response: {exc}") from exc
        result = self.normalize_response(raw)
        result["jurisdictions"] = self._named_jurisdictions(state, result, raw)
        return result

    def normalize_response(self, raw: dict) -> dict:
        combined = float(raw.get("combined_rate", 0))
        state_r = float(raw.get("state_rate", 0))
        county_r = float(raw.get("county_rate", 0))
        city_r = float(raw.get("city_rate", 0))
        district_r = combined - state_r - county_r - city_r
        return {
            "state_rate": state_r,
            "county_rate": county_r,
            "city_rate": city_r,
            "district_rate": max(0.0, round(district_r, 6)),
            "total_rate": combined,
            "source_date": None,
            "raw_response": raw,
        }
