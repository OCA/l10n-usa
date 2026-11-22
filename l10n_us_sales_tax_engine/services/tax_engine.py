# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging
from datetime import date as date_type

import psycopg2

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .address_resolver import is_us_address
from .cache_manager import CacheManager
from .provider_base import ProviderError

_logger = logging.getLogger(__name__)


class UsTaxEngineService(models.AbstractModel):
    """Main US Tax Engine orchestrator.

    Implements the full calculation flow:
    1. Resolve address
    2. Check nexus
    3. Check product category taxability
    4. Try cache
    5. Try local database
    6. Try external API fallback chain
    7. Apply result to Odoo document
    8. Write audit log
    """

    _name = "us.tax.engine.service"
    _description = "US Tax Engine Service"

    # ── Public entry points ───────────────────────────────────────────────────

    @api.model
    def calculate_for_sale_order(self, order):
        """Calculate and apply US Sales Tax for a sale.order record.

        The address, the date and the line set come from the document's
        own hooks, the same ones the input fingerprint is built from, so
        overriding a hook downstream moves what the engine taxes and what
        marks the document outdated together.
        """
        return self._process(
            res_model="sale.order",
            res_id=order.id,
            address=order._us_tax_get_address(),
            lines=order._us_tax_get_lines(),
            doc_date=self._us_tax_doc_date(order),
            company_id=order.company_id.id,
            currency_id=order.currency_id.id,
            apply_fn=lambda result: self._apply_to_sale_order(order, result),
            partner=order.partner_id,
        )

    @api.model
    def calculate_for_invoice(self, move):
        """Calculate and apply US Sales Tax for an account.move record.

        Same hooks as calculate_for_sale_order, for the same reason.
        """
        return self._process(
            res_model="account.move",
            res_id=move.id,
            address=move._us_tax_get_address(),
            lines=move._us_tax_get_lines(),
            doc_date=self._us_tax_doc_date(move),
            company_id=move.company_id.id,
            currency_id=move.currency_id.id,
            apply_fn=lambda result: self._apply_to_invoice(move, result),
            partner=move.partner_id,
        )

    @api.model
    def _us_tax_doc_date(self, document):
        """Return the date to price on, from the document's own hook.

        _us_tax_get_date() yields the date-only ISO string the input
        fingerprint holds, so parsing it back here is what keeps the two
        from drifting. It is empty on a document with no date, which
        prices on today.
        """
        return fields.Date.to_date(document._us_tax_get_date()) or date_type.today()

    @api.model
    def _provider_failure_error(self, document, error):
        """Return the UserError shown when no provider could price document."""
        return UserError(
            self.env._(
                "US sales tax could not be calculated for %(document)s: %(error)s",
                document=document.display_name,
                error=error,
            )
        )

    @api.model
    def _calculate_on_validation(self, document, calculate):
        """Calculate the tax of a document that is being confirmed or posted.

        Under the block policy a provider failure stops the validation.
        Under the others the document goes through, and a note in its
        chatter says the tax could not be calculated. A tax that could
        not be written on the lines, and a US tax taken off a document
        that is no longer priced as US, get a note of their own. Any
        other failure is logged and lets the validation continue.
        """
        try:
            result = calculate(document)
        except ProviderError as exc:
            raise self._provider_failure_error(document, exc) from exc
        except psycopg2.OperationalError:
            raise
        except Exception as exc:
            _logger.warning(
                "US Tax calculation on %s failed: %s", document.display_name, exc
            )
            return {}
        if not result.get("applied", True):
            document.message_post(
                body=self.env._(
                    "US sales tax could not be written on the lines, so they "
                    "kept the tax they had. Calculate it again before sending "
                    "this document."
                )
            )
        elif result.get("tax_removed"):
            document.message_post(
                body=self.env._(
                    "US sales tax was taken off the lines: this document no "
                    "longer has a US address with a ZIP code and a state."
                )
            )
        elif result.get("source") == "error":
            document.message_post(
                body=self.env._(
                    "US sales tax could not be calculated: no rate provider "
                    "answered. Lines that already had a US tax kept it and the "
                    "others were priced at zero. Check the tax before sending "
                    "this document."
                )
            )
        return result

    # ── Core calculation flow ─────────────────────────────────────────────────

    @api.model
    def _process(
        self,
        res_model,
        res_id,
        address,
        lines,
        doc_date,
        company_id,
        currency_id,
        apply_fn,
        partner=None,
    ):
        """Orchestrate the full calculation flow.

        Runs as sudo: the engine computes tax in the background for any
        user who creates/confirms a sale or invoice, regardless of whether
        they personally hold the us_tax_user/manager/technical groups —
        those groups gate manual access to the configuration screens
        (Nexus, Rates, Jurisdictions...), not the engine's own background
        calculation.
        """
        self = self.sudo()
        ICP = self.env["ir.config_parameter"].sudo()

        if ICP.get_param("l10n_us_tax.engine_active", "False") != "True":
            return {"source": "disabled"}

        # Step 1: Validate address is US
        if not address or not is_us_address(address):
            return self._skip(apply_fn, "skip_non_us", res_model, res_id, address)

        zip_code = address.get("zip", "")
        state_code = address.get("state", "")
        if not zip_code or not state_code:
            _logger.warning(
                "Tax engine: missing ZIP or state for %s %s", res_model, res_id
            )
            return self._skip(apply_fn, "skip_no_address", res_model, res_id, address)

        # Step 2: Resolve state record
        state = self.env["res.country.state"].search(
            [("code", "=", state_code), ("country_id.code", "=", "US")], limit=1
        )

        # Step 3: Check nexus
        has_nexus = self.env["us.tax.nexus"].has_nexus(
            company_id, state.id if state else False
        )
        if not has_nexus:
            # Apply too — an order may already carry a tax from an earlier
            # calculation; losing nexus afterward must clear/replace it
            # with the explicit exempt tax, not leave it stale.
            final_result = {"source": "exempt_nexus", "tax_amount": 0.0, "lines": []}
            self._apply_result(apply_fn, final_result, res_model, res_id)
            self._log(
                res_model,
                res_id,
                address,
                "exempt_nexus",
                taxable_amount=0,
                tax_amount=0,
                state_id=state.id if state else False,
                nexus_applied=False,
                applied=final_result["applied"],
            )
            return final_result

        # Step 3.5: Partner-level exemption certificate
        if partner and partner.sudo().us_tax_exempt:
            final_result = {"source": "exempt_partner", "tax_amount": 0.0, "lines": []}
            self._apply_result(apply_fn, final_result, res_model, res_id)
            self._log(
                res_model,
                res_id,
                address,
                "exempt_partner",
                taxable_amount=0,
                tax_amount=0,
                state_id=state.id if state else False,
                nexus_applied=has_nexus,
                partner_id=partner.id,
                applied=final_result["applied"],
            )
            return final_result

        # Step 4: Initialize cache manager
        ttl = int(ICP.get_param("l10n_us_tax.cache_ttl_hours", "720"))
        cache = CacheManager(self.env, ttl_hours=ttl)

        # Step 5: Calculate per document line
        engine_mode = ICP.get_param("l10n_us_tax.engine_mode", "hybrid")
        fail_policy = ICP.get_param("l10n_us_tax.fail_policy", "warn")
        total_tax = 0.0
        results = []

        # Pre-load TANGIBLE category for fallback (no category = taxable goods)
        tangible_cat = self.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )

        for line in lines:
            if not hasattr(line, "price_subtotal") or line.price_subtotal == 0:
                continue
            product = getattr(line, "product_id", None)
            # sudo: reading us_tax_category_id.code below needs access to
            # us.tax.product.category, gated by group_us_tax_user — but
            # `product` is bound to the calling user (line/lines are
            # parameters, not derived from self), so it doesn't inherit
            # _process()'s own sudo.
            if product:
                product = product.sudo()

            # Resolve product fiscal category — default to TANGIBLE if not set
            if product and product.us_tax_category_id:
                cat_code = product.us_tax_category_id.code
                cat_id = product.us_tax_category_id.id
            else:
                # No category set → assume TANGIBLE (standard physical goods)
                cat_code = "TANGIBLE"
                cat_id = tangible_cat.id if tangible_cat else False
                _logger.debug(
                    'Product "%s" has no US Tax Category — defaulting to TANGIBLE',
                    product.name if product else "unknown",
                )

            # Check taxability rule
            taxable, rate_override = self.env["us.tax.rule"].is_taxable(
                state.id if state else False, cat_id, date=doc_date
            )
            if not taxable:
                results.append(
                    {"line_id": line.id, "source": "exempt_rule", "tax": 0.0}
                )
                continue

            # Calculate rate for this line
            try:
                rate_result = self._get_rate(
                    zip_code=zip_code,
                    state_code=state_code,
                    state_id=state.id if state else False,
                    product_category_code=cat_code,
                    product_category_id=cat_id,
                    doc_date=doc_date,
                    address=address,
                    cache=cache,
                    engine_mode=engine_mode,
                    fail_policy=fail_policy,
                    rate_override=rate_override,
                )
            except ProviderError:
                # The block policy raises here, and the caller's transaction
                # will be rolled back with everything it wrote.
                self._log_on_own_cursor(
                    res_model,
                    res_id,
                    address,
                    "error",
                    state_id=state.id if state else False,
                    nexus_applied=has_nexus,
                )
                raise
            line_tax = round(line.price_subtotal * rate_result["total_rate"], 4)
            total_tax += line_tax
            results.append(
                {
                    "line_id": line.id,
                    "source": rate_result["source"],
                    "rate": rate_result["total_rate"],
                    "tax": line_tax,
                    "subtotal": line.price_subtotal,
                    "rate_detail": rate_result,
                }
            )

        # Step 6: Apply to document
        final_result = {
            "source": self._aggregate_source(results),
            "tax_amount": total_tax,
            "lines": results,
        }
        self._apply_result(apply_fn, final_result, res_model, res_id)

        # Step 7: Audit log — include state, nexus, rate detail and provider
        best_rate = next(
            (r["rate_detail"] for r in results if r.get("rate_detail")), {}
        )
        # Extract provider_id from best rate result (set in _get_rate)
        used_provider_id = best_rate.get("provider_id", False)

        self._log(
            res_model,
            res_id,
            address,
            source=final_result["source"],
            taxable_amount=sum(r.get("subtotal", 0) for r in results),
            tax_amount=total_tax,
            state_id=state.id if state else False,
            nexus_applied=has_nexus,
            total_rate=best_rate.get("total_rate", 0),
            state_rate=best_rate.get("state_rate", 0),
            county_rate=best_rate.get("county_rate", 0),
            provider_id=used_provider_id,
            applied=final_result["applied"],
        )
        return final_result

    @api.model
    def _skip(self, apply_fn, source, res_model, res_id, address):
        """Answer a document the engine does not price.

        Its lines still go through apply_fn, so a tax the engine wrote
        while the document was taxable does not stay behind. Taking that
        tax off leaves a skipped audit row, and failing to leaves an error
        row. A skip that changes nothing leaves none, so documents the
        engine never priced do not fill the log. The "tax_removed" key
        tells the caller the lines lost the engine's tax.
        """
        final_result = {"source": source, "tax_amount": 0.0, "lines": []}
        changed = self._apply_result(apply_fn, final_result, res_model, res_id)
        final_result["tax_removed"] = bool(changed) and final_result["applied"]
        if changed or not final_result["applied"]:
            self._log(
                res_model,
                res_id,
                address or {},
                source,
                applied=final_result["applied"],
            )
        return final_result

    @api.model
    def _aggregate_source(self, results):
        """Return the source that stands for the whole document.

        A single line whose providers all failed makes it "error", so the
        audit row and the caller see the calculation as failed even when
        the other lines did get a rate.
        """
        if not results:
            return "no_lines"
        if any(result["source"] == "error" for result in results):
            return "error"
        return results[0]["source"]

    @api.model
    def _apply_result(self, apply_fn, final_result, res_model, res_id):
        """Write the tax on the lines, all of them or none.

        A failure rolls back to a savepoint and is reported through
        final_result["applied"] instead of raising. Database errors are
        re-raised so the core can retry the transaction. Return what
        apply_fn returns, or None when the write failed.
        """
        final_result["applied"] = True
        try:
            with self.env.cr.savepoint():
                return apply_fn(final_result)
        except psycopg2.OperationalError:
            raise
        except Exception as exc:
            final_result["applied"] = False
            _logger.error("Tax apply error on %s %s: %s", res_model, res_id, exc)
            return None

    @api.model
    def _get_rate(
        self,
        zip_code,
        state_code,
        state_id,
        product_category_code,
        product_category_id,
        doc_date,
        address,
        cache,
        engine_mode,
        fail_policy,
        rate_override=None,
    ):
        """Return rate dict from best available source.

        Runs as sudo — called directly by the REST controller, outside
        _process()'s own sudo, for the same background-calculation reason.
        """
        self = self.sudo()

        if rate_override is not None:
            return {
                "total_rate": rate_override,
                "state_rate": rate_override,
                "county_rate": 0,
                "city_rate": 0,
                "district_rate": 0,
                "source": "manual",
            }

        payload = {
            "zip": zip_code,
            "state": state_code,
            "city": address.get("city", ""),
            "address": address.get("address", ""),
            "date": str(doc_date),
            "product_category": product_category_code,
        }

        # Cache check
        cache_hash = cache.build_hash(
            zip_code, state_code, product_category_code, doc_date
        )
        cached = cache.get(cache_hash)
        if cached:
            cached["source"] = "cache"
            return cached

        # Get ordered providers
        providers = self._get_active_providers(engine_mode)
        last_error = None

        skipped_providers = []

        for provider_rec in providers:
            # ── Pre-call limit check ─────────────────────────────────────────
            if provider_rec.code != "local" and provider_rec.is_limit_reached():
                _logger.info(
                    'US Tax: skipping provider "%s" — monthly limit reached '
                    "(%d/%d). Moving to next provider.",
                    provider_rec.name,
                    provider_rec.calls_this_month,
                    provider_rec.monthly_call_limit,
                )
                skipped_providers.append(provider_rec.name)
                last_error = ProviderError(
                    f"{provider_rec.name}: monthly limit reached "
                    f"({provider_rec.calls_this_month}/{provider_rec.monthly_call_limit})"
                )
                continue

            try:
                svc = provider_rec._get_provider_service()(provider_rec)
                rates = svc.get_rate(payload)
                rates["source"] = "api" if provider_rec.code != "local" else "local"
                rates["provider_id"] = (
                    provider_rec.id if provider_rec.code != "local" else False
                )
                # Save to cache only for external providers
                if provider_rec.code != "local":
                    cache.set(
                        cache_hash,
                        provider_rec.id,
                        rates,
                        zip_code=zip_code,
                        state_id=state_id,
                        request_payload=payload,
                        response_payload=rates.get("raw_response", {}),
                    )
                return rates

            except ProviderError as exc:
                last_error = exc
                _logger.warning('Provider "%s" failed: %s', provider_rec.code, exc)
                continue

        # All providers exhausted — log which ones were skipped due to limits
        if skipped_providers:
            _logger.warning(
                "US Tax: providers skipped due to limits: %s",
                ", ".join(skipped_providers),
            )

        # Apply fail policy
        return self._handle_all_failed(fail_policy, cache_hash, last_error, address)

    @api.model
    def _get_active_providers(self, engine_mode):
        """Return ordered list of active provider records based on mode."""
        domain = [("active", "=", True)]
        if engine_mode == "local":
            domain.append(("code", "=", "local"))
        elif engine_mode == "api":
            domain.append(("code", "!=", "local"))
        # hybrid: all active, ordered by priority
        return self.env["us.tax.provider"].search(domain, order="priority, id")

    @api.model
    def _handle_all_failed(self, fail_policy, cache_hash, last_error, address):
        """Apply fail policy when all providers fail."""
        if fail_policy == "block":
            raise ProviderError(
                f'US Tax: all providers failed for ZIP={address.get("zip")}. '
                f'Last error: {last_error}'
            )
        if fail_policy == "last_cache":
            # Try expired cache
            entry = self.env["us.tax.api.cache"].search(
                [("address_hash", "=", cache_hash)], order="cached_at desc", limit=1
            )
            if entry:
                _logger.warning("Using expired cache for %s", cache_hash[:12])
                return {
                    "total_rate": entry.total_rate,
                    "state_rate": entry.state_rate,
                    "county_rate": entry.county_rate,
                    "city_rate": entry.city_rate,
                    "district_rate": entry.district_rate,
                    "source": "cache_expired",
                }
        # warn or manual → return 0 tax
        _logger.warning(
            "US Tax: all providers failed, applying 0 tax. Policy=%s", fail_policy
        )
        return {
            "total_rate": 0.0,
            "state_rate": 0.0,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": 0.0,
            "source": "error",
        }

    # ── Apply tax to Odoo documents ───────────────────────────────────────────

    @api.model
    def _apply_to_sale_order(self, order, result):
        """Apply calculated US tax to sale order lines.

        Always runs — even for $0 tax (exempt) to remove existing taxes.
        Sudo: called via a closure captured before _process()'s own sudo
        (the lambda is built in calculate_for_sale_order, a different
        method scope), and _get_or_create_state_tax below needs to create
        account.tax records a plain salesperson has no rights to create.

        Sections and notes carry no amount and are left alone: the core
        never clears a tax written on them, and the invoice would copy it.
        So are the lines the order's _us_tax_get_lines() hook leaves out,
        the ones already invoiced, whose invoice keeps the tax it was
        issued with. A skip returns the lines it took the engine's tax off.
        """
        self = self.sudo()
        order_source = result.get("source", "")
        lines_map = {r["line_id"]: r for r in result.get("lines", [])}
        product_lines = order._us_tax_get_lines().filtered(
            lambda line: not line.display_type
        )
        state_code = (
            order.partner_shipping_id.state_id.code
            if order.partner_shipping_id and order.partner_shipping_id.state_id
            else order.partner_id.state_id.code
        )

        # skip_*: the engine never evaluated taxability at all — take back
        # its own taxes, but do NOT assign the exempt tax (that would falsely
        # claim "evaluated, not taxable" for a case we never assessed).
        if order_source in ("skip_non_us", "skip_no_address"):
            return self._remove_us_taxes(product_lines, "tax_id")

        # Order-wide exemption (no nexus or partner certificate) — assign the
        # explicit 0% exempt tax on every line so "evaluated, no tax" is visible.
        if order_source in ("exempt_nexus", "exempt_partner"):
            exempt_tax = self._get_or_create_exempt_tax(order.company_id)
            for line in product_lines:
                line.tax_id = (
                    [Command.set([exempt_tax.id])] if exempt_tax else [Command.clear()]
                )
            return

        for line in product_lines:
            line_result = lines_map.get(line.id, {})
            source = line_result.get("source", order_source)
            rate = line_result.get("rate", 0.0)

            # No provider answered: a line already priced keeps its tax
            # rather than dropping to the 0% the warn policy hands back.
            if source == "error" and self._us_engine_taxes(line.tax_id):
                continue

            if source in ("exempt_rule", "exempt_nexus", "exempt_partner"):
                exempt_tax = self._get_or_create_exempt_tax(order.company_id)
                line.tax_id = (
                    [Command.set([exempt_tax.id])] if exempt_tax else [Command.clear()]
                )
                continue

            tax = self._get_or_create_state_tax(state_code, order.company_id, rate)
            if tax:
                line.tax_id = [Command.set([tax.id])]

    @api.model
    def _apply_to_invoice(self, move, result):
        """Apply calculated US tax to invoice lines — REPLACE existing taxes.

        Sudo: same reason as _apply_to_sale_order — the apply_fn closure
        predates _process()'s sudo, and account.tax creation needs it.

        Only product lines are touched, for the same reason as on the
        sale order. A skip returns the lines it took the engine's tax off.
        """
        self = self.sudo()
        move_source = result.get("source", "")
        lines_map = {r["line_id"]: r for r in result.get("lines", [])}
        product_lines = move.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        state_code = (
            move.partner_shipping_id.state_id.code
            if (
                hasattr(move, "partner_shipping_id")
                and move.partner_shipping_id
                and move.partner_shipping_id.state_id
            )
            else move.partner_id.state_id.code
        )
        if move_source in ("skip_non_us", "skip_no_address"):
            return self._remove_us_taxes(product_lines, "tax_ids")

        for line in product_lines:
            line_result = lines_map.get(line.id, {})
            rate = line_result.get("rate", 0.0)
            source = line_result.get("source", move_source)

            if source == "error" and self._us_engine_taxes(line.tax_ids):
                continue

            if source in ("exempt_rule", "exempt_nexus", "exempt_partner"):
                exempt_tax = self._get_or_create_exempt_tax(move.company_id)
                line.tax_ids = (
                    [Command.set([exempt_tax.id])] if exempt_tax else [Command.clear()]
                )
                continue

            tax = self._get_or_create_state_tax(state_code, move.company_id, rate)
            if tax:
                line.tax_ids = [Command.set([tax.id])]

    @api.model
    def _us_engine_taxes(self, taxes):
        """Return the taxes in ``taxes`` that the engine itself applies.

        They are told apart by name, the same way the engine finds them
        again before reusing them.
        """
        return taxes.filtered(lambda tax: tax.name.startswith("US Sales Tax"))

    @api.model
    def _remove_us_taxes(self, lines, field_name):
        """Take the engine's own taxes off ``lines`` and keep the rest.

        Return the lines that had one.
        """
        changed = lines.browse()
        for line in lines:
            us_taxes = self._us_engine_taxes(line[field_name])
            if us_taxes:
                line[field_name] = [Command.unlink(tax.id) for tax in us_taxes]
                changed |= line
        return changed

    @api.model
    def _result_source(self, result):
        """Return the tax source a document records for ``result``.

        A tax that did not land on the lines records "error", as its
        audit row does, even when the engine found a rate.
        """
        if not result.get("applied", True):
            return "error"
        return result.get("source", "")

    @api.model
    def _repair_us_tax(self, tax):
        """Bring a reused tax back to what the engine creates.

        Whatever carries the engine's name gets applied, whether it comes
        from an earlier version, was created by hand or was edited later,
        so the fields the amounts depend on are rewritten when they
        differ. A price-included tax would put the tax inside the price
        instead of on top of it.
        """
        vals = {}
        if tax.price_include_override != "tax_excluded":
            vals["price_include_override"] = "tax_excluded"
        if not tax.tax_group_id or tax.tax_group_id.name != "US Sales Tax":
            vals["tax_group_id"] = self._get_us_tax_group(tax.company_id).id
        if vals:
            tax.write(vals)

    @api.model
    def _get_or_create_state_tax(self, state_code, company, rate_pct=0.0):
        """Get or create an account.tax for this US state with the exact rate.

        We use one tax per state+rate combination so rates are traceable.
        Rate is stored as percentage (e.g., 7.0 for 7%).
        The tax lives on the root of the company tree, so every branch
        shares it: core requires tax names to be unique across the tree.
        """
        if not state_code:
            return False

        amount_pct = round(rate_pct * 100, 4)  # 0.07 → 7.0
        name = f"US Sales Tax {state_code} {amount_pct:.4g}%"

        # Use sudo() — tax creation requires accounting permissions
        Tax = self.env["account.tax"].sudo()

        tax = Tax.search(
            [
                ("name", "=", name),
                ("type_tax_use", "=", "sale"),
                *Tax._check_company_domain(company),
            ],
            limit=1,
        )

        if not tax:
            root = company.root_id
            tax = Tax.create(
                {
                    "name": name,
                    "type_tax_use": "sale",
                    "amount_type": "percent",
                    "amount": amount_pct,
                    "price_include_override": "tax_excluded",
                    "company_id": root.id,
                    "tax_group_id": self._get_us_tax_group(root).id,
                    "description": f"US Sales Tax — {state_code} @ {amount_pct:.4g}%",
                }
            )
            _logger.info('Created tax "%s" at %s%%', name, amount_pct)
        else:
            self._repair_us_tax(tax)

        return tax

    @api.model
    def _get_or_create_exempt_tax(self, company):
        """Get or create the shared 0% tax for exempt lines.

        One tax for both exempt_rule and exempt_nexus, across all states —
        the specific reason (which category, which state, no nexus) is
        already on us.tax.calculation.log per calculation. This tax only
        needs to show "evaluated, no tax due" on the document/report,
        instead of leaving the line with no tax at all, which is
        indistinguishable from "tax was never calculated".
        Like the state taxes, it lives on the root of the company tree.
        """
        if not company:
            return False

        name = "US Sales Tax - Exempt (0%)"
        Tax = self.env["account.tax"].sudo()

        tax = Tax.search(
            [
                ("name", "=", name),
                ("type_tax_use", "=", "sale"),
                *Tax._check_company_domain(company),
            ],
            limit=1,
        )
        if not tax:
            root = company.root_id
            tax = Tax.create(
                {
                    "name": name,
                    "type_tax_use": "sale",
                    "amount_type": "percent",
                    "amount": 0.0,
                    "price_include_override": "tax_excluded",
                    "company_id": root.id,
                    "tax_group_id": self._get_us_tax_group(root).id,
                    "description": (
                        "US Sales Tax — Exempt (product category or no "
                        "nexus); see Calculation Log for the specific reason."
                    ),
                }
            )
            _logger.info('Created tax "%s"', name)
        else:
            self._repair_us_tax(tax)
        return tax

    @api.model
    def _get_us_tax_group(self, company):
        """Return the US Sales Tax group shared by the whole tree of
        ``company``, so taxes created on its root can use it.
        """
        TaxGroup = self.env["account.tax.group"].sudo()
        root = company.root_id
        tax_group = TaxGroup.search(
            [("name", "=", "US Sales Tax"), *TaxGroup._check_company_domain(root)],
            limit=1,
        )
        if not tax_group:
            tax_group = TaxGroup.create(
                {"name": "US Sales Tax", "sequence": 10, "company_id": root.id}
            )
        return tax_group

    # ── Audit log ─────────────────────────────────────────────────────────────

    @api.model
    def _log(
        self,
        res_model,
        res_id,
        address,
        source,
        taxable_amount=0,
        tax_amount=0,
        provider_id=None,
        state_id=None,
        nexus_applied=False,
        total_rate=0,
        state_rate=0,
        county_rate=0,
        partner_id=None,
        applied=True,
    ):
        # Resolve state_id from address if not provided
        if not state_id and address.get("state"):
            state = self.env["res.country.state"].search(
                [("code", "=", address["state"]), ("country_id.code", "=", "US")],
                limit=1,
            )
            state_id = state.id if state else False

        self.env["us.tax.calculation.log"].sudo().log_calculation(
            {
                "res_model": res_model,
                "res_id": res_id,
                "partner_id": partner_id,
                "shipping_zip": address.get("zip", ""),
                "shipping_city": address.get("city", ""),
                "shipping_state_id": state_id or False,
                "full_address": address.get("address", ""),
                "source": source,
                "provider_id": provider_id,
                "nexus_applied": nexus_applied,
                "total_rate": total_rate,
                "state_rate": state_rate,
                "county_rate": county_rate,
                "taxable_amount": taxable_amount,
                "tax_amount": tax_amount,
                "calculated_by": self.env.user.id,
                "status": self._log_status(source, applied),
            }
        )

    @api.model
    def _log_status(self, source, applied):
        if not applied or source == "error":
            return "error"
        if source in ("skip_non_us", "skip_no_address"):
            return "skipped"
        return "success"

    @api.model
    def _log_on_own_cursor(self, res_model, res_id, *args, **kwargs):
        """Write an audit row that outlives the rollback of the caller.

        Used right before an exception leaves the engine, when the row is
        the only trace the failed calculation will leave. The separate
        cursor commits that single insert and nothing else, so the
        caller's transaction is not committed.

        A failure to write the row is logged and swallowed, so the
        caller's own exception is the one that leaves the engine: the
        block policy relies on its ProviderError to stop the validation.
        """
        try:
            with self.env.registry.cursor() as cr:
                self.with_env(self.env(cr=cr))._log(res_model, res_id, *args, **kwargs)
        except Exception as exc:
            _logger.warning(
                "US Tax audit row for %s %s could not be written: %s",
                res_model,
                res_id,
                exc,
            )
