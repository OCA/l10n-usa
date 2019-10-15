# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    'name': 'Account TaxJar',
    'version': '12.0.1.0.0',
    'development_status': 'alpha',
    "maintainers": ['hveficent'],
    'category': 'Account',
    'summary': 'TaxJar SmartCalc API integration on Sale Invoices',
    'author': 'Eficent, '
              'Odoo Community Association (OCA)',
    "website": "https://www.eficent.com/",
    'depends': [
        'account',
        'sale_stock_sourcing_address',
    ],
    'external_dependencies': {'python': ['taxjar']},
    'data': [
        'data/account_tax_group.xml',
        'security/ir.model.access.csv',
        'views/account_fiscal_position.xml',
        'views/account_invoice_views.xml',
        'views/account_tax_views.xml',
        'views/product_views.xml',
        'views/taxjar_api_key_views.xml',
        'views/taxjar_nexus_sourcing_views.xml',
        'views/taxjar_category_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}
