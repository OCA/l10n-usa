# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxAuthority(models.Model):
    _name = "us.tax.authority"
    _description = "US Sales Tax Authority (State DOR)"
    _order = "state_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    state_id = fields.Many2one(
        "res.country.state",
        string="State",
        required=True,
        domain="[('country_id.code', '=', 'US')]",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Tax Authority (DOR)",
        required=True,
        help="Vendor the sales-tax remittance bill is raised against for this "
        "state's returns.",
    )
    state_registration_id = fields.Char(
        string="State Registration / Account No.",
        help="The seller's sales-tax account number with this state's revenue "
        "department, for the remittance reference.",
    )
    allowance_rate = fields.Float(
        string="Collection Allowance %",
        digits=(5, 4),
        help="Vendor collection allowance / timely-filing discount rate this "
        "state grants (e.g. 0.025 for Florida's 2.5%). 0 falls back to the "
        "built-in per-state default.",
    )
    allowance_cap = fields.Monetary(
        help="Maximum allowance per return. 0 = no cap.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Remittance Journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        help="Purchase journal for this state's remittance bill. Falls back to "
        "the company default when empty.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "company_state_uniq",
            "unique(company_id, state_id)",
            "A tax authority is already configured for this state and company.",
        )
    ]

    @api.constrains("allowance_rate")
    def _check_allowance_rate(self):
        for rec in self:
            if not 0.0 <= rec.allowance_rate <= 1.0:
                raise ValidationError(
                    self.env._(
                        "Collection Allowance %% must be between 0 and 1 "
                        "(e.g. 0.025 for 2.5%%), got %(rate)s.",
                        rate=rec.allowance_rate,
                    )
                )

    @api.depends("state_id.code", "partner_id.name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = " - ".join(
                filter(None, [rec.state_id.code, rec.partner_id.name])
            )

    @api.model
    def _get_for(self, company, state):
        """The active authority for a (company, state), or an empty recordset."""
        if not state:
            return self.browse()
        return self.search(
            [("company_id", "=", company.id), ("state_id", "=", state.id)],
            limit=1,
        )

    def collection_allowance(self, tax_amount):
        """This state's configured allowance on a tax amount."""
        self.ensure_one()
        amount = tax_amount * self.allowance_rate
        if self.allowance_cap:
            amount = min(amount, self.allowance_cap)
        return self.company_id.currency_id.round(amount)
