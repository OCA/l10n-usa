Hybrid US Sales Tax engine for Odoo: resolves the combined state + county +
city + district rate for a ZIP code, applies it to sale orders and invoices,
and keeps a full audit trail of every calculation.

Resolution order: local rate database first, external API providers as
fallback (configured independently in their own `l10n_us_sales_tax_provider_*`
modules — this module never imports their code directly). Tracks nexus per
state, taxability per product category, and caches external API responses
to control call volume.
