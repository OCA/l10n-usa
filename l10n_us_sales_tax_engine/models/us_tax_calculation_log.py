# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class UsTaxCalculationLog(models.Model):
    _name = "us.tax.calculation.log"
    _description = "US Tax Calculation Audit Log"
    _order = "calculated_at desc"

    # Source document
    res_model = fields.Char(index=True, help="sale.order or account.move")
    res_id = fields.Integer(index=True)
    document_ref = fields.Char(
        compute="_compute_document_ref",
        store=False,
        help="Human-readable reference.",
    )
    partner_id = fields.Many2one("res.partner", ondelete="set null")

    # Address used for calculation
    shipping_zip = fields.Char(size=5)
    shipping_state_id = fields.Many2one("res.country.state")
    shipping_city = fields.Char()
    shipping_county = fields.Char()
    full_address = fields.Char()

    # Calculation result
    source = fields.Selection(
        [
            ("local", "Local Database"),
            ("api", "External API"),
            ("cache", "Cached Result"),
            ("manual", "Manual Rate"),
            ("exempt_nexus", "Exempt — No Nexus"),
            ("exempt_rule", "Exempt — Tax Rule"),
            ("error", "Error"),
        ],
        required=True,
    )
    provider_id = fields.Many2one("us.tax.provider", ondelete="set null")
    product_category_id = fields.Many2one(
        "us.tax.product.category", ondelete="set null"
    )
    nexus_applied = fields.Boolean()

    state_rate = fields.Float(digits=(5, 4))
    county_rate = fields.Float(digits=(5, 4))
    city_rate = fields.Float(digits=(5, 4))
    district_rate = fields.Float(digits=(5, 4))
    total_rate = fields.Float(digits=(5, 4))

    taxable_amount = fields.Monetary(currency_field="currency_id")
    tax_amount = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda s: s.env.company.currency_id,
    )

    # Audit data
    request_payload = fields.Text()
    response_payload = fields.Text(help="Sanitized — no API keys stored.")
    calculated_at = fields.Datetime(default=fields.Datetime.now, index=True)
    calculated_by = fields.Many2one(
        "res.users",
        default=lambda s: s.env.user,
        ondelete="set null",
    )
    status = fields.Selection(
        [
            ("success", "Success"),
            ("error", "Error"),
            ("skipped", "Skipped"),
        ],
        default="success",
    )
    error_message = fields.Text()

    def write(self, vals):  # pylint: disable=method-required-super
        # Audit log is immutable — prevent accidental updates
        raise UserError(self.env._("Calculation log records are immutable."))

    def unlink(self):  # pylint: disable=method-required-super,no-raise-unlink
        raise UserError(self.env._("Calculation log records cannot be deleted."))  # pylint: disable=no-raise-unlink

    @api.depends("res_model", "res_id")
    def _compute_document_ref(self):
        recs_by_model = {}
        for rec in self:
            rec.document_ref = ""
            if rec.res_model and rec.res_id:
                recs_by_model.setdefault(rec.res_model, []).append(rec)

        for res_model, recs in recs_by_model.items():
            existing = self.env[res_model].browse([r.res_id for r in recs]).exists()
            names = {doc.id: doc.display_name for doc in existing}
            for rec in recs:
                rec.document_ref = names.get(rec.res_id) or (
                    f"{rec.res_model},{rec.res_id}"
                )

    @api.model
    def log_calculation(self, payload):
        """Create an audit log entry. payload is a dict of field values.

        Uses sudo() because audit logs are system records — any user
        who triggers a tax calculation should have their action logged
        regardless of their group permissions on this model.
        """
        for key in ("request_payload", "response_payload"):
            if key in payload and isinstance(payload[key], dict):
                sanitized = {
                    k: v
                    for k, v in payload[key].items()
                    if "key" not in k.lower() and "token" not in k.lower()
                }
                payload[key] = json.dumps(sanitized)
        # sudo() so any user can trigger log creation (system record)
        return super(UsTaxCalculationLog, self.sudo()).create(payload)  # pylint: disable=super-method-mismatch
