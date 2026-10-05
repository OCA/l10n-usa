# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


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

    @api.model
    def _commercial_fields(self):
        """An exemption certificate is issued to the legal entity, not to each
        of its contacts — the same reasoning Odoo applies to ``vat``.

        Without this, an order shipped to a child contact of an exempt customer
        is taxed in full, because the certificate lives on the parent only.
        """
        return super()._commercial_fields() + [
            "us_tax_exempt",
            "us_tax_exemption_code",
            "us_tax_exemption_number",
        ]
