Changelog
=========

18.0.1.3.0 (2026-09-03)
------------------------
* New setting **Automatic Tax Calculation**
  (``l10n_us_tax.auto_calculate``, off by default) governing every
  automatic trigger: sale order confirmation, invoice posting, the new
  ``write()``/``create()`` hooks and the new cron. Unticking the engine
  also turns it off
* US tax is now recalculated as the document changes — editing a
  quantity, a price, a product or a line on a draft sale order or
  customer invoice recalculates in the same write, no confirmation
  needed
* Outdated-tax detection: documents keep a fingerprint of the engine's
  inputs (``us_tax_input_hash``) and of the last calculation
  (``us_tax_calculated_hash``). A change to the customer address, the
  exemption certificate or the document date marks the document as
  outdated without calling the engine
* Warning banner on the sale order and customer invoice forms when the
  tax is outdated, with a button to recalculate on the spot
* New crons **US Tax: Recalculate Outdated Sales Orders** and **US Tax:
  Recalculate Outdated Invoices** (daily, one per document model) that
  recalculate outdated documents in batches
* The **Calculate US Tax** button is now hidden when the engine is
  disabled, instead of writing ``us_tax_source = "disabled"`` without
  calculating anything
* Fixed: the manual **Calculate US Tax** button ran the calculation
  twice when the automation was enabled — the engine's writes on the
  lines re-entered the automatic trigger before the calculated hash was
  stamped
* **On upgrade**, the new setting is inherited from the engine switch: a
  database where **Enable US Tax Engine** was already on gets
  **Automatic Tax Calculation** turned on too, so that updating the
  module never silently stops calculating tax. Be aware that the
  automation goes further than the confirm/post calculation of
  ``18.0.1.2.0``: it also recalculates on ``write()``/``create()`` and
  runs a daily cron, which consumes more provider quota. Turn the
  setting off in *Accounting → Configuration → Settings* to get the
  previous behaviour. A database that never enabled the engine is left
  untouched. Documents that already carried a calculation are stamped
  with their current fingerprint, so outdated detection covers them from
  the upgrade on instead of reading them as never calculated
* Documents are only kept up to date while they can still take a tax
  change: draft, sent and unlocked sale orders that are not fully
  invoiced, and draft customer invoices and refunds. Outside that,
  the fingerprint is frozen, the banner and the recalculate buttons are
  hidden, and neither the cron nor the manual button touches the
  document — reset the invoice to draft or unlock the order to
  recalculate it
* The **Block** API failure policy keeps applying to the **Calculate US
  Tax** button, and only to it: on the automatic path the error is
  logged and swallowed, so a provider outage cannot make every draft
  document impossible to edit, confirm or post
* Fixed: a failed calculation no longer marks the document as
  calculated. The tax the engine could not apply is rolled back to a
  savepoint, the audit row is recorded as an error, and the document
  stays outdated so the cron picks it up again
* Fixed: a change to a customer address no longer rewrites posted,
  cancelled, locked or fully invoiced documents, nor vendor bills of the
  same partner
* Fixed: a document whose **first** calculation failed is now outdated
  like any other, so the banner shows and the cron retries it. Outdated
  detection rests on the attempt rather than on the last successful
  calculation, and every attempt — not only the cron's — stamps
  ``us_tax_auto_attempt_at``
* Fixed: calling **Calculate US Tax** while the engine is disabled, or
  on a document the engine skips as non-US, no longer stamps the
  document as calculated
* **Behaviour change:** an address with no country is no longer taken
  for an American one. A partner carrying a ZIP and a state but an empty
  **Country** used to be taxed by the **Calculate US Tax** button; the
  engine now answers ``skip_non_us`` and applies nothing, leaving any
  tax already on the lines untouched. Set the country on those partners
  to keep calculating their tax

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
