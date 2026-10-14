"""noctus.dev.finance_import_igig -- move igig's own finance into the seed finance organ (E10 cutover step 1-2).

Roadmap `erp-seed-2026-10` E10, marker `NOC-REMEDIATE[igig-finance-cutover]` (products/igig/backend/app/main.py).
Maps `igig.fatura` / `fatura_item` (NUMERIC reais) to `igig.fin_entries` / `fin_settlements` (integer cents,
round-half-even via `noctusai_lib.primitives.money.to_cents`) for ONE org, through
`noctusai_lib.domain.finance.importers.igig`.

Modes (writes are the exception, never the default):
  * default (`dry_run=True`)          read igig rows, plan, RECONCILE per org x month x direction; writes nothing.
  * `dry_run=False, confirm=False`    status `planned`: the same report, still no write.
  * `dry_run=False, confirm=True`     writes idempotently, ONLY when the reconciliation is clean, then re-reads the
                                      stored totals and re-checks them against the plan (`post_write_mismatch` if not).
  * `confirm=True` with `dry_run=True` is REFUSED (a contradictory request is never resolved by guessing).

PROD GATE. The Supabase project behind the service-role key is the production database (there is no second one), so
building the real client -- even to READ in dry-run -- requires `allow_prod=True`. That flag is OWNER-GATED: live
database decisions are the owner's; an agent never sets it on its own authority. With an injected client (tests, a
local database) the gate does not apply. No credentials => `not_configured`, never a silent skip.

KB § PATTERNS/architect/mcp-first-scripts.md · roadmap project-history/roadmaps/erp-seed-2026-10.md E10.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from settings import REPO_ROOT

for _p in (REPO_ROOT / "seed" / "lib" / "backend",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from noctusai_lib.domain.finance._common import Scope  # noqa: E402
from noctusai_lib.domain.finance.config import FinanceConfig  # noqa: E402
from noctusai_lib.domain.finance.importers import igig as imp  # noqa: E402

logger = logging.getLogger(__name__)

SCHEMA = "igig"
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ENV_URL = "SUPABASE_URL"
ENV_KEY = "SUPABASE_SERVICE_ROLE_KEY"


def _real_client() -> Optional[Any]:
    """Service-role client bound to the `igig` schema, or None when no credentials resolve."""
    url, key = os.environ.get(ENV_URL), os.environ.get(ENV_KEY)
    if not url or not key:
        return None
    from supabase import create_client
    from supabase.lib.client_options import ClientOptions

    return create_client(url, key, options=ClientOptions(schema=SCHEMA))


def finance_import_igig(
    org_id: str,
    *,
    dry_run: bool = True,
    confirm: bool = False,
    allow_prod: bool = False,
    db: Any = None,
    client_factory: Callable[[], Optional[Any]] = _real_client,
) -> dict[str, Any]:
    """See the module docstring. `db` injects a client bound to the `igig` schema (tests / local DB)."""

    def out(status: str, **kw: Any) -> dict[str, Any]:
        return {"status": status, "ok": status in ("dry_run", "planned", "imported"), "org_id": org_id,
                "dry_run": dry_run, "confirm": confirm, **kw}

    if not org_id or not _UUID.match(str(org_id)):
        return out("error", error="org_id must be a UUID")
    if confirm and dry_run:
        return out("refused_contradiction", error="confirm=True requires dry_run=False (a write is never implied by a dry run)")
    if db is None:
        if not allow_prod:
            return out(
                "refused_prod",
                error=(
                    "the service-role client targets the PRODUCTION database; pass allow_prod=True only on the OWNER's "
                    "explicit decision (live-DB access is owner-gated). Nothing was read."
                ),
            )
        db = client_factory()
        if db is None:
            return out("not_configured", error=f"NOC-REMEDIATE[credentials]: {ENV_URL} / {ENV_KEY} not set; nothing read.")

    try:
        faturas, itens, clientes = imp.read_igig(db, org_id)
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed status, never swallowed
        logger.error("igig finance read failed for org=%s", org_id, exc_info=True)
        return out("error", error=f"could not read igig finance rows: {exc}")

    plan = imp.plan_import(org_id, faturas, itens, clientes)
    rec = imp.reconcile(plan, faturas)
    report = {
        "faturas": len(faturas), "to_import": len(plan.entries), "skipped": plan.skipped,
        "reconciliation": rec.as_dict(),
        "not_imported": "custos: igig keeps no cost ledger (custo_hora* are rates), nothing to move",
    }
    if not rec.ok:
        return out("refused_reconciliation", error="reconciliation does not match to the cent; no writes", **report)
    if dry_run:
        return out("dry_run", **report)
    if not confirm:
        return out("planned", **report)

    scope = Scope(db, FinanceConfig(schema=SCHEMA), org_id)
    try:
        written = imp.apply_plan(scope, plan)
    except Exception as exc:  # noqa: BLE001
        logger.error("igig finance import failed for org=%s", org_id, exc_info=True)
        return out("error", error=f"import failed part-way ({exc}); it is idempotent -- fix and re-run", **report)
    stored = imp.written_totals(scope)
    expected = {r["competencia"]: r["after_cents"] for r in rec.rows if r["after_cents"]}
    if stored != expected:
        return out("post_write_mismatch", written=written, stored_cents=stored, expected_cents=expected, **report)
    return out("imported", written=written, stored_cents=stored, **report)


def register(server) -> None:
    @server.tool(
        name="noctus.dev.finance_import_igig",
        description=(
            "Import igig's own finance (fatura/fatura_item, NUMERIC reais) into the seed finance organ (fin_entries/"
            "fin_settlements, integer cents, round-half-even via primitives.money.to_cents) for ONE org -- roadmap E10, "
            "NOC-REMEDIATE[igig-finance-cutover]. dry_run=True (default) reads + returns the reconciliation report "
            "(totals per org x month x direction, NUMERIC before vs cents after) and writes NOTHING. confirm=True needs "
            "dry_run=False AND a clean reconciliation; writes idempotently (source='import', source_ref='igig:fatura:<id>') "
            "and re-checks the stored totals. Reconciliation mismatch => refused, rows listed. allow_prod=True is REQUIRED "
            "to touch the real database (it IS production) and is OWNER-GATED: never set it without the owner's explicit "
            "decision. Returns {status: dry_run|planned|imported|refused_*|not_configured|error, ok, reconciliation, ...}. "
            "KB § PATTERNS/architect/mcp-first-scripts.md."
        ),
    )
    def _finance_import_igig(org_id: str, dry_run: bool = True, confirm: bool = False, allow_prod: bool = False) -> dict:
        return finance_import_igig(org_id, dry_run=dry_run, confirm=confirm, allow_prod=allow_prod)


__all__ = ["finance_import_igig"]
