# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import csv
import io
import logging

from .importer_base import ImporterBase

_logger = logging.getLogger(__name__)

# Florida DOR surtax rates by county (updated semiannually)
# Source: https://floridarevenue.com/taxes/taxesfees/Pages/tax_interest_rates.aspx
# Format: county_name -> surtax_rate
FL_STATE_RATE = 0.06  # Florida base rate: 6%

FL_COUNTY_SURTAX = {
    "ALACHUA": 0.005,
    "BAKER": 0.005,
    "BAY": 0.005,
    "BRADFORD": 0.005,
    "BREVARD": 0.005,
    "BROWARD": 0.01,
    "CALHOUN": 0.005,
    "CHARLOTTE": 0.005,
    "CITRUS": 0.005,
    "CLAY": 0.005,
    "COLLIER": 0.005,
    "COLUMBIA": 0.005,
    "DESOTO": 0.005,
    "DIXIE": 0.005,
    "DUVAL": 0.005,
    "ESCAMBIA": 0.005,
    "FLAGLER": 0.005,
    "FRANKLIN": 0.005,
    "GADSDEN": 0.005,
    "GILCHRIST": 0.005,
    "GLADES": 0.005,
    "GULF": 0.005,
    "HAMILTON": 0.005,
    "HARDEE": 0.005,
    "HENDRY": 0.005,
    "HERNANDO": 0.005,
    "HIGHLANDS": 0.005,
    "HILLSBOROUGH": 0.005,
    "HOLMES": 0.005,
    "INDIAN RIVER": 0.005,
    "JACKSON": 0.005,
    "JEFFERSON": 0.005,
    "LAFAYETTE": 0.005,
    "LAKE": 0.005,
    "LEE": 0.005,
    "LEON": 0.005,
    "LEVY": 0.005,
    "LIBERTY": 0.0,
    "MADISON": 0.005,
    "MANATEE": 0.005,
    "MARION": 0.005,
    "MARTIN": 0.005,
    "MIAMI-DADE": 0.01,
    "MONROE": 0.005,
    "NASSAU": 0.005,
    "OKALOOSA": 0.005,
    "OKEECHOBEE": 0.005,
    "ORANGE": 0.005,
    "OSCEOLA": 0.005,
    "PALM BEACH": 0.01,
    "PASCO": 0.005,
    "PINELLAS": 0.01,
    "POLK": 0.01,
    "PUTNAM": 0.005,
    "SAINT JOHNS": 0.005,
    "SAINT LUCIE": 0.005,
    "SANTA ROSA": 0.005,
    "SARASOTA": 0.005,
    "SEMINOLE": 0.005,
    "SUMTER": 0.005,
    "SUWANNEE": 0.005,
    "TAYLOR": 0.005,
    "UNION": 0.005,
    "VOLUSIA": 0.005,
    "WAKULLA": 0.005,
    "WALTON": 0.005,
    "WASHINGTON": 0.005,
}


