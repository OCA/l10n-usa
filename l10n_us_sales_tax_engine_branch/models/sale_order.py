# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "us.tax.origin.mixin"]

    def _prepare_invoice(self):
        """Rate the invoice with the same address as its order."""
        invoice_vals = super()._prepare_invoice()
        invoice_vals["us_tax_based_on_company"] = self.us_tax_based_on_company
        return invoice_vals

    def _get_invoice_grouping_keys(self):
        """Never merge orders rated with different addresses in one invoice."""
        return super()._get_invoice_grouping_keys() + ["us_tax_based_on_company"]
