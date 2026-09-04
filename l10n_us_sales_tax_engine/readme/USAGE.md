## Calculating US sales tax

**Calculate US Tax** on the sale order and the customer invoice runs the
engine on demand. With **Automatic Tax Calculation** on, the engine also
runs on its own — both settings live under *Settings → Accounting → US
Sales Tax Engine* and are described in *Configuration*.

### Outdated tax and the warning banner

Editing the *customer's* address does not recalculate every draft
document that customer has — that would block the transaction on a
customer with hundreds of quotations. Instead, each document keeps a
fingerprint of the inputs the engine reads, and those documents show a
warning banner saying the tax is outdated.

An outdated document is brought up to date in three ways: the next edit
to the document itself, the **Recalculate US Tax** button on the banner,
or the daily cron.

A document the engine was never asked to price is not outdated and shows
no banner. One whose calculation was attempted and failed is, even when
that was its first calculation and it carries no tax yet.

"Outdated" means *outdated and still recalculable*. A document the
engine can no longer write a tax onto — a posted or cancelled invoice, a
locked sale order, one that is fully invoiced — never shows the banner
and never reaches the cron, and both **Calculate US Tax** buttons are
hidden on it. Odoo freezes `tax_ids` on a posted move and protects
`tax_id` on a locked order, so a button there would clear the banner
without changing a single tax. To recalculate such a document, reset the
invoice to draft or unlock the order first; it becomes outdated again on
its own if its inputs moved while it was out.

For the same reason the fingerprint itself is only maintained inside
those states. A customer address change marks the customer's draft
documents and leaves the rest exactly as they were, `write_date`
included — vendor bills of that customer among them.

One case the banner cannot catch: when a document has no shipping
address of its own and the engine falls back to the customer's
`delivery` child contact, a change to *that contact's* address is not
detected. Use the **Calculate US Tax** button on those documents.

### Which changes mark a document as outdated

The fingerprint holds what the engine actually reads: the ZIP, the
state, the city and the country of the address it would use, the
customer's exemption flag, the document date, the company, and each
line's fiscal category and subtotal. A change that does not move any of
those cannot change the tax, so it deliberately raises no banner. Two
cases come up often:

- **ZIP+4 and other ZIP formatting.** The engine truncates the ZIP to
  its first five digits, so `33101`, `33101-4521` and `331014521` are
  the same ZIP to it. Rewriting one as another changes no rate and
  raises no banner.
- **Street.** The rate is resolved from ZIP, state, fiscal category and
  date; the street is not part of the cache key, so editing it returns
  the very same rate. It raises no banner either.

Which address the fingerprint watches depends on **Tax Based on Shipping
Address** on the sale order: with it ticked the delivery address counts
and the invoice address does not, and the other way round. Note that
Odoo copies a company contact's address down to its child contacts, so
editing the customer's address usually updates the delivery contact the
order points at as well.

### The recalculation cron

**Settings → Technical → Scheduled Actions → US Tax: Recalculate
Outdated Sales Orders** and **US Tax: Recalculate Outdated Invoices**,
both daily. One per document model, so that a failure processing sale
orders does not discard the invoice work of the same run: Odoo rolls
back a scheduled action as a whole.

*Why it exists.* Changing one customer's address can outdate every draft
quotation and invoice that customer has. Recalculating them on the spot
would hold the transaction open for as long as it takes to price
hundreds of documents, and would consume an API call for each one that
is not cached — while the user waits on a partner form. So the
recalculation is deferred, and the cron is the unattended floor under
the other two routes: it catches the documents nobody reopened and
nobody pressed the button on.

*What it does.* On each run it looks for the documents the automation
tried at least once and whose inputs no longer match, in the states the
automation is allowed to touch — draft, sent and unlocked sale orders
that are not fully invoiced, and draft customer invoices and credit
notes. It recalculates up to 200 of them per run and leaves the rest for
the next one.

A document whose calculation fails keeps its old fingerprint, so the
next run picks it up again — including a document whose very first
calculation failed and therefore has no fingerprint of its own yet. To
stop those from monopolising every run, every attempt stamps the
document with its time, successful or not, and the queue is ordered by
it: never-attempted documents first, then the least recently attempted.

