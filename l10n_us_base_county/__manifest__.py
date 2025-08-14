{
    "name": "United States - Counties",
    "version": "18.0.0.0.0",
    "category": "Localization",
    "summary": "Add United States counties.",
    "author": "MetricWise, Odoo Community Association (OCA)",
    "license": "LGPL-3",
    "maintainer": "Adam Heinz <adam.heinz@metricwise.com>",
    "website": "https://github.com/OCA/l10n-usa",
    "depends": [
        "contacts",
        "l10n_us",
    ],
    "data": [
        "data/res.country.state.county.csv",
        "security/ir.model.access.csv",
        "views/res_country_state_county_views.xml",
        "views/res_partner_views.xml",
    ],
}
