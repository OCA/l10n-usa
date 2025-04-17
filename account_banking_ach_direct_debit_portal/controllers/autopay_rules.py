import json
from datetime import date

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..controllers.user_portal import UserPortalController as user_portal


class AutoPayRulesController(CustomerPortal):
    @http.route(
        ["/autopay-rules"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def portal_autopay_rules(self, **kw):
        if not user_portal.is_ach_accessible():
            return user_portal.deny_403()

        if request.httprequest.method == "POST":
            autopay_rule = kw.get("autopay_rule")

            partner = request.env.user.partner_id
            partner.write({"autopay": autopay_rule})
            request.session["updated_autopay_rules"] = True
            return request.redirect("/autopay-rules")

        current_date = date.today().strftime("%-m-%-d-%Y")

        partner = request.env.user.partner_id

        bank_account_total = request.env["res.partner.bank"].search_count(
            [("partner_id", "=", partner.id)]
        )

        values = {
            "page_name": "autopay_rules",
            "current_date": current_date,
            "partner": partner,
            "bank_account_total": bank_account_total,
        }

        if request.session.get("updated_autopay_rules"):
            values["updated_autopay_rules"] = True
            request.session["updated_autopay_rules"] = False

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_autopay_rules", values
        )

    # Frontend route: Handles the selection of an autopay rule when a user makes a choice
    @http.route(
        "/autopay-rules/change", type="http", auth="user", methods=["POST"], csrf=False
    )
    def update_autopay(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
            autopay_value = data.get("autopay_rule")
        except Exception:
            return request.make_json_response({"error": "Invalid JSON"}, status=400)

        if autopay_value not in ["disabled", "end_of_month", "on_due_date"]:
            return request.make_json_response({"error": "Invalid value"}, status=400)

        partner = request.env.user.partner_id
        partner.write({"autopay": autopay_value})

        return request.make_json_response(
            {"status": "success", "autopay": autopay_value}
        )
