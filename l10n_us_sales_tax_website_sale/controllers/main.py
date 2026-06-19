# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleUsTax(WebsiteSale):
    def _get_shop_payment_values(self, order, **kwargs):
        # Refresh before the payment page renders (ship-to is known by now).
        order._us_tax_recompute_if_needed()
        return super()._get_shop_payment_values(order, **kwargs)

    @route(
        "/shop/checkout",
        type="http",
        methods=["GET"],
        auth="public",
        website=True,
        sitemap=False,
    )
    def shop_checkout(self, try_skip_step=None, **kw):
        # The review page shows totals right after the address is entered.
        order = request.website.sale_get_order()
        if order:
            order._us_tax_recompute_if_needed()
        return super().shop_checkout(try_skip_step=try_skip_step, **kw)
