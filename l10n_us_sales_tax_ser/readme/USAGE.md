1.  In *Accounting → Configuration → Settings → SST Electronic Return*,
    set the company **SST ID** (and FEIN / transmitter ID). A seller
    that is not SST-registered can instead set a **State Registration
    ID** on the individual return.
2.  Open a generated return (*US Sales Tax → Returns*) and press
    **Export SER (XML)**.
3.  The downloaded XML is the SST Simplified Electronic Return for that
    state and period, ready to validate against the state's schema and
    transmit.

SER is only meaningful for SST member states; import the state's SST
Rate & Boundary data (`l10n_us_sales_tax_sst`) first so the
`JurisdictionDetail` lines carry FIPS codes.
