# Copyright (C) 2019 Brian McMaster
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, tools


class AccountPayment1099Report(models.Model):
    _name = "account.payment.1099.report"
    _description = "1099 Payment Statistics"
    _auto = False

    date = fields.Date("Payment Date", readonly=True)
    amount = fields.Float("Payment Amount", readonly=True)
    vendor_id = fields.Many2one("res.partner", "Vendor", readonly=True)
    type_1099 = fields.Many2one("type.1099", "1099 Type", readonly=True)
    box_1099_misc = fields.Many2one("box.1099.misc", "1099-MISC Box", readonly=True)

    def _select(self):
        return """
            SELECT
                pmt.id AS id,
                pmt.payment_date AS date,
                pmt.amount AS amount,
                v.id AS vendor_id,
                v.type_1099_id AS type_1099,
                v.box_1099_misc_id AS box_1099_misc
        """

    def _from(self):
        return """
            FROM account_payment AS pmt
        """

    def _join(self):
        return """
            JOIN res_partner AS v ON pmt.partner_id = v.id
        """

    def _where(self):
        return """
            WHERE
                v.is_1099 = TRUE
        """

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        sql = """
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
                %s
            )
        """ % (
            self._table,
            self._select(),
            self._from(),
            self._join(),
            self._where(),
        )
        self._cr.execute(sql)
