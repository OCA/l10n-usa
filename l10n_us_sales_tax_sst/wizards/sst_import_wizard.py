# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import io
import zipfile

from odoo import fields, models
from odoo.exceptions import UserError

from ..services.importer_sst import SstImporter


class SstImportWizard(models.TransientModel):
    _name = "sst.import.wizard"
    _description = "Import SST Rate & Boundary Files"

    state_id = fields.Many2one(
        "res.country.state",
        string="State",
        required=True,
        domain=[("country_id.code", "=", "US")],
        help="The SST member state these files cover.",
    )
    rate_file = fields.Binary(required=True)
    rate_filename = fields.Char()
    boundary_file = fields.Binary()
    boundary_filename = fields.Char()

    def _decode(self, data, filename):
        """Return CSV text from a base64 .csv or .zip (same-named inner CSV)."""
        raw = base64.b64decode(data)
        if (filename or "").lower().endswith(".zip") or raw[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                if not names:
                    raise UserError(self.env._("The zip archive is empty."))
                raw = zf.read(names[0])
        return raw.decode("utf-8-sig", errors="replace")

    def action_import(self):
        self.ensure_one()
        batch = self.env["us.tax.import.batch"].create(
            {
                "source": "sst",
                "state_id": self.state_id.id,
                "file_name": self.rate_filename or self.boundary_filename,
                "status": "running",
            }
        )
        importer = SstImporter(self.env, batch)
        try:
            importer.import_rate_file(
                self._decode(self.rate_file, self.rate_filename), self.state_id
            )
            if self.boundary_file:
                importer.import_boundary_file(
                    self._decode(self.boundary_file, self.boundary_filename),
                    self.state_id,
                )
            batch.write({"status": "done", "finished_at": fields.Datetime.now()})
        except Exception as exc:
            batch.write(
                {
                    "status": "failed",
                    "finished_at": fields.Datetime.now(),
                    "error_log": str(exc),
                }
            )
            raise UserError(self.env._("SST import failed: %s", exc)) from exc

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Import Batch"),
            "res_model": "us.tax.import.batch",
            "res_id": batch.id,
            "view_mode": "form",
            "target": "current",
        }
