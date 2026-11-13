# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, models


class UsTaxLineHashMixin(models.AbstractModel):
    """Input fingerprint of the document lines the engine would price."""

    _name = "us.tax.line.hash.mixin"
    _description = "US Tax Line Input Fingerprint"

    def _us_tax_hash_parts(self):
        """Return one deterministic string per line the engine would price.

        Mirrors the per-line loop of us.tax.engine.service._process():
        lines with a zero subtotal are skipped (sections, notes, free
        lines) and a product without a fiscal category counts as
        TANGIBLE, so neither shows up as a change the engine cannot see.

        _origin.id is used instead of id because the hash is also computed
        on unsaved form records, whose NewId is not orderable.
        """
        parts = []
        for line in self.sorted(lambda line: line._origin.id):
            if not line.price_subtotal:
                continue
            category = line.product_id.sudo().us_tax_category_id
            code = category.code if category else "TANGIBLE"
            parts.append(f"{line._origin.id}:{code}:{line.price_subtotal:.2f}")
        return parts

    def _us_tax_auto_parents(self):
        """Return the documents in self whose tax may need recalculating."""
        raise NotImplementedError

    @api.model_create_multi
    def create(self, vals_list):
        """Recalculate the parent documents that just got new lines.

        A new line is born with the product's or the fiscal position's
        default tax, never with the US one, so creation always has to
        reach the engine. unlink() is deliberately not overridden: the
        rate depends on ZIP, state, fiscal category and date, never on
        the document total, so removing a line cannot change the tax of
        the remaining ones.
        """
        lines = super().create(vals_list)
        lines._us_tax_auto_parents()._us_tax_auto_recalculate()
        return lines

    def write(self, vals):
        """Recalculate the parent documents whose engine inputs changed.

        _us_tax_auto_parents() is already deduplicated by the ORM, so a
        document gets recalculated once no matter how many of its lines
        the write touched.
        """
        res = super().write(vals)
        self._us_tax_auto_parents()._us_tax_auto_recalculate()
        return res
