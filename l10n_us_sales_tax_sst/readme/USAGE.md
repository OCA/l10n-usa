1.  Download a member state's Rate file (and Boundary file) from
    [streamlinedsalestax.org/ratesandboundry](https://www.streamlinedsalestax.org/Shared-Pages/rate-and-boundary-files).
    The data is free and updated quarterly.
2.  Go to *Accounting → Configuration → US Sales Tax → Tax Rates →
    Import SST Files*.
3.  Pick the **State**, upload the **Rate** file (required) and the
    **Boundary** file (optional but needed for address resolution).
    Plain CSV or the published `.zip` are both accepted.
4.  Press **Import**. Jurisdictions, rates and boundary records are
    created under one import batch (re-importing a newer quarter
    upserts).
5.  With the `local` provider active, the engine now resolves US
    addresses in that state through the SST data automatically.

> [!NOTE]
> Rate & Boundary data exists only for the SST member states (23 full
> members plus Tennessee). For other states the engine keeps using its
> ZIP-mapping data and external API providers.
