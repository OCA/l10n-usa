# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_us_sales_tax_state_returns.services import (
    state_return_builder,
)


class UsTaxReturn(models.Model):
    _inherit = "us.tax.return"

    state = fields.Selection(
        selection_add=[("remitted", "Remitted")],
        ondelete={"remitted": "set default"},
    )
    move_id = fields.Many2one(
        "account.move",
        string="Remittance Bill",
        readonly=True,
        copy=False,
    )
    remitted_date = fields.Date(readonly=True, copy=False)
    authority_id = fields.Many2one(
        "us.tax.authority",
        compute="_compute_authority",
        string="State Tax Authority",
        help="Per-state DOR this return remits to (Settings > US Tax > Tax "
        "Authorities). Falls back to the company default when unset.",
    )
    collection_allowance = fields.Monetary(
        compute="_compute_collection_allowance",
        currency_field="currency_id",
        help="Vendor collection allowance / timely-filing discount kept by the "
        "seller. Credited to income on the remittance bill.",
    )
    net_tax_due = fields.Monetary(
        compute="_compute_collection_allowance",
        currency_field="currency_id",
        help="Tax remitted to the authority = total tax less the allowance.",
    )
    tax_collected_gl = fields.Monetary(
        compute="_compute_tie_out",
        currency_field="currency_id",
        help="Sales tax credited to the payable account in the period, per the "
        "general ledger (excludes this return's own remittance).",
    )
    tie_out_variance = fields.Monetary(
        compute="_compute_tie_out",
        currency_field="currency_id",
        help="Return total tax minus the GL-collected tax. Non-zero means the "
        "return does not reconcile with the payable account.",
    )

    @api.depends("company_id", "state_id")
    def _compute_authority(self):
        Authority = self.env["us.tax.authority"]
        for rec in self:
            rec.authority_id = Authority._get_for(rec.company_id, rec.state_id)

    @api.depends("total_tax", "state_id", "company_id")
    def _compute_collection_allowance(self):
        # The builder is the single source of truth: it prefers a configured
        # us.tax.authority, falls back to the per-state table, and clamps to the
        # tax. (Non-stored, so an authority-rate edit reflects on next read.)
        for rec in self:
            rec.collection_allowance = state_return_builder.collection_allowance(rec)
            rec.net_tax_due = rec.total_tax - rec.collection_allowance

    @api.depends("total_tax", "date_from", "date_to", "state_id", "move_id")
    def _compute_tie_out(self):
        for rec in self:
            if not rec.company_id.us_tax_payable_account_id or not rec.date_from:
                rec.tax_collected_gl = 0.0
                rec.tie_out_variance = 0.0
                continue
            lines = self.env["account.move.line"].search(
                rec._collected_tax_domain() + [("move_id", "!=", rec.move_id.id)]
            )
            # Collected = credits less any non-remittance debits (refunds).
            collected = sum(lines.mapped("credit")) - sum(lines.mapped("debit"))
            currency = rec.company_id.currency_id
            rec.tax_collected_gl = currency.round(collected)
            rec.tie_out_variance = currency.round(rec.total_tax - collected)

    def _collected_tax_domain(self):
        """Posted lines carrying *this state's* sales tax on the shared payable
        account, within the period. The us_tax_state_id tag is what lets one
        common account reconcile per state without per-state sub-accounts."""
        self.ensure_one()
        return [
            ("account_id", "=", self.company_id.us_tax_payable_account_id.id),
            ("parent_state", "=", "posted"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("us_tax_state_id", "=", self.state_id.id),
        ]

    def action_create_remittance(self):
        """Book the DOR remittance bill: clear the payable, credit the
        allowance to income, owe the net to the authority, reconcile."""
        self.ensure_one()
        # A still-live (posted) bill means it's already remitted; a cancelled
        # bill may be re-remitted (clear the stale link below).
        if self.move_id and self.move_id.state != "cancel":
            raise UserError(self.env._("This return is already remitted."))
        if self.state not in ("generated", "filed", "remitted"):
            raise UserError(
                self.env._("Generate (and file) the return before remitting.")
            )
        if self.company_id.currency_id.compare_amounts(self.total_tax, 0.0) <= 0:
            raise UserError(
                self.env._(
                    "Nothing to remit: the return total tax is %(amt)s. A "
                    "refund/credit period must be handled with a credit note.",
                    amt=self.total_tax,
                )
            )
        company = self.company_id
        # A per-state Tax Authority supplies the DOR vendor (the authority you
        # remit to differs by state, so there is no single company-wide vendor).
        authority = self.authority_id
        if not authority or not authority.partner_id:
            raise UserError(
                self.env._(
                    "No Sales Tax Authority with a DOR vendor is configured for "
                    "%s. Create a Sales Tax Authority for this state before "
                    "remitting.",
                    self.state_id.display_name,
                )
            )
        partner = authority.partner_id
        journal = authority.journal_id or company.us_tax_remittance_journal_id
        missing = [
            label
            for value, label in (
                (company.us_tax_payable_account_id, "Sales Tax Payable Account"),
                (journal, "Remittance Journal"),
            )
            if not value
        ]
        if missing:
            raise UserError(
                self.env._(
                    "Configure these in Settings > US Tax before remitting: %s.",
                    ", ".join(missing),
                )
            )

        period = f"{self.state_id.code} {self.date_from} - {self.date_to}"
        line_vals = [
            (
                0,
                0,
                {
                    "name": self.env._("Sales tax payable (%s)", period),
                    "account_id": company.us_tax_payable_account_id.id,
                    "quantity": 1,
                    "price_unit": self.total_tax,
                    "tax_ids": [(6, 0, [])],
                },
            )
        ]
        if self.collection_allowance and company.us_tax_allowance_account_id:
            line_vals.append(
                (
                    0,
                    0,
                    {
                        "name": self.env._("Collection allowance"),
                        "account_id": company.us_tax_allowance_account_id.id,
                        "quantity": 1,
                        "price_unit": -self.collection_allowance,
                        "tax_ids": [(6, 0, [])],
                    },
                )
            )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "journal_id": journal.id,
                "invoice_date": self.date_to,
                "ref": self.env._("Sales tax remittance %s", period),
                "invoice_line_ids": line_vals,
            }
        )
        bill.action_post()
        self.write(
            {
                "move_id": bill.id,
                "state": "remitted",
                "remitted_date": fields.Date.context_today(self),
            }
        )
        self._reconcile_payable(bill)
        return self.action_view_remittance()

    def _reconcile_payable(self, bill):
        """Reconcile the remittance debit on the payable account against the
        period's collected-tax credits, clearing the accrual. Only auto-
        reconcile when the return ties out to the ledger; a non-zero variance is
        a real discrepancy, so the bill is left for the user to reconcile (the
        tie_out_variance field flags it) rather than forcing a partial that
        strands a residual on the tax-payable account."""
        self.ensure_one()
        account = self.company_id.us_tax_payable_account_id
        if not account.reconcile:
            return
        if not self.company_id.currency_id.is_zero(self.tie_out_variance):
            return
        bill_lines = bill.line_ids.filtered(lambda line: line.account_id == account)
        credit_lines = self.env["account.move.line"].search(
            self._collected_tax_domain()
            + [("reconciled", "=", False), ("move_id", "!=", bill.id)]
        )
        to_reconcile = (bill_lines | credit_lines).filtered(
            lambda line: not line.reconciled
        )
        if len(to_reconcile) > 1:
            to_reconcile.reconcile()

    def action_view_remittance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }
