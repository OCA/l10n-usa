# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["us.tax.line.hash.mixin", "sale.order.line"]

    def _us_tax_auto_parents(self):
        """Return the orders the lines in self belong to."""
        return self.order_id
