TaxJar address-level rate provider for the US sales tax engine, packaged as a
standalone addon.

It demonstrates the engine's provider extension point: a provider lives in its
own module and registers itself by extending ``us.tax.provider._provider_service_classes``
- no edit to the engine. Install it (and set the TaxJar token) only if you use
TaxJar; the engine ships only its built-in local provider.
