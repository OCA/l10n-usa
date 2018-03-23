{
    'name': 'United States Sample GAAP Chart of Accounts',
    'version': '11.0.1.0.0',
    'category': 'Localization',
    'author': 'Eficent,'
              'Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/l10n-usa/',
    'depends': ['account'],
    'data': [
        'data/account_chart_template_data.xml',
        'data/account_group.xml',
        'data/account_us_gaap_data.xml',
        'data/account_chart_template_data.yml',
        'data/res_company_data.xml',
    ],
    'installable': True,
    'license': 'AGPL-3',
}
