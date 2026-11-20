# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    us_tax_input_hash = fields.Char(copy=False)

    def _recompute_taxes(self):
        """The single hook every checkout flow calls on an address/fiscal-
        position change - including express checkout (Apple/Google Pay), which
        bypasses the normal address step. Run the engine after the standard
        recompute so US destination tax is applied in all flows; the guard keeps
        it off plain cart changes (which don't call this) and unchanged inputs.
        """
        res = super()._recompute_taxes()
        self._us_tax_recompute_if_needed()
        return res

    def _us_tax_input_hash(self):
        """Fingerprint of the tax-relevant inputs: the ship-to (rooftop-level),
        the fiscal position, the currency, and the lines."""
        self.ensure_one()
        ship = self.partner_shipping_id
        parts = [
            str(ship.id),
            (ship.street or "").strip(),
            (ship.city or "").strip(),
            ship.zip or "",
            ship.state_id.code or "",
            ship.country_id.code or "",
            str(self.fiscal_position_id.id),
            str(self.currency_id.id),
        ]
        for line in self.order_line.sorted("id"):
            parts.append(
                f"{line.id}:{line.product_id.id}:"
                f"{line.price_unit:.4f}:{line.product_uom_qty}"
            )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def _us_tax_recompute_if_needed(self):
        """Recompute engine tax at checkout - only when the tax-relevant inputs
        changed since the last calc and a US ship-to is known.

        No-op before an address is entered (cart page); the engine's rate cache
        keeps repeat addresses off the provider, so the cost is at most one live
        call per checkout, never per cart change. A hard provider failure is left
        to the engine's ``l10n_us_tax.fail_policy`` (block vs warn) - this never
        swallows it into a silently under-taxed order.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param("l10n_us_tax.engine_active", "False") != "True":
            return
        engine = self.env["us.tax.engine.service"]
        for order in self:
            ship = order.partner_shipping_id
            # US 50 states + DC; territories (PR/GU/VI/...) run their own tax
            # regimes and are out of scope for this engine.
            if not (ship.zip and ship.country_id.code == "US"):
                continue
            digest = order._us_tax_input_hash()
            if digest == order.us_tax_input_hash:
                continue  # unchanged → no recompute, no provider call
            engine.calculate_for_sale_order(order)
            order.us_tax_input_hash = digest
