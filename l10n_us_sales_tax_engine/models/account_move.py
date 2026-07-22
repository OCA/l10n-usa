# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    us_tax_source = fields.Char(
        string="Tax Source",
        help="Source used for the last US tax calculation.",
    )
    us_tax_calculated_at = fields.Datetime(
        string="Tax Calculated At",
    )

    def action_calculate_us_tax(self):
        """Manual trigger — recalculate US tax for this invoice."""
        self.ensure_one()
        engine = self.env["us.tax.engine.service"]
        try:
            result = engine.calculate_for_invoice(self)
            self.write(
                {
                    "us_tax_source": result.get("source", ""),
                    "us_tax_calculated_at": fields.Datetime.now(),
                }
            )
        except Exception as exc:
            _logger.error("US Tax calculation error on invoice %s: %s", self.name, exc)
            raise

    def _post(self, soft=True):
        """Auto-calculate tax when a move is actually posted.

        Overrides _post() rather than action_post(): action_post() is the
        UI-facing action and can, on some Odoo 18 core paths, return a
        wizard instead of posting — hooking into it would risk calculating
        tax on a move that never actually reaches the "posted" state.
        _post() only runs when the move is genuinely being posted, so
        reaching this point already guarantees the post will happen.

        Calculation must run BEFORE calling super(): once the move is
        posted, its lines' tax_ids can no longer be modified ("you should
        reset the journal entry to draft to do so").
        """
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param("l10n_us_tax.engine_active", "False") == "True":
            for move in self.filtered(
                lambda m: m.move_type in ("out_invoice", "out_refund")
            ):
                try:
                    self.env["us.tax.engine.service"].calculate_for_invoice(move)
                except Exception as exc:
                    _logger.error("US Tax auto-calc on post failed: %s", exc)
        return super()._post(soft=soft)
