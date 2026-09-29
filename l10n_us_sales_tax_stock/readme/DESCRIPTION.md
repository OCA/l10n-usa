Bridge between the US sales-tax engine and Inventory.

Origin-based states rate an intrastate sale from the seller's **ship-from**
address. The engine sources that from the company address by default; this
module resolves it from the **shipping warehouse** instead - the warehouse on
the sale order (or the warehouse of the originating order for an invoice) -
falling back to the company address when no warehouse can be determined.

Installs automatically when both `l10n_us_sales_tax_engine` and `sale_stock`
are present.
