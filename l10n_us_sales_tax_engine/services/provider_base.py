# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from abc import ABC, abstractmethod


class ProviderBase(ABC):
    """Abstract base class for all US Sales Tax providers.

    Each provider must implement this interface. The provider receives
    an Odoo us.tax.provider record on initialization.
    """

    CODE: str = ""
    NAME: str = ""
    SUPPORTS_ADDRESS: bool = False
    SUPPORTS_ZIP: bool = True
    # Raw-response keys holding the county / city names, when the provider
    # returns them. Set by providers that can name jurisdictions.
    COUNTY_NAME_KEY: str = ""
    CITY_NAME_KEY: str = ""

    def __init__(self, provider_record):
        self.record = provider_record
        self.env = provider_record.env
        self.timeout = provider_record.timeout or 5

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Test stored credentials. Return True if valid."""

    @abstractmethod
    def get_rate(self, payload: dict) -> dict:
        """Fetch tax rate from provider.

        Args:
            payload: {
                'zip':              '33101',
                'state':            'FL',
                'city':             'Miami',
                'county':           'Miami-Dade',
                'address':          '123 Main St',
                'date':             '2025-01-15',
                'product_category': 'TANGIBLE',
                'amount':           100.0,
            }
        Returns:
            {
                'state_rate':    0.06,
                'county_rate':   0.01,
                'city_rate':     0.00,
                'district_rate': 0.00,
                'total_rate':    0.07,
                'source_date':   '2025-01-01',
                'raw_response':  {...},
            }
        Raises:
            ProviderError on any failure.
        """

    @abstractmethod
    def normalize_response(self, raw: dict) -> dict:
        """Map provider-specific response to standard rate dict."""

    def get_api_key(self) -> str:
        key = self.record.get_api_key()
        if not key:
            raise ProviderError(
                f"{self.NAME}: API key not configured. Set in Settings → US Tax Engine."
            )
        return key

    def get_priority(self) -> int:
        return self.record.priority

    def supports_address_level_lookup(self) -> bool:
        return self.SUPPORTS_ADDRESS

    def supports_zip_level_lookup(self) -> bool:
        return self.SUPPORTS_ZIP

    def _mask_key(self, key: str) -> str:
        """Return last 4 chars for safe logging."""
        return f"...{key[-4:]}" if len(key) > 4 else "****"

    # ── Named-jurisdiction resolution ─────────────────────────────────────────

    def resolve_named_jurisdictions(self, state_code, components):
        """Turn (level, name, rate) components into the engine jurisdiction list.

        Find-or-creates a ``us.tax.jurisdiction`` per named component so the
        engine books one tax line per *named* jurisdiction and returns/worksheets
        aggregate by name — even for non-SST states where there are no FIPS
        codes. Unnamed components (e.g. a combined district rate) stay
        level-only with ``jurisdiction_id`` empty.

        Note: jurisdictions created here carry a name but NO FIPS code, so an
        API-provider-sourced return cannot be filed as an SST SER (which keys
        JurisdictionDetail by FIPS). The named breakdown is for the worksheet
        and non-SST state portals.
        """
        state = self.env["res.country.state"].search(
            [("code", "=", state_code), ("country_id.code", "=", "US")], limit=1
        )
        Jur = self.env["us.tax.jurisdiction"].sudo()
        result = []
        for comp in components:
            rate = comp.get("rate") or 0.0
            if rate <= 0:
                continue
            level = comp["level"]
            name = (comp.get("name") or "").strip()
            if level == "state" and state:
                name = name or state.name
            jurisdiction_id = False
            if name and state:
                jur = Jur.search(
                    [
                        ("state_id", "=", state.id),
                        ("type", "=", level),
                        ("name", "=", name),
                    ],
                    limit=1,
                )
                if not jur:
                    jur = Jur.create(
                        {"name": name, "type": level, "state_id": state.id}
                    )
                jurisdiction_id = jur.id
            result.append(
                {
                    "jurisdiction_id": jurisdiction_id,
                    "fips": "",
                    "level": level,
                    "rate": rate,
                    "label": name or level.title(),
                }
            )
        return result

    def _named_jurisdictions(self, state_code, normalized, raw):
        """Build the jurisdiction list from a normalized rate dict + raw names."""
        county = raw.get(self.COUNTY_NAME_KEY) if self.COUNTY_NAME_KEY else None
        city = raw.get(self.CITY_NAME_KEY) if self.CITY_NAME_KEY else None
        components = [
            {"level": "state", "name": None, "rate": normalized.get("state_rate", 0.0)},
            {
                "level": "county",
                "name": county,
                "rate": normalized.get("county_rate", 0.0),
            },
            {"level": "city", "name": city, "rate": normalized.get("city_rate", 0.0)},
            {
                "level": "district",
                "name": None,
                "rate": normalized.get("district_rate", 0.0),
            },
        ]
        return self.resolve_named_jurisdictions(state_code, components)


class ProviderError(Exception):
    """Raised when a provider call fails."""
