# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    us_tax_exempt = fields.Boolean(
        string="US Tax Exempt",
        help=(
            "When checked, this partner is exempt from US Sales Tax on all orders. "
            "Attach the exemption certificate document to this record."
        ),
    )
    us_tax_exemption_code = fields.Char(
        string="Exemption Code",
        help=(
            "Category of exemption (e.g. RESALE, AGRICULTURE, GOVERNMENT, NONPROFIT)."
        ),
    )
    us_tax_exemption_number = fields.Char(
        string="Exemption Certificate #",
        help="Official exemption certificate number issued by the state authority.",
    )
