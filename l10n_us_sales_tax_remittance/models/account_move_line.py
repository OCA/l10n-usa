# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    us_tax_state_id = fields.Many2one(
        "res.country.state",
        string="US Tax State",
        compute="_compute_us_tax_state_id",
        inverse="_inverse_us_tax_state_id",
        store=True,
        index=True,
        readonly=False,
        help="State whose sales tax this line carries. Auto-filled from the "
        "line's tax on customer invoices; this tag lets collected tax accrue to "
        "one shared payable account yet reconcile per state - no per-state "
        "sub-accounts.",
    )

    @api.depends("tax_line_id.us_tax_state_id")
    def _compute_us_tax_state_id(self):
        for line in self:
            # Fill from the tax when the line carries one; never clobber an
            # explicit tag (e.g. on adjustment entries).
            line.us_tax_state_id = (
                line.tax_line_id.us_tax_state_id or line.us_tax_state_id
            )

    def _inverse_us_tax_state_id(self):
        # Stored directly by the ORM; the compute preserves explicit values.
        pass
