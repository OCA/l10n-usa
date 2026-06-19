# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # The DOR vendor the remittance bill is raised against is NOT a company
    # field: it differs per state, so it lives on the per-state us.tax.authority.
    # us_tax_payable_account_id is defined on res.company by the engine (which
    # books collected tax to it); the remittance bill debits it to clear the
    # period. Defined upstream so the engine can post to it without depending
    # on this module.
    us_tax_allowance_account_id = fields.Many2one(
        "account.account",
        string="Collection Allowance Income Account",
        help="Income account the vendor collection allowance / timely-filing "
        "discount is credited to (the part of the tax the seller keeps).",
    )
    us_tax_remittance_journal_id = fields.Many2one(
        "account.journal",
        string="Remittance Journal",
        help="Purchase journal the remittance vendor bill is posted in.",
        domain="[('type', '=', 'purchase')]",
    )
