No configuration. Once installed alongside ``sale_stock``, origin-based sales
tax (intrastate sales in origin-based states) is sourced from the order's
**shipping warehouse** address instead of the company address, falling back to
the company when no warehouse can be determined.

Note: an invoice that consolidates orders shipped from **different** warehouses
is sourced from one of them (logged as a warning); per-line warehouse sourcing
is out of scope.
