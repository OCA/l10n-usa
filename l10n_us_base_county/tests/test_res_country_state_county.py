import csv
import tempfile

import xlwt

from odoo.tests import TransactionCase
from odoo.tools import file_open, mute_logger


class TestCountryStateCounty(TransactionCase):
    def test_counties(self):
        self.assertEqual(3141, self.env["res.country.state.county"].search_count([]))

    @mute_logger("odoo.addons.l10n_us_base_county.models.res_country_state_county")
    def test_import_counties(self):
        County = self.env["res.country.state.county"]
        County.search([]).unlink()

        book = xlwt.Workbook()
        sheet = book.add_sheet("Sheet 1")
        with file_open("l10n_us_base_county/tests/data/LND01.csv") as file:
            reader = csv.reader(file)
            for r, row in enumerate(reader):
                for c, cell in enumerate(row):
                    sheet.write(r, c, cell)
        with tempfile.TemporaryFile(suffix=".xls") as file:
            book.save(file)
            file.seek(0)
            County._import_counties(file.read())
        self.assertEqual(2, County.search_count([]))

    @mute_logger("odoo.addons.l10n_us_base_county.models.res_country_state_county")
    def test_import_counties_full(self):
        County = self.env["res.country.state.county"]
        County.search([]).unlink()

        try:
            with file_open("l10n_us_base_county/tests/data/LND01.xls", "rb") as file:
                County._import_counties(file.read())
            self.assertEqual(3141, County.search_count([]))
        except FileNotFoundError:
            # https://www2.census.gov/library/publications/2011/compendia/usa-counties/excel/LND01.xls
            self.skipTest("download 1.5MB LND01.xls to run this test")
