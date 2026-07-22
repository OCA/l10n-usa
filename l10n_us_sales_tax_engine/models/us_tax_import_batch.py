# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxImportBatch(models.Model):
    _name = "us.tax.import.batch"
    _description = "US Tax Rate Import Batch"
    _order = "started_at desc"

    name = fields.Char(compute="_compute_name", store=True)
    source = fields.Char(
        required=True,
        help="florida_dor, texas_open_data, manual_csv, api_ziptax",
    )
    file_name = fields.Char()
    state_id = fields.Many2one(
        "res.country.state",
        string="State Covered",
        domain=[("country_id.code", "=", "US")],
    )
    effective_date = fields.Date(help="Rates effective date from the imported source.")
    imported_by = fields.Many2one(
        "res.users",
        default=lambda s: s.env.user,
        ondelete="set null",
    )
    started_at = fields.Datetime(default=fields.Datetime.now)
    finished_at = fields.Datetime()
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("running", "Running"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    records_created = fields.Integer(default=0)
    records_updated = fields.Integer(default=0)
    records_skipped = fields.Integer(default=0)
    error_log = fields.Text()
    can_rollback = fields.Boolean(default=True)

    @api.depends("source", "state_id", "started_at")
    def _compute_name(self):
        for rec in self:
            date_str = rec.started_at.strftime("%Y-%m-%d") if rec.started_at else ""
            state = rec.state_id.code if rec.state_id else "ALL"
            rec.name = f"{rec.source} | {state} | {date_str}"

    def action_rollback(self):
        """Archive all rates created by this batch."""
        self.ensure_one()
        if not self.can_rollback:
            return
        rates = self.env["us.tax.rate"].search([("import_batch_id", "=", self.id)])
        rates.write({"active": False})
        mappings = self.env["us.tax.zip.mapping"].search(
            [("import_batch_id", "=", self.id)]
        )
        mappings.unlink()
        self.write(
            {
                "status": "failed",
                "can_rollback": False,
                "error_log": (self.error_log or "") + "\n[ROLLED BACK]",
            }
        )
