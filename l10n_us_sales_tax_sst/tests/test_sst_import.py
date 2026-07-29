# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date

from odoo.tests.common import TransactionCase

from ..services.importer_sst import SstImporter
from ..services.provider_local_sst import ProviderLocalSst
from ..services.sst_resolver import SstResolver
from .common import BOUNDARY_CSV, RATE_CSV, boundary_row


class TestSstImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.batch = cls.env["us.tax.import.batch"].create(
            {"source": "sst", "state_id": cls.wy.id}
        )
        importer = SstImporter(cls.env, cls.batch)
        importer.import_rate_file(RATE_CSV, cls.wy)
        importer.import_boundary_file(BOUNDARY_CSV, cls.wy)

    def test_rate_import_creates_fips_jurisdictions(self):
        Jur = self.env["us.tax.jurisdiction"]
        state = Jur.search([("state_id", "=", self.wy.id), ("type", "=", "state")])
        county = Jur.search(
            [("state_id", "=", self.wy.id), ("fips_county", "=", "021")]
        )
        district = Jur.search(
            [("state_id", "=", self.wy.id), ("district_code", "=", "55555")]
        )
        self.assertEqual(len(state), 1)
        self.assertEqual(state.fips_state, "56")
        self.assertEqual(county.type, "county")
        self.assertEqual(district.type, "district")
        # Leading zeros preserved (parsed as strings, not ints).
        self.assertEqual(county.fips_county, "021")

    def test_rate_values_land_in_right_columns(self):
        Rate = self.env["us.tax.rate"]
        county = self.env["us.tax.jurisdiction"].search(
            [("state_id", "=", self.wy.id), ("fips_county", "=", "021")]
        )
        rate = Rate.get_rate_for_date(county.id, date(2025, 1, 1))
        self.assertAlmostEqual(rate.county_rate, 0.01, places=5)
        self.assertAlmostEqual(rate.total_rate, 0.01, places=5)

    def test_jtype_single_digit_classifies_correctly(self):
        """Some member states (e.g. Tennessee) emit unpadded jurisdiction
        types ('0' county, '1' city) instead of '00'/'01'; they must still
        classify by level, not fall through to 'district'."""
        from ..services.sst_common import jtype_to_level

        self.assertEqual(jtype_to_level("0"), "county")
        self.assertEqual(jtype_to_level("1"), "city")
        self.assertEqual(jtype_to_level("00"), "county")
        self.assertEqual(jtype_to_level("45"), "state")
        self.assertEqual(jtype_to_level("63"), "district")

    def test_boundary_links_jurisdiction_set(self):
        boundary = self.env["us.tax.boundary"].search(
            [("state_id", "=", self.wy.id), ("zip", "=", "82001")]
        )
        self.assertEqual(len(boundary), 1)
        self.assertEqual(boundary.record_type, "Z")
        types = set(boundary.jurisdiction_ids.mapped("type"))
        self.assertEqual(types, {"state", "county", "district"})

    def test_boundary_real_layout_blank_zip_uses_range(self):
        """Real published SST boundary records leave the MTSA single-zip
        (col 15) blank and carry the zip in the low/high RANGE (cols 17/19),
        with FIPS State / Indicator / County / Place at cols 22-25 and special
        districts from col 29 (validated against Ohio's published file). A
        ZIP5 query must resolve via the range, not the blank zip field — the
        primary fixture additionally populates col 15, so this locks in
        real-file compatibility."""
        row = [""] * 29
        row[0] = "Z"  # ZIP5-level record (the resolver's ZIP5 path requires "Z")
        row[1] = "20200101"
        row[2] = "29991231"
        row[17] = "82001"  # zip5 low (MTSA single-zip @15 left blank, as real files do)
        row[19] = "82001"  # zip5 high
        row[22] = "56"  # FIPS State
        row[23] = "56"  # FIPS State Indicator (== state code → state tax applies)
        row[24] = "021"  # FIPS County
        row += ["ST", "55555", "63"]  # special-district triplet
        batch = self.env["us.tax.import.batch"].create(
            {"source": "sst", "state_id": self.wy.id}
        )
        SstImporter(self.env, batch).import_boundary_file(",".join(row), self.wy)
        boundary = self.env["us.tax.boundary"].search(
            [("state_id", "=", self.wy.id), ("zip_low", "=", "82001")], limit=1
        )
        self.assertTrue(boundary, "real zip+4 row should import")
        self.assertFalse(boundary.zip, "MTSA single-zip is blank on a '4' record")
        self.assertEqual(
            set(boundary.jurisdiction_ids.mapped("type")),
            {"state", "county", "district"},
        )
        # The resolver must still match via the zip RANGE, not the empty zip.
        self.assertEqual(
            len(SstResolver(self.env).resolve(self.wy, "82001", date(2025, 1, 1))), 3
        )

    def test_resolver_returns_full_jurisdiction_set(self):
        jurisdictions = SstResolver(self.env).resolve(
            self.wy, "82001", date(2025, 1, 1)
        )
        self.assertEqual(len(jurisdictions), 3)
        total = sum(
            self.env["us.tax.rate"].get_rate_for_date(j.id, date(2025, 1, 1)).total_rate
            for j in jurisdictions
        )
        self.assertAlmostEqual(total, 0.055, places=5)

    def test_sst_registers_local_provider_override(self):
        from ..services.provider_local_sst import ProviderLocalSst

        rec = (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "local")], limit=1)
        )
        self.assertIs(rec._get_provider_service(), ProviderLocalSst)
        # The override swaps the class registered under "local", not the key.
        self.assertIn("local", rec._provider_service_classes())

    def test_resolver_misses_unknown_zip(self):
        jurisdictions = SstResolver(self.env).resolve(
            self.wy, "00000", date(2025, 1, 1)
        )
        self.assertFalse(jurisdictions)

    def test_reimport_is_idempotent(self):
        """Re-importing the same quarter upserts, not duplicates."""
        before = self.env["us.tax.rate"].search_count(
            [("jurisdiction_id.state_id", "=", self.wy.id)]
        )
        SstImporter(self.env, self.batch).import_rate_file(RATE_CSV, self.wy)
        after = self.env["us.tax.rate"].search_count(
            [("jurisdiction_id.state_id", "=", self.wy.id)]
        )
        self.assertEqual(before, after)

    def test_boundary_reimport_replaces_not_duplicates(self):
        before = self.env["us.tax.boundary"].search_count(
            [("state_id", "=", self.wy.id)]
        )
        SstImporter(self.env, self.batch).import_boundary_file(BOUNDARY_CSV, self.wy)
        after = self.env["us.tax.boundary"].search_count(
            [("state_id", "=", self.wy.id)]
        )
        self.assertEqual(before, after)

    def _local_provider(self):
        rec = (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", "local")], limit=1)
        )
        return ProviderLocalSst(rec)

    def test_food_drug_reduced_rate(self):
        """A FOOD product uses the jurisdiction's reduced food/drug rate."""
        payload = {"zip": "82001", "state": "WY", "date": "2025-01-01"}
        general = self._local_provider().get_rate(
            {**payload, "product_category": "TANGIBLE"}
        )
        food = self._local_provider().get_rate({**payload, "product_category": "FOOD"})
        # State rate drops 4% → 2% for food; county/district unchanged.
        self.assertAlmostEqual(general["total_rate"], 0.055, places=4)
        self.assertAlmostEqual(food["total_rate"], 0.035, places=4)
        state_food = next(j for j in food["jurisdictions"] if j["level"] == "state")
        self.assertAlmostEqual(state_food["rate"], 0.02, places=4)

    def test_provider_falls_back_to_engine_when_no_sst_data(self):
        """A state with engine ZIP-mapping data but no SST boundary falls back."""
        ny = self.env["res.country.state"].search(
            [("code", "=", "NY"), ("country_id", "=", self.us.id)], limit=1
        )
        jur = self.env["us.tax.jurisdiction"].create(
            {"name": "NY County", "type": "county", "state_id": ny.id}
        )
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jur.id,
                "state_rate": 0.04,
                "county_rate": 0.045,
                "effective_date": "2020-01-01",
            }
        )
        self.env["us.tax.zip.mapping"].create(
            {"zip": "10001", "state_id": ny.id, "jurisdiction_id": jur.id}
        )
        result = self._local_provider().get_rate(
            {"zip": "10001", "state": "NY", "date": "2025-01-01"}
        )
        # No SST boundary for NY → engine local path → its 8.5% combined rate.
        self.assertAlmostEqual(result["total_rate"], 0.085, places=4)
        # Rooftop resolution names the local jurisdiction even on the SST
        # fallback, so a per-jurisdiction breakdown comes back.
        self.assertIn("jurisdictions", result)
        # Fallback is visible, not silent.
        self.assertTrue(result.get("fallback"))
        self.assertTrue(result.get("fallback_reason"))

    def test_multi_district_boundary_links_all(self):
        """A boundary row with two district triplets links both districts."""
        ut = self.env["res.country.state"].search(
            [("code", "=", "UT"), ("country_id", "=", self.us.id)], limit=1
        )
        rate_csv = "\n".join(
            [
                "49,45,49,0.0485,0.0485,0,0,20200101,29991231",
                "49,63,80001,0.001,0.001,0,0,20200101,29991231",
                "49,63,80002,0.002,0.002,0,0,20200101,29991231",
            ]
        )
        boundary_csv = boundary_row(
            zip5="84101", fips_state="49", fips_county="", districts=("80001", "80002")
        )
        importer = SstImporter(self.env, self.batch)
        importer.import_rate_file(rate_csv, ut)
        importer.import_boundary_file(boundary_csv, ut)
        jurisdictions = SstResolver(self.env).resolve(ut, "84101", date(2025, 1, 1))
        district_codes = set(
            jurisdictions.filtered(lambda j: j.type == "district").mapped(
                "district_code"
            )
        )
        self.assertEqual(district_codes, {"80001", "80002"})

    def test_resolver_address_and_zip4_tiers(self):
        """A (odd/even + numeric range) → 4 (ZIP+4) → Z fallback ordering."""
        Boundary = self.env["us.tax.boundary"]
        state_jur = self.env["us.tax.jurisdiction"].search(
            [("state_id", "=", self.wy.id), ("type", "=", "state")], limit=1
        )
        common = {
            "state_id": self.wy.id,
            "zip": "82009",
            "begin_date": "2020-01-01",
            "jurisdiction_ids": [(6, 0, state_jur.ids)],
        }
        Boundary.create(
            {
                **common,
                "record_type": "A",
                "addr_low": "100",
                "addr_high": "200",
                "odd_even": "E",
            }
        )
        Boundary.create(
            {
                **common,
                "record_type": "4",
                "zip_low": "82009",
                "zip_high": "82009",
                "zip4_low": "1000",
                "zip4_high": "1099",
            }
        )
        Boundary.create(
            {**common, "record_type": "Z", "zip_low": "82009", "zip_high": "82009"}
        )
        resolver = SstResolver(self.env)
        doc = date(2025, 1, 1)
        # House 150 (even) → address tier matches.
        self.assertTrue(resolver._match_address(self.wy, "82009", None, 150, doc))
        # House 151 (odd) fails the even-only address row.
        self.assertFalse(resolver._match_address(self.wy, "82009", None, 151, doc))
        # ZIP+4 inside the range matches the 4 tier.
        self.assertTrue(resolver._match_zip4(self.wy, "82009", "1050", doc))
        self.assertFalse(resolver._match_zip4(self.wy, "82009", "2000", doc))
        # Z always resolves the ZIP.
        self.assertTrue(resolver._match_zip5(self.wy, "82009", doc))

    def test_open_ended_sentinels(self):
        from ..services.sst_common import parse_sst_date

        # Spec sentinel, real-file sentinel, and blank all mean "open".
        self.assertIsNone(parse_sst_date("29991231"))
        self.assertIsNone(parse_sst_date("99991231"))
        self.assertIsNone(parse_sst_date(""))
        self.assertEqual(str(parse_sst_date("20250115")), "2025-01-15")

    def test_superseded_rate_is_closed(self):
        ia = self.env["res.country.state"].search(
            [("code", "=", "IA"), ("country_id", "=", self.us.id)], limit=1
        )
        importer = SstImporter(self.env, self.batch)
        importer.import_rate_file("19,45,19,0.06,0.06,0,0,20200101,99991231", ia)
        importer.import_rate_file("19,45,19,0.065,0.065,0,0,20260101,99991231", ia)
        jur = self.env["us.tax.jurisdiction"].search(
            [("state_id", "=", ia.id), ("type", "=", "state")], limit=1
        )
        rates = self.env["us.tax.rate"].search(
            [("jurisdiction_id", "=", jur.id)], order="effective_date"
        )
        self.assertEqual(len(rates), 2)
        # Old period is closed the day before the new one; new one stays open.
        self.assertEqual(rates[0].end_date, date(2025, 12, 31))
        self.assertFalse(rates[1].end_date)
        # Resolution on a mid-2025 date returns the old (open-at-the-time) rate.
        self.assertEqual(
            self.env["us.tax.rate"]
            .get_rate_for_date(jur.id, date(2025, 6, 1))
            .state_rate,
            0.06,
        )


