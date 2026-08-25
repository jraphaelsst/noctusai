"""Sources (``lead_sources`` + ``lead_source_aliases``) and brokers
(``lead_corretores`` + ``lead_corretor_aliases``) — the two canonical
dimensions + their editable normalization maps (§4 of the contract).

Read-then-write, not DB ``upsert()``
────────────────────────────────────
``noctusai_lib.testing.MockRequestBuilder.upsert()`` is a documented
no-op for propagation (returns the CURRENT data, doesn't mutate) — using
it here would silently do nothing under the test double while working
against a real Supabase client, the same prod/test divergence
``services/query.py`` avoids for ``q``. Every write in this module is
therefore read-existing-then-insert/update-missing, mirroring
``app/modules/mailchimp/store.py``'s established idiom for this codebase.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError

from app.modules.leads.seed_data import (
    CANONICAL_CORRETORES,
    CANONICAL_SOURCES,
    CORRETOR_ALIAS_RAW,
    SOURCE_ALIAS_RAW,
    normalize_alias,
)
from app.modules.leads.services.query import chunked, iter_leads_rows

_SCHEMA = "social_wiring"
_RELINK_CHUNK_SIZE = 500

#: `list_unmapped_origens`'s distinct bucket for leads with NO origem_raw
#: at all (as opposed to an unrecognized one) — see that function's
#: docstring for why these were previously invisible.
_BLANK_ORIGEM_BUCKET = "(sem origem)"

#: Columns migration 025 declares `NOT NULL` on `lead_sources` /
#: `lead_corretores` (excluding `slug`, handled separately in
#: `update_source`) — an explicit `null` patch value for one of these is
#: ignored rather than applied. See `update_source`/`update_corretor`.
_SOURCE_NOT_NULLABLE_FIELDS = {"label", "categoria", "ativo", "ordem"}
_CORRETOR_NOT_NULLABLE_FIELDS = {"nome", "ativo"}


def _table(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see
    # `app/modules/leads/deps.py::get_leads_client`'s docstring.
    return client.table(name)


def _new_id_and_created_at() -> tuple[str, str]:
    """Explicit `id`/`created_at` on every insert in this module — same
    reasoning as ``leads_service.create_lead``: a deterministic UUID +
    timestamp the caller controls, portable across the real Supabase
    client and ``MockSupabaseClient`` (whose auto-id is
    ``mock-<table>-<n>``, not a UUID)."""
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    """NFD-strip accents -> lowercase -> non-alphanumeric to ``-`` ->
    collapse repeats -> trim. Single-purpose to this module (only one
    caller-shape needs it today — a slug derived from a source
    ``label``); promote to ``noctusai_lib`` if a second product needs
    the same derivation (the N=2 recurrence rule)."""
    normalized = unicodedata.normalize("NFD", value)
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "origem"


def _unique_slug(client: Any, org_id: UUID, base_slug: str, *, exclude_id: Optional[str] = None) -> str:
    """``base_slug`` if free in this org, else ``base_slug-2``,
    ``base_slug-3``, ... — never a bare 409 on a duplicate label."""
    existing = {
        r["slug"] for r in list_sources(client, org_id) if r["id"] != exclude_id
    }
    if base_slug not in existing:
        return base_slug
    n = 2
    while f"{base_slug}-{n}" in existing:
        n += 1
    return f"{base_slug}-{n}"


# ─── sources ──────────────────────────────────────────────────────────────

def list_sources(client: Any, org_id: UUID) -> list[dict]:
    resp = _table(client, "lead_sources").select("*").eq("org_id", str(org_id)).execute()
    rows = list(resp.data or [])
    rows.sort(key=lambda r: (r.get("ordem") or 0, r.get("label") or ""))
    return rows


def get_source(client: Any, org_id: UUID, source_id: UUID) -> Optional[dict]:
    resp = (
        _table(client, "lead_sources")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(source_id))
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else None


def create_source(
    client: Any,
    org_id: UUID,
    *,
    slug: Optional[str] = None,
    label: str,
    categoria: str = "outro",
    cor: Optional[str] = None,
    ativo: bool = True,
    ordem: int = 0,
) -> dict:
    # `slug` is optional at the HTTP boundary (§ schemas.LeadSourceCreate)
    # — the UI never sends one. Derive from `label` when absent/blank,
    # then guarantee `UNIQUE (org_id, slug)` (migration 025) holds by
    # appending `-2`/`-3`/... on collision instead of letting the INSERT
    # 500 on a duplicate label.
    base_slug = _slugify(slug) if slug and slug.strip() else _slugify(label)
    slug = _unique_slug(client, org_id, base_slug)
    row_id, created_at = _new_id_and_created_at()
    payload = {
        "id": row_id,
        "org_id": str(org_id),
        "slug": slug,
        "label": label,
        "categoria": categoria,
        "cor": cor,
        "ativo": ativo,
        "ordem": ordem,
        "created_at": created_at,
        "updated_at": None,
    }
    resp = _table(client, "lead_sources").insert(payload).execute()
    rows = list(resp.data or [])
    return rows[0] if rows else payload


def update_source(client: Any, org_id: UUID, source_id: UUID, **patch: Any) -> Optional[dict]:
    """The router now calls this with ``**body.model_dump(exclude_unset=True)``
    (see ``routers/sources.py``) — a key's PRESENCE here means the caller
    explicitly sent it, so (unlike the old ``is not None`` filter) an
    explicit ``null`` for ``label``/``categoria``/``cor``/``ativo``/``ordem``
    genuinely clears that field rather than being silently dropped.

    ``slug`` is the one exception: it's ``NOT NULL UNIQUE(org_id, slug)``
    (migration 025) — there's no valid cleared state for it, so an
    explicit `null`/blank slug is silently ignored (kept as-is) rather
    than attempted as a clear. A truthy slug is slugified + made unique
    (excluding this row) the same way ``create_source`` derives one."""
    existing = get_source(client, org_id, source_id)
    if existing is None:
        return None
    raw_slug = patch.pop("slug", None)
    # `label`/`categoria`/`ativo`/`ordem` are `NOT NULL` (migration 025) —
    # same reasoning as `slug`: an explicit `null` for one of these has no
    # valid applied state, so it's ignored rather than sent to the DB
    # (which would 500 on the constraint). `cor` IS nullable — an
    # explicit `null` there genuinely clears it.
    clean = {
        k: v for k, v in patch.items()
        if not (v is None and k in _SOURCE_NOT_NULLABLE_FIELDS)
    }
    if raw_slug and raw_slug.strip():
        clean["slug"] = _unique_slug(
            client, org_id, _slugify(raw_slug), exclude_id=str(source_id)
        )
    if not clean:
        return existing
    resp = (
        _table(client, "lead_sources")
        .update(clean)
        .eq("id", str(source_id))
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else {**existing, **clean}


def count_leads_for_source(client: Any, org_id: UUID, source_id: UUID) -> int:
    resp = (
        _table(client, "leads")
        .select("id", count="exact")
        .eq("org_id", str(org_id))
        .eq("origem_id", str(source_id))
        .execute()
    )
    return resp.count or 0


def delete_source(
    client: Any, org_id: UUID, source_id: UUID, *, reassign_to: Optional[UUID] = None
) -> bool:
    existing = get_source(client, org_id, source_id)
    if existing is None:
        return False
    referenced = count_leads_for_source(client, org_id, source_id)
    if referenced > 0:
        if reassign_to is None:
            raise ConflictError(
                f"{referenced} lead(s) still reference this source",
                resource="lead_sources",
            )
        # Paged read (>1000 referencing leads is exactly the scenario a
        # bare `.select()` silently truncated) + batched writes (one
        # UPDATE per ~500 ids instead of one per row — a 12k-lead source
        # deletion was previously thousands of round-trips).
        ids = [
            r["id"]
            for r in iter_leads_rows(client, org_id, "id", origem_id=str(source_id))
        ]
        for chunk in chunked(ids, _RELINK_CHUNK_SIZE):
            _table(client, "leads").update({"origem_id": str(reassign_to)}).in_(
                "id", chunk
            ).execute()
    _table(client, "lead_sources").delete().eq("id", str(source_id)).execute()
    return True


def list_source_aliases(client: Any, org_id: UUID) -> list[dict]:
    resp = (
        _table(client, "lead_source_aliases")
        .select("*")
        .eq("org_id", str(org_id))
        .execute()
    )
    return list(resp.data or [])


def list_unmapped_origens(client: Any, org_id: UUID) -> list[dict]:
    """Distinct ``origem_raw`` values on ``leads`` with no matching alias
    yet — drives the import "map these first" UI queue. Blank/missing
    ``origem_raw`` leads (~79 in the real dataset — see
    ``importer.resolvers.resolve_origem``, which flags them
    ``needs_review`` but has no alias to attach) are folded into a
    distinct ``_BLANK_ORIGEM_BUCKET`` entry instead of being silently
    skipped — they were previously invisible to this queue forever."""
    aliases = list_source_aliases(client, org_id)
    known_norms = {a["alias_norm"] for a in aliases}
    rows = iter_leads_rows(client, org_id, "origem_raw")
    counts: dict[str, int] = {}
    blank_count = 0
    for row in rows:
        raw = row.get("origem_raw")
        if not raw:
            blank_count += 1
            continue
        norm = normalize_alias(raw)
        if norm in known_norms:
            continue
        counts[raw] = counts.get(raw, 0) + 1
    out = [{"alias": alias, "count": count} for alias, count in sorted(
        counts.items(), key=lambda kv: -kv[1]
    )]
    if blank_count:
        out.append({"alias": _BLANK_ORIGEM_BUCKET, "count": blank_count})
    return out


def create_source_alias(client: Any, org_id: UUID, *, alias: str, source_id: UUID) -> dict:
    """Create/repoint an alias, then re-link matching leads (their
    ``origem_id`` + ``needs_review`` — true only when the target source's
    ``categoria`` is ``outro``)."""
    source = get_source(client, org_id, source_id)
    if source is None:
        raise NotFoundError("lead_sources", str(source_id))
    alias_norm = normalize_alias(alias)
    existing = [
        a for a in list_source_aliases(client, org_id) if a["alias_norm"] == alias_norm
    ]
    row_id_new, created_at = _new_id_and_created_at()
    payload = {
        "id": row_id_new,
        "org_id": str(org_id),
        "alias": alias,
        "alias_norm": alias_norm,
        "source_id": str(source_id),
        "origem": "manual",
        "created_at": created_at,
    }
    if existing:
        row_id = existing[0]["id"]
        resp = (
            _table(client, "lead_source_aliases")
            .update({"source_id": str(source_id), "origem": "manual"})
            .eq("id", str(row_id))
            .execute()
        )
        rows = list(resp.data or [])
        record = rows[0] if rows else {**existing[0], "source_id": str(source_id), "origem": "manual"}
    else:
        resp = _table(client, "lead_source_aliases").insert(payload).execute()
        rows = list(resp.data or [])
        record = rows[0] if rows else payload

    _relink_leads_by_origem(client, org_id, alias_norm, source_id, source.get("categoria"))
    return record


def _relink_leads_by_origem(
    client: Any, org_id: UUID, alias_norm: str, source_id: UUID, categoria: Optional[str]
) -> None:
    """Paged read (mapping an alias against a >1000-lead org used to
    relink only the first page and silently report success — see
    ``services/query.py``'s header for the class of bug this is) +
    batched writes (one UPDATE per ~500 matching ids, not one per row —
    a 3,000-lead alias was previously 3,000 round-trips)."""
    rows = iter_leads_rows(client, org_id, "id, origem_raw")
    needs_review = categoria == "outro"
    matching_ids = [
        row["id"] for row in rows
        if row.get("origem_raw") and normalize_alias(row["origem_raw"]) == alias_norm
    ]
    for chunk in chunked(matching_ids, _RELINK_CHUNK_SIZE):
        _table(client, "leads").update(
            {"origem_id": str(source_id), "needs_review": needs_review}
        ).in_("id", chunk).execute()


def delete_source_alias(client: Any, org_id: UUID, alias_id: UUID) -> bool:
    existing = [a for a in list_source_aliases(client, org_id) if a["id"] == str(alias_id)]
    if not existing:
        return False
    _table(client, "lead_source_aliases").delete().eq("id", str(alias_id)).execute()
    return True


# ─── corretores ───────────────────────────────────────────────────────────

def list_corretores(client: Any, org_id: UUID) -> list[dict]:
    resp = _table(client, "lead_corretores").select("*").eq("org_id", str(org_id)).execute()
    rows = list(resp.data or [])
    rows.sort(key=lambda r: r.get("nome") or "")
    return rows


def get_corretor(client: Any, org_id: UUID, corretor_id: UUID) -> Optional[dict]:
    resp = (
        _table(client, "lead_corretores")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(corretor_id))
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else None


def create_corretor(
    client: Any, org_id: UUID, *, nome: str, cor: Optional[str] = None, ativo: bool = True
) -> dict:
    row_id, created_at = _new_id_and_created_at()
    payload = {
        "id": row_id,
        "org_id": str(org_id),
        "nome": nome,
        "nome_norm": normalize_alias(nome),
        "cor": cor,
        "ativo": ativo,
        "created_at": created_at,
        "updated_at": None,
    }
    resp = _table(client, "lead_corretores").insert(payload).execute()
    rows = list(resp.data or [])
    return rows[0] if rows else payload


def update_corretor(client: Any, org_id: UUID, corretor_id: UUID, **patch: Any) -> Optional[dict]:
    """See ``update_source``'s docstring — same "explicit null genuinely
    clears the field, except on NOT NULL columns" rule. ``nome``/``ativo``
    are `NOT NULL` (migration 025); `cor` is nullable."""
    existing = get_corretor(client, org_id, corretor_id)
    if existing is None:
        return None
    clean = {
        k: v for k, v in patch.items()
        if not (v is None and k in _CORRETOR_NOT_NULLABLE_FIELDS)
    }
    if "nome" in clean:
        clean["nome_norm"] = normalize_alias(clean["nome"])
    if not clean:
        return existing
    resp = (
        _table(client, "lead_corretores")
        .update(clean)
        .eq("id", str(corretor_id))
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else {**existing, **clean}


def count_leads_for_corretor(client: Any, org_id: UUID, corretor_id: UUID) -> int:
    resp = (
        _table(client, "leads")
        .select("id", count="exact")
        .eq("org_id", str(org_id))
        .eq("corretor_id", str(corretor_id))
        .execute()
    )
    return resp.count or 0


def delete_corretor(
    client: Any, org_id: UUID, corretor_id: UUID, *, reassign_to: Optional[UUID] = None
) -> bool:
    existing = get_corretor(client, org_id, corretor_id)
    if existing is None:
        return False
    referenced = count_leads_for_corretor(client, org_id, corretor_id)
    if referenced > 0:
        if reassign_to is None:
            raise ConflictError(
                f"{referenced} lead(s) still reference this corretor",
                resource="lead_corretores",
            )
        # Paged read + batched writes — same reasoning as
        # `delete_source`'s reassign path.
        ids = [
            r["id"]
            for r in iter_leads_rows(client, org_id, "id", corretor_id=str(corretor_id))
        ]
        for chunk in chunked(ids, _RELINK_CHUNK_SIZE):
            _table(client, "leads").update({"corretor_id": str(reassign_to)}).in_(
                "id", chunk
            ).execute()
    _table(client, "lead_corretores").delete().eq("id", str(corretor_id)).execute()
    return True


#: The grouped view migration 080 added. Read once, not once per broker.
_CONTAGEM_VIEW = "vw_lead_corretor_contagem"


def list_corretores_with_lead_count(client: Any, org_id: UUID) -> list[dict]:
    """§5.2: ``GET /api/leads/corretores`` → each row carries ``lead_count``.

    🔴 TWO QUERIES, FIXED — NOT ONE PER BROKER.

    This used to loop `count_leads_for_corretor` over the brokers, on the
    stated reasoning that "brokers are a small dimension". Both halves of that
    were true and the conclusion was still wrong: 29 brokers meant 30
    SEQUENTIAL PostgREST round trips, and in production on 2026-08-25 this was
    the single slowest endpoint the container served — 3343ms against a p50 of
    6.4ms, on an endpoint the app shell fetches for EVERY page.

    The counting was never the problem (`idx_sw_leads_org_corretor` covers it);
    the thirty HTTP round trips were. N+1 over a small N is still N+1.

    A broker missing from the view is reported as 0 rather than skipped —
    `vw_lead_corretor_contagem` LEFT JOINs so that should not happen, and if it
    ever does, a broker with a wrong count is a far smaller failure than a
    broker that vanishes from the list.
    """
    rows = list_corretores(client, org_id)
    if not rows:
        return []
    contagens = {
        str(r["corretor_id"]): r["lead_count"]
        for r in (
            _table(client, _CONTAGEM_VIEW)
            .select("corretor_id,lead_count")
            .eq("org_id", str(org_id))
            .execute()
        ).data
        or []
    }
    return [{**r, "lead_count": contagens.get(str(r["id"]), 0)} for r in rows]


def list_corretor_aliases(client: Any, org_id: UUID) -> list[dict]:
    resp = (
        _table(client, "lead_corretor_aliases")
        .select("*")
        .eq("org_id", str(org_id))
        .execute()
    )
    return list(resp.data or [])


def list_unmapped_corretores(client: Any, org_id: UUID) -> list[dict]:
    aliases = list_corretor_aliases(client, org_id)
    known_norms = {a["alias_norm"] for a in aliases}
    rows = iter_leads_rows(client, org_id, "corretor_raw")
    counts: dict[str, int] = {}
    for row in rows:
        raw = row.get("corretor_raw")
        if not raw:
            continue
        norm = normalize_alias(raw)
        if norm in known_norms:
            continue
        counts[raw] = counts.get(raw, 0) + 1
    return [{"alias": alias, "count": count} for alias, count in sorted(
        counts.items(), key=lambda kv: -kv[1]
    )]


def create_corretor_alias(client: Any, org_id: UUID, *, alias: str, corretor_id: UUID) -> dict:
    corretor = get_corretor(client, org_id, corretor_id)
    if corretor is None:
        raise NotFoundError("lead_corretores", str(corretor_id))
    alias_norm = normalize_alias(alias)
    existing = [
        a for a in list_corretor_aliases(client, org_id) if a["alias_norm"] == alias_norm
    ]
    row_id_new, created_at = _new_id_and_created_at()
    payload = {
        "id": row_id_new,
        "org_id": str(org_id),
        "alias": alias,
        "alias_norm": alias_norm,
        "corretor_id": str(corretor_id),
        "created_at": created_at,
    }
    if existing:
        row_id = existing[0]["id"]
        resp = (
            _table(client, "lead_corretor_aliases")
            .update({"corretor_id": str(corretor_id)})
            .eq("id", str(row_id))
            .execute()
        )
        rows = list(resp.data or [])
        record = rows[0] if rows else {**existing[0], "corretor_id": str(corretor_id)}
    else:
        resp = _table(client, "lead_corretor_aliases").insert(payload).execute()
        rows = list(resp.data or [])
        record = rows[0] if rows else payload

    rows = iter_leads_rows(client, org_id, "id, corretor_raw")
    matching_ids = [
        row["id"] for row in rows
        if row.get("corretor_raw") and normalize_alias(row["corretor_raw"]) == alias_norm
    ]
    for chunk in chunked(matching_ids, _RELINK_CHUNK_SIZE):
        _table(client, "leads").update({"corretor_id": str(corretor_id)}).in_(
            "id", chunk
        ).execute()
    return record


def delete_corretor_alias(client: Any, org_id: UUID, alias_id: UUID) -> bool:
    existing = [a for a in list_corretor_aliases(client, org_id) if a["id"] == str(alias_id)]
    if not existing:
        return False
    _table(client, "lead_corretor_aliases").delete().eq("id", str(alias_id)).execute()
    return True


# ─── default-dimension seeding (see module + migration docstrings) ─────

def ensure_default_dimensions(client: Any, org_id: UUID) -> None:
    """Idempotently upsert the canonical source/corretor catalog (+ their
    alias maps) for ``org_id``. Called from the import-commit path
    (a real write already occurs there) — never from a bare GET."""
    existing_sources = {r["slug"]: r for r in list_sources(client, org_id)}
    for seed in CANONICAL_SOURCES:
        if seed["slug"] not in existing_sources:
            row = create_source(
                client,
                org_id,
                slug=seed["slug"],
                label=seed["label"],
                categoria=seed["categoria"],
                cor=seed["cor"],
                ordem=seed["ordem"],
            )
            existing_sources[seed["slug"]] = row

    existing_source_aliases = {a["alias_norm"] for a in list_source_aliases(client, org_id)}
    for raw, slug in SOURCE_ALIAS_RAW.items():
        alias_norm = normalize_alias(raw)
        if alias_norm in existing_source_aliases:
            continue
        source_row = existing_sources.get(slug)
        if source_row is None:
            continue
        row_id, created_at = _new_id_and_created_at()
        _table(client, "lead_source_aliases").insert(
            {
                "id": row_id,
                "org_id": str(org_id),
                "alias": raw,
                "alias_norm": alias_norm,
                "source_id": str(source_row["id"]),
                "origem": "seed",
                "created_at": created_at,
            }
        ).execute()
        existing_source_aliases.add(alias_norm)

    existing_corretores = {r["nome_norm"]: r for r in list_corretores(client, org_id)}
    for seed in CANONICAL_CORRETORES:
        norm = normalize_alias(seed["nome"])
        if norm not in existing_corretores:
            row = create_corretor(client, org_id, nome=seed["nome"], cor=seed["cor"])
            existing_corretores[norm] = row

    existing_corretor_aliases = {a["alias_norm"] for a in list_corretor_aliases(client, org_id)}
    for raw, nome in CORRETOR_ALIAS_RAW.items():
        alias_norm = normalize_alias(raw)
        if alias_norm in existing_corretor_aliases:
            continue
        corretor_row = existing_corretores.get(normalize_alias(nome))
        if corretor_row is None:
            continue
        row_id, created_at = _new_id_and_created_at()
        _table(client, "lead_corretor_aliases").insert(
            {
                "id": row_id,
                "org_id": str(org_id),
                "alias": raw,
                "alias_norm": alias_norm,
                "corretor_id": str(corretor_row["id"]),
                "created_at": created_at,
            }
        ).execute()
        existing_corretor_aliases.add(alias_norm)


def build_resolution_maps(
    client: Any, org_id: UUID
) -> tuple[dict[str, tuple[str, bool]], dict[str, str]]:
    """Return ``({alias_norm: (source_id, needs_review)}, {alias_norm:
    corretor_id})`` for this org — the importer resolves every row against
    these two in-memory maps instead of one DB round-trip per row."""
    sources_by_id = {r["id"]: r for r in list_sources(client, org_id)}
    source_map: dict[str, tuple[str, bool]] = {}
    for a in list_source_aliases(client, org_id):
        source = sources_by_id.get(a["source_id"])
        needs_review = bool(source and source.get("categoria") == "outro")
        source_map[a["alias_norm"]] = (a["source_id"], needs_review)

    corretor_map: dict[str, str] = {
        a["alias_norm"]: a["corretor_id"] for a in list_corretor_aliases(client, org_id)
    }
    return source_map, corretor_map


__all__ = [
    "list_sources",
    "get_source",
    "create_source",
    "update_source",
    "count_leads_for_source",
    "delete_source",
    "list_source_aliases",
    "list_unmapped_origens",
    "create_source_alias",
    "delete_source_alias",
    "list_corretores",
    "list_corretores_with_lead_count",
    "get_corretor",
    "create_corretor",
    "update_corretor",
    "count_leads_for_corretor",
    "delete_corretor",
    "list_corretor_aliases",
    "list_unmapped_corretores",
    "create_corretor_alias",
    "delete_corretor_alias",
    "ensure_default_dimensions",
    "build_resolution_maps",
]
