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
    'ALACHUA': 0.005,
    'BAKER': 0.005,
    'BAY': 0.005,
    'BRADFORD': 0.005,
    'BREVARD': 0.005,
    'BROWARD': 0.01,
    'CALHOUN': 0.005,
    'CHARLOTTE': 0.005,
    'CITRUS': 0.005,
    'CLAY': 0.005,
    'COLLIER': 0.005,
    'COLUMBIA': 0.005,
    'DESOTO': 0.005,
    'DIXIE': 0.005,
    'DUVAL': 0.005,
    'ESCAMBIA': 0.005,
    'FLAGLER': 0.005,
    'FRANKLIN': 0.005,
    'GADSDEN': 0.005,
    'GILCHRIST': 0.005,
    'GLADES': 0.005,
    'GULF': 0.005,
    'HAMILTON': 0.005,
    'HARDEE': 0.005,
    'HENDRY': 0.005,
    'HERNANDO': 0.005,
    'HIGHLANDS': 0.005,
    'HILLSBOROUGH': 0.005,
    'HOLMES': 0.005,
    'INDIAN RIVER': 0.005,
    'JACKSON': 0.005,
    'JEFFERSON': 0.005,
    'LAFAYETTE': 0.005,
    'LAKE': 0.005,
    'LEE': 0.005,
    'LEON': 0.005,
    'LEVY': 0.005,
    'LIBERTY': 0.0,
    'MADISON': 0.005,
    'MANATEE': 0.005,
    'MARION': 0.005,
    'MARTIN': 0.005,
    'MIAMI-DADE': 0.01,
    'MONROE': 0.005,
    'NASSAU': 0.005,
    'OKALOOSA': 0.005,
    'OKEECHOBEE': 0.005,
    'ORANGE': 0.005,
    'OSCEOLA': 0.005,
    'PALM BEACH': 0.01,
    'PASCO': 0.005,
    'PINELLAS': 0.01,
    'POLK': 0.01,
    'PUTNAM': 0.005,
    'SAINT JOHNS': 0.005,
    'SAINT LUCIE': 0.005,
    'SANTA ROSA': 0.005,
    'SARASOTA': 0.005,
    'SEMINOLE': 0.005,
    'SUMTER': 0.005,
    'SUWANNEE': 0.005,
    'TAYLOR': 0.005,
    'UNION': 0.005,
    'VOLUSIA': 0.005,
    'WAKULLA': 0.005,
    'WALTON': 0.005,
    'WASHINGTON': 0.005,
}


class FloridaDorImporter(ImporterBase):
    """Importer for Florida DOR data.

    Supports two modes:
    1. Built-in county surtax table (instant, no file needed)
    2. Florida DOR Master Address List CSV (detailed, from pointmatch.floridarevenue.com)
    """

    SOURCE_CODE = 'florida_dor'

    def run(self, file_obj, state, effective_date):
        """Import FL data. If file_obj has content, parse it; otherwise use built-in table."""
        content = file_obj.read()

        if content and len(content) > 100:
            return self._import_from_file(content, state, effective_date)
        return self._import_builtin(state, effective_date)

    def _import_builtin(self, state, effective_date):
        """Load FL surtax data from the hardcoded county table."""
        _logger.info('Florida DOR: loading built-in county surtax table (%d counties)',
                     len(FL_COUNTY_SURTAX))
        created = 0
        for county_name, surtax in FL_COUNTY_SURTAX.items():
            jur = self._get_or_create_jurisdiction(
                state, county=county_name, jtype='county'
            )
            rates = {
                'state_rate':  FL_STATE_RATE,
                'county_rate': surtax,
                'city_rate':   0.0,
                'district_rate': 0.0,
                'total_rate':  FL_STATE_RATE + surtax,
            }
            self._upsert_rate(jur, effective_date, rates, self.SOURCE_CODE)
            created += 1

        self.batch.write({
            'records_created': created,
            'records_updated': 0,
            'records_skipped': 0,
        })
        _logger.info('Florida DOR built-in import: %d county rates loaded', created)

    def _import_from_file(self, content, state, effective_date):
        """Parse Florida DOR Master Address List CSV."""
        # FL DOR format columns vary by release; handle common formats
        reader = csv.DictReader(io.StringIO(content.decode('utf-8', errors='replace')))
        created = updated = skipped = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                zip_code = str(row.get('ZIP', row.get('zip', '')) or '').strip()[:5]
                if not zip_code or len(zip_code) < 5:
                    skipped += 1
                    continue
                county = (row.get('COUNTY', row.get('county', '')) or '').strip().upper()
                city = (row.get('CITY', row.get('city', '')) or '').strip().upper()
                surtax = float(row.get('SURTAX', row.get('surtax', '0')) or 0)
                if surtax > 1:
                    surtax /= 100

                rates = {
                    'state_rate':  FL_STATE_RATE,
                    'county_rate': surtax,
                    'city_rate':   0.0,
                    'district_rate': 0.0,
                    'total_rate':  FL_STATE_RATE + surtax,
                }
                jur = self._get_or_create_jurisdiction(
                    state, county=county, city=city,
                    jtype='city' if city else 'county',
                )
                _, action = self._upsert_rate(jur, effective_date, rates, self.SOURCE_CODE)
                self._upsert_zip_mapping(
                    zip_code, state, jur, county=county, city=city,
                    confidence=1.0, source=self.SOURCE_CODE,
                )
                if action == 'created':
                    created += 1
                else:
                    updated += 1

            except Exception as exc:
                errors.append(f'Row {row_num}: {exc}')
                skipped += 1

        self.batch.write({
            'records_created': created,
            'records_updated': updated,
            'records_skipped': skipped,
            'error_log': '\n'.join(errors) if errors else False,
        })
        _logger.info('FL DOR file import: %d created, %d updated, %d skipped',
                     created, updated, skipped)
