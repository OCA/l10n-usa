# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

import requests

from odoo.addons.l10n_us_sales_tax_engine.services.provider_base import (
    ProviderBase,
    ProviderError,
)

_logger = logging.getLogger(__name__)

CDTFA_BASE = "https://services.maps.cdtfa.ca.gov/api/taxrate"
# California statewide minimum (state 6.00% + Bradley-Burns local 1.25%).
# Anything above this on a given rooftop is district (transactions & use) tax.
CA_BASE_RATE = 0.0725


class ProviderCdtfa(ProviderBase):
    """California CDTFA rate provider — free, keyless, rooftop.

    Calls the California Department of Tax and Fee Administration's public
    address-rate service (no API key). California-only: it raises for other
    states so the engine falls through to the next provider in the chain.

    Service: https://services.maps.cdtfa.ca.gov/
    Terms:   https://www.cdtfa.ca.gov/dataportal/policy.htm
    """

    CODE = "cdtfa"
    NAME = "California CDTFA"
    SUPPORTS_ADDRESS = True
    SUPPORTS_ZIP = True

    def _get_rate_by_address(self, address, city, zip_code):
        resp = requests.get(
            f"{CDTFA_BASE}/GetRateByAddress",
            params={"address": address, "city": city, "zip": zip_code},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def validate_credentials(self) -> bool:
        # No credentials (free public service); just confirm the endpoint answers.
        try:
            data = self._get_rate_by_address("450 N Street", "Sacramento", "95814")
            return bool(data.get("taxRateInfo"))
        except Exception as exc:
            _logger.warning("CDTFA endpoint check failed: %s", exc)
            return False

    def get_rate(self, payload: dict) -> dict:
        state = payload.get("state", "").strip().upper()
        if state != "CA":
            # CDTFA only covers California; let the engine try the next provider.
            raise ProviderError(f"CDTFA: California addresses only (state={state}).")

        zip_code = payload.get("zip", "").strip()
        city = payload.get("city", "").strip()
        address = payload.get("address", "").strip()
        _logger.info(
            "CDTFA rate lookup for %s, %s %s", address or "(zip only)", city, zip_code
        )

        try:
            data = self._get_rate_by_address(address, city, zip_code)
        except requests.Timeout as exc:
            raise ProviderError(
                f"CDTFA: request timed out after {self.timeout}s."
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            # Connection/HTTP errors or a non-JSON body — surface as a
            # ProviderError so the engine falls through to the next provider
            # instead of letting the exception abort the whole calculation.
            raise ProviderError(f"CDTFA request failed: {exc}") from exc

        info = (data.get("taxRateInfo") or [{}])[0]
        if not info.get("rate"):
            raise ProviderError(f"CDTFA: no rate for {address or zip_code}, CA.")

        self.record.increment_call_counter()
        result = self.normalize_response(info)
        result["jurisdictions"] = self._ca_jurisdictions(result, info)
        return result

    def normalize_response(self, raw: dict) -> dict:
        # CDTFA returns one combined rooftop rate (no per-level split). Book the
        # 7.25% statewide base as the state portion and the remainder as the
        # local district add-on so state + district == the exact rooftop total.
        total = float(raw.get("rate") or 0.0)
        state_rate = min(CA_BASE_RATE, total)
        return {
            "state_rate": state_rate,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": round(total - state_rate, 6),
            "total_rate": total,
            "source_date": None,
            "raw_response": raw,
        }

    def _ca_jurisdictions(self, normalized, raw):
        """California reports a single combined rate per Tax Area Code, not a
        per-level breakdown — book the statewide base as the state line and the
        rooftop remainder as a named district (by the CDTFA jurisdiction)."""
        label = (raw.get("jurisdiction") or raw.get("city") or "CA").title()
        components = [
            {"level": "state", "name": "California", "rate": normalized["state_rate"]},
            {
                "level": "district",
                "name": f"{label} (CA)",
                "rate": normalized["district_rate"],
            },
        ]
        return self.resolve_named_jurisdictions("CA", components)