*Cost.* Every recalculation that is not already cached consumes an
external API call, so the cron is subject to **Automatic Tax
Calculation**: with the setting off, a run exits immediately without
touching anything. You can also lower its frequency or deactivate it
from the scheduled action itself.

### How automatic recalculation is triggered

Every `create()` and `write()` on the sale order, the customer invoice
and their two line models funnels into a single method,
`_us_tax_auto_recalculate()`, which reaches the engine only when all
four of these hold:

1. **`us_tax_skip_auto` is not in the context.** The engine writes the
   tax back onto the lines, and that write goes through the same
   overrides; this key is what stops it from calculating a second time
   on its own output.
2. **Both settings are on.** `l10n_us_tax.engine_active` and
   `l10n_us_tax.auto_calculate` are read at runtime instead of being
   trusted from the settings form, because `set_param()` can write
   either one without going through it.
3. **The document is in an allowed state.** Draft, sent and unlocked
   sale orders that are not fully invoiced; draft customer invoices and
   credit notes. Posted, cancelled, locked and fully invoiced documents
   are out, because Odoo will not let a tax be written on them.
4. **The fingerprint changed.** `us_tax_input_hash` differs from
   `us_tax_calculated_hash`.

A calculation the engine cannot apply does not count as one. The tax
already written on the earlier lines is rolled back, the audit row is
recorded as an error, and `us_tax_calculated_hash` is left alone, so the
document stays outdated and the cron picks it up again. Only
`us_tax_source` and **Tax Calculated** are updated, so the attempt is
still visible on the document.

**The `Block` failure policy applies to the manual calculation only.**
With *API Failure Policy* set to *Block — prevent document
confirmation*, a run where every provider failed raises, and the
**Calculate US Tax** button shows that error to the user. On the
automatic path the error is logged and swallowed instead: a provider
outage would otherwise make every draft sale order and customer invoice
impossible to edit, confirm or post. Nothing is lost by that — the
document keeps its previous tax, the audit row is recorded as an error,
and the banner and the cron keep asking for the calculation until a
provider answers.

The fourth gate is the only trigger there is: nowhere in the module is
there a list of "fields that cause a recalculation". A field outside the
fingerprint's `@api.depends` leaves both hashes equal, so writing it
never reaches the engine.

**Creation is deliberately asymmetric.** An invoice calculates tax when
it is created; a quotation does not. The engine writes a
`us.tax.calculation.log` row on every run, including the runs that price
nothing, and a quotation is routinely created empty and filled in
afterwards — calculating on creation would log a row for each of those.
A quotation gets its tax on its first line and on confirmation.

**Extending the fingerprint from another module.** Override the compute
with your own dependencies and call `super()`:

```python
class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends("partner_id.my_custom_field")
    def _compute_us_tax_input_hash(self):
        super()._compute_us_tax_input_hash()
```

`Field.get_depends()` collects the dependencies of every override of the
compute in the MRO, so yours are added to the ones this module declares.
Redefining the field with the `depends=` keyword instead **replaces**
that list rather than extending it, which silently drops all of them.

The four hooks the dependency list is built from —
`_us_tax_partner_fields()`, `_us_tax_partner_address_fields()`,
`_us_tax_extra_depends()` and `_us_tax_state_depends()` — are
overridable too. All four are evaluated once per registry build, so they
have to return static lists, and a change only takes effect when the
module is upgraded.

A module adding a third document type inherits `us.tax.auto.mixin`,
implements `_us_tax_get_address()`, `_us_tax_get_date()`,
`_us_tax_get_lines()`, `_us_tax_engine_run()`, `_us_tax_state_domain()`
and `_us_tax_state_depends()`, and ships its own `ir.cron` record
pointing at its model and calling
`model._us_tax_cron_recalculate_stale()`. The first three hooks are also
what `us.tax.engine.service` reads, so overriding one moves the
fingerprint and what actually gets taxed together.

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
