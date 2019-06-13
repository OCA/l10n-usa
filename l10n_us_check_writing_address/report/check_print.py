# Copyright 2019 Open Source Integrators
# <https://www.opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import time
from odoo import api, models


class ReportCheckPrintTop(models.AbstractModel):
    _name = 'report.l10n_us_check_writing_address.report_check_base_top'
    _inherit = 'report.account_check_printing_report_base.report_check_base'

    @api.model
    def get_report_values(self, docids, data=None):
        payments = self.env['account.payment'].browse(docids)
        paid_lines = self.get_paid_lines(payments)
        return {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'time': time,
            'fill_stars': self.fill_stars,
            'paid_lines': paid_lines
        }


class ReportCheckPrintBottom(models.AbstractModel):
    _name = 'report.l10n_us_check_writing_address.report_check_base_bottom'
    _inherit = 'report.account_check_printing_report_base.report_check_base'

    @api.model
    def get_report_values(self, docids, data=None):
        payments = self.env['account.payment'].browse(docids)
        paid_lines = self.get_paid_lines(payments)
        return {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'time': time,
            'fill_stars': self.fill_stars,
            'paid_lines': paid_lines
        }


class ReportCheckPrintMiddle(models.AbstractModel):
    _name = 'report.l10n_us_check_writing_address.report_check_base_middle'
    _inherit = 'report.account_check_printing_report_base.report_check_base'

    @api.model
    def get_report_values(self, docids, data=None):
        payments = self.env['account.payment'].browse(docids)
        paid_lines = self.get_paid_lines(payments)
        return {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'time': time,
            'fill_stars': self.fill_stars,
            'paid_lines': paid_lines
        }
