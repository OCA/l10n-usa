# -*- coding: utf-8 -*-
# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'USA - Delivery',
    'summary': 'This module makes ounces the default unit of measure for '
               'stock pickings.',
    'version': '10.0.1.0.0',
    'category': 'Delivery',
    'website': 'https://laslabs.com/',
    'author': 'LasLabs, '
              'Odoo Community Association (OCA)',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'delivery',
    ],
    'data': [
        'views/stock_quant_package_view.xml',
    ],
}
