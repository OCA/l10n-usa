# Copyright 2018 Thinkwell Designs <dave@thinkwelldesigns.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    'name': 'Account Banking ACH Direct Debit',
    'summary': 'Create ACH files for Direct Debit',
    'version': '11.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Thinkwell Designs',
    'website': 'https://github.com/thinkwelltwd/countinghouse',
    'category': 'Banking addons',
    'depends': [
        'account_banking_mandate_sale',
        'countinghouse_ach_base',
    ],
    'data': [
        'data/mandate_expire_cron.xml',
        'data/account_payment_method.xml',
        'views/account_payment_order.xml',
        'views/account_banking_mandate_view.xml',
    ],
    'demo': [
        'demo/ach_direct_debit_demo.xml',
    ],
    'post_init_hook': 'update_bank_journals',
    'installable': True,
}
