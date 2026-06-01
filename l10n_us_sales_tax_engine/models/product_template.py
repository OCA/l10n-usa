# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    us_tax_category_id = fields.Many2one(
        "us.tax.product.category",
        string="US Tax Category",
        help="Fiscal classification for US Sales Tax calculation. "
        "If empty, defaults to TANGIBLE GOODS.",
    )
