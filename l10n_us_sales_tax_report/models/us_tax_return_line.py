# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models

from odoo.addons.l10n_us_sales_tax_engine.levels import LEVEL_SELECTION


class UsTaxReturnLine(models.Model):
    _name = "us.tax.return.line"
    _description = "US Sales Tax Return Line (per jurisdiction)"
    _order = "sequence, id"

    return_id = fields.Many2one(
        "us.tax.return",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="return_id.company_id", store=True)
    currency_id = fields.Many2one(related="return_id.currency_id")
    state_id = fields.Many2one(related="return_id.state_id", store=True)
    sequence = fields.Integer(default=10)
    level = fields.Selection(LEVEL_SELECTION, required=True)
    jurisdiction_id = fields.Many2one(
        "us.tax.jurisdiction",
        string="Jurisdiction",
        help="Named jurisdiction, when the tax was resolved by the local "
        "provider. Empty for rates sourced from an API that only returns the "
        "level breakdown.",
    )
    taxable_base = fields.Monetary(currency_field="currency_id")
    tax_amount = fields.Monetary(currency_field="currency_id")