class TestSstImportBom(TransactionCase):
    """Some member states publish these files with a UTF-8 BOM.

    Of the 23 states publishing boundary files for 2026Q3, Iowa and Vermont
    do. The BOM otherwise lands in the first field and the opening record is
    rejected as an unknown record type.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        cls.ia = cls.env["res.country.state"].search(
            [("code", "=", "IA"), ("country_id", "=", cls.us.id)], limit=1
        )

    def _batch(self, source):
        return self.env["us.tax.import.batch"].create(
            {
                "source": source,
                "state_id": self.ia.id,
                "effective_date": "2026-07-01",
                "status": "running",
            }
        )

    def test_boundary_file_with_bom_imports(self):
        importer = SstImporter(self.env, self._batch("sst_boundary"))
        importer.import_boundary_file("﻿" + BOUNDARY_CSV, self.ia)
        boundary = self.env["us.tax.boundary"].search(
            [("state_id", "=", self.ia.id)], limit=1
        )
        self.assertTrue(boundary, "a BOM at the start of the file lost the first row")
        self.assertEqual(
            boundary.record_type,
            boundary.record_type.strip("﻿"),
            "record type still carries the BOM",
        )

    def test_lowercase_record_type_imports(self):
        """Minnesota publishes "z" where the other states publish "Z"."""
        importer = SstImporter(self.env, self._batch("sst_boundary"))
        importer.import_boundary_file(BOUNDARY_CSV.replace("Z,", "z,", 1), self.ia)
        boundary = self.env["us.tax.boundary"].search(
            [("state_id", "=", self.ia.id)], limit=1
        )
        self.assertTrue(boundary, "a lower-case record type lost the row")
        self.assertEqual(boundary.record_type, boundary.record_type.upper())

    def test_rate_file_with_bom_imports(self):
        importer = SstImporter(self.env, self._batch("sst_rate"))
        importer.import_rate_file("﻿" + RATE_CSV, self.ia)
        self.assertTrue(
            self.env["us.tax.jurisdiction"].search_count(
                [("state_id", "=", self.ia.id)]
            ),
            "a BOM at the start of the rate file lost the first jurisdiction",
        )
