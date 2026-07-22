# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import json

from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestUsTaxApiController(HttpCase):
    """Real JSON-RPC dispatch — Odoo unwraps the envelope's "params" into
    the controller's **kwargs, so a test calling the method directly with
    keyword arguments would not have caught the body/kwargs mismatch bug
    that broke /calculate while /rate_lookup worked."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        us = cls.env.ref("base.us")
        fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", us.id)], limit=1
        )
        jur = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Miami-Dade",
                "type": "county",
                "state_id": fl.id,
                "county": "MIAMI-DADE",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jur.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33101",
                "state_id": fl.id,
                "jurisdiction_id": jur.id,
                "confidence": 1.0,
                "source": "test",
            }
        )

    def _call(self, route, params):
        self.authenticate("admin", "admin")
        response = self.url_open(
            route,
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"},
        )
        return response.json()["result"]

    def test_calculate_reads_params_from_real_jsonrpc_envelope(self):
        """Reproduces the real dispatch path — was returning
        {"error": "zip is required"} even with a valid ZIP before the fix."""
        result = self._call(
            "/api/v1/us_tax/calculate",
            {"zip": "33101", "state": "FL", "amount": 100, "date": "2026-06-26"},
        )
        self.assertNotIn("error", result, result)
        self.assertAlmostEqual(result["total_rate"], 0.07, places=4)
        self.assertAlmostEqual(result["tax_amount"], 7.0, places=2)

    def test_calculate_missing_zip_still_errors(self):
        """The validation itself must still work once a real ZIP isn't sent."""
        result = self._call("/api/v1/us_tax/calculate", {"state": "FL", "amount": 100})
        self.assertEqual(result.get("error"), "zip is required")

    def test_rate_lookup_still_works(self):
        """Regression guard — this endpoint already worked before the fix."""
        result = self._call(
            "/api/v1/us_tax/rate_lookup", {"zip": "33101", "state": "FL"}
        )
        self.assertTrue(result.get("found"))
        self.assertAlmostEqual(result["total_rate"], 0.07, places=4)
