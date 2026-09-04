# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models

from ..services.address_resolver import resolve_shipping_address


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["us.tax.auto.mixin", "account.move"]

    def _us_tax_extra_depends(self):
        """Add what the move contributes to the hash beyond the address.

        move_type is not listed here: _us_tax_state_depends() already
        carries it, since the state domain is expressed on it.
        """
        return [
            "invoice_date",
            "company_id",
            "invoice_line_ids.price_subtotal",
            "invoice_line_ids.product_id.us_tax_category_id",
        ]

    def _us_tax_state_depends(self):
        """Return the fields _us_tax_state_domain() is expressed on."""
        return ["state", "move_type"]

    def _us_tax_get_address(self):
        """Resolve the shipping address, the only one a move can be taxed on."""
        return resolve_shipping_address(self)

    def _us_tax_get_date(self):
        """Return the date the engine prices on, as an ISO string.

        A move with no invoice_date is priced on today, so the
        fingerprint holds today too. Holding the raw field instead
        would give two different fingerprints to two moves the engine
        treats alike, and would move the fingerprint when the core
        fills invoice_date in during _post() without a single engine
        input having changed.
        """
        return (self.invoice_date or fields.Date.context_today(self)).isoformat()

    def _us_tax_get_lines(self):
        """Return the invoice lines."""
        return self.invoice_line_ids

    def _us_tax_engine_run(self):
        """Run the engine for this move."""
        return self.env["us.tax.engine.service"].calculate_for_invoice(self)

    def _us_tax_state_domain(self):
        """Only customer invoices and refunds that are still editable."""
        return [
            ("state", "=", "draft"),
            ("move_type", "in", self.get_sale_types()),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        """Recalculate the moves that were just created.

        Kept on account.move alone rather than shared through the mixin:
        sale.order has no create-time trigger, and giving it one would
        run the engine on an empty quotation, which _process() answers
        with a us.tax.calculation.log row all the same.

        _us_tax_state_domain() keeps this to draft customer invoices and
        refunds; anything else leaves the engine untouched.
        """
        moves = super().create(vals_list)
        moves._us_tax_auto_recalculate()
        return moves

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
        reset the journal entry to draft to do so"). The move is still
        draft here, which is what the state domain requires.

        Posting goes through the mixin's single entry point, so it is
        subject to the same four guards as any other write: a move whose
        inputs still match its last calculation reaches the engine no
        more than a plain write would, and leaves no extra row in
        us.tax.calculation.log. No move-type filter is needed here —
        _us_tax_state_domain() already carries that restriction.
        """
        self._us_tax_auto_recalculate()
        return super()._post(soft=soft)
