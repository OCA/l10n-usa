# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestSourcing(UsTaxBaseTest):
    """Unit tests for origin/destination sourcing (`_sourcing_zip`).

    Destination-based sales rate the buyer's ZIP; intrastate sales in an
    origin-based state rate the seller's ship-from ZIP. Interstate sales are
    always destination-based.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["us.tax.engine.service"]
        cls.company = cls.env.company
        cls.tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", cls.us.id)], limit=1
        )

    def _set_origin(self, state, zip_code):
        self.company.partner_id.write(
            {"country_id": self.us.id, "state_id": state.id, "zip": zip_code}
        )

    def test_destination_based_state_keeps_buyer_zip(self):
        # FL is not origin-based → always rate the destination ZIP.
        self._set_origin(self.fl, "33102")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "33101", "FL"),
            "33101",
        )

    def test_origin_based_intrastate_uses_seller_zip(self):
        # TX is origin-based; seller in TX → rate the seller's ship-from ZIP.
        self._set_origin(self.tx, "75001")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "77001", "TX"),
            "75001",
        )

    def test_origin_based_interstate_keeps_buyer_zip(self):
        # Buyer in TX (origin-based) but seller is in FL → interstate → dest ZIP.
        self._set_origin(self.fl, "33101")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "77001", "TX"),
            "77001",
        )

    def test_ca_excluded_from_origin_sourcing(self):
        # CA is a hybrid state we deliberately exclude → destination ZIP.
        ca = self.env["res.country.state"].search(
            [("code", "=", "CA"), ("country_id", "=", self.us.id)], limit=1
        )
        self._set_origin(ca, "90001")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "90210", "CA"),
            "90210",
        )

    def test_origin_based_blank_seller_zip_falls_back_to_destination(self):
        # Origin-based, seller in-state but no ship-from ZIP → fall back to dest.
        # It warns about the misconfiguration; assert (and swallow) that warning
        # so it doesn't trip the OCA checklog gate.
        self._set_origin(self.tx, "")
        logger = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"
        with self.assertLogs(logger, level="WARNING"):
            self.assertEqual(
                self.service._sourcing_zip(
                    False, False, self.company.id, "77001", "TX"
                ),
                "77001",
            )
