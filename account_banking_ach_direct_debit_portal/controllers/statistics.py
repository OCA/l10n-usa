# Copyright 2025 Kencove (https://www.kencove.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from datetime import date

from psycopg2 import sql

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class StatisticsController(CustomerPortal):
    def _get_invoice_stats(self, date_from, date_to):
        """Get invoice statistics for a given date range."""
        cr = request.env.cr

        # Total number of invoices
        cr.execute(
            sql.SQL(
                """
                        SELECT COUNT(*)
                        FROM account_move
                        WHERE move_type = 'out_invoice'
                          AND state = 'posted'
                          AND invoice_date >= %s
                          AND invoice_date <= %s
                        """
            ),
            (date_from, date_to),
        )
        total_invoices = cr.fetchone()[0]

        # Count invoices paid by ACH or CC
        cr.execute(
            sql.SQL(
                """
                        WITH invoice_moves AS (
                        SELECT id
                        FROM account_move
                        WHERE move_type = 'out_invoice'
                          AND state = 'posted'
                          AND invoice_date BETWEEN %s AND %s
                        ),

                        reconciled_payments AS (
                            SELECT
                                im.id AS invoice_id,
                                pm.code AS payment_method_code
                            FROM invoice_moves im
                            JOIN account_move_line aml
                                ON aml.move_id = im.id
                            JOIN account_partial_reconcile apr
                                ON apr.debit_move_id = aml.id
                                OR apr.credit_move_id = aml.id
                            JOIN account_move_line payment_aml
                                ON payment_aml.id =
                                   CASE
                                       WHEN apr.debit_move_id = aml.id THEN apr.credit_move_id
                                       ELSE apr.debit_move_id
                                   END
                            JOIN account_payment ap
                                ON ap.move_id = payment_aml.move_id
                            JOIN account_payment_method pm
                                ON pm.id = ap.payment_method_id
                            WHERE pm.code IN ('ACH-In', 'authorize')
                        )

                        SELECT
                            payment_method_code,
                            COUNT(DISTINCT invoice_id) AS invoice_count
                        FROM reconciled_payments
                        GROUP BY payment_method_code;
                        """
            ),
            (date_from, date_to),
        )

        results = cr.fetchall()
        cc_paid_count = 0
        ach_paid_count = 0

        for code, count in results:
            if code == "ACH-In":
                ach_paid_count = count
            elif code == "authorize":
                cc_paid_count = count

        return {
            "total": total_invoices,
            "paid_by_cc": cc_paid_count,
            "paid_by_ach": ach_paid_count,
        }

    def _get_portal_user_stats(self):
        """Get portal user statistics using a single query with CTE."""
        cr = request.env.cr
        portal_group_id = request.env.ref("base.group_portal").id

        cr.execute(
            sql.SQL(
                """
                        WITH portal_partners AS (
                        SELECT DISTINCT rp.id
                        FROM res_partner rp
                        JOIN res_users ru ON ru.partner_id = rp.id
                        JOIN res_groups_users_rel gur ON gur.uid = ru.id
                        WHERE gur.gid = %s
                    ),

                    portal_users_count AS (
                        SELECT COUNT(DISTINCT gur.uid) AS total
                        from res_groups_users_rel gur
                        WHERE gur.gid = %s
                    ),

                    used_payment AS (
                        SELECT COUNT(DISTINCT am.partner_id) AS total
                        FROM portal_partners pp
                        JOIN account_move am
                            ON am.partner_id = pp.id
                           AND am.move_type = 'out_invoice'
                           AND am.state = 'posted'
                        JOIN account_move_line aml
                            ON aml.move_id = am.id
                        JOIN account_partial_reconcile apr
                            ON apr.debit_move_id = aml.id
                            OR apr.credit_move_id = aml.id
                        JOIN account_move_line payment_aml
                            ON payment_aml.id =
                               CASE
                                   WHEN apr.debit_move_id = aml.id THEN apr.credit_move_id
                                   ELSE apr.debit_move_id
                               END
                        JOIN account_payment ap
                            ON ap.move_id = payment_aml.move_id
                        JOIN account_payment_method pm
                            ON pm.id = ap.payment_method_id
                        WHERE pm.code IN ('ACH-In', 'authorize')
                    ),

                    with_bank AS (
                        SELECT COUNT(DISTINCT pp.id) AS total
                        FROM portal_partners pp
                        JOIN res_partner_bank rpb
                            ON rpb.partner_id = pp.id
                    ),

                    with_autopay AS (
                        SELECT COUNT(*) AS total
                        FROM portal_partners pp
                        JOIN res_partner rp ON rp.id = pp.id
                        WHERE rp.autopay IS NOT NULL
                          AND rp.autopay != 'disabled'
                    )

                    SELECT
                        puc.total AS portal_users,
                        up.total AS used_payment,
                        wb.total AS with_bank,
                        wa.total AS with_autopay
                    FROM portal_users_count puc
                    CROSS JOIN used_payment up
                    CROSS JOIN with_bank wb
                    CROSS JOIN with_autopay wa;
                        """
            ),
            (portal_group_id, portal_group_id),
        )

        result = cr.fetchone()

        return {
            "total": result[0] or 0,
            "used_portal_payment": result[1] or 0,
            "with_bank_account": result[2] or 0,
            "with_autopay": result[3] or 0,
        }

    @http.route(["/stats"], type="http", auth="user", website=True)
    def statistics_page(self, **kw):
        # Check if user is in Administration/Settings group
        if not request.env.user.has_group("base.group_system"):
            return request.render(
                "account_banking_ach_direct_debit_portal.statistics_access_denied"
            )

        values = self._prepare_portal_layout_values()

        # Calculate date ranges
        today = date.today()
        this_year_start = date(today.year, 1, 1)
        this_year_end = date(today.year, 12, 31)
        last_year_start = date(today.year - 1, 1, 1)
        last_year_end = date(today.year - 1, 12, 31)

        # Get statistics for each year
        this_year_stats = self._get_invoice_stats(this_year_start, this_year_end)
        last_year_stats = self._get_invoice_stats(last_year_start, last_year_end)

        # Get portal user statistics
        portal_user_stats = self._get_portal_user_stats()

        values.update(
            {
                "page_name": "statistics",
                "this_year": today.year,
                "last_year": today.year - 1,
                "this_year_stats": this_year_stats,
                "last_year_stats": last_year_stats,
                "portal_user_stats": portal_user_stats,
            }
        )

        return request.render(
            "account_banking_ach_direct_debit_portal.statistics_page", values
        )
