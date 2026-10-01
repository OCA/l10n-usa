from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_hazardous_drug = fields.Boolean("Hazardous Drug (NIOSH)")
