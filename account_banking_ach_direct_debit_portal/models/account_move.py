from odoo import Command, _, models
from odoo.tools import float_is_zero


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

    def add_discount_line(self, discount_percent, discount_amount=None):
        self.ensure_one()
        discount_account = self._get_discount_account()
        if not discount_account:
            return

        if discount_amount is None:
            discount_amount = self.currency_id.round(
                self.amount_residual * discount_percent / 100
            )

        if float_is_zero(discount_amount, precision_rounding=self.currency_id.rounding):
            return

        self.sudo().write(
            {
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": _(
                                "%.4g%% Bank Transfer Discount"
                                % round(discount_percent, 4)
                            ),
                            "quantity": 1.0,
                            "price_unit": -discount_amount,
                            "account_id": discount_account.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ]
            }
        )

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
