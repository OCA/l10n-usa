from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    controlled_substance = fields.Selection(
        [
            ("C-I", "C-I"),
            ("C-II", "C-II"),
            ("C-III", "C-III"),
            ("C-IV", "C-IV"),
            ("C-VI", "C-VI"),
            ("C-VII", "C-VII"),
        ],
        string="DEA Number",
        help="Sold and shipped to customer with a DEA #",
    )
