# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = "account.fiscal.position"

    is_us_tax_exempt = fields.Boolean(
        string="US Tax Exempt",
        help="Customers assigned this fiscal position are exempt from US "
        "Sales Tax. Use this when exemption is managed through fiscal "
        "positions; a certificate on the customer takes precedence and "
        "records the certificate number as well.",
    )
    us_tax_exemption_reason_id = fields.Many2one(
        "us.tax.exemption.reason",
        string="Exemption Reason",
        help="Reason recorded on the calculation log for sales exempted by "
        "this fiscal position.",
    )
