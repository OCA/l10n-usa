# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging
from abc import ABC, abstractmethod

_logger = logging.getLogger(__name__)


class ImporterBase(ABC):
    """Abstract base for all tax rate importers.

    Design note — why a custom importer instead of OCA's connector_importer
    or Odoo's built-in CSV import: this loads ad-hoc, irregularly-shaped
    government-published flat files (Florida DOR's Master Address List,
    future state exports) on a manual, periodic basis — there is no
    recurring sync flow, external system, or webhook to reconcile against,
    which is what connector_importer is built for. The import itself is a
    handful of domain-specific upserts (jurisdiction → rate → ZIP mapping)
    rather than a generic field-mapping problem, so Odoo's built-in import
    (designed around mapping CSV columns directly to model fields) doesn't
    fit either — there's no model whose fields line up 1:1 with a DOR
    export row. Revisit if/when a recurring, multi-state sync requirement
    emerges; for the current "upload a file a few times a year" use case,
    the added dependency footprint isn't justified.
    """

    SOURCE_CODE: str = ""

    def __init__(self, env, batch):
        self.env = env
        self.batch = batch

    @abstractmethod
    def run(self, file_obj, state, effective_date):
        """Execute import. Must update batch counters and log errors."""

    def _get_or_create_jurisdiction(self, state, county="", city="", jtype="county"):
        """Find or create a jurisdiction record."""
        Jur = self.env["us.tax.jurisdiction"]
        domain = [
            ("state_id", "=", state.id),
            ("type", "=", jtype),
            ("county", "=", county),
            ("city", "=", city),
        ]
        jur = Jur.search(domain, limit=1)
        if not jur:
            jur = Jur.create(
                {
                    "name": city or county or state.name,
                    "type": jtype,
                    "state_id": state.id,
                    "county": county,
                    "city": city,
                }
            )
        return jur

    def _upsert_rate(self, jurisdiction, effective_date, rates, source):
        """Create or update a rate record."""
        Rate = self.env["us.tax.rate"]
        existing = Rate.search(
            [
                ("jurisdiction_id", "=", jurisdiction.id),
                ("effective_date", "=", effective_date),
                ("product_tax_category_id", "=", False),
            ],
            limit=1,
        )
        vals = {
            "jurisdiction_id": jurisdiction.id,
            "effective_date": effective_date,
            "state_rate": rates.get("state_rate", 0.0),
            "county_rate": rates.get("county_rate", 0.0),
            "city_rate": rates.get("city_rate", 0.0),
            "district_rate": rates.get("district_rate", 0.0),
            "source": source,
            "import_batch_id": self.batch.id,
        }
        if existing:
            existing.write(vals)
            return existing, "updated"
        return Rate.create(vals), "created"

    def _upsert_zip_mapping(
        self,
        zip_code,
        state,
        jurisdiction,
        county="",
        city="",
        confidence=1.0,
        source="",
    ):
        """Create or update a ZIP mapping."""
        ZipMap = self.env["us.tax.zip.mapping"]
        existing = ZipMap.search(
            [
                ("zip", "=", zip_code),
                ("jurisdiction_id", "=", jurisdiction.id),
            ],
            limit=1,
        )
        vals = {
            "zip": zip_code,
            "state_id": state.id,
            "jurisdiction_id": jurisdiction.id,
            "county": county,
            "city": city,
            "confidence": confidence,
            "source": source,
            "import_batch_id": self.batch.id,
        }
        if existing:
            existing.write(vals)
        else:
            ZipMap.create(vals)
