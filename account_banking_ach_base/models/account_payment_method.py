# Copyright 2016-2020 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class AccountPaymentMethod(models.Model):
    _inherit = "account.payment.method"

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        res["ACH-In"] = {"mode": "multi", "domain": [("type", "=", "bank")]}
        res["ACH-Out"] = {"mode": "multi", "domain": [("type", "=", "bank")]}
        return res
