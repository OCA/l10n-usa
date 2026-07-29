# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxJurisdiction(models.Model):
    _inherit = "us.tax.jurisdiction"

    jurisdiction_type = fields.Char(
        string="SST Jurisdiction Type",
        size=2,
        help="X12 Data Element 1721 code from the SST rate file "
        "(00=county, 01=city, 45=state, 63=special district, …).",
    )
