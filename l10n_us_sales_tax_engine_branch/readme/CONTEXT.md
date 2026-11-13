The US Sales Tax Engine (`l10n_us_sales_tax_engine`) is designed for a single
company that ships to its customers: it looks for the nexus on the exact company
of the document and always rates the tax with an address of the customer.
Companies organised in branches, and companies that collect tax at the point of
sale, need more than that:

- A branch should collect tax wherever its parent company has nexus. With the
  engine alone, a nexus declared only on the parent company leaves the branches
  exempt, so the same nexus has to be repeated on every branch.
- In origin-based states the rate is the one of the seller's location, and in
  destination-based states a sale picked up in the store is taxed where the
  store is. Both cases need the address of the selling company or branch
  instead of the customer's.

This module keeps the engine's calculation and only changes which nexus and
which address it uses. It does not hold a list of origin-based states: each
company chooses its default sourcing and each document can override it. The
origin address is the company address, not the one of a warehouse.

It is useful in multi-company setups that use branches (companies with a parent
company), and also for a single company that sells over the counter. A company
without a parent that keeps destination sourcing is rated exactly as with the
engine alone.
