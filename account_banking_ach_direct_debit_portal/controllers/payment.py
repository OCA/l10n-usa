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
from ..utils import get_invoice_due_status

_logger = logging.getLogger(__name__)


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
        "/select-payment-method",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def select_payment_method(self, **kw):
        invoice_ids = list(map(int, request.httprequest.args.getlist("invoice")))
        order_id = request.httprequest.args.get("order")
        invoices, order = self._get_documents(invoice_ids, order_id)

        if not invoices and not order:
            raise ValidationError(_("The provided parameters are invalid."))

        surcharge_percent = self._get_surcharge_percent()

        amounts = self._compute_amounts(
            invoices=invoices,
            order=order,
            surcharge_percent=surcharge_percent,
        )
        currency = amounts["currency"]
        ach_rule = amounts["ach_rule"]

        base_total_amount = currency.round(amounts["base_total_amount"])
        surcharge_amount = currency.round(amounts["surcharge_amount"])
        ach_discount_amount = currency.round(amounts["ach_discount_amount"])
        ach_charge_amount = currency.round(amounts["ach_charge_amount"])

        providers_sudo = (
            request.env["payment.provider"]
            .sudo()
            ._get_compatible_providers(
                request.env.company.id,
                request.env.user.partner_id.id,
                0,
                currency_id=currency.id,
                include_ach_bank_account=True,
                **kw,
            )
        )
        if not providers_sudo:
            return request.redirect("/my/payment_method")

        provider_note = {}

        for provider in providers_sudo:
            if invoices:
                if provider.code == "authorize":
                    provider_note[
                        provider.id
                    ] = f"{surcharge_percent:.4g}% Surcharge"  # noqa: E231
                elif provider.code == "ach_bank_account" and ach_rule:
                    if ach_rule.amount_type == "percent":
                        unit = "%"
                    else:
                        unit = currency.symbol

                    provider_note[
                        provider.id
                    ] = f"{ach_rule.amount:.4g}{unit} {ach_rule.discount_or_charge.capitalize()} (with plaid verification)"  # noqa: B950,E231

        selected_payment_option_id = kw.get(
            "selected_payment_option_id",
            providers_sudo[0].id if providers_sudo else None,
        )
        query_params = {"selected_payment_option_id": selected_payment_option_id}
        selected_provider = (
            providers_sudo.filtered(lambda p: p.id == int(selected_payment_option_id))
            if selected_payment_option_id
            else False
        )
        total_amount = base_total_amount
        if selected_provider:
            selected_payment_option_id = selected_provider.id
            query_params["selected_payment_option_id"] = selected_provider.id
            if selected_provider.code == "authorize":
                total_amount = currency.round(total_amount + surcharge_amount)
            elif selected_provider.code == "ach_bank_account":
                total_amount = currency.round(total_amount - ach_discount_amount)
                total_amount = currency.round(total_amount + ach_charge_amount)

        invoice_due_status_values = get_invoice_due_status(invoices)

        if invoices:
            query_params["invoice"] = [inv.id for inv in invoices]
            make_payment_url = "/make-payment/invoices?"

        if order:
            query_params["order"] = order.id
            make_payment_url = "/make-payment/order?"

        make_payment_url = make_payment_url + werkzeug.urls.url_encode(query_params)

        partner_banks = request.env["res.partner.bank"].search(
            [
                ("partner_id", "=", request.env.user.partner_id.id),
            ]
        )
        partner_bank_default = (
            partner_banks.filtered(lambda b: b.default)[:1] or partner_banks[:1]
        )

        partner_credit_cards = request.env["payment.token"].search(
            [
                ("partner_id", "=", request.env.user.partner_id.id),
                ("verified", "=", True),
                ("active", "=", True),
            ]
        )
        credit_card_default = (
            partner_credit_cards.filtered(lambda b: b.default)[:1]
            or partner_credit_cards[:1]
        )

        values = {
            "page_name": "select_payment_method",
            "selected_payment_option_id": selected_payment_option_id,
            "surcharge_percent": surcharge_percent,
            "invoices": invoices,
            "invoice_due_status_values": invoice_due_status_values,
            "order": order,
            "base_total_amount": base_total_amount,
            "total_amount": total_amount,
            "surcharge_amount": surcharge_amount,
            "ach_discount_amount": ach_discount_amount,
            "ach_charge_amount": ach_charge_amount,
            "display_currency": currency,
            "make_payment_url": make_payment_url,
            "selected_provider": selected_provider
            if selected_provider
            else providers_sudo[0],
            "providers": providers_sudo,
            "provider_note": provider_note,
            "invisible_button": not user_portal.is_ach_accessible(),
            "partner_banks": partner_banks,
            "partner_bank_default": partner_bank_default,
            "partner_credit_cards": partner_credit_cards,
            "credit_card_default": credit_card_default,
        }

        if ach_rule:
            if ach_rule.amount_type == "percent":
                values["plaid_discount_percent"] = ach_rule.amount
            else:
                values["plaid_discount"] = ach_rule.amount

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_select_payment_method",
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

        invoices = (
            request.env["account.move"]
            .sudo()
            .search(
                [
                    ("id", "in", invoice_ids),
                    *self._get_invoices_domain(),
                ]
            )
        )

        if not invoices:
            raise ValidationError(_("The provided parameters are invalid."))

        surcharge_percent = self._get_surcharge_percent()

        amounts = self._compute_amounts(
            invoices=invoices,
            order=False,
            surcharge_percent=surcharge_percent,
        )

        if float_is_zero(amounts["base_total_amount"], precision_digits=2):
            return request.render("payment.pay", {"amount": 0})

        selected_payment_option_id = kw.get("selected_payment_option_id", False)
        if not selected_payment_option_id:
            raise ValidationError(_("The provided parameters are invalid."))
        selected_provider = (
            request.env["payment.provider"]
            .sudo()
            .browse(int(selected_payment_option_id))
        )
        if not selected_provider:
            raise ValidationError(_("The provided parameters are invalid."))
        if selected_provider.code != "ach_bank_account":
            payment_token_id = (
                int(kw.get("partner_payment_token_id"))
                if kw.get("partner_payment_token_id")
                else False
            )

            return self._redirect_to_native_payment(
                invoices=invoices,
                order=False,
                amounts=amounts,
                provider=selected_provider,
                default_token_id=payment_token_id,
            )

        partner_bank_id = (
            int(kw.get("partner_bank_id")) if kw.get("partner_bank_id") else False
        )

        pay_date = fields.Date.context_today(request.env.user)

        for invoice in invoices:
            discount_amount = 0
            charge_amount = 0

            adj_amount, rule = invoice._compute_ach_adjustment(pay_date)

            if rule and rule.discount_or_charge == "discount":
                discount_amount = adj_amount
                pay_amount = invoice.amount_residual - discount_amount
            elif rule and rule.discount_or_charge == "charge":
                charge_amount = adj_amount
                pay_amount = invoice.amount_residual + charge_amount
            else:
                pay_amount = invoice.amount_residual

            payment_vals = invoice.prepare_payment_register_vals(partner_bank_id)
            if not payment_vals:
                return request.redirect("/my/invoices")

            payment_vals.update(
                {
                    "amount": invoice.currency_id.round(pay_amount),
                }
            )

            register_payment = (
                request.env["account.payment.register"]
                .with_context(active_model="account.move", active_ids=[invoice.id])
                .sudo()
                .create(payment_vals)
            )

            if rule and charge_amount > 0.0:
                invoice.add_charge_line(charge_amount, rule)

            is_success = register_payment.with_context(
                dont_redirect_to_payments=True,
            ).action_create_payments()

            if is_success:
                _logger.info(f"Create successful payment for invoice: '{invoice.name}'")

                request.session["payment_successful"] = True

                if rule and discount_amount > 0.0:
                    invoice.sudo()._create_discount_entry_and_reconcile(
                        discount_amount, rule
                    )
            else:
                _logger.info(f"Create failed payment for invoice: '{invoice.name}'")

                request.session["payment_failed"] = True

        return request.redirect("/my/payment-account")

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

        amounts = self._compute_amounts(
            invoices=False,
            order=order,
            surcharge_percent=surcharge_percent,
        )

        if float_is_zero(amounts["base_total_amount"], precision_digits=2):
            return request.render("payment.pay", {"amount": 0})

        selected_payment_option_id = kw.get("selected_payment_option_id", False)
        if not selected_payment_option_id:
            raise ValidationError(_("The provided parameters are invalid."))
        selected_provider = (
            request.env["payment.provider"]
            .sudo()
            .browse(int(selected_payment_option_id))
        )
        if not selected_provider:
            raise ValidationError(_("The provided parameters are invalid."))

        order_data = dict()

        account_payment_term_immediate = request.env.ref(
            "account.account_payment_term_immediate",
            raise_if_not_found=False,
        )

        if account_payment_term_immediate:
            order_data["payment_term_id"] = account_payment_term_immediate.id

        if selected_provider.code == "ach_bank_account":
            partner_bank_id = (
                int(kw.get("partner_bank_id")) if kw.get("partner_bank_id") else False
            )

            order_data["partner_bank_id"] = partner_bank_id

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

            request.session["payment_successful"] = True

            return request.redirect("/my/payment-account")

        payment_token_id = (
            int(kw.get("partner_payment_token_id"))
            if kw.get("partner_payment_token_id")
            else False
        )

        return self._redirect_to_native_payment(
            invoices=False,
            order=order,
            amounts=amounts,
            provider=selected_provider,
            default_token_id=payment_token_id,
        )

    def _redirect_to_native_payment(
        self, invoices, order, amounts, provider, default_token_id=None
    ):
        currency = amounts["currency"]
        total_amount = amounts["base_total_amount"]
        if (
            not float_is_zero(amounts["surcharge_amount"], precision_digits=2)
            and provider.code == "authorize"
        ):
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
            "provider_id": provider.id,
        }

        if default_token_id:
            params["default_token_id"] = default_token_id

        if invoices:
            params["invoice"] = [inv.id for inv in invoices]
        elif order:
            params["reference"] = order.display_name
            params["sale_order_id"] = order.id

        return request.redirect("/payment/pay?" + werkzeug.urls.url_encode(params))

    def _compute_amounts(self, invoices, order, surcharge_percent):
        base_total = 0.0
        surcharge_amount = 0.0
        ach_discount_amount = 0.0
        ach_charge_amount = 0.0
        display_currency = None
        ach_rule = None

        pay_date = fields.Date.context_today(request.env.user)

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

                adj_amount, rule = inv.sudo()._compute_ach_adjustment(pay_date)

                if rule:
                    ach_rule = rule

                    if rule.discount_or_charge == "discount":
                        ach_discount_amount += adj_amount
                    elif rule and rule.discount_or_charge == "charge":
                        ach_charge_amount += adj_amount

            display_currency = invoices[0].currency_id if invoices else None

        if order:
            base_total += order.amount_total
            display_currency = display_currency or order.currency_id

        currency = display_currency or request.env.user.company_id.currency_id

        return {
            "base_total_amount": base_total,
            "surcharge_amount": surcharge_amount,
            "ach_discount_amount": ach_discount_amount,
            "ach_charge_amount": ach_charge_amount,
            "currency": currency,
            "ach_rule": ach_rule,
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

    def _get_documents(self, invoice_ids, order_id):
        invoices = order = False
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
            order = request.env["sale.order"].search([("id", "=", order_id)])
            if not order:
                raise ValidationError(_("The provided parameters are invalid."))

        return invoices, order


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
                }
            )

            if references is not None and references[0]:
                rendering_context_values.update(
                    {
                        "reference_prefix": ", ".join(references),
                    }
                )

        default_token_id = kwargs.get("default_token_id", None)
        if default_token_id and default_token_id.isdigit():
            default_token_id = int(default_token_id)
        rendering_context_values.update(
            {
                "default_token_id": default_token_id,
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
