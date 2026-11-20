Exports a sales-tax return as a **state-structured filing worksheet** for the
non-SST states **Texas, Florida and Pennsylvania** (SST states use the SER XML
in `l10n_us_sales_tax_ser`).

Each export organizes the return to that state's form - the summary lines and
the per-jurisdiction breakdown the state requires - and computes the state's
**vendor collection allowance / timely-filing discount** and the **net tax
due** (Florida 2.5% capped at $30, Texas 0.5%, Pennsylvania 1% capped). A
**Export State Return** button appears on the return for supported states.

This is a filing *worksheet* (the values to key or upload), not a byte-exact
portal file; the exact upload schema (Texas EDI 813, Florida DR-15 e-file,
Pennsylvania myPATH) is a per-state spec to map on top. Allowance rates and
caps are best-effort and should be confirmed against current state rules.
