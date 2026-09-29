This module adds **customer / entity sales-tax exemption certificates**
to the US Sales Tax Engine: resale, agricultural, government,
manufacturing, nonprofit, direct-pay and other exemptions.

A certificate records the customer, the reason, the states it covers, an
effective and (optional) expiry date, the signed document, and a
validity status. When a sale ships to a covered state on a date the
certificate is valid, the engine exempts the whole sale and records the
reason (visible in the calculation log). Each reason maps to an SST SER
`ExemptionDeductionBreakout` category so exempt sales can be reported
under the right heading.

## How exemptions map to the return and providers

Each exemption reason carries two mappings: `ser_breakout` places exempt
sales under the right SST SER `ExemptionDeductionBreakout` heading
(Agriculture / Direct Pay / Government-Exempt-Org / Manufacturing /
Resale / Other), and `entity_use_code` (e.g. G resale, H agriculture, A
government) is the Avatax/SST entity-use code for provider interop. So
the chain is: certificate → reason → `ser_breakout` → SER return line,
and reason → `entity_use_code` → external provider.

The model is provider-agnostic — it adapts the OCA
`account_avatax_exemption` shape without the Avatax coupling. v1 fully
exempts a covered sale; e-sign capture, per-state PDF forms and
product-conditional exemption are out of scope.

## Two ways to trigger an exemption

A **certificate** is the primary trigger and the one to prefer: it is
scoped to the states it actually covers, carries the reason and the
certificate number, and stops applying when it expires.

A **fiscal position** flagged *US Tax Exempt* is the second trigger, for
installations that already express "this customer is not taxed here"
the Odoo-native way and do not track the certificates themselves. A
certificate wins when both apply, because it carries the number an
auditor asks for.

## Why the invoice keeps its own copy

The certificate number and reason are written onto the invoice when it
is posted, rather than read back from the customer on demand. By the
time a zero-tax line is questioned, the customer record may have been
edited, the certificate may have lapsed, or the exemption may have been
revoked — all of which answer "is this customer exempt today", which is
not the question being asked. The stored values answer what was true
when the invoice was posted.

