# Copyright (C) 2019 Brian McMaster
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.tools import SQL


class AccountPayment1099Report(models.Model):
    _name = "account.payment.1099.report"
    _description = "1099 Payment Statistics"
    _auto = False

    _depends = {
        "account.payment": ["partner_id", "amount", "move_id"],
        "account.move": ["date"],
        "res.partner": ["is_1099", "type_1099_id", "box_1099_misc_id"],
    }

    date = fields.Date(string="Payment Date", readonly=True)
    amount = fields.Float(string="Payment Amount", readonly=True)
    vendor_id = fields.Many2one("res.partner", readonly=True)
    type_1099 = fields.Many2one("type.1099", string="1099 Type", readonly=True)
    box_1099_misc = fields.Many2one(
        "box.1099.misc", string="1099-MISC Box", readonly=True
    )

    @property
    def _table_query(self):
        return SQL(
            """
            SELECT
                pmt.id AS id,
                am.date AS date,
                pmt.amount AS amount,
                v.id AS vendor_id,
                v.type_1099_id AS type_1099,
                v.box_1099_misc_id AS box_1099_misc
            FROM account_payment AS pmt
            JOIN res_partner AS v ON pmt.partner_id = v.id
            JOIN account_move AS am ON pmt.move_id = am.id
            WHERE v.is_1099 = TRUE
            """
        )
