import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo12-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo12-addon-account_banking_ach_base',
        'odoo12-addon-account_banking_ach_credit_transfer',
        'odoo12-addon-account_banking_ach_direct_debit',
        'odoo12-addon-l10n_us_account_profile',
        'odoo12-addon-l10n_us_form_1099',
        'odoo12-addon-l10n_us_gaap',
        'odoo12-addon-l10n_us_gaap_mis_report',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
    ]
)
