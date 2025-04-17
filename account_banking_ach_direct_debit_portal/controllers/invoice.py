from collections import OrderedDict

from odoo import _, http
from odoo.http import request
from odoo.osv import expression

from odoo.addons.account.controllers.portal import PortalAccount
from odoo.addons.portal.controllers.portal import pager as portal_pager

from ..controllers.user_portal import UserPortalController as user_portal


class InvoiceController(PortalAccount):
    def _get_status_searchbar_filters(self):
        return {
            "all": {"label": _("All"), "domain": []},
            "paid": {
                "label": _("Paid"),
                "domain": [
                    ("state", "=", "posted"),
                    ("payment_state", "in", ("paid", "in_payment")),
                ],
            },
            "waiting": {
                "label": _("Unpaid"),
                "domain": [
                    ("state", "=", "posted"),
                    ("payment_state", "not in", ("in_payment", "paid", "reversed")),
                ],
            },
        }

    def _prepare_my_invoices_values(
        self,
        page,
        date_begin,
        date_end,
        sortby,
        filterby,
        status_filterby,
        domain=None,
        url="/my/invoices",
    ):
        values = self._prepare_portal_layout_values()
        AccountInvoice = request.env["account.move"]

        domain = expression.AND(
            [
                domain or [],
                self._get_invoices_domain(),
            ]
        )

        searchbar_sortings = self._get_account_searchbar_sortings()
        # default sort by order
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]

        searchbar_filters = self._get_account_searchbar_filters()
        # default filter by value
        if not filterby:
            filterby = "all"
        domain += searchbar_filters[filterby]["domain"]

        status_searchbar_filters = self._get_status_searchbar_filters()
        # default status filter by value
        if not status_filterby:
            status_filterby = "all"
        domain += status_searchbar_filters[status_filterby]["domain"]

        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]

        values.update(
            {
                "date": date_begin,
                # content according to pager and archive selected
                # lambda function to get the invoices recordset
                # when the pager will be defined in the main method of a route
                "invoices": lambda pager_offset: (
                    AccountInvoice.search(
                        domain,
                        order=order,
                        limit=self._items_per_page,
                        offset=pager_offset,
                    )
                    if AccountInvoice.check_access_rights("read", raise_exception=False)
                    else AccountInvoice
                ),
                "page_name": "invoice",
                "pager": {  # vals to define the pager.
                    "url": url,
                    "url_args": {
                        "date_begin": date_begin,
                        "date_end": date_end,
                        "sortby": sortby,
                    },
                    "total": AccountInvoice.search_count(domain)
                    if AccountInvoice.check_access_rights("read", raise_exception=False)
                    else 0,
                    "page": page,
                    "step": self._items_per_page,
                },
                "default_url": url,
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
                "searchbar_filters": OrderedDict(sorted(searchbar_filters.items())),
                "filterby": filterby,
                "status_searchbar_filters": OrderedDict(
                    sorted(status_searchbar_filters.items())
                ),
                "status_filterby": status_filterby,
            }
        )
        return values

    @http.route(
        ["/my/invoices", "/my/invoices/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_invoices(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        status_filterby=None,
        search="",
        search_in="all",
        **kw
    ):
        searchbar_inputs = {
            "all": {"label": _("All"), "input": "all"},
            "name": {"label": _("Invoice"), "input": "name"},
            "partner": {"label": _("Partner"), "input": "partner_id"},
        }

        partner = request.env.user.partner_id

        domain = [("partner_id", "=", partner.id)]
        if search:
            if search_in == "name":
                domain += [("name", "ilike", search)]
            elif search_in == "partner":
                domain += [("partner_id.name", "ilike", search)]
            else:
                domain += [
                    "|",
                    ("name", "ilike", search),
                    ("partner_id.name", "ilike", search),
                ]

        values = self._prepare_my_invoices_values(
            page, date_begin, date_end, sortby, filterby, status_filterby, domain
        )

        # pager
        pager = portal_pager(**values["pager"])

        # content according to pager and archive selected
        invoices = values["invoices"](pager["offset"])
        request.session["my_invoices_history"] = invoices.ids[:100]

        values.update(
            {
                "invoices": invoices,
                "pager": pager,
                "search": search,
                "search_in": search_in,
                "searchbar_inputs": searchbar_inputs,
                "invisible_button": not user_portal.is_ach_accessible(),
            }
        )

        values.pop("searchbar_sortings")

        return request.render(
            "account_banking_ach_direct_debit_portal.portal_custom_my_invoices", values
        )
