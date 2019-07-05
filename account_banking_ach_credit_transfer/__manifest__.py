# Copyright 2018 Thinkwell Designs <dave@thinkwelldesigns.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    'name': 'Account Banking ACH Credit Transfer',
    'summary': 'Create ACH files for Credit Transfers',
    'version': '12.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Thinkwell Designs, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/l10n-usa',
    'category': 'Banking addons',
    'depends': [
        'account_banking_ach_base',
    ],
    'data': [
        'data/account_payment_method.xml',
        'views/account_payment_order.xml',
    ],
    'demo': [
        'demo/ach_credit_transfer_demo.xml',
    ],
    'post_init_hook': 'update_bank_journals',
    'installable': True,
}
