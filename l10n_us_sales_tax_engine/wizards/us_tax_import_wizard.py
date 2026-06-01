# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import io
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class UsTaxImportWizard(models.TransientModel):
    _name = "us.tax.import.wizard"
    _description = "US Tax Rate Import Wizard"

    source = fields.Selection(
        [
            ("florida_dor", "Florida DOR (Master Address List)"),
            ("texas_open_data", "Texas Open Data"),
            ("generic_csv", "Generic CSV (any state)"),
        ],
        required=True,
        default="generic_csv",
    )

    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        required=True,
    )
    effective_date = fields.Date(required=True, default=fields.Date.today)
    file_data = fields.Binary(string="File", required=True)
    file_name = fields.Char()
    delimiter = fields.Char(default=",", size=1)
    preview_html = fields.Html(readonly=True)

    def action_preview(self):
        """Show first 5 rows as preview before committing import."""
        self.ensure_one()
        if not self.file_data:
            raise UserError(self.env._("Please upload a file first."))
        content = base64.b64decode(self.file_data).decode("utf-8", errors="replace")
        lines = content.splitlines()[:6]
        from markupsafe import Markup, escape

        rows = Markup("")
        for line in lines:
            cells = Markup("").join(
                Markup("<td>%s</td>") % escape(c) for c in line.split(self.delimiter)
            )
            rows += Markup("<tr>%s</tr>") % cells
        table = (
            Markup(
                '<table class="table table-sm table-bordered">'
                "<tbody>%s</tbody></table>"
            )
            % rows
        )
        self.preview_html = table
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_import(self):
        """Execute import using the appropriate importer."""
        self.ensure_one()
        if not self.file_data:
            raise UserError(self.env._("Please upload a file first."))

        content = base64.b64decode(self.file_data)
        batch = self.env["us.tax.import.batch"].create(
            {
                "source": self.source,
                "file_name": self.file_name or "upload",
                "state_id": self.state_id.id,
                "effective_date": self.effective_date,
                "status": "running",
            }
        )

        try:
            from ..importers import importer_florida_dor, importer_generic_csv

            if self.source == "florida_dor":
                importer = importer_florida_dor.FloridaDorImporter(self.env, batch)
            else:
                importer = importer_generic_csv.GenericCsvImporter(
                    self.env, batch, delimiter=self.delimiter
                )
            importer.run(io.BytesIO(content), self.state_id, self.effective_date)
            batch.status = "done"

        except Exception as exc:
            _logger.error("Import failed: %s", exc)
            batch.write({"status": "failed", "error_log": str(exc)})
            raise UserError(self.env._("Import failed: %s", exc)) from exc

        return {
            "type": "ir.actions.act_window",
            "res_model": "us.tax.import.batch",
            "res_id": batch.id,
            "view_mode": "form",
        }
