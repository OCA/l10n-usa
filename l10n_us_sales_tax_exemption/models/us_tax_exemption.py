# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxExemption(models.Model):
    _name = "us.tax.exemption"
    _description = "US Sales Tax Exemption Certificate"
    _inherit = ["mail.thread"]
    _order = "partner_id, effective_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        index=True,
        tracking=True,
        help="Commercial entity the certificate is held for.",
    )
    reason_id = fields.Many2one(
        "us.tax.exemption.reason",
        string="Exemption Reason",
        tracking=True,
        help="Required once the certificate leaves draft. Optional while it "
        "is being filled in, so a partially completed submission can be "
        "saved rather than lost.",
    )
    state_ids = fields.Many2many(
        "res.country.state",
        string="Covered States",
        domain=[("country_id.code", "=", "US")],
        help="States the certificate exempts the customer in. A blanket "
        "certificate covers several states. Required once the certificate "
        "leaves draft.",
    )
    certificate_number = fields.Char(tracking=True)
    effective_date = fields.Date(default=fields.Date.context_today, required=True)
    expiry_date = fields.Date(
        help="Leave empty if the certificate does not expire.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("signed", "Signed by Customer"),
            ("valid", "Valid"),
            ("expired", "Expired"),
            ("revoked", "Revoked"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    is_blanket = fields.Boolean(
        string="Blanket Certificate",
        default=True,
        help="Covers ongoing/future purchases (vs a single transaction). "
        "Advisory metadata in this version — exemption applies whenever the "
        "certificate is valid regardless of this flag.",
    )
    document = fields.Binary(string="Signed Certificate", attachment=True)
    document_filename = fields.Char()
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    notes = fields.Text()

    @api.depends("partner_id", "reason_id", "effective_date")
    def _compute_name(self):
        for rec in self:
            parts = [rec.partner_id.display_name or "", rec.reason_id.name or ""]
            rec.name = " — ".join(p for p in parts if p) or self.env._("New Exemption")

    @api.constrains("effective_date", "expiry_date")
    def _check_dates(self):
        for rec in self:
            if (
                rec.expiry_date
                and rec.effective_date
                and rec.effective_date > rec.expiry_date
            ):
                raise ValidationError(
                    self.env._("Effective date must be on or before the expiry date.")
                )

    @api.constrains("state", "reason_id", "state_ids")
    def _check_complete_outside_draft(self):
        """A certificate only has to be complete once it stops being a draft.

        Both fields are needed to decide anything, but demanding them at
        creation makes a partially completed submission impossible to save —
        a portal form or an API caller has to be able to put down what it has
        and come back to it.
        """
        for rec in self:
            if rec.state == "draft":
                continue
            missing = []
            if not rec.reason_id:
                missing.append(self.env._("an exemption reason"))
            if not rec.state_ids:
                missing.append(self.env._("at least one covered state"))
            if missing:
                raise ValidationError(
                    self.env._(
                        "%(name)s needs %(missing)s before it leaves draft.",
                        name=rec.display_name,
                        missing=self.env._(" and ").join(missing),
                    )
                )

    # ── Actions ─────────────────────────────────────────────────────────────---

    def action_validate(self):
        """Accept the certificate for use.

        Kept as the single approval step: whoever runs this is vouching for
        the certificate, whether they typed it in themselves or are accepting
        something the customer submitted.
        """
        self.write({"state": "valid"})

    def action_revoke(self):
        self.write({"state": "revoked"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_mark_signed(self):
        """Record that the customer has completed the certificate.

        Signed is not the same as accepted. The engine exempts on ``valid``
        only, so a submission — from a portal, an API caller, or an
        e-signature integration — waits here until somebody has reviewed it.
        Without that step anything able to create a record could grant itself
        an exemption.
        """
        self.write({"state": "signed"})

    @api.model
    def _resolve(self, partner_id, state, doc_date, company_id=False):
        """The certificate covering ``partner_id`` in ``state`` on ``doc_date``.

        Single source of truth for "is this sale exempt": the engine hook needs
        the reason code, the invoice snapshot needs the record itself.
        """
        if not partner_id or not state:
            return self.browse()
        domain = [
            ("partner_id", "=", partner_id),
            ("state", "=", "valid"),
            ("state_ids", "in", state.id),
            ("effective_date", "<=", doc_date),
            "|",
            ("expiry_date", "=", False),
            ("expiry_date", ">=", doc_date),
        ]
        if company_id:
            # The company's own certificates, or company-blank (global) ones.
            domain.append(("company_id", "in", [company_id, False]))
        return self.search(domain, limit=1)

    @api.model
    def _cron_expire_certificates(self):
        """Flip valid certificates whose expiry has passed to 'expired'."""
        today = fields.Date.context_today(self)
        expired = self.search(
            [
                ("state", "=", "valid"),
                ("expiry_date", "!=", False),
                ("expiry_date", "<", today),
            ]
        )
        expired.write({"state": "expired"})
        return len(expired)
