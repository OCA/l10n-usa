import logging

import xlrd

from odoo import fields, models

_logger = logging.getLogger(__name__)


class County(models.Model):
    _name = "res.country.state.county"
    _description = "United States County"
    _sql_constraints = [
        (
            "name_uniq",
            "unique(name, state_id)",
            "County name must be unique per state!",
        ),
    ]

    name = fields.Char()
    country_id = fields.Many2one(
        "res.country", related="state_id.country_id", readonly=True
    )
    state_id = fields.Many2one("res.country.state")

    def _import_counties(self, file_contents):
        """Import Excel spreadsheet from U.S. Census Bureau.
        See https://www.census.gov/library/publications/2011/compendia/usa-counties-2011.html"""
        self.check_access("create")

        country_id = self.env.ref("base.us").id

        def get_state_id(code):
            return (
                self.env["res.country.state"]
                .search(
                    [
                        ("country_id", "=", country_id),
                        ("code", "=", code),
                    ],
                    limit=1,
                )
                .id
            )

        # https://www2.census.gov/library/publications/2011/compendia/usa-counties/excel/LND01.xls
        workbook = xlrd.open_workbook(filename="LND01.xls", file_contents=file_contents)
        sheet = workbook.sheet_by_index(0)
        for i, row in enumerate(sheet.get_rows()):
            if i == 0:
                assert row[0].value == "Areaname", row
                assert row[1].value == "STCOU"
                continue

            areaname = row[0].value
            stcou = int(row[1].value)
            if (stcou % 1000) == 0:
                _logger.debug("reading %s", areaname)
                continue

            if not areaname:
                continue
            if ", " not in areaname:
                if areaname == "District of Columbia":
                    areaname += ", DC"
                else:
                    _logger.warning("skipping %s", areaname)
                    continue

            county_name, state_code = areaname.split(", ")
            state_id = get_state_id(state_code)
            if self.search([("name", "=", county_name), ("state_id", "=", state_id)]):
                _logger.warning("skipping duplicate %s", areaname)
                continue

            county = self.create(
                {
                    "name": county_name,
                    "state_id": get_state_id(state_code),
                }
            )
            self.env["ir.model.data"].create(
                {
                    "module": "l10n_us_base_county",
                    "model": self._name,
                    "name": f"res_country_state_county_{stcou}",
                    "res_id": county.id,
                }
            )
            _logger.info("created %s", areaname)
