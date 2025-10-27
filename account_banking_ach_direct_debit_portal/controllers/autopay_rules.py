from datetime import date

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..controllers.user_portal import UserPortalController as user_portal


class AutoPayRulesController(CustomerPortal):
    def send_autopay_enrollment_mail(self, partner):
        template_id = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enrollment_template_id"
            )
        )

        if template_id:
            template = request.env["mail.template"].sudo().browse(int(template_id))

            if template and template.active:
                autopay_label = dict(partner._fields["autopay"].selection).get(
                    partner.autopay
                )

                template.with_context(autopay_name=autopay_label).send_mail(
                    partner.id, force_send=True
                )

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
            autopay_enabled = kw.get("autopay_enabled") == "1"
            autopay_rule = kw.get("autopay_rule")

            if autopay_enabled:
                autopay_value = autopay_rule
            else:
                autopay_value = "disabled"

            partner = request.env.user.partner_id
            partner.write({"autopay": autopay_value})

            if autopay_value != "disabled":
                self.send_autopay_enrollment_mail(partner)

            request.session["updated_autopay_rules"] = True
            return request.redirect("/autopay-rules")

        current_date = date.today().strftime("%-m-%-d-%Y")

        partner = request.env.user.partner_id

        bank_account_total = request.env["res.partner.bank"].search_count(
            [("partner_id", "=", partner.id)]
        )

        autopay_enable_end_of_month = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_end_of_month"
            )
        ) in ["1", "True", "true"]

        autopay_enable_on_due_date = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_on_due_date"
            )
        ) in ["1", "True", "true"]

        values = {
            "page_name": "autopay_rules",
            "current_date": current_date,
            "partner": partner,
            "bank_account_total": bank_account_total,
            "autopay_enable_end_of_month": autopay_enable_end_of_month,
            "autopay_enable_on_due_date": autopay_enable_on_due_date,
        }

        if request.session.get("updated_autopay_rules"):
            values["updated_autopay_rules"] = True
            request.session["updated_autopay_rules"] = False

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_autopay_rules", values
        )
