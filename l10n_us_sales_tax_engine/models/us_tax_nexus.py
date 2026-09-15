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
    single_local_rate_elected = fields.Boolean(
        help="Remote seller has elected this state's single/simplified local "
        "rate in lieu of the actual local rate at each destination (e.g. the "
        "Texas single local use rate). Only for an interstate (remote) seller.",
    )
    single_local_mandatory = fields.Boolean(
        string="Single Local Rate Mandatory",
        help="The state's simplified rate applies to remote sellers without an "
        "election (e.g. Alabama Simplified Sellers Use Tax once enrolled).",
    )
    single_local_rate = fields.Float(
        digits=(7, 6),
        help="The simplified rate as a decimal (e.g. 0.0175 for Texas 1.75%); "
        "interpreted per the mode below.",
    )
    single_local_mode = fields.Selection(
        [
            ("add_on", "Added to the state rate"),
            ("combined", "Combined flat (replaces state + local)"),
        ],
        default="add_on",
        string="Single Local Rate Mode",
        help="Add-on: the rate is added to the state rate (Texas 6.25% + 1.75% "
        "= 8.00%). Combined flat: the rate replaces state + local entirely "
        "(e.g. Alabama SSUT 8%).",
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

    @api.model
    def _single_local_nexus(self, company_id, state_id):
        """The active nexus whose single/simplified local rate applies - elected
        or mandatory, with a non-zero rate - or an empty recordset."""
        return self.search(
            [
                ("company_id", "=", company_id),
                ("state_id", "=", state_id),
                ("active", "=", True),
                ("single_local_rate", "!=", 0),
                "|",
                ("single_local_rate_elected", "=", True),
                ("single_local_mandatory", "=", True),
            ],
            limit=1,
        )
