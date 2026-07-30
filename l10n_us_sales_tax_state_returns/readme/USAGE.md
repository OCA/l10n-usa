1. Open a generated **US Tax Return** for a supported state (FL, TX, PA).
2. Click **Export State Return** to download the filing worksheet (CSV): the
   per-jurisdiction breakdown, the state's collection allowance / timely-filing
   discount, and the net tax due, organised to that state's form.

The worksheet is the set of values to key or upload, not a byte-exact portal
file - the exact upload schema (e.g. Texas EDI 813, Florida DR-15 e-file) is a
per-state spec a deployer maps on top. The allowance shown matches the
remittance bill: when the *remittance* module is installed and a
``us.tax.authority`` is configured for the state, its rate/cap is used;
otherwise the built-in per-state table applies.
