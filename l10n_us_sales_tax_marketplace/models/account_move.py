# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    us_tax_marketplace_id = fields.Many2one(
        "us.tax.marketplace",
        string="Marketplace Facilitator",
        copy=False,
        help="Set when this invoice is collected and remitted by a marketplace "
        "facilitator — the engine then does not collect US sales tax.",
    )
