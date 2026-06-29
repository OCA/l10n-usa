# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestFinancialReportUSACommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Models instance
        cls.AccountJournal = cls.env["account.journal"]
        cls.MisReportInstance = cls.env["mis.report.instance"]
        cls.RangeType = cls.env["date.range.type"]
        cls.DateRange = cls.env["date.range"]

        # Create journals
        cls.journal_test1 = cls.AccountJournal.create(
            {
                "name": "Test Journal 1",
                "code": "TJ1",
                "type": "general",
            }
        )
        cls.journal_test2 = cls.AccountJournal.create(
            {
                "name": "Test Journal 2",
                "code": "TJ2",
                "type": "general",
            }
        )

        # Create report instance
        cls.date_range_type = cls.RangeType.create(
            {
                "name": "Test Range Type",
            }
        )
        cls.date_range = cls.DateRange.create(
            {
                "name": "Test date range",
                "type_id": cls.date_range_type.id,
                "date_start": datetime.now() - relativedelta(months=6),
                "date_end": datetime.now(),
            }
        )

        cls.mis_report_instance_journals = cls.MisReportInstance.create(
            {
                "name": "Test MIS Report Instance",
                "journal_ids": [
                    Command.set([cls.journal_test1.id, cls.journal_test2.id])
                ],
                "report_id": cls.env.ref(
                    "l10n_us_mis_financial_report.report_cash_basis_us"
                ).id,
                "date_range_id": cls.date_range.id,
            }
        )

        cls.create_mis_report_instance_values = {
            "name": "Test MIS Report Instance",
            "report_id": cls.env.ref(
                "l10n_us_mis_financial_report.report_cash_basis_us"
            ).id,
            "date_range_id": cls.date_range.id,
            "hide_all_lines_0": True,
        }

        cls.mis_report_instance_hide_lines0 = cls.MisReportInstance.create(
            cls.create_mis_report_instance_values
        )
