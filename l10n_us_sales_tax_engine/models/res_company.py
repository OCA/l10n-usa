# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_payable_account_id = fields.Many2one(
        "account.account",
        string="Sales Tax Payable Account",
        domain="[('account_type', '=', 'liability_current')]",
        help="Liability account collected US sales tax accrues to, so it can "
        "be reconciled and remitted. Left empty, the engine reuses whatever "
        "account the chart of accounts already books sales tax to.",
    )

    def _us_tax_account_from_chart(self):
        """The account this company's chart already books sales tax to.

        Charts ship a tax account (``251000`` in the generic chart) and their
        taxes point at it. Creating a second liability alongside it would split
        the sales-tax balance across two accounts for no reason, so look there
        first and only fall back to creating one when a company has no sale tax
        configured at all.
        """
        self.ensure_one()

        def _tax_account(tax):
            lines = tax.invoice_repartition_line_ids.filtered(
                lambda r: r.repartition_type == "tax" and r.account_id
            )
            return lines[:1].account_id

        default_tax = self.account_sale_tax_id
        if default_tax:
            account = _tax_account(default_tax)
            if account:
                return account

        for tax in (
            self.env["account.tax"]
            .sudo()
            .search([("company_id", "=", self.id), ("type_tax_use", "=", "sale")])
        ):
            account = _tax_account(tax)
            if account:
                return account
        return self.env["account.account"]

    def get_us_tax_payable_account(self):
        """The account collected US sales tax books to.

        Explicit configuration wins; otherwise reuse the chart's own tax
        account. Only a company with no sale tax at all gets a new account,
        and the resolved choice is written back to the setting so it is
        visible and overridable rather than implicit.
        """
        self.ensure_one()
        if self.us_tax_payable_account_id:
            return self.us_tax_payable_account_id

        account = self._us_tax_account_from_chart()
        if not account:
            Account = self.env["account.account"].sudo().with_company(self)
            account = Account.search(
                [
                    ("account_type", "=", "liability_current"),
                    ("name", "=", "US Sales Tax Payable"),
                    ("company_ids", "in", self.id),
                ],
                limit=1,
            )
        if not account:
            existing = set(
                self.env["account.account"]
                .sudo()
                .with_company(self)
                .search([("company_ids", "in", self.id)])
                .mapped("code")
            )
            code = 251100
            while str(code) in existing:
                code += 1
            account = (
                self.env["account.account"]
                .sudo()
                .with_company(self)
                .create(
                    {
                        "name": "US Sales Tax Payable",
                        "code": str(code),
                        "account_type": "liability_current",
                        "company_ids": [(4, self.id)],
                    }
                )
            )
            _logger.info(
                "US Tax: no sale tax account found for %s; created %s (%s).",
                self.display_name,
                account.code,
                account.name,
            )
        self.sudo().us_tax_payable_account_id = account
        return account
