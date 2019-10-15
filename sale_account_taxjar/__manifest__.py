# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    'name': 'Sale Account TaxJar',
    'version': '12.0.1.0.0',
    'development_status': 'alpha',
    "maintainers": ['hveficent'],
    'category': 'Account',
    'summary': 'TaxJar SmartCalc API integration on Sale Orders',
    'author': 'Eficent, '
              'Odoo Community Association (OCA)',
    "website": "https://www.eficent.com/",
    'depends': [
        'account_taxjar',
        'sale_management',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'AGPL-3',
}
