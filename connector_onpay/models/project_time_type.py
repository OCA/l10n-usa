# Copyright (C) 2020 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ProjectTimeType(models.Model):
    _inherit = "project.time.type"

    onpay_pay_type_id = fields.Many2one(
        "onpay.pay.type",
        string="OnPay Pay Type",
    )
