from odoo import _, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..controllers.user_portal import UserPortalController as user_portal


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

    def _get_invoice_searchbar_sortings(self):
        return {
            "newest": {"label": _("Newest"), "order": "date desc"},
            "oldest": {"label": _("Oldest"), "order": "date"},
        }

    def _get_payment_searchbar_sortings(self):
        return {
            "newest": {"label": _("Newest"), "order": "date desc"},
            "oldest": {"label": _("Oldest"), "order": "date"},
        }

    def _prepare_homepage_layout_values(
        self, invoice_sortby=None, payment_sortby=None, **kw
    ):
        values = self._prepare_portal_layout_values()

        invoice_searchbar_sortings = self._get_invoice_searchbar_sortings()
        payment_searchbar_sortings = self._get_payment_searchbar_sortings()

        if not invoice_sortby:
            invoice_sortby = "newest"

        if not payment_sortby:
            payment_sortby = "newest"

        values.update(
            {
                "invoice_searchbar_sortings": invoice_searchbar_sortings,
                "payment_searchbar_sortings": payment_searchbar_sortings,
                "invoice_sortby": invoice_sortby,
                "payment_sortby": payment_sortby,
            }
        )

        return values

    @http.route(["/my", "/my/home"], type="http", auth="user", website=True)
    def home(self, invoice_sortby=None, payment_sortby=None, **kw):
        values = self._prepare_homepage_layout_values(invoice_sortby, payment_sortby)

        partner = request.env.user.partner_id

        invoices = request.env["account.move"].search(
            [*self._get_invoices_domain(), ("partner_id", "=", partner.id)],
            order="date desc" if values["payment_sortby"] == "newest" else "date",
            limit=5,
        )

        payments = request.env["account.payment"].search(
            [("partner_id", "=", partner.id)],
            order="invoice_date desc"
            if values["payment_sortby"] == "newest"
            else "invoice_date",
            limit=5,
        )

        due_invoices = request.env["account.move"].search(
            [
                ("partner_id", "=", partner.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
            ]
        )

        amount_due = sum(due_invoices.mapped("amount_residual"))

        credit_limit = partner.credit_limit or 0.0

        values.update(
            {
                "invoices": invoices,
                "total_credit_limit": credit_limit,
                "available_credit": credit_limit - amount_due,
                "display_currency": partner.currency_id,
                "payments": payments,
                "amount_due": amount_due,
                "invisible_button": not user_portal.is_ach_accessible(),
            }
        )

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_my_home", values
        )
