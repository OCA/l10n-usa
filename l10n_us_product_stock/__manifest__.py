# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'USA - Stock',
    'summary': 'This module overrides the product weight and volume to use '
               'ounces and cubic inches. It automatically installs if you '
               'have l10n_us_product and stock installed.',
    'version': '10.0.1.0.0',
    'category': 'Extra Tools',
    'website': 'https://laslabs.com/',
    'author': 'LasLabs, '
              'Odoo Community Association (OCA)',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
    'auto_install': True,
    'depends': [
        'l10n_us_product',
        'stock',
    ],
    'data': [
        'views/product_template_view.xml',
    ],
}
