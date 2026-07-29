This module adds **marketplace facilitator** handling to the US Sales
Tax Engine. In most states a marketplace (Amazon, eBay, Etsy, Walmart,
…) collects and remits sales tax on the seller's behalf, so the seller
must **not** also collect on those orders.

Flag a sale order or invoice with its **Marketplace Facilitator** and
the engine short-circuits the calculation to the `marketplace` source —
no tax is charged (collected by the facilitator). The US tax return
records those sales as an informational `Marketplace Sales` figure
(already part of gross sales and of the non-taxable deductions) to help
you complete a state's marketplace-facilitator deduction line. It is a
memo total, not an automatic entry on the SER export.

Install this only if you sell through marketplaces that collect for you.
