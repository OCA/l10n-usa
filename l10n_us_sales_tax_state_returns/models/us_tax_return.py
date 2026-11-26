# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import state_return_builder


class UsTaxReturn(models.Model):
    _inherit = "us.tax.return"

    state_return_supported = fields.Boolean(
        compute="_compute_state_return_supported",
        help="A state-structured return export is available for this state.",
    )

    @api.depends("state_id")
    def _compute_state_return_supported(self):
        for rec in self:
            rec.state_return_supported = state_return_builder.is_supported(
                rec.state_id.code
            )

    def action_export_state_return(self):
        """Export this return as the state's filing worksheet (TX/FL/PA)."""
        self.ensure_one()
        if self.state == "draft" or not self.line_ids:
            raise UserError(self.env._("Generate the return before exporting it."))
        code = self.state_id.code
        if not state_return_builder.is_supported(code):
            raise UserError(
                self.env._(
                    "No state return export for %(state)s. Supported: %(supported)s.",
                    state=code,
                    supported=", ".join(sorted(state_return_builder.SUPPORTED)),
                )
            )
        data = state_return_builder.build(self)
        filename = f"return_{code}_{self.date_from}_{self.date_to}.csv"
        return self._download_attachment(filename, data, "text/csv")
