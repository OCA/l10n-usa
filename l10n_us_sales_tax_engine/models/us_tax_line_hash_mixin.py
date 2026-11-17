# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


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
