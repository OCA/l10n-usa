import copy

import werkzeug.urls

from odoo import _, fields, http
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.http import request
from odoo.tools import float_repr

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..controllers.user_portal import UserPortalController as user_portal

PAYMENT_METHODS = [
    {
        "id": "1",
        "value": "bank_account",
        "label": "Bank account",
        "note": "1% Discount (with plaid verification)",
        "checked": False,
        "image": None,
    },
    {
        "id": "2",
        "value": "credit_card",
        "label": "Credit card",
        "note": "",
        "checked": False,
        "image": "/account_banking_ach_direct_debit_portal/static/src/img/credit_card.png",
    },
]


class PaymentController(CustomerPortal):
    def _get_invoices_domain(self):
        return [
            ("state", "not in", ("cancel", "draft")),
            (
                "move_type",
                "in",
                (
                    "out_invoice",
                    "out_refund",
                    "in_invoice",
                    "in_refund",
                    "out_receipt",
                    "in_receipt",
                ),
            ),
        ]

    @http.route(
        ["/my/payments", "/my/payments/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_payments(
        self, page=1, sortby=None, filterby=None, search="", search_in="all", **kw
    ):
        if not user_portal.is_ach_accessible():
            return user_portal.deny_403()

        ScheduledPayment = request.env["account.payment"]

        searchbar_inputs = {
            "all": {"label": _("All"), "input": "all"},
            "partner": {"label": _("Amount"), "input": "amount_total"},
        }

        # -- Filters
        filter_options = {
            "all": {"label": _("All"), "domain": []},
            "future": {
                "label": _("Upcoming"),
                "domain": [("scheduled_date", ">=", fields.Date.today())],
            },
            "past": {
                "label": _("Past"),
                "domain": [("scheduled_date", "<", fields.Date.today())],
            },
        }

        domain = []

        if filterby in filter_options:
            domain += filter_options[filterby]["domain"]
        else:
            filterby = "all"

        # -- Search
        if search:
            if search_in == "partner":
                domain += [("contact_bank_id.bank_name", "ilike", search)]
            else:
                domain += [
                    "|",
                    ("name", "ilike", search),
                    ("contact_bank_id.bank_name", "ilike", search),
                ]

        # -- Count & pager
        total = ScheduledPayment.search_count(domain)
        pager = portal_pager(
            url="/my/payments",
            total=total,
            page=page,
            step=20,
            url_args={"sortby": sortby, "filterby": filterby, "search": search},
        )

        payments = ScheduledPayment.search(
            domain, order="invoice_date desc", offset=pager["offset"], limit=20
        )

        values = {
            "payments": payments,
            "page_name": "schedule_payment",
            "pager": pager,
            "default_url": "/my/payments",
            "searchbar_filters": filter_options,
            "sortby": sortby,
            "filterby": filterby,
            "search": search,
            "search_in": search_in,
            "searchbar_inputs": searchbar_inputs,
        }

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_scheduled_payments", values
        )

    @http.route(
        "/payment",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def payment(self, **kw):
        try:
            invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        except Exception:
            return request.redirect("/my/invoices")

        invoices = request.env["account.move"].search(
            [
                ("id", "in", invoice_ids),
                *self._get_invoices_domain(),
            ]
        )

        if len(invoices) == 0:
            return request.redirect("/my/invoices")

        earliest_due_date = (
            min(invoices.mapped("invoice_date_due")) if invoices else None
        )

        total_amount = sum(
            -inv.amount_residual
            if inv.move_type == "out_refund"
            else inv.amount_residual
            for inv in invoices
        )

        display_currency = invoices[0].currency_id if invoices else None

        select_payment_url = "/select-payment-method?" + "&".join(
            f"invoice={invoice_id}" for invoice_id in invoice_ids
        )

        values = {
            "page_name": "payment",
            "invoices": invoices,
            "quantity": len(invoices),
            "earliest_due_date": earliest_due_date,
            "total_amount": total_amount,
            "display_currency": display_currency,
            "select_payment_url": select_payment_url,
            "invisible_button": not user_portal.is_ach_accessible(),
        }

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_payment", values
        )

    @http.route(
        "/select-payment-method",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def select_payment_method(self, **kw):
        try:
            invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        except Exception:
            return request.redirect("/my/invoices")

        invoices = request.env["account.move"].search(
            [
                ("id", "in", invoice_ids),
                *self._get_invoices_domain(),
            ]
        )

        if not invoices:
            raise ValidationError(_("The provided parameters are invalid."))

        earliest_due_date = (
            min(invoices.mapped("invoice_date_due")) if invoices else None
        )

        base_total_amount = sum(
            -inv.amount_residual
            if inv.move_type == "out_refund"
            else inv.amount_residual
            for inv in invoices
        )

        display_currency = invoices[0].currency_id if invoices else None

        selected_payment_method = kw.get("payment_method") or "bank_account"
        query_params = {
            "invoice": invoice_ids,
            "payment_method": selected_payment_method,
        }
        make_payment_url = "/select-payment-method?" + werkzeug.urls.url_encode(
            query_params
        )

        surcharge_percent = self._get_surcharge_percent()
        surcharge_amount = 0.0

        plaid_discount_percent = self._get_plaid_discount_percent()
        discount_amount = 0.0

        company = request.env.user.partner_id.company_id
        currency = display_currency or company.currency_id
        total_amount = base_total_amount

        if selected_payment_method == "credit_card":
            surcharge_amount = currency.round(
                base_total_amount * surcharge_percent / 100
            )
            total_amount += surcharge_amount
        elif selected_payment_method == "bank_account":
            discount_amount = currency.round(
                base_total_amount * plaid_discount_percent / 100
            )
            total_amount -= discount_amount

        total_amount_format = float_repr(
            total_amount, precision_digits=currency.decimal_places
        )
        total_amount = float(total_amount_format)

        if request.params.get("action") == "make_payment":
            make_payment_url = "/payment-confirmation?" + werkzeug.urls.url_encode(
                query_params
            )
            return request.redirect(make_payment_url)

        payment_methods = copy.deepcopy(PAYMENT_METHODS)

        payment_methods[0].update(
            {
                "checked": selected_payment_method == "bank_account",
                "note": f"{plaid_discount_percent:.4g}% Discount "  # noqa: E231
                "(with plaid verification)"
                if surcharge_percent
                else "",
            }
        )
        payment_methods[1].update(
            {
                "checked": selected_payment_method == "credit_card",
                "note": f"{surcharge_percent:.4g}% Surcharge"  # noqa: E231
                if surcharge_percent
                else "",
            }
        )

        values = {
            "page_name": "select_payment_method",
            "invoices": invoices,
            "earliest_due_date": earliest_due_date,
            "base_total_amount": base_total_amount,
            "total_amount": total_amount,
            "display_currency": display_currency,
            "make_payment_url": make_payment_url,
            "surcharge_percent": (
                surcharge_percent if selected_payment_method == "credit_card" else 0.0
            ),
            "surcharge_amount": surcharge_amount,
            "plaid_discount_percent": (
                plaid_discount_percent
                if selected_payment_method == "bank_account"
                else 0.0
            ),
            "discount_amount": discount_amount,
            "selected_payment_method": selected_payment_method,
            "payment_methods": payment_methods,
            "invisible_button": not user_portal.is_ach_accessible(),
        }

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_select_payment_method",
            values,
        )

    @http.route(
        "/payment-confirmation",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def payment_confirmation(self, **kw):
        try:
            invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        except Exception:
            return request.redirect("/my/invoices")

        invoices = request.env["account.move"].search(
            [
                ("id", "in", invoice_ids),
                *self._get_invoices_domain(),
            ]
        )

        if not invoices:
            raise ValidationError(_("The provided parameters are invalid."))

        payment_method = request.httprequest.args.get("payment_method", "bank_account")

        make_payment_url = "/make-payment?" + "&".join(
            f"invoice={invoice_id}" for invoice_id in invoice_ids
        )

        make_payment_url += f"&payment_method={payment_method}"

        earliest_due_date = (
            min(invoices.mapped("invoice_date_due")) if invoices else None
        )

        total_due = sum(invoices.mapped("amount_residual"))

        total_amount = sum(
            -inv.amount_residual
            if inv.move_type == "out_refund"
            else inv.amount_residual
            for inv in invoices
        )

        company = request.env.user.partner_id.company_id
        display_currency = invoices[0].currency_id if invoices else None
        currency = display_currency or company.currency_id

        surcharge_amount = 0.0
        if payment_method == "credit_card":
            surcharge_percent = self._get_surcharge_percent()
            surcharge_amount = currency.round(total_amount * surcharge_percent / 100)
            total_amount += surcharge_amount

        discount_amount = 0
        if payment_method == "bank_account":
            plaid_discount_percent = self._get_plaid_discount_percent()
            discount_amount = display_currency.round(
                total_amount * plaid_discount_percent / 100
            )
            total_amount -= discount_amount

        partner_banks = request.env["res.partner.bank"].search(
            [
                ("partner_id", "=", request.env.user.partner_id.id),
            ]
        )

        partner_bank_default = partner_banks.filtered(lambda b: b.default)[:1]

        values = {
            "page_name": "payment_confirmation",
            "make_payment_url": make_payment_url,
            "invoices": invoices,
            "total_due": total_due,
            "earliest_due_date": earliest_due_date,
            "surcharge_amount": surcharge_amount,
            "discount_amount": discount_amount,
            "payment_method": payment_method,
            "total_amount": total_amount,
            "partner_banks": partner_banks,
            "partner_bank": partner_bank_default,
            "show_select_bank": len(partner_banks) > 1,
            "display_currency": display_currency,
        }

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_payment_confirmation",
            values,
        )

    @http.route(
        "/make-payment",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def make_payment(self, **kw):
        try:
            invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        except Exception:
            return request.redirect("/my/invoices")

        invoices = request.env["account.move"].search(
            [
                ("id", "in", invoice_ids),
                *self._get_invoices_domain(),
            ]
        )

        if not invoices:
            raise ValidationError(_("The provided parameters are invalid."))

        payment_method = kw.get("payment_method", "bank_account")

        if payment_method == "credit_card":
            display_currency = invoices[0].currency_id if invoices else None
            company = request.env.user.partner_id.company_id
            currency = display_currency or company.currency_id
            partner_id = request.env.user.partner_id.id
            currency_id = currency.id

            base_total_amount = sum(
                -inv.amount_residual
                if inv.move_type == "out_refund"
                else inv.amount_residual
                for inv in invoices
            )

            total_amount = base_total_amount

            surcharge_percent = self._get_surcharge_percent()
            surcharge_amount = 0.0

            if surcharge_percent:
                surcharge_amount = currency.round(
                    base_total_amount * surcharge_percent / 100
                )
                total_amount += surcharge_amount

            access_token = payment_utils.generate_access_token(
                partner_id, total_amount, currency_id
            )

            query_params = {
                "amount": total_amount,
                "access_token": access_token,
                "surcharge_amount": surcharge_amount,
                "base_total_amount": base_total_amount,
                "partner_id": partner_id,
                "currency_id": currency_id,
                "invoice": invoice_ids,
            }
            return request.redirect(
                "/payment/pay?" + werkzeug.urls.url_encode(query_params)
            )

        partner_bank_id = kw.get("partner_bank_id")

        plaid_discount_percent = self._get_plaid_discount_percent()

        payments_vals = request.env["account.payment"].make_payment_values(
            invoices, plaid_discount_percent, partner_bank_id
        )

        if payments_vals:
            payment = request.env["account.payment"].sudo().create(payments_vals)
            payment.action_post()
        else:
            return request.redirect("/my/invoices")

        return request.redirect("/payment-success")

    @http.route(
        "/payment-success",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def payment_success(self, **kw):
        if not user_portal.is_ach_accessible():
            return user_portal.deny_403()

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_payment_success"
        )

    def _get_surcharge_percent(self):
        surcharge_parameter = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.credit_card_surcharge")
        )
        return self._cast_as_float(surcharge_parameter) if surcharge_parameter else 0.0

    def _get_plaid_discount_percent(self):
        plaid_discount = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("account_banking_ach_direct_debit_portal.plaid_discount")
        )
        return self._cast_as_float(plaid_discount) if plaid_discount else 0.0


