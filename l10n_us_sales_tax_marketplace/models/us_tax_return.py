# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxReturn(models.Model):
    _inherit = "us.tax.return"

    marketplace_sales = fields.Monetary(
        readonly=True,
        currency_field="currency_id",
        help="Of the period's sales, the portion collected & remitted by a "
        "marketplace facilitator (informational; already part of gross sales and "
        "of the non-taxable deductions). Some states report it on its own line.",
    )

    def _marketplace_sales(self):
        """Sales shipped to this state in the period that a marketplace
        facilitator collected for (the marketplace-only slice of gross sales)."""
        return self._sum_sales_shipped_to_state(
            [("us_tax_marketplace_id", "!=", False)]
        )

    def action_generate(self):
        res = super().action_generate()
        for rec in self:
            rec.marketplace_sales = rec.currency_id.round(rec._marketplace_sales())
        return res
