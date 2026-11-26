# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # us_tax_payable_account_id related is provided by the engine settings.
    us_tax_allowance_account_id = fields.Many2one(
        related="company_id.us_tax_allowance_account_id", readonly=False
    )
    us_tax_remittance_journal_id = fields.Many2one(
        related="company_id.us_tax_remittance_journal_id", readonly=False
    )