class FloridaDorImporter(ImporterBase):
    """Importer for Florida DOR data.

    Supports two modes:
    1. Built-in county surtax table (instant, no file needed)
    2. Florida DOR Master Address List CSV (detailed,
       from pointmatch.floridarevenue.com)
    """

    SOURCE_CODE = "florida_dor"

    def run(self, file_obj, state, effective_date):
        """Import FL data. If file_obj has content, parse it; otherwise use built-in."""
        content = file_obj.read()

        if content and len(content) > 100:
            return self._import_from_file(content, state, effective_date)
        return self._import_builtin(state, effective_date)

    def _import_builtin(self, state, effective_date):
        """Load FL surtax data from the hardcoded county table."""
        _logger.info(
            "Florida DOR: loading built-in county surtax table (%d counties)",
            len(FL_COUNTY_SURTAX),
        )
        created = 0
        for county_name, surtax in FL_COUNTY_SURTAX.items():
            jur = self._get_or_create_jurisdiction(
                state, county=county_name, jtype="county"
            )
            rates = {
                "state_rate": FL_STATE_RATE,
                "county_rate": surtax,
                "city_rate": 0.0,
                "district_rate": 0.0,
                "total_rate": FL_STATE_RATE + surtax,
            }
            self._upsert_rate(jur, effective_date, rates, self.SOURCE_CODE)
            created += 1

        self.batch.write(
            {
                "records_created": created,
                "records_updated": 0,
                "records_skipped": 0,
            }
        )
        _logger.info("Florida DOR built-in import: %d county rates loaded", created)

    def _import_from_file(self, content, state, effective_date):
        """Parse Florida DOR Master Address List CSV.

        The real DOR export (pointmatch.floridarevenue.com) is address-point
        level: one row per street segment, no SURTAX column, and CITY is
        published as MAILCITY. Surtax has only one granularity in Florida
        (per county), so rows are deduplicated to one rate lookup per county
        and one ZIP mapping per unique ZIP — not per address row — to keep a
        655k-row county file importable in seconds instead of hours.
        """
        reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))

        zip_city = {}  # (zip_code, county) -> city, first occurrence wins
        county_surtax_col = {}  # county -> raw SURTAX column value, if present
        skipped = 0

        for row in reader:
            try:
                zip_code = str(row.get("ZIP", row.get("zip", "")) or "").strip()[:5]
                county = (
                    (row.get("COUNTY", row.get("county", "")) or "").strip().upper()
                )
                if not zip_code or len(zip_code) < 5 or not county:
                    skipped += 1
                    continue
                city = (
                    (row.get("CITY") or row.get("MAILCITY") or row.get("city") or "")
                    .strip()
                    .upper()
                )

                zip_city.setdefault((zip_code, county), city)
                if county not in county_surtax_col:
                    county_surtax_col[county] = row.get("SURTAX", row.get("surtax"))
            except Exception as exc:
                skipped += 1
                _logger.warning("FL DOR row parse error: %s", exc)

        county_rates = {}
        for county, surtax_col in county_surtax_col.items():
            if surtax_col is not None:
                surtax = float(surtax_col or 0)
                if surtax > 1:
                    surtax /= 100
            else:
                surtax = FL_COUNTY_SURTAX.get(county, 0.0)
            county_rates[county] = surtax

        jur_by_county = {}
        for county, surtax in county_rates.items():
            jur = self._get_or_create_jurisdiction(state, county=county, jtype="county")
            self._upsert_rate(
                jur,
                effective_date,
                {
                    "state_rate": FL_STATE_RATE,
                    "county_rate": surtax,
                    "city_rate": 0.0,
                    "district_rate": 0.0,
                    "total_rate": FL_STATE_RATE + surtax,
                },
                self.SOURCE_CODE,
            )
            jur_by_county[county] = jur

        ZipMap = self.env["us.tax.zip.mapping"]
        jur_ids = {jur.id for jur in jur_by_county.values()}
        existing_maps = ZipMap.search(
            [
                ("zip", "in", [z for z, _ in zip_city]),
                ("jurisdiction_id", "in", list(jur_ids)),
            ]
        )
        existing_by_key = {(m.zip, m.jurisdiction_id.id): m for m in existing_maps}

        to_create = []
        created = updated = 0
        for (zip_code, county), city in zip_city.items():
            jur = jur_by_county[county]
            vals = {
                "zip": zip_code,
                "state_id": state.id,
                "jurisdiction_id": jur.id,
                "county": county,
                "city": city,
                "confidence": 1.0,
                "source": self.SOURCE_CODE,
                "import_batch_id": self.batch.id,
            }
            existing = existing_by_key.get((zip_code, jur.id))
            if existing:
                existing.write(vals)
                updated += 1
            else:
                to_create.append(vals)
                created += 1

        if to_create:
            ZipMap.create(to_create)

        self.batch.write(
            {
                "records_created": created,
                "records_updated": updated,
                "records_skipped": skipped,
            }
        )
        _logger.info(
            "FL DOR file import: %d counties, %d ZIPs created, %d updated, %d skipped",
            len(jur_by_county),
            created,
            updated,
            skipped,
        )
