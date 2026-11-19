The US Sales Tax Engine (`l10n_us_sales_tax_engine`) always rates the tax with
an address of the customer. That is right for a company that ships to its
customers, but not for every sale:

- In origin-based states, a sale made inside the state is taxed at the rate of
  the seller's location, not the customer's.
- In any state, a sale picked up at the store is taxed where the store is, even
  if the customer lives in another state.

Both cases need the address of the selling company instead of the customer's.

This module keeps the engine's calculation and only changes which address it
rates. It does not hold a list of origin-based states: each company chooses its
default sourcing and each document can override it. With origin sourcing, a
document starts rated with the company address only when the delivery address
is in the company's state or has none; a shipment to another state starts with
the customer address, and an in-store pickup by an out-of-state customer is
checked by hand. The origin address is the company address, not the one of a
warehouse.

It works for a single company and for each branch of a company tree, since
every branch has its own address and its own sourcing setting. A company that
keeps destination sourcing is rated exactly as with the engine alone.
