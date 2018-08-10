# -*- coding: utf-8 -*-
# Copyright 2017 Ursa Information Systems <http://www.ursainfosystems.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import time
from odoo import api, exceptions, models, _
from odoo.tools import float_is_zero


class ReportCheckPrintTop(models.AbstractModel):
    _name = 'report.l10n_us_check_writing_address.report_check_base_top'
    _inherit = 'report.account_check_printing_report_base.report_check_base'
    
    @api.multi
    def render_html(self, docids, data=None):
        print "RENDER HTML CALLED ReportCheckPrintTop"
        payments = self.env['account.payment'].browse(docids)
        paid_lines = self.get_paid_lines(payments)
        docargs = {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'time': time,
            'fill_stars': self.fill_stars,
            'paid_lines': paid_lines
        }
        if self.env.user.company_id.check_layout_id:
            return self.env['report'].render(
                'l10n_us_check_writing_address.report_check_base_top',
                docargs)
        raise exceptions.Warning(_('You must define a check layout'))
#     _wrapped_report_class = ReportCheckPrint


class ReportCheckPrintBottom(models.AbstractModel):
    _name = 'report.l10n_us_check_writing_address.report_check_base_bottom'
    _inherit = 'report.account_check_printing_report_base.report_check_base'
    
    @api.multi
    def render_html(self, docids, data=None):
        print "RENDER HTML CALLED BOTTOM"
        payments = self.env['account.payment'].browse(docids)
        paid_lines = self.get_paid_lines(payments)
        docargs = {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'time': time,
            'fill_stars': self.fill_stars,
            'paid_lines': paid_lines
        }
        if self.env.user.company_id.check_layout_id:
            return self.env['report'].render(
                'l10n_us_check_writing_address.report_check_base_bottom',
                docargs)
        raise exceptions.Warning(_('You must define a check layout'))


class ReportCheckPrintMiddle(models.AbstractModel):
    _name = 'report.l10n_us_check_writing_address.report_check_base_middle'
    _inherit = 'report.account_check_printing_report_base.report_check_base'
    
    @api.multi
    def render_html(self, docids, data=None):
        print "RENDER HTML CALLED Middle"
        payments = self.env['account.payment'].browse(docids)
        paid_lines = self.get_paid_lines(payments)
        docargs = {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'time': time,
            'fill_stars': self.fill_stars,
            'paid_lines': paid_lines
        }
        if self.env.user.company_id.check_layout_id:
            return self.env['report'].render(
                'l10n_us_check_writing_address.report_check_base_middle',
                docargs)
        raise exceptions.Warning(_('You must define a check layout'))