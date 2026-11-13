# Copyright 2026 Binhex - Edilio Escalona Almira.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "us.tax.origin.mixin"]

    def _us_tax_origin_applicable(self):
        """Only customer invoices and credit notes are rated by origin."""
        self.ensure_one()
        return self.is_sale_document()
