# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Resolve a US address to its SST jurisdiction set via the boundary file.

Implements the SST mandatory 3-tier fallback: try an address-level (``A``)
match first when a street + house number are available, then ZIP+4 (``4``),
then 5-digit ZIP (``Z``). The first matching boundary row's jurisdictions are
returned. ZIPs are zero-padded fixed-width strings, so lexicographic range
comparison equals numeric comparison.
"""

import logging

_logger = logging.getLogger(__name__)


class SstResolver:
    def __init__(self, env):
        self.env = env

    def resolve(self, state, zip5, doc_date, zip4=None, house_number=None):
        """Return the us.tax.jurisdiction recordset for an address, or empty."""
        boundary = (
            self._match_address(state, zip5, zip4, house_number, doc_date)
            or self._match_zip4(state, zip5, zip4, doc_date)
            or self._match_zip5(state, zip5, doc_date)
        )
        if not boundary:
            return self.env["us.tax.jurisdiction"]
        return boundary.jurisdiction_ids

    # ── Tier matchers (A → 4 → Z) ─────────────────────────────────────────────

    def _date_domain(self, doc_date):
        return [
            "|",
            ("begin_date", "=", False),
            ("begin_date", "<=", doc_date),
            "|",
            ("end_date", "=", False),
            ("end_date", ">=", doc_date),
        ]

    def _zip_domain(self, zip5):
        # Either a single ZIP on the row, or zip5 within the row's ZIP range.
        return [
            "|",
            ("zip", "=", zip5),
            "&",
            ("zip_low", "<=", zip5),
            ("zip_high", ">=", zip5),
        ]

    def _match_zip5(self, state, zip5, doc_date):
        if not zip5:
            return self.env["us.tax.boundary"]
        domain = (
            [("state_id", "=", state.id), ("record_type", "=", "Z")]
            + self._date_domain(doc_date)
            + self._zip_domain(zip5)
        )
        return self.env["us.tax.boundary"].search(domain, limit=1)

    def _match_zip4(self, state, zip5, zip4, doc_date):
        if not (zip5 and zip4):
            return self.env["us.tax.boundary"]
        domain = (
            [
                ("state_id", "=", state.id),
                ("record_type", "=", "4"),
                ("zip4_low", "<=", zip4),
                ("zip4_high", ">=", zip4),
            ]
            + self._date_domain(doc_date)
            + self._zip_domain(zip5)
        )
        return self.env["us.tax.boundary"].search(domain, limit=1)

    def _match_address(self, state, zip5, zip4, house_number, doc_date):
        if not (zip5 and house_number):
            return self.env["us.tax.boundary"]
        num = self._as_int(house_number)
        if num is None:
            return self.env["us.tax.boundary"]
        # Address ranges are variable-width integers, so the low/high containment
        # check must be numeric (a SQL string compare breaks across digit widths,
        # e.g. "300" <= "2000" is False lexicographically). Fetch the ZIP's A
        # rows for the date, then range- and odd/even-filter in Python.
        domain = [
            ("state_id", "=", state.id),
            ("record_type", "=", "A"),
            ("zip", "=", zip5),
        ] + self._date_domain(doc_date)
        for boundary in self.env["us.tax.boundary"].search(domain):
            low = self._as_int(boundary.addr_low)
            high = self._as_int(boundary.addr_high)
            if low is None or high is None or not (low <= num <= high):
                continue
            if self._odd_even_ok(boundary.odd_even, num):
                return boundary
        return self.env["us.tax.boundary"]

    @staticmethod
    def _as_int(value):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @classmethod
    def _odd_even_ok(cls, odd_even, num):
        if not odd_even or odd_even == "B":
            return True
        num = cls._as_int(num)
        if num is None:
            return True
        return (odd_even == "O") == (num % 2 == 1)
