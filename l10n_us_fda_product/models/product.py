from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ndc = fields.Char("NDC")
