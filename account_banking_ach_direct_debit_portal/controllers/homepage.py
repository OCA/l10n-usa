import calendar
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, fields, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..controllers.user_portal import UserPortalController as user_portal
from ..utils import get_invoice_due_status


class HomepageController(CustomerPortal):
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

    @staticmethod
    def _get_invoice_searchbar_sortings():
        return {
            "newest": {"label": _("Newest"), "order": "date desc"},
            "oldest": {"label": _("Oldest"), "order": "date"},
        }

    @staticmethod
    def _get_invoice_status_filters():
        return {
            "all": {"label": _("All"), "domain": []},
            "awaiting_payment": {
                "label": _("Awaiting payment"),
                "domain": [
                    ("state", "=", "posted"),
                    ("payment_state", "not in", ["in_payment", "paid", "reversed"]),
                ],
            },
            "paid": {
                "label": _("Paid"),
                "domain": [
                    ("state", "=", "posted"),
                    ("payment_state", "in", ["in_payment", "paid"]),
                ],
            },
            "reversed": {
                "label": _("Reversed"),
                "domain": [
                    ("state", "=", "posted"),
                    ("payment_state", "=", "reversed"),
                ],
            },
            "cancelled": {
                "label": _("Cancelled"),
                "domain": [
                    ("state", "=", "cancel"),
                ],
            },
        }

    def _prepare_homepage_layout_values(
        self, invoice_sortby=None, invoice_status=None, **kw
    ):
        values = self._prepare_portal_layout_values()

        invoice_searchbar_sortings = self._get_invoice_searchbar_sortings()
        invoice_status_filters = self._get_invoice_status_filters()

        if not invoice_sortby:
            invoice_sortby = "newest"

        if not invoice_status:
            invoice_status = "all"

        values.update(
            {
                "invoice_searchbar_sortings": invoice_searchbar_sortings,
                "invoice_status_filters": invoice_status_filters,
                "invoice_sortby": invoice_sortby,
                "invoice_status": invoice_status,
            }
        )

        return values

    def _get_next_autopay_date(self, partner, today=None):
        today = today or fields.Date.today()

        if partner.autopay == "disabled":
            return None

        if partner.autopay == "on_due_date":
            moves = partner.env["account.move"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    ("amount_residual", ">", 0),
                    ("invoice_date_due", ">=", today),
                ],
                order="invoice_date_due asc",
                limit=1,
            )
            return moves.invoice_date_due if moves else None

        if partner.autopay == "specific_date":
            start = partner.autopay_specific_date
            if not start:
                return None

            if start >= today:
                return start

            day = start.day
            next_month = today + relativedelta(months=1)
            last_day_next_month = calendar.monthrange(
                next_month.year, next_month.month
            )[1]
            safe_day = min(day, last_day_next_month)
            return date(next_month.year, next_month.month, safe_day)

    @http.route(["/my/payment-account"], type="http", auth="user", website=True)
    def payment_account(
        self, search="", invoice_sortby=None, invoice_status=None, **kw
    ):
        values = self._prepare_homepage_layout_values(invoice_sortby, invoice_status)

        partner = request.env.user.partner_id

        invoice_status_domain = (
            self._get_invoice_status_filters().get(invoice_status, {}).get("domain", [])
        )

        domain = [
            *self._get_invoices_domain(),
            ("partner_id", "=", partner.id),
            *invoice_status_domain,
        ]

        search = search.strip()

        if search:
            domain.append(
                ("name", "ilike", search),
            )

        invoices = request.env["account.move"].search(
            domain,
            order="date desc" if values["invoice_sortby"] == "newest" else "date",
            limit=5,
        )

        invoice_due_status_values = get_invoice_due_status(invoices)

        due_invoices = request.env["account.move"].search(
            [
                ("partner_id", "=", partner.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
            ]
        )

        amount_due = sum(due_invoices.mapped("amount_residual"))
        max_due_date = (
            max(due_invoices.mapped("invoice_date_due")) if due_invoices else None
        )

        credit_limit = partner.credit_limit or 0.0

        today = fields.Date.today()

        next_autopay_date = self._get_next_autopay_date(partner, today=today)

        upcoming_amount = 0.0
        if next_autopay_date:
            if partner.autopay == "on_due_date":
                invoices_to_pay = request.env["account.move"].search(
                    [
                        ("partner_id", "=", partner.id),
                        ("move_type", "=", "out_invoice"),
                        ("state", "=", "posted"),
                        ("amount_residual", ">", 0),
                        ("invoice_date_due", "=", next_autopay_date),
                    ]
                )
            else:
                invoices_to_pay = request.env["account.move"].search(
                    [
                        ("partner_id", "=", partner.id),
                        ("move_type", "=", "out_invoice"),
                        ("state", "=", "posted"),
                        ("amount_residual", ">", 0),
                        ("invoice_date_due", ">=", today),
                        ("invoice_date_due", "<=", next_autopay_date),
                    ]
                )

            upcoming_amount = sum(invoices_to_pay.mapped("amount_residual"))

        values.update(
            {
                "invoices": invoices,
                "invoice_due_status_values": invoice_due_status_values,
                "total_credit_limit": credit_limit,
                "available_credit": credit_limit - amount_due,
                "credit_limit": credit_limit,
                "display_currency": partner.currency_id,
                "amount_due": amount_due,
                "max_due_date": max_due_date,
                "invisible_button": not user_portal.is_ach_accessible(),
                "invoice_search": search or "",
                "upcoming_autopay_amount": upcoming_amount,
                "upcoming_autopay_date": next_autopay_date,
            }
        )

        if request.session.get("payment_successful"):
            values["payment_successful"] = True
            request.session["payment_successful"] = False

        if request.session.get("payment_failed"):
            values["payment_failed"] = True
            request.session["payment_failed"] = False

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_my_home", values
        )
