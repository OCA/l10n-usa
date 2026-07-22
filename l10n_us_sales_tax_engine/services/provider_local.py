# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from .provider_base import ProviderBase, ProviderError

_logger = logging.getLogger(__name__)


class ProviderLocal(ProviderBase):
    """Local database provider — no external calls."""

    CODE = "local"
    NAME = "Local Database"
    SUPPORTS_ADDRESS = False
    SUPPORTS_ZIP = True

    def validate_credentials(self) -> bool:
        # Local provider never needs credentials
        return True

    def get_rate(self, payload: dict) -> dict:
        zip_code = payload.get("zip", "").strip()
        state_code = payload.get("state", "").strip()
        date = payload.get("date")
        product_category_code = payload.get("product_category", "")
        confidence_min = float(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_us_tax.confidence_threshold", "0.7")
        )

        # Step 1: Resolve ZIP → jurisdiction
        ZipMapping = self.env["us.tax.zip.mapping"]
        jurisdiction = ZipMapping.get_best_jurisdiction(
            zip_code, state_code=state_code, confidence_min=confidence_min
        )
        if not jurisdiction:
            raise ProviderError(
                f"Local: no jurisdiction found for ZIP={zip_code}, "
                f"state={state_code} (confidence_min={confidence_min})"
            )

        # Step 2: Resolve product category ID
        category_id = False
        if product_category_code:
            cat = self.env["us.tax.product.category"].search(
                [("code", "=", product_category_code)], limit=1
            )
            category_id = cat.id if cat else False

        # Step 3: Get rate valid on document date
        rate = self.env["us.tax.rate"].get_rate_for_date(
            jurisdiction.id, date, product_category_id=category_id
        )
        if not rate:
            raise ProviderError(
                f"Local: no rate found for jurisdiction={jurisdiction.complete_name}, "
                f"date={date}, category={product_category_code}"
            )

        return self.normalize_response(
            {
                "state_rate": rate.state_rate,
                "county_rate": rate.county_rate,
                "city_rate": rate.city_rate,
                "district_rate": rate.district_rate,
                "total_rate": rate.total_rate,
                "source_date": str(rate.effective_date),
                "source": rate.source,
                "jurisdiction": jurisdiction.complete_name,
            }
        )

    def normalize_response(self, raw: dict) -> dict:
        return {
            "state_rate": raw.get("state_rate", 0.0),
            "county_rate": raw.get("county_rate", 0.0),
            "city_rate": raw.get("city_rate", 0.0),
            "district_rate": raw.get("district_rate", 0.0),
            "total_rate": raw.get("total_rate", 0.0),
            "source_date": raw.get("source_date"),
            "raw_response": raw,
        }
