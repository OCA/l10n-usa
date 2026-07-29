# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""SST-aware local provider.

Resolves an address to its FIPS jurisdiction set (SST boundary file), reads
each jurisdiction's own rate, and returns a per-jurisdiction component list the
engine books one tax line each from — plus rolled-up level scalars for any
consumer that still expects the state/county/city/district split. Falls back to
the engine's single-jurisdiction ZIP-mapping provider when no SST boundary data
covers the address (e.g. a non-member state).
"""

import logging

from odoo import fields

from odoo.addons.l10n_us_sales_tax_engine.levels import level_to_rate_field
from odoo.addons.l10n_us_sales_tax_engine.services.provider_local import (
    ProviderLocal,
)

from .sst_common import FOOD_DRUG_CATEGORIES
from .sst_resolver import SstResolver

_logger = logging.getLogger(__name__)


class ProviderLocalSst(ProviderLocal):
    NAME = "Local Database (SST)"

    def get_rate(self, payload: dict) -> dict:
        zip5 = payload.get("zip", "").strip()
        state_code = payload.get("state", "").strip()
        date_str = payload.get("date")
        doc_date = fields.Date.to_date(date_str) if date_str else fields.Date.today()
        product_category = payload.get("product_category", "")

        state = self.env["res.country.state"].search(
            [("code", "=", state_code), ("country_id.code", "=", "US")], limit=1
        )
        if not state:
            return self._fallback(payload, f"no US state for {state_code!r}")

        jurisdictions = SstResolver(self.env).resolve(
            state,
            zip5,
            doc_date,
            zip4=payload.get("zip4"),
            house_number=payload.get("house_number"),
        )
        if not jurisdictions:
            # No SST coverage for this address — defer to the engine's ZIP path.
            return self._fallback(
                payload,
                f"no SST boundary coverage for ZIP {zip5}/{state_code}",
            )

        use_food_drug = product_category in FOOD_DRUG_CATEGORIES
        Rate = self.env["us.tax.rate"]
        scalars = {
            "state_rate": 0.0,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": 0.0,
        }
        jur_list = []
        total = 0.0
        for jur in jurisdictions:
            rate = Rate.get_rate_for_date(jur.id, doc_date, product_category_id=None)
            if not rate:
                continue
            value = rate.total_rate
            if use_food_drug and rate.food_drug_rate:
                value = rate.food_drug_rate
            if value <= 0:
                continue
            scalars[level_to_rate_field(jur.type)] += value
            total += value
            jur_list.append(
                {
                    "jurisdiction_id": jur.id,
                    "fips": jur.fips_place or jur.fips_county or jur.fips_state or "",
                    "level": jur.type,
                    "rate": value,
                    "label": jur.name,
                }
            )

        if not jur_list:
            return self._fallback(
                payload,
                f"resolved jurisdictions have no SST rate for {state_code}",
            )

        result = dict(scalars)
        result.update(
            {
                "total_rate": round(total, 6),
                "jurisdictions": jur_list,
                "source_date": str(doc_date),
                "raw_response": {
                    "jurisdictions": [j["label"] for j in jur_list],
                    "source": "sst",
                },
            }
        )
        return result

    def _fallback(self, payload, reason):
        """Defer to the engine ZIP-mapping provider, logged and flagged.

        Silent substitution hides coverage gaps, so every fallback is logged and
        the returned rate is tagged so callers/audit can see it was not resolved
        from SST data. Falling back is an expected hybrid-provider path (non-member
        states, partial coverage), so it logs at info — the ``fallback`` flag on
        the result is the durable audit signal.
        """
        _logger.info("SST local provider falling back to ZIP mapping: %s", reason)
        result = super().get_rate(payload)
        if isinstance(result, dict):
            result["fallback"] = True
            result["fallback_reason"] = reason
        return result
