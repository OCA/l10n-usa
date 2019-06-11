# -*- coding: utf-8 -*-
# Copyright 2017 Ursa Information Systems <http://www.ursainfosystems.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'US Check Printing with Payee Address',
    'summary': 'Print US Checks',
    'version': '10.0.1.1.0',
    'license': 'AGPL-3',
    'author': 'Open Source Integrators, Odoo Community Association (OCA)',
    'category': 'Localization/Checks Printing',
    'maintainer': 'Open Source Integrators',
    'website': 'https://www.opensourceintegrators.com',
    'depends': [
        'account_check_printing_report_base',
    ],
    'data': [
        'data/account_payment_check_report_data.xml',
        'report/report_check_base_top.xml',
        'report/report_check_base_middle.xml',
        'report/report_check_base_bottom.xml',
        'report/account_check_writing_report.xml',
    ],
    'installable': True,
}
