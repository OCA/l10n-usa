import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo14-addons-oca-l10n-usa",
    description="Meta package for oca-l10n-usa Odoo addons",
    version=version,
    install_requires=[
        'odoo14-addon-l10n_us_form_1099',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
    ]
)
