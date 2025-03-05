# Copyright 2022 ForgeFlow S.L. (https://www.forgeflow.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

{
    "name": "Bank Routing Numbers",
    "version": "18.0.1.0.0",
    "category": "Banking addons",
    "summary": "Add the routing numbers to the banks",
    "author": "ForgeFlow, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "depends": ["base"],
    "data": ["views/res_bank.xml"],
    "installable": True,
    "license": "LGPL-3",
    "external_dependencies": {"python": ["python-stdnum"]},
}
