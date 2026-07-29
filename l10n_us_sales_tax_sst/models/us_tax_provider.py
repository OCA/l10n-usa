# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class UsTaxProvider(models.Model):
    _inherit = "us.tax.provider"

    def _provider_service_classes(self):
        """Swap the local provider for the SST-aware implementation.

        When this addon is installed, the ``local`` provider resolves rates
        through the SST Rate & Boundary data (address → FIPS jurisdiction set →
        per-jurisdiction rate) instead of the engine's single-jurisdiction ZIP
        mapping. Registered via the engine's provider registry, so no engine
        edit is needed.
        """
        from ..services.provider_local_sst import (  # noqa: PLC0415
            ProviderLocalSst,
        )

        classes = super()._provider_service_classes()
        classes["local"] = ProviderLocalSst
        return classes
