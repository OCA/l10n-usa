# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    discount_amount = fields.Monetary(currency_field="currency_id")
    total_amount = fields.Monetary(
        compute="_compute_total_amount", currency_field="currency_id"
    )
    payment_difference_handling = fields.Selection(
        [("open", "Keep open"), ("reconcile", "Mark invoice as fully paid")],
        default="reconcile",
        string="Action",
        copy=False,
    )
    writeoff_account_id = fields.Many2one(
        "account.account",
        string="Account",
        domain=[("deprecated", "!=", True)],
        copy=False,
    )
    reason_code = fields.Many2one("payment.adjustment.reason")
    note = fields.Text()
    payment_difference = fields.Float()
    move_id = fields.Many2one(
        "account.move", related="move_line_id.move_id", store=True
    )

    @api.onchange("discount_amount")
    def _onchange_discount_amount(self):
        if self.discount_amount:
            self.amount_currency = self.amount_currency - self.discount_amount

    @api.depends("amount_currency", "discount_amount")
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = line.amount_currency + line.payment_difference

    @api.model
    def same_fields_payment_line_and_bank_payment_line(self):
        res = super(
            AccountPaymentLine, self
        ).same_fields_payment_line_and_bank_payment_line()
        res.update(
            {
                "payment_difference_handling",
                "writeoff_account_id",
                "reason_code",
                "move_id",
            }
        )
        return res

    @api.model
    def _get_payment_line_grouping_fields(self):
        """This list of fields is used o compute the grouping hashcode."""
        fields = super()._get_payment_line_grouping_fields()
        fields.append("writeoff_account_id")
        return fields

    def _prepare_account_payment_vals(self):
        values = super()._prepare_account_payment_vals()
        note = ""
        total_payment_difference = 0.0
        for rec in self:
            payment_difference = rec.payment_difference
            if rec.reason_code:
                note = rec.reason_code.display_name + ": "
            if rec.note:
                note += rec.note
            if rec.payment_type == "outbound":
                payment_difference *= -1
            total_payment_difference += payment_difference
        if not float_is_zero(
            total_payment_difference, precision_digits=self.currency_id.decimal_places
        ):
            if not self.writeoff_account_id:
                raise UserError(
                    _(
                        "A payment difference was found, but you "
                        "need to indicicate a corresponding "
                        "writeoff account"
                    )
                )
            write_off_line_vals = {
                "account_id": self[:1].writeoff_account_id.id,
                "name": note,
                "amount_currency": total_payment_difference,
                "balance": total_payment_difference,
            }
            values["write_off_line_vals"] = [write_off_line_vals]
        return values
