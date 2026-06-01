# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class UsTaxController(http.Controller):
    @http.route("/api/v1/us_tax/calculate", type="json", auth="user", methods=["POST"])
    def calculate(self, **kwargs):
        """Calculate US sales tax for given parameters.

        Body:
            zip (str): 5-digit ZIP code
            state (str): 2-letter state code
            amount (float): taxable amount
            product_category (str): TANGIBLE | SERVICE | FOOD | ...
            date (str): YYYY-MM-DD (optional, defaults to today)
        """
        try:
            from ..services.address_resolver import normalize_zip  # noqa: PLC0415
            from ..services.cache_manager import CacheManager  # noqa: PLC0415

            body = request.get_json_data() or {}
            zip_code = body.get("zip", kwargs.get("zip", "")).strip()
            state_code = body.get("state", kwargs.get("state", "")).strip()
            amount = float(body.get("amount", kwargs.get("amount", 0)))
            category = body.get(
                "product_category", kwargs.get("product_category", "TANGIBLE")
            )
            calc_date = (
                body.get("date") or kwargs.get("date") or str(fields.Date.today())
            )

            if not zip_code:
                return {"error": "zip is required"}

            ICP = request.env["ir.config_parameter"].sudo()
            engine = request.env["us.tax.engine.service"]
            address = {
                "zip": normalize_zip(zip_code),
                "state": state_code,
                "city": body.get("city", kwargs.get("city", "")),
                "country_code": "US",
                "address": f"{zip_code} {state_code}",
            }
            ttl = int(ICP.get_param("l10n_us_tax.cache_ttl_hours", "720"))
            cache = CacheManager(request.env, ttl_hours=ttl)
            mode = ICP.get_param("l10n_us_tax.engine_mode", "hybrid")
            fail = ICP.get_param("l10n_us_tax.fail_policy", "warn")

            rates = engine._get_rate(
                zip_code=normalize_zip(zip_code),
                state_code=state_code,
                state_id=False,
                product_category_code=category,
                product_category_id=False,
                doc_date=calc_date,
                address=address,
                cache=cache,
                engine_mode=mode,
                fail_policy=fail,
            )
            tax_amount = round(amount * rates["total_rate"], 4)
            return {
                "zip": zip_code,
                "state": state_code,
                "category": category,
                "total_rate": rates["total_rate"],
                "state_rate": rates.get("state_rate", 0),
                "county_rate": rates.get("county_rate", 0),
                "city_rate": rates.get("city_rate", 0),
                "district_rate": rates.get("district_rate", 0),
                "taxable_amount": amount,
                "tax_amount": tax_amount,
                "source": rates.get("source", "unknown"),
            }
        except Exception as exc:
            _logger.error("US Tax REST calculate error: %s", exc)
            return {"error": str(exc)}

    @http.route(
        "/api/v1/us_tax/rate_lookup", type="json", auth="user", methods=["GET", "POST"]
    )
    def rate_lookup(self, **kwargs):
        """Diagnostic: look up rate for a ZIP/state/date from local DB only.

        Sudo on the model calls below: any logged-in user may call this
        diagnostic endpoint (auth="user" is the access boundary), they do
        not need the us_tax_user group that gates the configuration menus.
        """
        try:
            from ..services.address_resolver import normalize_zip  # noqa: PLC0415

            body = request.get_json_data() or {}
            zip_code = body.get("zip", kwargs.get("zip", "")).strip()
            state_code = body.get("state", kwargs.get("state", "")).strip()
            calc_date = body.get("date", str(fields.Date.today()))

            zip_norm = normalize_zip(zip_code)
            mapping = (
                request.env["us.tax.zip.mapping"]
                .sudo()
                .get_best_jurisdiction(zip_norm, state_code=state_code)
            )
            if not mapping:
                return {
                    "zip": zip_code,
                    "state": state_code,
                    "found": False,
                    "message": "No local jurisdiction mapping found.",
                }

            rate = (
                request.env["us.tax.rate"]
                .sudo()
                .get_rate_for_date(mapping.id, calc_date)
            )
            if not rate:
                return {
                    "zip": zip_code,
                    "state": state_code,
                    "found": False,
                    "jurisdiction": mapping.complete_name,
                    "message": "Jurisdiction found but no rate for this date.",
                }

            return {
                "zip": zip_code,
                "state": state_code,
                "jurisdiction": mapping.complete_name,
                "total_rate": rate.total_rate,
                "state_rate": rate.state_rate,
                "county_rate": rate.county_rate,
                "effective_date": str(rate.effective_date),
                "source": rate.source,
                "found": True,
            }
        except Exception as exc:
            return {"error": str(exc)}
