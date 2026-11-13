This module extends the US Sales Tax Engine (`l10n_us_sales_tax_engine`) for
companies organised in branches, and lets sales be rated with the address of
the company or branch that sells instead of the customer's address.

- **Nexus inherited from parent companies.** A branch collects tax in a state
  when it, or any of its parent companies at any depth, has an active nexus
  there. A nexus declared on a sibling branch does not count.
- **Origin-based sourcing.** Each company chooses whether new sales orders and
  customer invoices are rated, by default, with the customer's delivery address
  (destination) or with the company address (origin). Each draft document keeps
  its own *Tax Based on Company Address* check, so a branch can mix in-store
  pickups and shipped orders. This covers origin-based states and in-store
  sales in destination-based states.

Every calculation log records whether the customer's or the company's address
was rated.
