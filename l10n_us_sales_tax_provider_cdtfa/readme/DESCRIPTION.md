Free California (CDTFA) rooftop tax-rate provider for the US sales tax engine,
packaged as a standalone addon.

California is not a Streamlined Sales Tax member, so it has no local SST rate
database. The California Department of Tax and Fee Administration (CDTFA)
publishes a **free, keyless, rooftop** rate service, which this provider calls
to resolve the exact combined rate for a California address.

It demonstrates the engine's provider extension point: a provider lives in its
own module and registers itself by extending
``us.tax.provider._provider_service_classes`` — no edit to the engine. Install
and activate it only if you sell into California; the engine ships only its
built-in local provider.
