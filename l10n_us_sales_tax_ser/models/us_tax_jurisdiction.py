# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxJurisdiction(models.Model):
    _inherit = "us.tax.jurisdiction"

    composite_ser_code = fields.Char(
        string="Composite SER Code",
        size=5,
        help="When a state assigns one composite FIPS code bundling state + all "
        "local tax, the combined amount is reported under this code on the SER. "
        "Set manually for the rare composite-code states; not auto-populated "
        "from the SST files.",
    )
