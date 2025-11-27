# Copyright 2025 Binhex.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    billcom_item_id = fields.Many2one(
        "billcom.item",
        string="Bill.com Item",
        help="Bill.com item (SALES_TAX) mapped to this tax for synchronization",
        ondelete="set null",
        copy=False,
    )
