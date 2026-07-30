This module turns the sales tax collected by `l10n_us_sales_tax_engine`
into per-jurisdiction returns ready for filing.

US state returns require collected tax to be reported broken down by
jurisdiction level — state, county, city and special districts. The
engine books each rate component as its own `account.tax` (tagged with
its jurisdiction level and state), so this module can aggregate the
posted tax lines into a return for one state over a filing period and
export a worksheet with the figures each state return expects.
