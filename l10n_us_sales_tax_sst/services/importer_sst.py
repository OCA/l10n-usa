# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Importer for the SST Rate & Boundary databases (positional CSV).

Files are comma-delimited with NO header row; column meaning is by position.
Codes (FIPS, ZIP) are kept as strings so leading zeros survive. The rate file
must be imported before the boundary file, because boundary rows are linked to
the jurisdictions the rate file creates (matched by FIPS).
"""

import csv
import logging

from odoo.addons.l10n_us_sales_tax_engine.levels import level_to_rate_field
from odoo.addons.l10n_us_sales_tax_engine.tools import close_superseded_periods

from .sst_common import (
    JTYPE_TO_LEVEL,
    jtype_to_level,
    parse_sst_date,
    parse_sst_rate,
)

_logger = logging.getLogger(__name__)

# Number of fixed leading boundary columns before the repeating special-district
# (source, code, type) triplets begin. Keeps the parser robust to the exact
# total column count, which varies with how many district slots a state emits.
_BOUNDARY_FIXED_COLS = 29


def _strip_bom(text):
    """Drop a leading UTF-8 BOM.

    Member states publish these files from different systems and some emit a
    BOM: of the 23 states publishing boundary files for 2026Q3, Iowa and
    Vermont do. Left in place it becomes part of the first field, so the
    opening record type reads as "\ufeffZ" and the row is rejected.
    """
    return text.lstrip("\ufeff") if text else text


class SstImporter:
    def __init__(self, env, batch):
        self.env = env
        self.batch = batch

    # ── Rate file ─────────────────────────────────────────────────────────────

    def import_rate_file(self, text, state):
        """Parse the 9-column SST rate file → jurisdictions + rates."""
        text = _strip_bom(text)
        created = updated = skipped = 0
        unknown_jtypes = set()
        for row in csv.reader(text.splitlines()):
            if len(row) < 9:
                skipped += 1
                continue
            fips_state = row[0].strip()
            jtype = row[1].strip()
            fips_code = row[2].strip()
            if jtype.zfill(2) not in JTYPE_TO_LEVEL:
                unknown_jtypes.add(jtype)
            level = jtype_to_level(jtype)
            jurisdiction = self._upsert_jurisdiction(
                state, fips_state, level, jtype, fips_code
            )
            _, action = self._upsert_rate(
                jurisdiction,
                level=level,
                effective_date=parse_sst_date(row[7]),
                end_date=parse_sst_date(row[8]),
                general_intra=parse_sst_rate(row[3]),
                food_drug_intra=parse_sst_rate(row[5]),
            )
            created += action == "created"
            updated += action == "updated"
        self.batch.records_created += created
        self.batch.records_updated += updated
        self.batch.records_skipped += skipped
        _logger.info(
            "SST rate import (%s): %d created, %d updated, %d skipped",
            state.code,
            created,
            updated,
            skipped,
        )
        if unknown_jtypes:
            _logger.warning(
                "SST rate import (%s): unmapped jurisdiction types treated as "
                "district: %s",
                state.code,
                ", ".join(sorted(unknown_jtypes)),
            )

    def _upsert_jurisdiction(self, state, fips_state, level, jtype, fips_code):
        Jur = self.env["us.tax.jurisdiction"]
        vals = {
            "state_id": state.id,
            "type": level,
            "jurisdiction_type": jtype,
            "fips_state": fips_state,
        }
        if level == "state":
            vals["name"] = state.name
            domain = [("state_id", "=", state.id), ("type", "=", "state")]
        elif level == "county":
            vals.update(fips_county=fips_code, name=f"{state.code} County {fips_code}")
            domain = [("state_id", "=", state.id), ("fips_county", "=", fips_code)]
        elif level == "city":
            vals.update(fips_place=fips_code, name=f"{state.code} City {fips_code}")
            domain = [("state_id", "=", state.id), ("fips_place", "=", fips_code)]
        else:
            vals.update(
                district_code=fips_code, name=f"{state.code} District {fips_code}"
            )
            domain = [("state_id", "=", state.id), ("district_code", "=", fips_code)]
        jur = Jur.search(domain, limit=1)
        if jur:
            jur.write(vals)
        else:
            jur = Jur.create(vals)
        return jur

    def _upsert_rate(
        self,
        jurisdiction,
        level,
        effective_date,
        end_date,
        general_intra,
        food_drug_intra,
    ):
        Rate = self.env["us.tax.rate"]
        vals = {
            "jurisdiction_id": jurisdiction.id,
            "product_tax_category_id": False,
            "effective_date": effective_date,
            "end_date": end_date,
            "state_rate": 0.0,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": 0.0,
            level_to_rate_field(level): general_intra,
            "food_drug_rate": food_drug_intra,
            "source": "sst",
            "import_batch_id": self.batch.id,
        }
        existing = Rate.search(
            [
                ("jurisdiction_id", "=", jurisdiction.id),
                ("effective_date", "=", effective_date),
                ("product_tax_category_id", "=", False),
            ],
            limit=1,
        )
        if existing:
            existing.write(vals)
            return existing, "updated"
        rate = Rate.create(vals)
        # Close any open prior rate period so exactly one is active per date.
        close_superseded_periods(
            Rate,
            [
                ("jurisdiction_id", "=", jurisdiction.id),
                ("product_tax_category_id", "=", False),
            ],
            effective_date,
        )
        return rate, "created"

    # ── Boundary file ─────────────────────────────────────────────────────────

    def import_boundary_file(self, text, state):
        """Parse the SST boundary file → us.tax.boundary rows, linking the
        FIPS jurisdictions the rate file created.

        SST states reissue the full boundary file each quarter, so existing
        rows for this state are cleared first — re-importing replaces, it does
        not duplicate.
        """
        text = _strip_bom(text)
        created = skipped = 0
        Boundary = self.env["us.tax.boundary"]
        Boundary.search([("state_id", "=", state.id)]).unlink()
        for row in csv.reader(text.splitlines()):
            if len(row) < _BOUNDARY_FIXED_COLS or not row[0].strip():
                skipped += 1
                continue
            vals = self._boundary_vals(row, state)
            vals["jurisdiction_ids"] = [
                (6, 0, self._resolve_boundary_jurisdictions(row, state).ids)
            ]
            Boundary.create(vals)
            created += 1
        self.batch.records_created += created
        self.batch.records_skipped += skipped
        _logger.info(
            "SST boundary import (%s): %d created, %d skipped",
            state.code,
            created,
            skipped,
        )

    @staticmethod
    def _col(row, i):
        return row[i].strip() if i < len(row) else ""

    def _boundary_vals(self, row, state):
        col = self._col
        return {
            # Upper-cased: the record type is a code, and states disagree on
            # case — Minnesota publishes "z" where the others publish "Z".
            "record_type": col(row, 0).upper(),
            "begin_date": parse_sst_date(col(row, 1)),
            "end_date": parse_sst_date(col(row, 2)),
            "addr_low": col(row, 3),
            "addr_high": col(row, 4),
            "odd_even": col(row, 5) or False,
            "street_pre_dir": col(row, 6),
            "street_name": col(row, 7),
            "street_suffix": col(row, 8),
            "street_post_dir": col(row, 9),
            "city": col(row, 14),
            "zip": col(row, 15),
            "zip4": col(row, 16),
            "zip_low": col(row, 17),
            "zip4_low": col(row, 18),
            "zip_high": col(row, 19),
            "zip4_high": col(row, 20),
            "fips_state": col(row, 22),
            "fips_county": col(row, 24),
            "fips_place": col(row, 25),
            "state_id": state.id,
            "source": "sst",
            "import_batch_id": self.batch.id,
        }

    def _resolve_boundary_jurisdictions(self, row, state):
        col = self._col
        Jur = self.env["us.tax.jurisdiction"]
        result = Jur.browse()
        # State tax applies only when the FIPS State Indicator equals the state
        # FIPS (col 23); "00" means no state-level tax for this boundary.
        if col(row, 23) and col(row, 23) != "00":
            result |= Jur.search(
                [("state_id", "=", state.id), ("type", "=", "state")], limit=1
            )
        if col(row, 24) and col(row, 24) != "000":
            result |= Jur.search(
                [("state_id", "=", state.id), ("fips_county", "=", col(row, 24))],
                limit=1,
            )
        if col(row, 25) and col(row, 25) != "00000":
            result |= Jur.search(
                [("state_id", "=", state.id), ("fips_place", "=", col(row, 25))],
                limit=1,
            )
        # Special-district triplets (source, code, type) from the fixed offset on.
        for i in range(_BOUNDARY_FIXED_COLS, len(row), 3):
            code = col(row, i + 1)
            if code:
                result |= Jur.search(
                    [("state_id", "=", state.id), ("district_code", "=", code)],
                    limit=1,
                )
        return result
