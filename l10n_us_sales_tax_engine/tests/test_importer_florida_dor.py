# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import io

from ..importers.importer_florida_dor import FL_COUNTY_SURTAX, FloridaDorImporter
from .common import UsTaxBaseTest


class TestImporterFloridaDor(UsTaxBaseTest):
    """Synthetic, small-scale rows mirroring the real DOR export columns
    (MAILCITY, no SURTAX) — never the full 655k-row county file in tests."""

    def _run_import(self, csv_content, effective_date="2026-07-01"):
        batch = self.env["us.tax.import.batch"].create(
            {
                "source": "florida_dor",
                "file_name": "test.csv",
                "state_id": self.fl.id,
                "effective_date": effective_date,
                "status": "running",
            }
        )
        importer = FloridaDorImporter(self.env, batch)
        # Call _import_from_file directly: these fixtures are intentionally
        # small, and run()'s ">100 bytes" heuristic would otherwise route
        # them to the unrelated _import_builtin path.
        importer._import_from_file(csv_content.encode(), self.fl, effective_date)
        return batch

    def test_real_format_columns_resolve_via_county_table(self):
        """The real DOR export has MAILCITY (not CITY) and no SURTAX column —
        the rate must come from FL_COUNTY_SURTAX by county name, and rows are
        deduplicated to one jurisdiction per county and one ZIP mapping per
        unique ZIP, not one per address row."""
        csv_content = (
            "NUMBER,MAILCITY,ZIP,COUNTYID,COUNTY,JURISDICTION,EFFDATE,TDTCODE\n"
            "399,HIALEAH,33178,086,BROWARD,HIALEAH,07/01/2026,0\n"
            "1005,MIAMI,33178,086,BROWARD,UNINCORPORATED,07/01/2019,0\n"
            "1011,MIAMI,33179,086,BROWARD,UNINCORPORATED,07/01/2019,0\n"
        )
        self._run_import(csv_content)

        jur = self.env["us.tax.jurisdiction"].search(
            [
                ("state_id", "=", self.fl.id),
                ("county", "=", "BROWARD"),
                ("type", "=", "county"),
            ]
        )
        self.assertEqual(len(jur), 1, "must dedupe to a single county jurisdiction")

        rate = self.env["us.tax.rate"].search(
            [("jurisdiction_id", "=", jur.id), ("effective_date", "=", "2026-07-01")]
        )
        self.assertEqual(rate.county_rate, FL_COUNTY_SURTAX["BROWARD"])
        self.assertNotEqual(rate.county_rate, 0.0)

        zip_maps = self.env["us.tax.zip.mapping"].search(
            [("jurisdiction_id", "=", jur.id)]
        )
        self.assertEqual(
            len(zip_maps), 2, "33178 and 33179, deduplicated from 3 address rows"
        )
        zip_33178 = zip_maps.filtered(lambda m: m.zip == "33178")
        self.assertEqual(
            zip_33178.city, "HIALEAH", "first MAILCITY occurrence wins for a ZIP"
        )

    def test_idempotent_on_second_run(self):
        """Importing the same file twice must not duplicate jurisdictions,
        rates or ZIP mappings."""
        csv_content = "MAILCITY,ZIP,COUNTY\nHIALEAH,33178,BROWARD\n"
        self._run_import(csv_content)
        self._run_import(csv_content)

        jur_count = self.env["us.tax.jurisdiction"].search_count(
            [("state_id", "=", self.fl.id), ("county", "=", "BROWARD")]
        )
        self.assertEqual(jur_count, 1)
        zip_count = self.env["us.tax.zip.mapping"].search_count([("zip", "=", "33178")])
        self.assertEqual(zip_count, 1)

    def test_surtax_column_takes_priority_over_builtin_table(self):
        """If a DOR release does include a SURTAX column, use it instead of
        the hardcoded fallback table."""
        csv_content = "MAILCITY,ZIP,COUNTY,SURTAX\nNAPLES,33999,COLLIER,2.5\n"
        self._run_import(csv_content)

        jur = self.env["us.tax.jurisdiction"].search(
            [("state_id", "=", self.fl.id), ("county", "=", "COLLIER")]
        )
        rate = self.env["us.tax.rate"].search([("jurisdiction_id", "=", jur.id)])
        self.assertAlmostEqual(rate.county_rate, 0.025, places=4)

    def test_unknown_county_defaults_to_zero_surtax(self):
        """A county absent from FL_COUNTY_SURTAX and without a SURTAX column
        must not raise — it falls back to 0.0, not a missing-key error."""
        csv_content = "MAILCITY,ZIP,COUNTY\nNOWHERE,33000,NONEXISTENT COUNTY\n"
        self._run_import(csv_content)

        jur = self.env["us.tax.jurisdiction"].search(
            [("state_id", "=", self.fl.id), ("county", "=", "NONEXISTENT COUNTY")]
        )
        rate = self.env["us.tax.rate"].search([("jurisdiction_id", "=", jur.id)])
        self.assertEqual(rate.county_rate, 0.0)

    def test_run_dispatches_to_file_import_for_real_sized_upload(self):
        """End-to-end through run() — the path the wizard actually calls.
        A real-sized upload (>100 bytes) must hit _import_from_file, not the
        unrelated built-in county table."""
        rows = "\n".join(
            f"{n},HIALEAH,33178,086,BROWARD,HIALEAH,07/01/2026,0" for n in range(10)
        )
        csv_content = (
            "NUMBER,MAILCITY,ZIP,COUNTYID,COUNTY,JURISDICTION,EFFDATE,TDTCODE\n"
            + rows
            + "\n"
        )
        self.assertGreater(len(csv_content), 100)

        batch = self.env["us.tax.import.batch"].create(
            {
                "source": "florida_dor",
                "file_name": "test.csv",
                "state_id": self.fl.id,
                "effective_date": "2026-07-01",
                "status": "running",
            }
        )
        importer = FloridaDorImporter(self.env, batch)
        importer.run(io.BytesIO(csv_content.encode()), self.fl, "2026-07-01")

        zip_map = self.env["us.tax.zip.mapping"].search([("zip", "=", "33178")])
        self.assertEqual(len(zip_map), 1, "10 duplicate rows must dedupe to 1 ZIP")
        self.assertEqual(zip_map.city, "HIALEAH")
