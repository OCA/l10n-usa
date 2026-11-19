This module extends the US Sales Tax Engine (`l10n_us_sales_tax_engine`) so
that sales can be rated with the address of the company or branch that sells
instead of the customer's address.

Each company chooses whether new sales orders and customer invoices are rated,
by default, with the customer's delivery address (destination) or with the
company address (origin). Each draft document keeps its own *Tax Based on
Company Address* check, so a company can mix in-store pickups and shipped
orders. This covers intrastate sales in origin-based states and in-store sales
in any state.

Every calculation log records whether the customer's or the company's address
was rated.
