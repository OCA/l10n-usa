# Copyright (C) 2019 Brian McMaster
# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from psycopg2.extensions import AsIs

from odoo import fields, models, tools


class AccountPayment1099Report(models.Model):
    _name = "account.payment.1099.report"
    _description = "1099 Payment Statistics"
    _auto = False

    date = fields.Date("Payment Date", readonly=True)
    amount = fields.Float("Payment Amount", readonly=True)
    vendor_id = fields.Many2one("res.partner", "Vendor", readonly=True)
    type_1099 = fields.Many2one("type.1099", "1099 Type", readonly=True)
    box_1099_misc = fields.Many2one("box.1099.misc", "1099-MISC Box", readonly=True)
    legal_id_number = fields.Char("Legal ID", readonly=True)

    def _select(self):
        return """
            SELECT
                v.id AS vendor_id,
                aml.id AS id,
                am.date AS date,
                aml.price_total AS amount,
                aml.type_1099_id AS type_1099,
                aml.box_1099_misc_id AS box_1099_misc,
                v.legal_id_number as legal_id_number
        """

    def _from(self):
        return """
            FROM account_move_line AS aml
        """

    def _join(self):
        return """
            JOIN account_move AS am ON aml.move_id = am.id
            JOIN res_partner AS v ON am.partner_id = v.id
        """

    def _where(self):
        return """
            WHERE
                am.payment_state='paid' and
                am.move_type='in_invoice' and
                aml.exclude_from_invoice_tab=false and
                aml.is_1099=True
        """

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
                %s
            )
        """,
            (
                AsIs(self._table),
                AsIs(self._select()),
                AsIs(self._from()),
                AsIs(self._join()),
                AsIs(self._where()),
            ),
        )
