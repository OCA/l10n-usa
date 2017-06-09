# -*- coding: utf-8 -*-
##############################################################################
#
#    Ursa Information Systems
#    Author: Jenny Wu (<contact@ursainfosystems.com>)
#    Website: (<http://www.ursainfosystems.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
{
    'name': 'l10n_us_form_1099',
    'version': '10.0.1.0.0',
    'author': 'Ursa Information Systems, Odoo Community Association (OCA)',
	"license": "AGPL-3",
    'summary': 'Add 1099 field to res.partner that will auto-check supplier',
    'category': 'Customers',
    'maintainer': 'Ursa Information Systems',
    'website': 'http://www.ursainfosystems.com',
    'depends': ['base'],
    'data': [
        'views/res_partner.xml',
    ],
    'qweb': [
    ],
    'installable': True,
}
