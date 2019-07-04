# Copyright 2018 Thinkwell Designs <dave@thinkwelldesigns.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    'name': 'Localizations for North American Banking & Financials',
    'summary': 'Add fields required for North American Banking & Financials',
    'version': '12.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Thinkwell Designs, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/l10n-usa',
    'category': 'Banking addons',
    'depends': [
        'account_payment_order',
        'account_banking_mandate',
    ],
    'data': [
        'views/account_banking_mandate.xml',
        'views/account_invoice.xml',
        'views/res_bank.xml',
        'views/res_company.xml',
        'views/res_partner.xml',
    ],
    "external_dependencies": {
        "python": ['stdnum',
                   'ach',
                   ],
    },
    'installable': True,
}
