"""Brand catalog loader — repo definitions → DB rows (idempotent seed).

The branding system's source of truth is a **version-controlled catalog**:
each agent (brand owner) is a directory under ``catalog/<slug>/`` with a
``brand.json`` describing the owner + its brandings (brand kits) +
references. :func:`load_catalog` parses it; :func:`seed_catalog` upserts
it into one org's ``mc_brand_owners`` / ``mc_brand_kits`` /
``mc_brand_references`` (agency model: one org manages many agents).

Idempotent: re-seeding the same catalog updates in place (keyed by
``(org_id, owner.slug)`` and ``(org_id, owner, branding.slug)``) — never
duplicates. IDs are generated here (not relied upon from insert-return) so
the same code path works against the real Supabase client and the test
``MockSupabaseClient``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"


@dataclass(frozen=True)
class ReferenceDef:
    kind: str
    label: str
    asset_url: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class BrandingDef:
    slug: str
    name: str
    default_lang: str = "pt-BR"
    persona: str = ""
    design_system: str = ""
    design_tokens: dict[str, Any] = field(default_factory=dict)
    references: list[ReferenceDef] = field(default_factory=list)


@dataclass(frozen=True)
class BrandOwnerDef:
    slug: str
    name: str
    kind: str = "real_estate_agent"
    notes: str | None = None
    brandings: list[BrandingDef] = field(default_factory=list)


# ── Parse ────────────────────────────────────────────────────────────────


def load_owner(brand_json_path: Path) -> BrandOwnerDef:
    """Parse one ``brand.json`` into a :class:`BrandOwnerDef`."""
    raw = json.loads(brand_json_path.read_text(encoding="utf-8"))
    owner = raw["owner"]
    brandings = [
        BrandingDef(
            slug=b["slug"],
            name=b["name"],
            default_lang=b.get("default_lang", "pt-BR"),
            persona=b.get("persona", ""),
            design_system=b.get("design_system", ""),
            design_tokens=b.get("design_tokens", {}) or {},
            references=[
                ReferenceDef(
                    kind=r["kind"],
                    label=r["label"],
                    asset_url=r.get("asset_url"),
                    notes=r.get("notes"),
                )
                for r in b.get("references", [])
            ],
        )
        for b in raw.get("brandings", [])
    ]
    return BrandOwnerDef(
        slug=owner["slug"],
        name=owner["name"],
        kind=owner.get("kind", "real_estate_agent"),
        notes=owner.get("notes"),
        brandings=brandings,
    )


def load_catalog(catalog_dir: Path | None = None) -> list[BrandOwnerDef]:
    """Parse every ``<owner>/brand.json`` under ``catalog_dir`` (sorted)."""
    base = catalog_dir or CATALOG_DIR
    return [load_owner(p) for p in sorted(base.glob("*/brand.json"))]


# ── Seed (idempotent upsert) ──────────────────────────────────────────────


def _upsert_owner(db, org_id: str, owner: BrandOwnerDef, created_by: str | None) -> tuple[str, str]:
    existing = (
        db.table("mc_brand_owners")
        .select("*")
        .eq("org_id", org_id)
        .eq("slug", owner.slug)
        .execute()
    )
    fields = {"name": owner.name, "kind": owner.kind, "notes": owner.notes}
    if existing.data:
        oid = existing.data[0]["id"]
        db.table("mc_brand_owners").update(fields).eq("id", oid).eq("org_id", org_id).execute()
        return oid, "updated"
    oid = str(uuid.uuid4())
    db.table("mc_brand_owners").insert(
        {"id": oid, "org_id": org_id, "slug": owner.slug, "created_by": created_by, **fields}
    ).execute()
    return oid, "created"


def _upsert_branding(
    db, org_id: str, owner_id: str, branding: BrandingDef, created_by: str | None
) -> tuple[str, str]:
    existing = (
        db.table("mc_brand_kits")
        .select("*")
        .eq("org_id", org_id)
        .eq("brand_owner_id", owner_id)
        .eq("slug", branding.slug)
        .execute()
    )
    fields = {
        "name": branding.name,
        "default_lang": branding.default_lang,
        "persona": branding.persona,
        "design_system": branding.design_system,
        "design_tokens": branding.design_tokens,
    }
    if existing.data:
        kid = existing.data[0]["id"]
        db.table("mc_brand_kits").update(fields).eq("id", kid).eq("org_id", org_id).execute()
        return kid, "updated"
    kid = str(uuid.uuid4())
    db.table("mc_brand_kits").insert(
        {
            "id": kid,
            "org_id": org_id,
            "brand_owner_id": owner_id,
            "slug": branding.slug,
            "created_by": created_by,
            **fields,
        }
    ).execute()
    return kid, "created"


def _replace_references(db, org_id: str, kit_id: str, references: list[ReferenceDef]) -> int:
    db.table("mc_brand_references").delete().eq("org_id", org_id).eq("brand_kit_id", kit_id).execute()
    if not references:
        return 0
    payload = [
        {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "brand_kit_id": kit_id,
            "kind": r.kind,
            "label": r.label,
            "asset_url": r.asset_url,
            "notes": r.notes,
        }
        for r in references
    ]
    db.table("mc_brand_references").insert(payload).execute()
    return len(payload)


def seed_catalog(
    db,
    org_id: str,
    owners: list[BrandOwnerDef] | None = None,
    *,
    created_by: str | None = None,
    catalog_dir: Path | None = None,
) -> dict[str, Any]:
    """Idempotently seed ``owners`` (or the repo catalog) into one org.

    Returns a summary: per-owner created/updated + brandings + references.
    Safe to re-run — existing rows are updated in place by slug.
    """
    if owners is None:
        owners = load_catalog(catalog_dir)

    summary: dict[str, Any] = {"owners": [], "owners_created": 0, "owners_updated": 0,
                               "brandings_created": 0, "brandings_updated": 0, "references": 0}
    for owner in owners:
        oid, o_action = _upsert_owner(db, org_id, owner, created_by)
        summary[f"owners_{o_action}"] += 1
        owner_brandings: list[dict[str, Any]] = []
        for branding in owner.brandings:
            kid, b_action = _upsert_branding(db, org_id, oid, branding, created_by)
            summary[f"brandings_{b_action}"] += 1
            ref_n = _replace_references(db, org_id, kid, branding.references)
            summary["references"] += ref_n
            owner_brandings.append({"slug": branding.slug, "id": kid, "action": b_action, "references": ref_n})
        summary["owners"].append(
            {"slug": owner.slug, "id": oid, "action": o_action, "brandings": owner_brandings}
        )
    return summary
