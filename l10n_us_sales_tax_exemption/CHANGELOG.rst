Changelog
=========

18.0.1.0.0 (2026-06-18)
------------------------
* Initial release: provider-agnostic customer/entity sales-tax exemption
  certificates (``us.tax.exemption`` + ``us.tax.exemption.reason``) that exempt
  a sale per customer, state and date, with effective/expiry, status workflow,
  signed-document attachment and a daily expiry cron. Implements the engine's
  ``_get_customer_exemption`` hook.
