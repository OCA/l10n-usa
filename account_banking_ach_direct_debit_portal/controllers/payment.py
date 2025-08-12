import copy
import logging

import werkzeug.urls

from odoo import _, fields, http
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.http import request
from odoo.tools import float_is_zero

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..controllers.user_portal import UserPortalController as user_portal

_logger = logging.getLogger(__name__)


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
        invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        order_id = request.httprequest.args.get("order")

        if not invoice_ids and not order_id:
            raise ValidationError(_("The provided parameters are invalid."))

        invoices = False
        order = False
        if invoice_ids:
            invoices = request.env["account.move"].search(
                [
                    ("id", "in", invoice_ids),
                    *self._get_invoices_domain(),
                ]
            )

            if not invoices:
                raise ValidationError(_("The provided parameters are invalid."))

        if order_id:
            order = request.env["sale.order"].search(
                [
                    ("id", "=", order_id),
                ]
            )
            if not order:
                raise ValidationError(_("The provided parameters are invalid."))

        surcharge_percent = self._get_surcharge_percent()
        discount_percent = self._get_plaid_discount_percent()

        amounts = self._compute_amounts(
            invoices=invoices,
            order=order,
            surcharge_percent=surcharge_percent,
            discount_percent=discount_percent,
        )
        currency = amounts["currency"]

        base_total_amount = currency.round(amounts["base_total_amount"])
        surcharge_amount = currency.round(amounts["surcharge_amount"])
        discount_amount = currency.round(amounts["discount_amount"])

        selected_payment_method = kw.get("payment_method") or "bank_account"

        total_amount = base_total_amount
        if selected_payment_method == "credit_card":
            total_amount = currency.round(total_amount + surcharge_amount)
        else:
            total_amount = currency.round(total_amount - discount_amount)

        query_params = {"payment_method": selected_payment_method}
        if invoices:
            query_params["invoice"] = [inv.id for inv in invoices]
        if order:
            query_params["order"] = order.id

        make_payment_url = "/select-payment-method?" + werkzeug.urls.url_encode(
            query_params
        )

        if request.params.get("action") == "make_payment":
            make_payment_url = "/payment-confirmation?" + werkzeug.urls.url_encode(
                query_params
            )
            return request.redirect(make_payment_url)

        earliest_due_date = None
        if invoices:
            dues = [d for d in invoices.mapped("invoice_date_due") if d]
            earliest_due_date = min(dues) if dues else None

        payment_methods = copy.deepcopy(PAYMENT_METHODS)

        payment_methods[0].update(
            {
                "checked": selected_payment_method == "bank_account",
                "note": f"{discount_percent:.4g}% Discount "  # noqa: E231
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
            "selected_payment_method": selected_payment_method,
            "surcharge_percent": surcharge_percent
            if selected_payment_method == "credit_card"
            else 0.0,
            "plaid_discount_percent": discount_percent
            if selected_payment_method == "bank_account"
            else 0.0,
            "invoices": invoices,
            "order": order,
            "earliest_due_date": earliest_due_date,
            "base_total_amount": base_total_amount,
            "total_amount": total_amount,
            "surcharge_amount": surcharge_amount,
            "discount_amount": discount_amount,
            "display_currency": currency,
            "make_payment_url": make_payment_url,
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
        invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        order_id = request.httprequest.args.get("order")

        if not invoice_ids and not order_id:
            raise ValidationError(_("The provided parameters are invalid."))

        selected_payment_method = kw.get("payment_method") or "bank_account"

        invoices = False
        order = False

        if invoice_ids:
            invoices = request.env["account.move"].search(
                [
                    ("id", "in", invoice_ids),
                    *self._get_invoices_domain(),
                ]
            )

            if not invoices:
                raise ValidationError(_("The provided parameters are invalid."))

        if order_id:
            order = request.env["sale.order"].search(
                [
                    ("id", "=", order_id),
                ]
            )

            if not order:
                raise ValidationError(_("The provided parameters are invalid."))

        surcharge_percent = self._get_surcharge_percent()
        discount_percent = self._get_plaid_discount_percent()

        amounts = self._compute_amounts(
            invoices=invoices,
            order=order,
            surcharge_percent=surcharge_percent,
            discount_percent=discount_percent,
        )
        currency = amounts["currency"]

        base_total_amount = currency.round(amounts["base_total_amount"])
        surcharge_amount = currency.round(amounts["surcharge_amount"])
        discount_amount = currency.round(amounts["discount_amount"])

        total_amount = base_total_amount
        if selected_payment_method == "credit_card":
            total_amount = currency.round(total_amount + surcharge_amount)
        else:
            total_amount = currency.round(total_amount - discount_amount)

        next_params = {"payment_method": selected_payment_method}
        if invoices:
            next_params["invoice"] = [inv.id for inv in invoices]
            make_payment_url = "/make-payment/invoices?" + werkzeug.urls.url_encode(
                next_params
            )
        else:
            next_params["order"] = order.id
            make_payment_url = "/make-payment/order?" + werkzeug.urls.url_encode(
                next_params
            )

        partner_banks = request.env["res.partner.bank"].search(
            [
                ("partner_id", "=", request.env.user.partner_id.id),
            ]
        )
        partner_bank_default = partner_banks.filtered(lambda b: b.default)[:1]

        if selected_payment_method == "bank_account" and not partner_bank_default:
            return request.redirect("/no-bank")

        earliest_due_date = None
        if invoices:
            dues = [d for d in invoices.mapped("invoice_date_due") if d]
            earliest_due_date = min(dues) if dues else None

        values = {
            "page_name": "payment_confirmation",
            "payment_method": selected_payment_method,
            "invoices": invoices or request.env["account.move"],
            "order": order or request.env["sale.order"],
            "earliest_due_date": earliest_due_date,
            "base_total_amount": base_total_amount,
            "total_amount": total_amount,
            "surcharge_amount": surcharge_amount,
            "discount_amount": discount_amount,
            "display_currency": currency,
            "make_payment_url": make_payment_url,
            "partner_banks": partner_banks,
            "partner_bank": partner_bank_default,
            "show_select_bank": len(partner_banks) > 1,
        }
        return request.render(
            "account_banking_ach_direct_debit_portal.portal_payment_confirmation",
            values,
        )

    @http.route(
        "/make-payment/invoices",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def pay_invoices(self, **kw):
        invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))

        if not invoice_ids:
            raise ValidationError(_("No invoice ids provided."))

        invoices = request.env["account.move"].search(
            [
                ("id", "in", invoice_ids),
                *self._get_invoices_domain(),
            ]
        )

        if not invoices:
            raise ValidationError(_("The provided parameters are invalid."))

        surcharge_percent = self._get_surcharge_percent()
        discount_percent = self._get_plaid_discount_percent()
        amounts = self._compute_amounts(
            invoices=invoices,
            order=False,
            surcharge_percent=surcharge_percent,
            discount_percent=discount_percent,
        )

        if float_is_zero(amounts["base_total_amount"], precision_digits=2):
            return request.render("payment.pay", {"amount": 0})

        payment_method = kw.get("payment_method", "bank_account")
        if payment_method == "credit_card":
            return self._redirect_credit_card(
                invoices=invoices, order=False, amounts=amounts
            )

        partner_bank_id = (
            int(kw.get("partner_bank_id")) if kw.get("partner_bank_id") else False
        )

        if discount_percent > 0.0 and amounts["discount_amount"] > 0.0:
            self._distribute_discount_amount(
                invoices.sudo(), amounts["discount_amount"], discount_percent
            )
        for invoice in invoices:
            payment_vals = invoice.prepare_payment_register_vals(partner_bank_id)
            if not payment_vals:
                return request.redirect("/my/invoices")

            register_payment = (
                request.env["account.payment.register"]
                .with_context(active_model="account.move", active_ids=[invoice.id])
                .sudo()
                .create(payment_vals)
            )

            is_success = register_payment.with_context(
                dont_redirect_to_payments=True,
                force_partner_bank_id=partner_bank_id,
            ).action_create_payments()
            if is_success:
                _logger.info(f"Create successful payment for invoice: '{invoice.name}'")
            else:
                _logger.info(f"Create failed payment for invoice: '{invoice.name}'")

        return request.redirect("/payment-success")

    @http.route(
        "/make-payment/order",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def pay_order(self, **kw):
        order_id = request.params.get("order")
        if not order_id:
            raise ValidationError(_("No order id provided."))
        order_id = int(order_id)

        order = (
            request.env["sale.order"]
            .sudo()
            .search(
                [
                    ("id", "=", order_id),
                ],
                limit=1,
            )
        )
        if not order:
            raise ValidationError(_("The provided parameters are invalid."))

        surcharge_percent = self._get_surcharge_percent()
        discount_percent = self._get_plaid_discount_percent()
        amounts = self._compute_amounts(
            invoices=False,
            order=order,
            surcharge_percent=surcharge_percent,
            discount_percent=discount_percent,
        )

        if float_is_zero(amounts["base_total_amount"], precision_digits=2):
            return request.render("payment.pay", {"amount": 0})

        payment_method = kw.get("payment_method", "bank_account")
        if payment_method == "credit_card":
            return self._redirect_credit_card(
                invoices=False, order=order, amounts=amounts
            )
        else:
            partner_bank_id = (
                int(kw.get("partner_bank_id")) if kw.get("partner_bank_id") else False
            )

            order_data = {
                "partner_bank_id": partner_bank_id,
            }

            journal = (
                request.env["account.journal"]
                .sudo()
                .search(
                    [
                        ("type", "=", "bank"),
                    ],
                    limit=1,
                )
            )

            if journal:
                order_data["payment_method_id"] = (journal.id,)

            ach_method = request.env.ref(
                "account_banking_ach_direct_debit.ach_direct_debit",
                raise_if_not_found=False,
            )

            if ach_method:
                payment_mode = (
                    request.env["account.payment.mode"]
                    .sudo()
                    .search([("payment_method_id", "=", ach_method.id)], limit=1)
                )

                order_data["payment_mode_id"] = payment_mode if payment_mode else None

            order.write(order_data)
            order.action_confirm()
            return request.redirect("/payment-success")

    def _redirect_credit_card(self, invoices, order, amounts):
        currency = amounts["currency"]
        total_amount = amounts["base_total_amount"]
        if not float_is_zero(amounts["surcharge_amount"], precision_digits=2):
            total_amount += amounts["surcharge_amount"]

        if invoices:
            partner_id = request.env.user.partner_id.id
        else:
            partner_id = order.partner_invoice_id.id

        access_token = payment_utils.generate_access_token(
            partner_id, currency.round(total_amount), currency.id
        )

        params = {
            "amount": currency.round(total_amount),
            "access_token": access_token,
            "surcharge_amount": currency.round(amounts["surcharge_amount"]),
            "base_total_amount": currency.round(amounts["base_total_amount"]),
            "partner_id": partner_id,
            "currency_id": currency.id,
        }
        if invoices:
            params["invoice"] = [inv.id for inv in invoices]
        elif order:
            params["reference"] = order.display_name
            params["sale_order_id"] = order.id

        return request.redirect("/payment/pay?" + werkzeug.urls.url_encode(params))

    def _compute_amounts(self, invoices, order, surcharge_percent, discount_percent):
        base_total = 0.0
        surcharge_amount = 0.0
        discount_amount = 0.0
        display_currency = None

        if invoices:
            for inv in invoices:
                if float_is_zero(inv.amount_residual, precision_digits=2):
                    continue
                residual = (
                    -inv.amount_residual
                    if inv.move_type == "out_refund"
                    else inv.amount_residual
                )
                base_total += residual
                surcharge_amount += residual * surcharge_percent / 100.0
                discount_amount += residual * discount_percent / 100.0
            display_currency = invoices[0].currency_id if invoices else None

        if order:
            base_total += order.amount_total
            surcharge_amount += order.amount_total * surcharge_percent / 100.0
            discount_amount += order.amount_total * discount_percent / 100.0
            display_currency = display_currency or order.currency_id

        currency = display_currency or request.env.user.company_id.currency_id
        return {
            "base_total_amount": base_total,
            "surcharge_amount": surcharge_amount,
            "discount_amount": discount_amount,
            "currency": currency,
        }

    @http.route(
        "/no-bank",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def no_bank(self, **kw):
        if not user_portal.is_ach_accessible():
            return user_portal.deny_403()

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_no_bank_account"
        )

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

    def _distribute_discount_amount(
        self, invoices_sudo, total_discount_amount, discount_percent
    ):
        if not invoices_sudo or total_discount_amount <= 0:
            return

        # Calculate base amounts for each invoice
        invoice_amounts = []
        total_base_amount = 0.0

        for invoice in invoices_sudo:
            amount_residual = (
                -invoice.amount_residual
                if invoice.move_type == "out_refund"
                else invoice.amount_residual
            )
            invoice_amounts.append(amount_residual)
            total_base_amount += amount_residual

        # Distribute discount proportionally
        distributed_amount = 0.0
        currency = invoices_sudo[0].currency_id

        for i, invoice in enumerate(invoices_sudo):
            if i == len(invoices_sudo) - 1:
                # Last invoice gets the remainder to ensure total matches exactly
                invoice_discount = total_discount_amount - distributed_amount
            else:
                # Calculate proportional amount
                if total_base_amount > 0:
                    proportion = invoice_amounts[i] / total_base_amount
                    invoice_discount = currency.round(
                        total_discount_amount * proportion
                    )
                else:
                    invoice_discount = 0.0

            if invoice_discount > 0:
                invoice.add_discount_line(discount_percent, invoice_discount)

            distributed_amount += invoice_discount


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
        self,
        *args,
        invoices=None,
        surcharge_amount=None,
        custom_create_values=None,
        **kwargs,
    ):
        if invoices:
            if custom_create_values is None:
                custom_create_values = {}
            custom_create_values["invoice_ids"] = [Command.set(invoices)]
            surcharge_amount = self._cast_as_float(surcharge_amount) or 0.0
            surcharge_percent = self._get_surcharge_percent()
            if surcharge_percent > 0.0 and surcharge_amount > 0.0:
                invoices_sudo = request.env["account.move"].sudo().browse(invoices)
                self._distribute_surcharge_amount(
                    invoices_sudo, surcharge_amount, surcharge_percent
                )
        return super()._create_transaction(
            *args, custom_create_values=custom_create_values, **kwargs
        )

    def _distribute_surcharge_amount(
        self, invoices_sudo, total_surcharge_amount, surcharge_percent
    ):
        if not invoices_sudo or total_surcharge_amount <= 0:
            return

        # Calculate base amounts for each invoice
        invoice_amounts = []
        total_base_amount = 0.0

        for invoice in invoices_sudo:
            amount_residual = (
                -invoice.amount_residual
                if invoice.move_type == "out_refund"
                else invoice.amount_residual
            )
            invoice_amounts.append(amount_residual)
            total_base_amount += amount_residual

        # Distribute surcharge proportionally
        distributed_amount = 0.0
        currency = invoices_sudo[0].currency_id

        for i, invoice in enumerate(invoices_sudo):
            if i == len(invoices_sudo) - 1:
                # Last invoice gets the remainder to ensure total matches exactly
                invoice_surcharge = total_surcharge_amount - distributed_amount
            else:
                # Calculate proportional amount
                if total_base_amount > 0:
                    proportion = invoice_amounts[i] / total_base_amount
                    invoice_surcharge = currency.round(
                        total_surcharge_amount * proportion
                    )
                else:
                    invoice_surcharge = 0.0

            if invoice_surcharge > 0:
                invoice.add_surcharge_line(surcharge_percent, invoice_surcharge)

            distributed_amount += invoice_surcharge
