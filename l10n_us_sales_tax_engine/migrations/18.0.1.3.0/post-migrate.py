# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Post-migration for l10n_us_sales_tax_engine 18.0.1.3.0.

Stamps us_tax_calculated_hash on the documents that already carried a
calculation before this version. Outdated detection reads an empty calculated
hash as "never calculated", so a document priced under 18.0.1.2.0 could
otherwise never be flagged again however much its address or its lines moved
afterwards: no banner, and nothing for the cron to find.

Runs post rather than pre because the fingerprint it copies is the one the
module itself defines, and that only exists once the module is loaded.

The hash is built through _us_tax_build_input_hash() rather than read from
us_tax_input_hash, which is only maintained inside _us_tax_state_domain(): a
posted or locked document has no stored fingerprint, and reading the column
would leave it unstamped and outside outdated detection for good once it is
reset to draft or unlocked.

The environment carries us_tax_skip_auto so that stamping cannot reach the
engine. An upgrade must not spend provider quota.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _document_models(env):
    """Return the concrete models carrying the automatic recalculation.

    Read off the registry instead of listed, so a downstream module that
    adds a third document type is migrated too. account.bank.statement.line
    delegates the field to account.move and is left out, or every move it
    points at would be stamped twice.
    """
    names = []
    for name, model in env.registry.items():
        field = model._fields.get("us_tax_calculated_hash")
        if field and not model._abstract and not field.inherited:
            names.append(name)
    return sorted(names)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {"us_tax_skip_auto": True})
    for model_name in _document_models(env):
        documents = env[model_name].search(
            [
                ("us_tax_calculated_at", "!=", False),
                ("us_tax_calculated_hash", "=", False),
            ]
        )
        stamped = 0
        for document in documents:
            fingerprint = document._us_tax_build_input_hash()
            if not fingerprint:
                continue
            document.us_tax_calculated_hash = fingerprint
            stamped += 1
        if stamped:
            _logger.info(
                "l10n_us_sales_tax_engine: stamped the calculated fingerprint "
                "on %s already calculated %s records.",
                stamped,
                model_name,
            )
