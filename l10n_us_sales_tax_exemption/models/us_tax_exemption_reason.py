# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxExemptionReason(models.Model):
    _name = "us.tax.exemption.reason"
    _description = "US Sales Tax Exemption Reason"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Stable code recorded on exempted calculations (resale, "
        "agriculture, government, …).",
    )
    # Maps the reason to the SST SER ExemptionDeductionBreakout bucket, so an
    # exempted sale can be reported under the right category on the return.
    ser_breakout = fields.Selection(
        [
            ("agriculture", "Agriculture"),
            ("direct_pay", "Direct Pay"),
            ("government", "Government / Exempt Organization"),
            ("manufacturing", "Manufacturing"),
            ("resale", "Resale"),
            ("other", "Other"),
        ],
        required=True,
        default="other",
        string="SER Breakout Category",
    )
    entity_use_code = fields.Char(
        help="Avatax / SST entity-use code for this reason (e.g. G resale, "
        "H agriculture, A federal government) — for provider interop.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "The exemption reason code must be unique."),
    ]
