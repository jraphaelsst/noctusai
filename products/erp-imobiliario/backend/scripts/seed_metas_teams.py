"""Seed the 3 canonical ERP teams — DRAGÃO, LEÃO, ÁGUIA — into a target org.

Usage:

    python -m app.scripts.seed_metas_teams --org-id <uuid>

Idempotent: re-running with the same `--org-id` reuses existing teams by name.
Team `lider_id` is left NULL — assign via the UI after real users exist.

Colors match the conventions set in `products/erp-imobiliario/METAS-PLAN.md`
(the 3 teams that the original spreadsheet used). Adjust if the pilot agency
prefers different ones.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from typing import Optional


TEAMS = [
    {"nome": "DRAGÃO", "cor": "#e53935"},
    {"nome": "LEÃO",   "cor": "#fb8c00"},
    {"nome": "ÁGUIA",  "cor": "#43a047"},
]


def _get_admin_client():
    try:
        from supabase import create_client
        from supabase.lib.client_options import ClientOptions
    except ImportError:
        sys.exit("Install supabase-py: pip install supabase")

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    return create_client(url, key, options=ClientOptions(schema="erp"))


def _ensure_team(db, org_id: str, nome: str, cor: str) -> dict:
    """Insert-if-absent a team by (org_id, nome). Returns the row."""
    existing = (
        db.table("equipes")
        .select("*")
        .eq("org_id", org_id)
        .eq("nome", nome)
        .execute()
        .data or []
    )
    if existing:
        # Refresh the cor in case the spec changed.
        if existing[0].get("cor") != cor:
            db.table("equipes").update({"cor": cor}).eq("id", existing[0]["id"]).execute()
        return existing[0]

    row = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "nome": nome,
        "cor": cor,
        "ativo": True,
    }
    result = db.table("equipes").insert(row).execute()
    return (result.data or [row])[0]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed DRAGÃO / LEÃO / ÁGUIA teams.")
    parser.add_argument("--org-id", required=True, help="Target org UUID")
    args = parser.parse_args(argv)

    db = _get_admin_client()

    print(f"Seeding 3 canonical teams into org {args.org_id}...")
    for spec in TEAMS:
        team = _ensure_team(db, args.org_id, spec["nome"], spec["cor"])
        print(f"  ✓ {team['nome']:<8} id={team['id']} cor={team.get('cor')}")

    print("Done. Assign leaders + members via /metas/configuracoes/equipes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
