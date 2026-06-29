# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.l10n_us_mis_financial_report.tests.test_common import (
    TestFinancialReportUSACommon,
)


@tagged("post_install", "-at_install")
class TestMisReportInstance(TestFinancialReportUSACommon):
    def test_get_filter_domain_with_journals(self):
        domain = self.mis_report_instance_journals._get_filter_domain(
            "account.move.line"
        )
        self.assertIn(
            ("journal_id", "in", [self.journal_test1.id, self.journal_test2.id]), domain
        )

    def test_get_filter_domain_without_journals(self):
        self.mis_report_instance_journals.journal_ids = [Command.clear()]
        domain = self.mis_report_instance_journals._get_filter_domain(
            "account.move.line"
        )
        self.assertNotIn(("journal_id", "in", []), domain)
        self.assertTrue(isinstance(domain, list))

    def test_hide_all_lines(self):
        report_id = self.mis_report_instance_hide_lines0.report_id
        report_styles = set(
            report_id.mapped("kpi_ids.style_id")
            + report_id.mapped("kpi_ids.auto_expand_accounts_style_id")
        )
        self.assertGreater(len(report_styles), 0)
        self.mis_report_instance_hide_lines0.hide_all_lines()
        self.assertTrue(
            all(
                [
                    style.hide_empty and style.hide_empty_inherit
                    for style in report_styles
                ]
            )
        )
        self.assertTrue(
            all(
                [
                    not style.hide_always and not style.hide_always_inherit
                    for style in report_styles
                ]
            )
        )

    def test_create_calls_hide_all_lines(self):
        with patch.object(
            type(self.MisReportInstance), "hide_all_lines"
        ) as mocked_hide:
            report_instance = self.MisReportInstance.create(
                self.create_mis_report_instance_values
            )
            self.assertEqual(len(report_instance), 1)
            self.assertEqual(mocked_hide.call_count, 1)

    def test_write_triggers_hide_all_lines(self):
        with patch.object(
            type(self.MisReportInstance), "hide_all_lines"
        ) as mocked_hide:
            self.mis_report_instance_hide_lines0.write({"hide_all_lines_0": True})
            mocked_hide.assert_called_once()

        with patch.object(
            type(self.MisReportInstance), "hide_all_lines"
        ) as mocked_hide:
            self.mis_report_instance_hide_lines0.write({"name": "Updated Name"})
            mocked_hide.assert_not_called()
