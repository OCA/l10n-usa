This module exports a US sales tax return as the **Streamlined Sales Tax
(SST) Simplified Electronic Return (SER)** XML, the uniform electronic
return the SST member states accept for filing.

It serialises a generated `us.tax.return` into the
`SSTSimplifiedReturnTransmission` document: a filing header (SST ID or
state registration ID, FEIN, the target state's FIPS code), the state
summary (total / exempt / taxable sales and state tax due) and a
`JurisdictionDetail` entry per local jurisdiction keyed by **FIPS
code**. It therefore requires FIPS-tagged jurisdictions, which the
`l10n_us_sales_tax_sst` Rate & Boundary import provides (the manifest
dependency is only on `l10n_us_sales_tax_report`, so SER can also be
produced from any other FIPS-tagged source).

> [!NOTE]
> The canonical SER XSD is published by FTA E-Standards. Confirm the
> schema version and validate the output against it before transmitting
> to a state.
