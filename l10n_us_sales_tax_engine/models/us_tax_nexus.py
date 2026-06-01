# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxNexus(models.Model):
    _name = "us.tax.nexus"
    _description = "US Tax Nexus Configuration"
    _check_company_auto = True
    _order = "company_id, state_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda s: s.env.company,
    )
    state_id = fields.Many2one(
        "res.country.state",
        required=True,
        domain=[("country_id.code", "=", "US")],
    )
    active = fields.Boolean(default=True)
    start_date = fields.Date(
        help="Date when economic nexus was established in this state.",
    )
    threshold_amount = fields.Float(
        help="Economic nexus threshold in USD (informational for MVP).",
    )
    threshold_transactions = fields.Integer(
        help="Transaction count threshold (informational for MVP).",
    )
    notes = fields.Text()

    _sql_constraints = [
        (
            "company_state_unique",
            "UNIQUE(company_id, state_id)",
            "A nexus record for this company and state already exists.",
        ),
    ]

    @api.model
    def has_nexus(self, company_id, state_id):
        """Check if a company has active nexus in a given state."""
        return bool(
            self.search(
                [
                    ("company_id", "=", company_id),
                    ("state_id", "=", state_id),
                ],
                limit=1,
            )
        )
