# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxProductCategory(models.Model):
    _name = "us.tax.product.category"
    _description = "US Tax Product Category"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        size=32,
        index=True,
        help="Technical code: TANGIBLE, SERVICE, FOOD, MEDICINE, DIGITAL, SHIPPING, EXEMPT",  # noqa: E501
    )
    description = fields.Text(translate=True)
    default_taxable = fields.Boolean(
        default=True,
        help="Taxable by default. Override per state via Tax Rules.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Product category code must be unique."),
    ]