class PaymentPortal(payment_portal.PaymentPortal):
    @http.route()
    def payment_pay(self, *args, **kwargs):
        try:
            invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        except Exception:
            invoice_ids = []
        if invoice_ids:
            invoice_sudo = (
                request.env["account.move"].sudo().browse(invoice_ids).exists()
            )
            if not invoice_sudo:
                raise ValidationError(_("The provided parameters are invalid."))
            kwargs.update(
                {
                    "invoices": invoice_sudo.ids,
                }
            )
        return super().payment_pay(*args, **kwargs)

    def _get_custom_rendering_context_values(self, invoices=None, **kwargs):
        rendering_context_values = super()._get_custom_rendering_context_values(
            invoices=invoices, **kwargs
        )
        if invoices:
            rendering_context_values["invoices"] = invoices
            invoice_sudo = request.env["account.move"].sudo().browse(invoices)
            if not invoice_sudo:
                return rendering_context_values
            references = invoice_sudo.mapped("payment_reference")
            base_total_amount, surcharge_amount = tuple(
                map(
                    self._cast_as_float,
                    (
                        kwargs.get("base_total_amount", 0.0),
                        kwargs.get("surcharge_amount", 0.0),
                    ),
                )
            )
            rendering_context_values.update(
                {
                    "surcharge_amount": surcharge_amount,
                    "base_total_amount": base_total_amount,
                    "reference_prefix": ", ".join(references),
                }
            )
        return rendering_context_values

    def _create_transaction(
        self, *args, invoices=None, custom_create_values=None, **kwargs
    ):
        if invoices:
            if custom_create_values is None:
                custom_create_values = {}
            custom_create_values["invoice_ids"] = [Command.set(invoices)]
        return super()._create_transaction(
            *args, custom_create_values=custom_create_values, **kwargs
        )
