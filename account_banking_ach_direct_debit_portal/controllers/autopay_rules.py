from datetime import date

from odoo import fields, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..controllers.user_portal import UserPortalController as user_portal
from ..utils import get_date_5days_before_end_of_month


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
        methods=["GET"],
    )
    def portal_autopay_rules(self, **kw):
        if not user_portal.is_ach_accessible():
            return user_portal.deny_403()

        current_date = date.today().strftime("%-m-%-d-%Y")

        partner = request.env.user.partner_id

        bank_accounts = request.env["res.partner.bank"].search(
            [("partner_id", "=", partner.id)],
        )

        autopay_enable_specific_date = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_specific_date"
            )
        ) in ["1", "True", "true"]

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

        today = fields.Date.today()
        Invoice = request.env["account.move"].sudo()

        domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("partner_id", "=", partner.id),
            ("amount_residual", ">", 0),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("invoice_date_due", ">=", today),
        ]

        next_due_invoice = Invoice.search(domain, order="invoice_date_due asc", limit=1)
        next_due_date = next_due_invoice.invoice_date_due if next_due_invoice else False

        next_date_end_of_month = get_date_5days_before_end_of_month(today)

        values = {
            "page_name": "autopay_rules",
            "current_date": current_date,
            "partner": partner,
            "autopay_enable_specific_date": autopay_enable_specific_date,
            "autopay_enable_end_of_month": autopay_enable_end_of_month,
            "autopay_enable_on_due_date": autopay_enable_on_due_date,
            "bank_accounts": bank_accounts,
            "next_due_date": next_due_date,
            "next_date_end_of_month": next_date_end_of_month,
        }

        if request.session.get("updated_autopay_rules"):
            values["updated_autopay_rules"] = True
            request.session["updated_autopay_rules"] = False

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_autopay_rules", values
        )

    @http.route(
        "/autopay-rules/change", type="http", auth="user", methods=["POST"], csrf=False
    )
    def update_autopay(self, **kwargs):
        return_url = kwargs.get("return_url")
        bank_id = kwargs.get("bank_id")
        autopay_specific_date = kwargs.get("autopay_specific_date", None)
        autopay_value = kwargs.get("autopay_value")

        if autopay_value not in [
            "disabled",
            "end_of_month",
            "on_due_date",
            "specific_date",
        ]:
            return request.make_json_response({"error": "Invalid value"}, status=400)

        partner = request.env.user.partner_id

        values = {"autopay": autopay_value}

        if bank_id and bank_id.isdigit():
            bank = request.env["res.partner.bank"].browse(int(bank_id))

            if bank:
                values["autopay_method"] = bank

        if autopay_value == "specific_date" and autopay_specific_date:
            try:
                date_val = fields.Date.to_date(autopay_specific_date)
            except Exception:
                return request.make_json_response({"error": "Invalid date"}, status=400)

            values["autopay_specific_date"] = date_val

        old_autopay_value = partner.autopay

        partner.write(values)

        if autopay_value != "disabled" and old_autopay_value != autopay_value:
            self.send_autopay_enrollment_mail(partner)

        return request.redirect(return_url)
