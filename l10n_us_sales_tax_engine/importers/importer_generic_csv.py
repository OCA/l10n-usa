# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import csv
import io
import logging

from .importer_base import ImporterBase

_logger = logging.getLogger(__name__)

# Expected columns (configurable)
DEFAULT_COLUMNS = {
    "zip": "zip",
    "county": "county",
    "city": "city",
    "state_rate": "state_rate",
    "county_rate": "county_rate",
    "city_rate": "city_rate",
    "district_rate": "district_rate",
    "total_rate": "total_rate",
}


class GenericCsvImporter(ImporterBase):
    """Generic CSV importer — works for any US state.

    Expected CSV columns (headers must match):
    zip, county, city, state_rate, county_rate, city_rate, district_rate, total_rate
    """

    SOURCE_CODE = "generic_csv"

    def __init__(self, env, batch, delimiter=",", column_map=None):
        super().__init__(env, batch)
        self.delimiter = delimiter
        self.column_map = column_map or DEFAULT_COLUMNS

    def run(self, file_obj, state, effective_date):
        content = file_obj.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content), delimiter=self.delimiter)

        created = updated = skipped = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                zip_code = str(row.get(self.column_map["zip"], "") or "").strip()[:5]
                if not zip_code or len(zip_code) < 5:
                    skipped += 1
                    continue

                county = (
                    (row.get(self.column_map.get("county", ""), "") or "")
                    .strip()
                    .upper()
                )
                city = (
                    (row.get(self.column_map.get("city", ""), "") or "").strip().upper()
                )

                def _rate(key, _row=row):
                    val = _row.get(self.column_map.get(key, key), "0") or "0"
                    return (
                        float(str(val).replace("%", "").strip()) / 100
                        if float(str(val).replace("%", "").strip()) > 1
                        else float(str(val).replace("%", "").strip())
                    )

                total_rate = _rate("total_rate") or (
                    _rate("state_rate")
                    + _rate("county_rate")
                    + _rate("city_rate")
                    + _rate("district_rate")
                )
                rates = {
                    "state_rate": _rate("state_rate"),
                    "county_rate": _rate("county_rate"),
                    "city_rate": _rate("city_rate"),
                    "district_rate": _rate("district_rate"),
                    "total_rate": total_rate,
                }

                jur = self._get_or_create_jurisdiction(
                    state,
                    county=county,
                    city=city,
                    jtype="city" if city else "county",
                )
                _, action = self._upsert_rate(
                    jur, effective_date, rates, self.SOURCE_CODE
                )
                self._upsert_zip_mapping(
                    zip_code,
                    state,
                    jur,
                    county=county,
                    city=city,
                    confidence=0.9,
                    source=self.SOURCE_CODE,
                )
                if action == "created":
                    created += 1
                else:
                    updated += 1

            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")
                skipped += 1
                _logger.warning("CSV import row %s error: %s", row_num, exc)

        self.batch.write(
            {
                "records_created": created,
                "records_updated": updated,
                "records_skipped": skipped,
                "error_log": "\n".join(errors) if errors else False,
            }
        )
        _logger.info(
            "Generic CSV import done: %d created, %d updated, %d skipped",
            created,
            updated,
            skipped,
        )
