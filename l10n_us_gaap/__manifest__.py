# Copyright 2018-22 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl
{
    "name": "United States Sample GAAP Chart of Accounts",
    "version": "15.0.1.0.0",
    "development_status": "Mature",
    "category": "Localization",
    "author": "ForgeFlow, Odoo Community Association (OCA)",
    "maintainers": ["JordiBForgeFlow"],
    "website": "https://github.com/OCA/l10n-usa",
    "depends": ["account"],
    "data": [
        "data/account_chart_template_data.xml",
        "data/account_group.xml",
        "data/account_us_gaap_data.xml",
        "data/account_chart_template_data_load.xml",
        "data/res_company_data.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
