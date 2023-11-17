import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo-addon-l10n_us_form_1099>=16.0dev,<16.1dev',
        'odoo-addon-l10n_us_gaap>=16.0dev,<16.1dev',
        'odoo-addon-l10n_us_gaap_mis_report>=16.0dev,<16.1dev',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 16.0',
    ]
)
