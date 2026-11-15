# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models

from ..levels import LEVEL_SELECTION


class AccountTax(models.Model):
    _inherit = "account.tax"

    us_tax_level = fields.Selection(
        LEVEL_SELECTION,
        string="US Tax Jurisdiction Level",
        index=True,
        help="Set on the per-jurisdiction child taxes booked by the US Sales "
        "Tax Engine. The combined parent (a group tax) leaves this empty; "
        "'combined' marks a single child booked when a provider returned only "
        "a total rate with no component breakdown.",
    )
    us_tax_state_id = fields.Many2one(
        "res.country.state",
        string="US Tax State",
        domain=[("country_id.code", "=", "US")],
        index=True,
        help="State this US Sales Tax component belongs to. Set on the "
        "per-jurisdiction child taxes so collected tax can be aggregated by "
        "state and jurisdiction level for return filing.",
    )
    us_tax_jurisdiction_id = fields.Many2one(
        "us.tax.jurisdiction",
        string="US Tax Jurisdiction",
        index=True,
        ondelete="set null",
        help="Named jurisdiction (when resolved by the local provider). API "
        "providers that only return rate components leave this empty; the "
        "level + state still allow state-return aggregation.",
    )
