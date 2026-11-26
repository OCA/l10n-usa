# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # Deliberately plain values, not related fields: a snapshot that can still
    # follow the certificate record is not a snapshot. Scalars also keep the
    # invoice readable by accountants who hold no US-tax group, since neither
    # us.tax.exemption nor its reason taxonomy is world-readable.
    us_tax_exemption_number = fields.Char(
        string="Exemption Certificate #",
        readonly=True,
        copy=False,
        help="Certificate number as it stood when this invoice was posted.",
    )
    us_tax_exemption_reason = fields.Char(
        string="Exemption Reason",
        readonly=True,
        copy=False,
        help="Reason the sale was exempt, recorded when this invoice was posted.",
    )
    us_tax_exemption_id = fields.Many2one(
        "us.tax.exemption",
        string="Exemption Certificate",
        readonly=True,
        ondelete="set null",
        copy=False,
        help="Certificate this invoice resolved to. Kept for traceability; the "
        "snapshot above is what defends the zero-tax line.",
    )

    def _snapshot_us_tax_exemption(self):
        """Freeze the exemption that applied, at post time.

        A zero-tax line has to be defensible years later, by which point the
        customer may have been edited, the certificate may have lapsed, or the
        exemption may have been revoked outright. Re-deriving it from the
        partner then answers "is this customer exempt today", which is not the
        question an auditor is asking.
        """
        for move in self:
            if move.move_type not in ("out_invoice", "out_refund"):
                continue
            partner = move.partner_id.commercial_partner_id
            state = move.partner_shipping_id.state_id or partner.state_id
            doc_date = move.invoice_date or fields.Date.context_today(move)
            certificate = (
                self.env["us.tax.exemption"]
                .sudo()
                ._resolve(partner.id, state, doc_date, move.company_id.id)
            )
            if certificate:
                move.us_tax_exemption_id = certificate.id
                move.us_tax_exemption_number = certificate.certificate_number
                move.us_tax_exemption_reason = certificate.reason_id.code
                continue
            position = partner.property_account_position_id
            if position.is_us_tax_exempt:
                move.us_tax_exemption_reason = (
                    position.sudo().us_tax_exemption_reason_id.code or "other"
                )

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._snapshot_us_tax_exemption()
        return posted
