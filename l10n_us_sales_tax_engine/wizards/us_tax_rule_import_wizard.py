# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Import an SST Taxability-Matrix slice as us.tax.rule records.

The SST Taxability Matrix has no official machine feed, so an admin prepares a
per-state CSV mapping the SST Library-of-Definitions items onto our product
categories. Columns (with header):

    category_code, taxable, rate_override, effective_date, end_date

``taxable`` accepts 1/0/true/false/yes/no; dates are YYYY-MM-DD or CCYYMMDD
(open-ended sentinels recognised); ``rate_override``/``end_date`` may be blank.
Importing a new effective-dated rule closes the prior open rule for the same
(state, category) so scheduled taxability changes supersede cleanly. A bad row
is skipped and recorded in the batch error log rather than aborting the import.
"""

import base64
import csv
import io

from odoo import fields, models

from ..tools import close_superseded_periods, parse_sst_date

_TRUE = {"1", "true", "t", "yes", "y", "x"}


class UsTaxRuleImportWizard(models.TransientModel):
    _name = "us.tax.rule.import.wizard"
    _description = "Import SST Taxability Matrix (us.tax.rule)"

    state_id = fields.Many2one(
        "res.country.state",
        string="State",
        required=True,
        domain=[("country_id.code", "=", "US")],
    )
    matrix_file = fields.Binary(string="Matrix CSV", required=True)
    matrix_filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        Category = self.env["us.tax.product.category"]
        Rule = self.env["us.tax.rule"]
        batch = self.env["us.tax.import.batch"].create(
            {
                "source": "taxability_matrix",
                "state_id": self.state_id.id,
                "file_name": self.matrix_filename,
                "status": "running",
            }
        )
        text = base64.b64decode(self.matrix_file).decode("utf-8-sig", errors="replace")
        created = updated = skipped = 0
        errors = []
        # Header is row 1; data rows start at 2.
        for line_no, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            try:
                with self.env.cr.savepoint():
                    action = self._import_row(Category, Rule, row)
                created += action == "created"
                updated += action == "updated"
                skipped += action == "skipped"
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort
                skipped += 1
                errors.append(f"row {line_no}: {exc}")

        batch.write(
            {
                "status": "done" if (created or updated or not errors) else "failed",
                "records_created": created,
                "records_updated": updated,
                "records_skipped": skipped,
                "error_log": "\n".join(errors) or False,
                "finished_at": fields.Datetime.now(),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "us.tax.import.batch",
            "res_id": batch.id,
            "view_mode": "form",
            "target": "current",
        }

    def _import_row(self, Category, Rule, row):
        code = (row.get("category_code") or "").strip()
        category = Category.search([("code", "=", code)], limit=1)
        if not category:
            return "skipped"
        eff = parse_sst_date(row.get("effective_date"))
        vals = {
            "state_id": self.state_id.id,
            "product_tax_category_id": category.id,
            "taxable": (row.get("taxable") or "").strip().lower() in _TRUE,
            "rate_override": float(row.get("rate_override") or 0.0),
            "effective_date": eff,
            "end_date": parse_sst_date(row.get("end_date")),
        }
        existing = Rule.search(
            [
                ("state_id", "=", self.state_id.id),
                ("product_tax_category_id", "=", category.id),
                ("effective_date", "=", eff),
            ],
            limit=1,
        )
        if existing:
            existing.write(vals)
            return "updated"
        Rule.create(vals)
        close_superseded_periods(
            Rule,
            [
                ("state_id", "=", self.state_id.id),
                ("product_tax_category_id", "=", category.id),
            ],
            eff,
        )
        return "created"
