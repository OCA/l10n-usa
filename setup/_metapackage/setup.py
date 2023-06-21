import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo-addon-account_banking_ach_base>=15.0dev,<15.1dev',
        'odoo-addon-account_banking_ach_credit_transfer>=15.0dev,<15.1dev',
        'odoo-addon-l10n_us_partner_legal_number>=15.0dev,<15.1dev',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 15.0',
    ]
)
