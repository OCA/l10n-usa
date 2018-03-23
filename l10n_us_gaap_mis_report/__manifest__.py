# Copyright 2018 Eficent Business and IT Consulting Services, S.L.
#                <contact@eficent.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl

{
    'name': 'MIS Builder Templates for US Chart of Accounts',
    'author': 'Eficent,'
              'Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/l10n-usa',
    'category': 'Reporting',
    'version': '11.0.1.0.0',
    'license': 'AGPL-3',
    'depends': [
        'mis_builder',  # OCA/mis-builder
        'l10n_us_gaap',  # OCA/mis-builder
    ],
    'data': [
        'data/mis_report_styles.xml',
        'data/mis_report_balance_sheet.xml',
        'data/mis_report_income_statement.xml',
    ],
    'installable': True,
}
