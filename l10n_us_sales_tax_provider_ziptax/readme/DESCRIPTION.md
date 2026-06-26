Adds the ZipTax (zip.tax) provider to the US Sales Tax Engine
(`l10n_us_sales_tax_engine`). Installs and uninstalls independently of any
other provider — the engine does not import this module's code, it discovers
ZipTax through the engine's documented extension point
(`_provider_service_classes`).

ZipTax offers ZIP-level rate lookups with a free tier of 100 calls/month. See
https://www.zip.tax/register to obtain an API key.
