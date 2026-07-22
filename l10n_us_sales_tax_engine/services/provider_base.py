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
                f"{self.NAME}: API key not configured. "
                f"Set in Settings → US Tax Engine."
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


class ProviderError(Exception):
    """Raised when a provider call fails."""
