# Copyright (C) 2020 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields


class HrExpense(models.Model):
    _inherit = "hr.expense"

    expense_onpay_id = fields.Many2one(
        related="product_id.product_onpay_id",
        string="OnPay Pay Type",
        store=True
    )
