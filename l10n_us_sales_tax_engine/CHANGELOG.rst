Changelog
=========

18.0.1.6.0 (2026-11-17)
------------------------
* New **Live** mode in **Automatic Tax Calculation**: US tax is
  recalculated as a draft sale order or customer invoice changes.
  Editing a quantity, a price, a product or a line recalculates in the
  same write, no confirmation needed. An invoice is calculated when it
  is created; a quotation on its first line
* New crons **US Tax: Recalculate Outdated Sales Orders** and **US Tax:
  Recalculate Outdated Invoices** (daily, one per document model) that,
  in the **Live** mode, recalculate outdated documents in batches of 10,
  reporting their progress so a worker time limit costs one batch at
  most. A document that fails is retried on the next run
* In the **Live** mode a provider outage never stops the edit of a draft
  document nor the cron, whatever the **API Failure Policy**: the error
  is logged, the tax the engine could not apply is rolled back to a
  savepoint, and the document stays outdated so the cron picks it up
  again
* **On upgrade** the mode stays as it was: **Live** consumes more
  provider quota, so it is never turned on by the upgrade

18.0.1.5.0 (2026-11-17)
------------------------
* Outdated-tax detection: documents keep a fingerprint of the engine's
  inputs (``us_tax_input_hash``) and of the last calculation
  (``us_tax_calculated_hash``). A change to the customer address, the
  customer's **US Tax Exempt** flag or the document date marks the
  document as outdated without calling the engine
* Warning banner on the sale order and customer invoice forms when the
  tax is outdated, with a button to recalculate on the spot
* Confirming an order or posting an invoice always recalculates the
  document, since rates, rules and nexus are not in the fingerprint
* On a partially invoiced sale order only the lines nothing has been
  invoiced from follow a new rate; the invoiced ones keep the tax their
  invoice was issued with
* The **Calculate US Tax** button is now hidden when the engine is
  disabled, instead of writing ``us_tax_source = "disabled"`` without
  calculating anything
* Under the **Block** API failure policy, a provider outage reaches the
  **Calculate US Tax** button as the same error message that refuses a
  confirmation or a posting, instead of a server error
* **On upgrade** the fingerprint is computed only for the documents that
  can still take a tax change, not for every journal entry. Documents
  that already carried a calculation are stamped with their current
  fingerprint, so outdated detection covers them from the upgrade on
  instead of reading them as never calculated
* Documents are only kept up to date while they can still take a tax
  change: draft, sent and unlocked sale orders that are not fully
  invoiced, and draft customer invoices and refunds. Outside that,
  the fingerprint is frozen, the banner and the recalculate buttons are
  hidden, and the manual button does not touch the document — reset the
  invoice to draft or unlock the order to recalculate it
* Fixed: a failed calculation no longer marks the document as
  calculated. The audit row is recorded as an error and the document
  stays outdated, even when its first calculation is the one that
  failed
* Fixed: a change to a customer address no longer rewrites posted,
  cancelled, locked or fully invoiced documents, nor vendor bills of the
  same partner
* Fixed: calling **Calculate US Tax** while the engine is disabled, or
  on a document the engine skips as non-US, no longer stamps the
  document as calculated

18.0.1.4.0 (2026-11-17)
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
