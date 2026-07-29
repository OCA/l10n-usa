# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxRate(models.Model):
    _inherit = "us.tax.rate"

    # SST reduced food/drug rate (§308). Default 0 / unused for non-SST sources.
    food_drug_rate = fields.Float(
        digits=(5, 4),
        default=0.0,
        help="Reduced rate for SST food/drug categories (§308). 0 = not used.",
    )
