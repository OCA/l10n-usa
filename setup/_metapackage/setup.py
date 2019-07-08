import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo11-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo11-addon-l10n_us_check_writing_address',
        'odoo11-addon-l10n_us_form_1099',
        'odoo11-addon-l10n_us_gaap',
        'odoo11-addon-l10n_us_gaap_mis_report',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
    ]
)
