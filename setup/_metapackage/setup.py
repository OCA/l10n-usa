import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo10-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo10-addon-l10n_us_account_profile',
        'odoo10-addon-l10n_us_check_writing_address',
        'odoo10-addon-l10n_us_form_1099',
        'odoo10-addon-l10n_us_product',
        'odoo10-addon-l10n_us_product_stock',
        'odoo10-addon-l10n_us_uom_profile',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 10.0',
    ]
)
