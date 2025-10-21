from odoo import fields, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..utils import get_date_5days_before_end_of_month
from .user_portal import UserPortalController as user_portal


class SettingsController(CustomerPortal):
    @http.route(
        ["/my/settings"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def ach_settings(self, **kw):
        if not user_portal.is_ach_accessible():
            return user_portal.deny_403()

        partner = request.env.user.partner_id

        bank_accounts = request.env["res.partner.bank"].search(
            [("partner_id", "=", partner.id)],
        )

        today = fields.Date.today()
        Invoice = request.env["account.move"].sudo()
        PaymentToken = request.env["payment.token"].sudo()

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

        credit_cards = PaymentToken.search(
            [
                ("partner_id", "=", partner.id),
                ("verified", "=", True),
                ("active", "=", True),
            ]
        )

        autopay_enable_specific_date = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_specific_date"
            )
        ) in ["1", "True", "true"]

        autopay_enable_on_due_date = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_on_due_date"
            )
        ) in ["1", "True", "true"]

        autopay_enable_end_of_month = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "account_banking_ach_direct_debit_portal.autopay_enable_end_of_month"
            )
        ) in ["1", "True", "true"]

        values = {
            "partner": partner,
            "bank_accounts": bank_accounts,
            "credit_cards": credit_cards,
            "next_due_date": next_due_date,
            "next_date_end_of_month": next_date_end_of_month,
            "autopay_enable_specific_date": autopay_enable_specific_date,
            "autopay_enable_on_due_date": autopay_enable_on_due_date,
            "autopay_enable_end_of_month": autopay_enable_end_of_month,
        }

        return request.render(
            "account_banking_ach_direct_debit_portal.ach_settings", values
        )
