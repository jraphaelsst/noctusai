"""
One-off backfill script: copy AdConnect mock JSON shapes into Supabase tables.

Reads `app/data/{categories,products,promos}.json` (the legacy mock shapes
that pre-date Phase 2's catalog tables) and inserts into:
  • adconnect.categorias
  • adconnect.products
  • adconnect.promos

Idempotent — uses upsert with `ignore_duplicates=True` (= ON CONFLICT DO
NOTHING) on the tables' natural unique keys. Safe to run multiple times.

Schema source-of-truth: `migrations/001_adconnect.sql`. The mock JSON
shapes diverge from the canonical schema; this script normalizes them.

Mock-to-canonical column mapping (Phase 0 audit):

  ┌─ categories.json ────────────────────────────────────────────────────┐
  │   id (slug-string e.g. "cat6") → DB id (UUID generated)               │
  │   name                          → nome                                │
  │   (no descricao in mock — left null)                                  │
  └──────────────────────────────────────────────────────────────────────┘

  ┌─ products.json ──────────────────────────────────────────────────────┐
  │   id (string "1")    → DB id (UUID generated)                         │
  │   name               → nome                                           │
  │   sku                → sku                                            │
  │   category (slug)    → categoria_id (UUID via lookup)                 │
  │   priceB2B           → base_price                                     │
  │   inStock            → in_stock                                       │
  │   image              → fotos[0]                                       │
  │   minOrder/multiple  → DROPPED (canonical schema has estoque_quantidade
  │                          not min/multiple — Phase 2 audit decision)   │
  │   cashback           → DROPPED (canonical: lives on regras_recompensa)│
  │   brand              → DROPPED (canonical: brand context is per-org)  │
  └──────────────────────────────────────────────────────────────────────┘

  ┌─ promos.json ────────────────────────────────────────────────────────┐
  │   id ("promo-1")     → DB id (UUID generated)                         │
  │   product            → nome (used as the promo's display name)        │
  │   sku                → DROPPED (canonical: aplicavel_produtos[] FK)   │
  │   type ("promo"/"exception") → encoded into nome (no equivalent col)  │
  │   label              → descricao                                      │
  │   cashbackPct        → DROPPED (canonical: belongs to regras_recompensa)│
  │   mktBudgetPct       → DROPPED (mkt budget not in canonical promos)   │
  │   validFrom/validTo  → valido_de/valido_ate (TIMESTAMPTZ)             │
  │   active             → ativa                                          │
  └──────────────────────────────────────────────────────────────────────┘

Promo CHECK constraint requires exactly one of desconto_percentual /
desconto_valor — mocks don't carry a discount value so we synthesize a
0% percentual placeholder; the brand calibrates real values via admin V2.

Usage:
    cd products/adconnect/backend
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
        ADCONNECT_BRAND_ORG_ID=<uuid> \\
        python scripts/seed_adconnect_mocks.py

Out of scope: actually running it (no Supabase credentials in worktree).
The script is authored + smoke-tested via dry-run mode.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger("seed_adconnect_mocks")

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "app" / "data"


def _read_json(name: str) -> list[dict[str, Any]]:
    path = DATA_DIR / name
    if not path.exists():
        logger.warning("seed: missing %s — skipping", path)
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_validity(raw: Any, *, fallback: datetime) -> str:
    """Parse a mock validFrom / validTo entry into a timestamp string.

    Mock shape includes literal `"—"` as "no value"; we treat that as the
    fallback. Already-formatted dates pass through.
    """
    if raw is None or raw == "—" or raw == "":
        return fallback.isoformat()
    return f"{raw}T00:00:00+00:00"


def _build_categoria_rows(
    categories: list[dict[str, Any]], *, org_id: str
) -> list[dict[str, Any]]:
    """Map mock category shape → adconnect.categorias rows."""
    return [
        {
            "id": str(uuid4()),
            "org_id": org_id,
            "nome": c["name"],
            "ordem": idx,
            "ativa": True,
        }
        for idx, c in enumerate(categories)
    ]


def _build_product_rows(
    products: list[dict[str, Any]],
    *,
    org_id: str,
    categoria_by_slug: dict[str, str],
) -> list[dict[str, Any]]:
    """Map mock product shape → adconnect.products rows."""
    rows: list[dict[str, Any]] = []
    for p in products:
        cat_slug = p.get("category") or ""
        rows.append(
            {
                "id": str(uuid4()),
                "org_id": org_id,
                "categoria_id": categoria_by_slug.get(cat_slug),
                "sku": p["sku"],
                "nome": p["name"],
                "base_price": float(p.get("priceB2B", 0)),
                "in_stock": bool(p.get("inStock", True)),
                "fotos": [p["image"]] if p.get("image") else [],
                "ativo": True,
            }
        )
    return rows


def _build_promo_rows(
    promos: list[dict[str, Any]], *, org_id: str
) -> list[dict[str, Any]]:
    """Map mock promo shape → adconnect.promos rows.

    Canonical CHECK: exactly one of desconto_percentual / desconto_valor.
    Since mocks don't carry a real discount value, we use 0% as a
    placeholder that satisfies the CHECK + lets the brand calibrate later.
    """
    epoch_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    epoch_end = datetime(2027, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "id": str(uuid4()),
            "org_id": org_id,
            "nome": f"{p.get('label') or p.get('product') or p.get('id')}",
            "descricao": p.get("label"),
            "desconto_percentual": float(p.get("cashbackPct", 0)),
            "valido_de": _parse_validity(p.get("validFrom"), fallback=epoch_start),
            "valido_ate": _parse_validity(p.get("validTo"), fallback=epoch_end),
            "ativa": bool(p.get("active", True)),
        }
        for p in promos
    ]


def _insert_idempotent(
    db: Any, table: str, rows: list[dict[str, Any]], *, conflict: str
) -> int:
    """Insert rows with ON CONFLICT DO NOTHING semantics via upsert.

    Supabase Python client supports `upsert(rows, on_conflict="col1,col2",
    ignore_duplicates=True)` — equivalent to ON CONFLICT DO NOTHING.
    """
    if not rows:
        return 0
    db.table(table).upsert(rows, on_conflict=conflict, ignore_duplicates=True).execute()
    return len(rows)


def run(*, dry_run: bool = False) -> dict[str, int]:
    """Read mocks, build rows, insert.

    Returns a dict of `{table: rows_built}` so callers (tests, callers in
    automation) can assert on the counts even in dry-run mode.
    """
    org_id = os.getenv("ADCONNECT_BRAND_ORG_ID", "00000000-0000-0000-0000-000000000001")

    categories = _read_json("categories.json")
    products = _read_json("products.json")
    promos = _read_json("promos.json")

    cat_rows = _build_categoria_rows(categories, org_id=org_id)
    cat_by_slug = {c["nome"].lower(): c["id"] for c in cat_rows}
    # Mock categories use slug-style ids; align lookup by both name and slug.
    for src, built in zip(categories, cat_rows):
        cat_by_slug[src["id"]] = built["id"]
    prod_rows = _build_product_rows(products, org_id=org_id, categoria_by_slug=cat_by_slug)
    promo_rows = _build_promo_rows(promos, org_id=org_id)

    counts = {
        "categorias": len(cat_rows),
        "products": len(prod_rows),
        "promos": len(promo_rows),
    }
    logger.info(
        "seed: built %d categorias / %d products / %d promos for org=%s",
        counts["categorias"], counts["products"], counts["promos"], org_id,
    )

    if dry_run:
        logger.info("seed: dry_run=True — exiting before DB writes")
        return counts

    # Lazy import — keeps `dry_run` testable without Supabase deps loaded.
    from app.database import get_admin_client  # type: ignore

    db = get_admin_client()
    _insert_idempotent(db, "categorias", cat_rows, conflict="org_id,nome")
    _insert_idempotent(db, "products", prod_rows, conflict="org_id,sku")
    # promos has no natural unique key in canonical schema → insert (not upsert)
    if promo_rows:
        db.table("promos").insert(promo_rows).execute()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Build rows but skip DB writes")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
