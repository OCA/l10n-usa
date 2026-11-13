## Automatic tax calculation

**Settings → Accounting → US Sales Tax Engine → Automatic Tax Calculation**
is off by default. With it off, tax is only calculated when you press
**Calculate US Tax** on the document. With it on, the engine also runs on
its own:

- when a quotation is confirmed and when a customer invoice is posted;
- whenever a draft document changes in a way that affects the tax — a
  quantity, a price, a product, a line added, the customer address, the
  exemption certificate or the document date;
- on the daily **US Tax: Recalculate Outdated Sales Orders** and **US
  Tax: Recalculate Outdated Invoices** crons.

A recalculation that is not already in the cache consumes external API
calls, which is why the setting is opt-in. Unticking **Enable US Sales
Tax Engine** turns the automation off with it.

## Scheduled actions

The module ships four scheduled actions, all under **Settings →
Technical → Scheduled Actions**, all running as OdooBot.

**US Tax: Recalculate Outdated Sales Orders** and **US Tax: Recalculate
Outdated Invoices** (daily) — described under *Usage*.

**US Tax: Purge Expired Cache** (daily) — archives the entries in
**US Sales Tax → Rate Database → API Cache** whose expiry has passed.
An API response is cached per ZIP, state, fiscal category and month for
as long as **Cache TTL (hours)** says, so that repeated calculations on
the same address cost no external call. The cron only archives: nothing
is deleted, and the archived entries stay readable with the *Archived*
filter, which keeps the record of what rate was applied and when.

**US Tax: Reset Monthly API Call Counters** (monthly) — sets
**Calls This Month** back to zero on every provider and re-arms the
warning that fires at 80% of **Monthly Call Limit**. It exists because
providers bill per calendar month while Odoo counts continuously; a
counter that never resets would leave every provider looking exhausted.
A provider with a limit of 0 is unlimited and is not affected in
practice.


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
