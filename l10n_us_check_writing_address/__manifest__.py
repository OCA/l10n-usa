# Copyright 2019 Open Source Integrators
# <https://www.opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'US Check Printing with Payee Address',
    'summary': 'Print US Checks',
    'version': '11.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Open Source Integrators, Odoo Community Association (OCA)',
    'category': 'Localization/Checks Printing',
    'maintainer': 'Open Source Integrators',
    'website': 'https://github.com/OCA/l10n-usa',
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
