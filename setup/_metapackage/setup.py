import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo14-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo14-addon-account_banking_ach_base',
        'odoo14-addon-account_banking_ach_credit_transfer',
        'odoo14-addon-account_banking_ach_direct_debit',
        'odoo14-addon-l10n_us_form_1099',
        'odoo14-addon-l10n_us_partner_legal_number',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 14.0',
    ]
)
