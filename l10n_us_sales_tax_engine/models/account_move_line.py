# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class AccountMoveLine(models.Model):
    _name = "account.move.line"
    _inherit = ["us.tax.line.hash.mixin", "account.move.line"]

    def _us_tax_auto_parents(self):
        """Return the moves the product lines in self belong to.

        account.move.line.create() and write() run inside the core's
        _sync_dynamic_lines, which creates, writes and unlinks tax,
        payment term, cogs and epd lines. Without this filter each of
        those re-enters _us_tax_auto_recalculate(), and on a stale move
        the engine would rewrite tax_ids on the very product lines whose
        plan the core has already computed.

        Sections and notes are left out on purpose: _compute_totals
        blanks price_subtotal for every display_type other than product
        and cogs, and _us_tax_hash_parts() skips lines with no subtotal,
        so they cannot change the hash and their only effect would be a
        recomputation whose outcome is known in advance.

        display_type is a stored precomputed column, whereas reading the
        core's invoice-line One2many would issue a search_fetch plus a
        flush of pending account.move.line writes in the middle of the
        core's synchronisation.
        """
        return self.filtered(lambda line: line.display_type == "product").move_id
