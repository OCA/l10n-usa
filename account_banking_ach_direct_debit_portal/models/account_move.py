import logging

from odoo import Command, _, fields, models
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def prepare_payment_register_vals(self, partner_bank_id=None):
        self.ensure_one()
        bank_journal = (
            self.env["account.journal"]
            .sudo()
            .search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("type", "=", "bank"),
                ],
                limit=1,
            )
        )

        payment_method_line = bank_journal._get_available_payment_method_lines(
            "inbound"
        ).filtered(lambda l: l.code == "ACH-In")
        if not payment_method_line:
            return {}

        vals = {
            "group_payment": False,
            "journal_id": bank_journal.id,
            "payment_method_line_id": payment_method_line.id,
        }
        if partner_bank_id:
            vals["partner_bank_id"] = partner_bank_id

        return vals

    def add_surcharge_line(self, surcharge_percent, surcharge_amount=None):
        self.ensure_one()
        surcharge_account = self._get_surcharge_account()
        if not surcharge_account:
            return

        # Use provided amount or calculate from percent
        if surcharge_amount is None:
            surcharge_amount = self.currency_id.round(
                self.amount_residual * surcharge_percent / 100
            )

        if float_is_zero(
            surcharge_amount, precision_rounding=self.currency_id.rounding
        ):
            return

        self.write(
            {
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": _(
                                "%.4g%% Credit Card Surcharge" % surcharge_percent
                            ),
                            "quantity": 1,
                            "price_unit": surcharge_amount,
                            "account_id": surcharge_account.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ]
            }
        )

    def _get_discount_account(self):
        self.ensure_one()
        return (
            self.env.company.discount_account_id
            or self.company_id._get_default_surcharge_discount_account()
        )

    def _get_surcharge_account(self):
        self.ensure_one()
        return (
            self.env.company.surcharge_account_id
            or self.company_id._get_default_surcharge_discount_account()
        )

    def _get_discount_journal(self):
        self.ensure_one()
        return (
            self.env.company.discount_journal_id
            or self.company_id._get_default_discount_journal()
        )

    def _create_discount_entry_and_reconcile(self, discount_amount, discount_percent):
        self.ensure_one()
        if discount_amount <= 0:
            return
        discount_account = self._get_discount_account()
        if not discount_account:
            _logger.warning(
                "No discount account found, cannot record discount journal entry."
            )
            return

        misc_journal = self._get_discount_journal()
        if not misc_journal:
            _logger.warning("No general journal found to record discount.")
            return

        receivable_lines = self.line_ids.filtered(
            lambda l: l.partner_id and l.account_id.account_type == "asset_receivable"
        )
        receivable_account = (
            receivable_lines[0].account_id
            if receivable_lines
            else self.partner_id.property_account_receivable_id
        )
        if not receivable_account:
            _logger.warning(
                f"No receivable account found on invoice {self.name}. Skipping discount."
            )
            return

        misc_move = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "journal_id": misc_journal.id,
                    "date": fields.Date.today(),
                    "ref": _(
                        f"Discount {discount_percent:.4g}% for invoice: {self.name}"  # noqa: E231,B950
                    ),
                    "line_ids": [
                        Command.create(
                            {
                                "name": _(
                                    f"Discount {discount_percent:.4g}% for {self.name}"  # noqa: E231,B950
                                ),
                                "account_id": discount_account.id,
                                "debit": discount_amount,
                                "credit": 0.0,
                                "partner_id": self.partner_id.id,
                            }
                        ),
                        Command.create(
                            {
                                "name": _(
                                    f"Discount {discount_percent:.4g}% adjustment for {self.name}"  # noqa: E231,B950
                                ),
                                "account_id": receivable_account.id,
                                "debit": 0.0,
                                "credit": discount_amount,
                                "partner_id": self.partner_id.id,
                            }
                        ),
                    ],
                }
            )
        )
        misc_move.action_post()

        # Reconcile lines: find lines on invoice and journal entry to reconcile
        # Outstanding receivable lines of invoice + credit lines of journal entry
        to_reconcile_lines = (self.line_ids + misc_move.line_ids).filtered(
            lambda l: l.account_id == receivable_account and not l.reconciled
        )
        if to_reconcile_lines:
            to_reconcile_lines.reconcile()
            _logger.info(
                f"Discount journal move ({discount_amount}) created & reconciled with invoice {self.name}"  # noqa: E231,B950
            )
