## Loading local rate data

The local provider needs three things before it can resolve a tax rate for a
ZIP code: a **Jurisdiction** (county/city), a **ZIP Mapping** pointing that
ZIP to the jurisdiction, and a **Tax Rate** on that jurisdiction. None of
these ship pre-loaded — only product categories and the provider registry
are seeded on install.

### Import Tax Rates wizard

US Sales Tax → Rate Database → Import Rates always requires a file upload —
there is no "instant, no file" option in the wizard.

- **Florida DOR**: upload the official Master Address List CSV from
  https://pointmatch.floridarevenue.com/General/AddressFiles.aspx (select a
  county and effective date, then download). This creates the jurisdiction,
  the rate, **and** the ZIP mapping for every row — full ZIP-level
  resolution.
- **Generic CSV (any state)**: any file with `ZIP`, `COUNTY`/`CITY`, and a
  rate column works the same way.

### Manual setup (quick test, single ZIP)

For testing a single ZIP without downloading a file, create the three
records by hand under US Sales Tax → Rate Database:
1. **Jurisdictions** — name, type (county/city), state.
2. **ZIP Mappings** — the ZIP code, pointing to that jurisdiction.
3. **Tax Rates** — the actual rate values on that jurisdiction.

### Nexus is independent of rate data

Creating a **Nexus** record (US Sales Tax → Configuration → Nexus) only
marks that the company has a legal obligation to collect tax in that state —
it does not create or require any jurisdiction, ZIP mapping, or rate. Both
are needed independently before a sale order calculates a non-zero local tax.

### Zero-tax lines always carry an explicit tax, never an empty tax field

When a line ends up with 0% tax, the engine always assigns a real
`account.tax` record rather than leaving the line untaxed:

- **Exempt product category or no nexus in that state** — assigned the
  shared `US Sales Tax - Exempt (0%)` tax (one tax for both reasons, across
  all states).
- **A state with a genuine 0% combined rate** (e.g. Oregon, Montana — states
  with no sales tax at all) — assigned `US Sales Tax {state} 0%`, the same
  per-state-and-rate tax used for any other rate.

This is deliberate: an empty `tax_id` is indistinguishable from "tax was
never calculated" on an invoice or in a tax report filtered/grouped by
`account.tax`/`account.tax.group`. An explicit 0% tax record shows that the
line was evaluated and a deliberate "no tax due" determination was made —
the kind of audit trail a sales-tax-exempt line should leave behind.

The *specific* reason for a 0% line (which product category, which state,
nexus or no nexus) is not encoded in the tax's name — that level of detail
already lives on `us.tax.calculation.log`, one record per calculation. The
tax itself only needs to answer "was this evaluated, and is it taxable" at
a glance.

**Migration note**: if you had ad-hoc reports filtering for lines with no
`tax_id`/`tax_ids` at all to flag "missing tax" cases, those lines will stop
matching once they carry the explicit 0% tax — this is the intended effect
of this change, not a regression.
