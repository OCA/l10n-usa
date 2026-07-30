Wires the US sales-tax engine into the website storefront.

US sales tax depends on the customer's **ship-to** address, which is only known
at checkout. This module recomputes the engine tax at the moments that matter -
when the delivery address is entered, before payment, and on **express checkout**
(Apple/Google Pay, which skips the normal address step) via the standard
``sale.order._recompute_taxes`` hook - and **only when the tax-relevant inputs
changed** since the last calculation (a per-order input hash of the ship-to +
lines).

It deliberately does **not** recompute on every cart change: there is no
destination to source from before checkout, and the engine's rate cache already
keeps repeat addresses off any metered provider - so the cost is at most one
live rate call per checkout, never per cart edit. Gated by the engine's
``l10n_us_tax.engine_active`` setting.
