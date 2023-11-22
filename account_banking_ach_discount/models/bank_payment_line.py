# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class BankPaymentLine(models.Model):
    _inherit = "bank.payment.line"

    discount_amount = fields.Monetary(
        compute="_compute_discount_amount", currency_field="currency_id"
    )
    total_amount = fields.Monetary(
        compute="_compute_total_amount", currency_field="currency_id"
    )

    @api.depends("amount_currency", "discount_amount")
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = line.amount_currency + line.discount_amount

    @api.depends("payment_line_ids", "payment_line_ids.discount_amount")
    def _compute_discount_amount(self):
        for bline in self:
            discount_amount = sum(bline.mapped("payment_line_ids.discount_amount"))
            bline.discount_amount = discount_amount
