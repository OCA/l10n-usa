Adds the API Ninjas provider to the US Sales Tax Engine
(`l10n_us_sales_tax_engine`). Installs and uninstalls independently of any
other provider — the engine does not import this module's code, it discovers
API Ninjas through the engine's documented extension point
(`_provider_service_classes`).

API Ninjas offers ZIP-level rate lookups with a free tier (county/city rates
require a premium subscription). See https://api-ninjas.com/register to
obtain an API key.
