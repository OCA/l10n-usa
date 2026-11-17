Changelog
=========

18.0.1.3.0 (2026-11-17)
------------------------
* New setting **Automatic Tax Calculation** (``l10n_us_tax.auto_mode``)
  with two modes: **Off** (only the **Calculate US Tax** button) and
  **On Validation** (on sale order confirmation and invoice posting, the
  default). With the engine disabled nothing is calculated, not even by
  **Calculate US Tax**
* **On upgrade** nothing changes: a database where no mode was ever
  chosen runs **On Validation**, which calculates on confirmation and
  posting as ``18.0.1.2.x`` did

18.0.1.0.12 (2026-06-26)
------------------------
* Provider-agnostic architecture: providers now self-register via a registry
  extension point (``_provider_service_classes()``) instead of being
  hardcoded in the engine
* ZipTax and API Ninjas moved to their own addons
  (``l10n_us_sales_tax_provider_ziptax``, ``l10n_us_sales_tax_provider_api_ninjas``)
* Removed TaxJar (covered by a separate community contribution, OCA/l10n-usa#183)
* Fixed: background tax calculation no longer requires the ``us_tax_user``/
  ``manager``/``technical`` groups — those gate manual access to the
  configuration screens, not the engine's own calculation for any user
* Fixed: exempt or genuinely 0%-rate lines now get an explicit tax
  (``US Sales Tax - Exempt (0%)`` or ``US Sales Tax {state} 0%``) instead of
  an empty ``tax_id``, for audit-trail clarity
* Fixed: REST API ``/calculate`` endpoint now reads parameters from the real
  JSON-RPC envelope body, not just ``kwargs``
* Fixed: Florida DOR rate importer — column resolution, deduplication, and
  batch performance for the full statewide file
* Fixed: ``get_rate_for_date`` falls back to the category-less rate when no
  category-specific rate exists for a jurisdiction

18.0.1.0.2 (2026-05-20)
------------------------
* Removed TaxCloud provider (not yet implemented — planned for Phase 2)

18.0.1.0.1 (2026-05-20)
------------------------
* First release
* Hybrid local DB + API fallback architecture
* Florida DOR seed data (67 counties)
* Providers: ZipTax, API Ninjas, TaxJar
* Sale Order and Invoice integration
* Nexus management per company/state
* Product fiscal categories
* Full immutable audit log
* Cache with configurable TTL
* REST API endpoints


18.0.1.0.0 (2026-05-20)
------------------------
* Initial release
