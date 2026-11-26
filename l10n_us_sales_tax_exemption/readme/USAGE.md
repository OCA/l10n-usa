1.  Go to *Accounting → Configuration → US Sales Tax → Exemption
    Certificates* (or the **US Tax Exemptions** smart button on a
    customer).
2.  Create a certificate: pick the customer, the reason, the covered
    states, an effective date and an optional expiry date; attach the
    signed document.
3.  Press **Validate**. Once valid, any sale shipping to a covered state
    on a covered date is exempted automatically (calculation log source
    = *Exempt — Customer Certificate*, with the reason recorded).
4.  Expired certificates flip to *Expired* automatically (daily cron);
    revoke a certificate with **Revoke**.

Configure the reason → SER breakout mapping under *Configuration → US
Sales Tax → Exemption Reasons*.
