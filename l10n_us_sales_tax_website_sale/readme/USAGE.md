1. Enable the engine: set ``l10n_us_tax.engine_active`` to ``True`` (System
   Parameters), and configure providers/nexus as for backend orders.
2. Tax is recomputed automatically during checkout - when the delivery address
   is entered, before payment, and on express checkout - and only when the
   ship-to or lines changed. The cart page shows no destination tax (there is
   no address yet); this is expected.

Scope and behaviour:

* Recompute fires only at the wired checkout touchpoints, not on backend writes
  to the order; a back-office edit to a web order should re-run tax from the
  backend (Calculate US Tax).
* A hard provider failure follows the engine's ``l10n_us_tax.fail_policy``
  (block stops checkout; warn lets it through) - it is never swallowed into a
  silently under-taxed order.
* Ship-to addresses in US territories (Puerto Rico, Guam, ...) run their own tax
  regimes and are out of scope.
