"""Clientes router — /api/clientes.

Contract: `products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §5.
Slice B (routers) over Slice A's `clientes_service.py` / `identidade_service.py`
(§6 — "A and B share `clientes_service.py`'s interface only"). This file does
NOT modify either of those; it consumes their exported functions and adds two
things `clientes_service.py` explicitly leaves for this slice:

  1. The `get_clientes_client()` DI seam `clientes_service.py`'s module
     docstring asks for — mirrors `app/modules/leads/deps.py::get_leads_client`
     / `app/services/portal_roi_service.py::get_portal_roi_client` exactly
     (same `MockSupabaseClient.schema()` data-loss bug, same fix).
  2. A durable "manter separados" marker (migration `049`,
     `cliente_revisao_rejeitadas`) — `clientes_service.list_review_groups`
     has no "don't resurface" concept; Slice A's delivery note flags this
     gap explicitly and leaves the decision to this slice. See `049`'s
     header for the full reasoning.

Auth: ``Depends(get_current_user_org)`` on every route, no exceptions —
``org_id`` always comes from the auth context, never a client parameter
(contract §5, non-negotiable). Mirrors `portal_roi_router.py`'s shape.

Error mapping: `clientes_service.py`'s own exceptions (`ClienteNotFound`,
`MergeNotFound`, `MergeAlreadyUndone`) are plain `Exception` subclasses, NOT
`AppException` — unlike `portal_roi_router.py`'s implicit mapping, this router
DOES need explicit `try/except` at each call site to convert them to
`NotFoundError`/`ConflictError` (both `AppException` subclasses, so the
platform-wide handler `create_product_app` wires still produces the right
status + an actionable ``{"error": {...}}`` body from there on).

Route-ordering hazard (mirrors `imoveis_router.py`'s `/{codigo}`-declared-last
discipline): `/revisao` is a literal 1-segment path exactly like `/{cliente_id}`
— it MUST be declared before the bare `/{cliente_id}` GET/PATCH routes, or
FastAPI would try to parse the literal "revisao" as a UUID `cliente_id` and
422 instead of matching the review-queue route.
"""
from __future__ import annotations

import weakref
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.services import clientes_backfill_job
from app.services import clientes_service as svc
from app.services import identidade_service as ident

router = APIRouter(prefix="/api/clientes", tags=["clientes"])

_SCHEMA = "social_wiring"
_PAGE = 1000  # PostgREST's default unpaginated-select row cap — see
# `clientes_service.py::_select_all`'s docstring for the bug this guards
# against.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── DI seam: schema-scoped, cached client ─────────────────────────────
#
# Mirrors `app/modules/leads/deps.py::get_leads_client` /
# `app/services/portal_roi_service.py::get_portal_roi_client` EXACTLY —
# `MockSupabaseClient.schema(name)` returns a BRAND NEW wrapper with an
# EMPTY per-table row cache on every call, so re-resolving `.schema()`
# per request (the `imoveis_service.py`/`marcas_service.py` shape —
# flagged as `drift-found:` in the Slice A delivery note, not fixed
# here, out of file scope) silently loses every prior write the instant
# two separate calls re-derive the schema binding. Binding once per
# underlying admin-client OBJECT and reusing it fixes this for the mock;
# a real Supabase client is stateless HTTP-request shaping either way.

_scoped_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_clientes_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin client,
    cached by the underlying admin-client object (see module docstring).
    This is the `get_clientes_client()` helper `clientes_service.py`'s
    module docstring asks Slice B to build."""
    admin = get_admin_client()
    cached = _scoped_cache.get(admin)
    if cached is None:
        cached = admin.schema(_SCHEMA)
        _scoped_cache[admin] = cached
    return cached


# ─── low-level table helpers (this router's own reads only — never
# duplicates a `clientes_service.py` write path) ────────────────────


def _t(client: Any, name: str):
    return client.table(name)


def _all_rows(client: Any, table: str, org_id: UUID, **eq_filters: Any) -> list[dict]:
    """Paginate past PostgREST's row cap — same bug class
    `clientes_service._select_all` guards against (private there, so
    duplicated here for reads that module doesn't expose: the
    `corretor_id` join and the review-rejection lookups)."""
    out: list[dict] = []
    start = 0
    while True:
        query = _t(client, table).select("*").eq("org_id", str(org_id))
        for key, value in eq_filters.items():
            query = query.eq(key, value)
        result = query.range(start, start + _PAGE - 1).execute()
        rows = result.data or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


def _all_clientes(
    client: Any, org_id: UUID, *, ativo: Optional[bool], q: Optional[str]
) -> list[dict]:
    """Unpaginated (past the row cap) fetch of every `clientes` row
    matching `ativo`/`q` — used ONLY on the `corretor_id` cross-filter
    path in `list_clientes_route`: that path must filter+paginate in
    Python AFTER intersecting with the corretor's touch-derived
    cliente-id set, so `clientes_service.list_clientes`'s own DB-side
    `.range()` pagination would paginate the WRONG (pre-filter) set. The
    default (no `corretor_id`) path never calls this — it uses
    `clientes_service.list_clientes` directly, which paginates correctly
    at the DB."""
    out: list[dict] = []
    start = 0
    while True:
        query = _t(client, "clientes").select("*").eq("org_id", str(org_id))
        if ativo is not None:
            query = query.eq("ativo", ativo)
        if q:
            query = query.ilike("nome", f"%{q}%")
        result = query.range(start, start + _PAGE - 1).execute()
        rows = result.data or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


def _cliente_ids_for_corretor(client: Any, org_id: UUID, corretor_id: UUID) -> set[str]:
    """`clientes` has no direct corretor column — decoupled from a single
    lead's corretor by design (see `clientes_service.list_clientes`'s
    docstring, which explicitly flags corretor_id filtering as "a
    routing/query decision" left for this router). Resolved through the
    touch trail instead: every `leads` row owned by this corretor ->
    every `cliente_touches` row for that lead -> the cliente it belongs
    to. `meta_ads_leads` carries no corretor assignment, so a cliente
    touched ONLY via Meta never matches a corretor filter — correct, not
    a gap: a Meta lead has no corretor to filter by.

    NOC-REMEDIATE[clientes-corretor-filter-perf]: fetches every touch for
    the org to cross-reference — correct at the live ~14.5k-row scale but
    not indexed for it; a dedicated RPC/join would avoid the full scan.
    2026-08-13."""
    leads = _all_rows(client, "leads", org_id, corretor_id=str(corretor_id))
    lead_ids = {str(r["id"]) for r in leads}
    if not lead_ids:
        return set()
    touches = _all_rows(client, "cliente_touches", org_id)
    return {
        t["cliente_id"]
        for t in touches
        if t["origem_tabela"] == "leads" and t["origem_id"] in lead_ids
    }


def _rejected_keys(client: Any, org_id: UUID) -> set[str]:
    rows = _all_rows(client, "cliente_revisao_rejeitadas", org_id)
    return {r["chave_canonica"] for r in rows}


def _reject_group(
    client: Any, org_id: UUID, chave_canonica: str, motivo: Optional[str]
) -> None:
    """Idempotent — matches migration `049`'s UNIQUE (org_id,
    chave_canonica): rejecting an already-rejected group is a no-op, not
    a second row or an error."""
    existing = (
        _t(client, "cliente_revisao_rejeitadas")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("chave_canonica", chave_canonica)
        .execute()
    ).data or []
    if existing:
        return
    _t(client, "cliente_revisao_rejeitadas").insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "chave_canonica": chave_canonica,
            "motivo": motivo,
            "rejeitado_em": _now(),
            "created_at": _now(),
        }
    ).execute()


# ─── Schemas ──────────────────────────────────────────────────────────────


class PageOut(BaseModel):
    items: list[dict] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pages: int = 1


def _paginate_items(items: list[dict], page: int, page_size: int) -> PageOut:
    """Python-side pagination over an already-filtered, already-fetched
    list — for read paths whose filtering can't happen at the DB query
    level, so `clientes_service`'s `.range()`-based `list_clientes`/
    `get_touches` (DB-side pagination, `count="exact"`) don't apply.
    Shared by the `corretor_id` cross-filter branch of
    `list_clientes_route` and `list_revisao`, so this `ceil(total/
    page_size)` arithmetic exists in exactly ONE place for this
    pagination style rather than a 3rd/4th hand-copy (DRY N=3 rule)."""
    total = len(items)
    start = max(0, (page - 1) * page_size)
    page_items = items[start : start + page_size]
    pages = max(1, (total + page_size - 1) // page_size)
    return PageOut(items=page_items, total=total, page=page, pages=pages)


class ClientePatchBody(StrictHttpModel):
    """PATCH body — `nome` and `ativo` are the only client-writable
    lifecycle fields. `arquivado_em`/`inativo_em` are derived
    server-side from the `ativo` transition, never accepted raw (a
    client-supplied archive timestamp is exactly the kind of
    silently-wrong write `StrictHttpModel`'s `extra="forbid"` exists to
    prevent elsewhere)."""

    nome: Optional[str] = None
    ativo: Optional[bool] = None

    # Identity substrate (migration 068) — the columns the Documentos-tab
    # checklist DERIVES from. There is no separate "tick the checklist" call:
    # filling a field here IS how its item gets ticked.
    #
    # `nome_completo` is deliberately distinct from `nome`. `nome` is whatever
    # the originating channel supplied (a WhatsApp push name, a Meta leadgen
    # `full_name`, an OLX display name) and is often a first name or a handle;
    # the checklist item asserts that someone collected the person's legal full
    # name. Folding them would auto-tick that item for every lead that ever
    # arrived with any name at all.
    #
    # `data_nascimento_origem` is NOT accepted — the server stamps it
    # (`clientes_service.update_cliente`), because provenance describes how a
    # value arrived and a caller must not be able to assert it.
    nome_completo: Optional[str] = None
    email: Optional[str] = None
    data_nascimento: Optional[date] = None
    genero: Optional[str] = None

    # Migration 073. `celular` is here for the same reason `email` is: the
    # canonical key holds one or the other, so a cliente keyed by email has
    # nowhere else to put a phone — and celular is now REQUIRED to move an
    # atendimento between stages.
    #
    # `genero_origem` is NOT accepted, exactly like `data_nascimento_origem`:
    # gender is now also read off an identity document, so its provenance is
    # the server's to stamp. A caller able to assert `origem='rg'` could make a
    # typed value look like a document reading, or the reverse.
    celular: Optional[str] = None
    profissao: Optional[str] = None

    # Migration 097 — qualificação civil, the fields an instrument needs to
    # name a party. `cpf` and `rg` are checklist items on the same terms as
    # everything above: filling one here IS how its tick happens.
    #
    # `cpf_origem` / `rg_origem` are NOT accepted, exactly like
    # `data_nascimento_origem` and `genero_origem` — both numbers are now read
    # off identity documents too, so their provenance is the server's to stamp.
    # A caller able to assert `origem='rg'` could make a typed value look like
    # a document reading, or the reverse.
    cpf: Optional[str] = None
    rg: Optional[str] = None
    #: Issuing body and UF as printed — "SSP/SP". A contract qualifies a party
    #: by the number AND its issuer; the number alone does not identify the
    #: document.
    rg_orgao_expedidor: Optional[str] = None

    #: 🔴 The one that changes how many people sign. A sale of real property by
    #: a married person without the other spouse's outorga is voidable
    #: (CC art. 1.647), so this is not a preference field.
    estado_civil: Optional[str] = None
    regime_bens: Optional[str] = None
    #: The spouse's OWN clientes row, so they get the same checklist, uploads
    #: and extraction as any other signatory. A name in TEXT signs nothing.
    conjuge_cliente_id: Optional[UUID] = None
    nacionalidade: Optional[str] = None

    # Residential address of the PERSON — not of any imóvel. Structured rather
    # than one line, matching `imoveis`: a contract prints the parts separately
    # and a CEP lookup fills them separately.
    endereco_cep: Optional[str] = None
    endereco_logradouro: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_complemento: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = None


class MergeGrupoBody(StrictHttpModel):
    cliente_id_sobrevivente: UUID


class MergeGrupoOut(BaseModel):
    cliente_id: UUID
    merged_ids: list[UUID] = Field(default_factory=list)
    merge_ids: list[UUID] = Field(default_factory=list)


class ManterSeparadosOut(BaseModel):
    chave_canonica: str
    rejeitado: bool = True


class MergeSegurosOut(BaseModel):
    """Result of draining the auto-mergeable part of the review queue."""

    grupos_mesclados: int
    clientes_absorvidos: int
    grupos_restantes: int


class DesfazerOut(BaseModel):
    cliente_id: UUID


# ─── Routes ───────────────────────────────────────────────────────────────
#
# `/revisao` (and its `/revisao/{grupo}/...` children) is declared BEFORE
# the bare `/{cliente_id}` GET/PATCH routes and `/{cliente_id}/touches` —
# see the module docstring's route-ordering-hazard note.


@router.get("", response_model=PageOut)
async def list_clientes_route(
    ativo: Optional[bool] = Query(True),
    q: Optional[str] = Query(None),
    corretor_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> PageOut:
    """Board list (contract §5). Default active-only (D4)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    if corretor_id is None:
        result = svc.list_clientes(
            client, org_id, ativo=ativo, q=q, page=page, page_size=page_size
        )
        return PageOut(**result)

    allowed = _cliente_ids_for_corretor(client, org_id, corretor_id)
    matching = _all_clientes(client, org_id, ativo=ativo, q=q)
    items = [c for c in matching if c["id"] in allowed]
    items.sort(key=lambda c: c.get("ultimo_contato_em") or "", reverse=True)
    return _paginate_items(items, page, page_size)


@router.get("/revisao", response_model=PageOut)
async def list_revisao(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> PageOut:
    """The review queue (contract §5) — the canonical paginated envelope
    (`{items,total,page,pages}`, matching `list_clientes_route`'s
    `PageOut` / `ClientesPage` / `ImovelPage`) rather than a bespoke
    `{groups:[...]}` shape. This is a house-shape requirement, not
    cosmetic: the FE's `useClientesRevisao.ts::normalizeRevisaoPage`
    only recognizes THIS envelope or a bare array — a `{groups:[...]}`
    response silently fell through both branches to an empty page while
    returning 200 with real data (live incident, ~350 groups rendered as
    "fila vazia").

    `POST .../manter-separados` decisions are durably excluded (see
    migration `049`) BEFORE pagination, not after: filtering must run
    against the FULL candidate set. Paginate-then-filter would silently
    shrink whichever page a rejected group used to occupy — a page that
    reports `page_size` slots but delivers fewer, hiding real remaining
    work rather than surfacing it on the next page.
    `clientes_service.list_review_groups` itself has no "don't resurface"
    concept — that filtering is this router's job."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    groups = svc.list_review_groups(client, org_id)
    rejected = _rejected_keys(client, org_id)
    visible = [g for g in groups if g["chave_canonica"] not in rejected]
    return _paginate_items(visible, page, page_size)


class BackfillOrgOut(BaseModel):
    """What the sweep did for one org. A per-org failure reports `ok=false`
    and leaves the counters at zero rather than omitting the org — a missing
    row would read as "nothing to do" instead of "this one broke"."""

    org_id: str
    ok: bool
    clientes_created: int = 0
    touches_created: int = 0
    atendimentos_repointed: int = 0
    atendimentos_collapsed: int = 0
    stragglers_parked_for_review: int = 0
    clientes_reactivated: int = 0


class BackfillOut(BaseModel):
    skipped: Optional[str] = None
    orgs: list[BackfillOrgOut] = Field(default_factory=list)


# 🔴 ROUTE ORDER: `/backfill` is a literal 1-segment path exactly like
# `/{cliente_id}` — it MUST stay above the bare `/{cliente_id}` GET/PATCH
# routes or FastAPI would try to parse "backfill" as a UUID and 422. Same
# hazard the module docstring flags for `/revisao`.
def get_backfill_runner():
    """DI seam: the person-layer sweep this route triggers.

    Tests override via `app.dependency_overrides[get_backfill_runner]` with a
    double, so the route's own behaviour (auth, response shaping, the
    `skipped` passthrough) is exercised without running a real org-wide sweep.
    Declared rather than patched — replacing `clientes_backfill_job.run_now`
    on this module would swap out the very thing the test claims to exercise.
    → KB § PATTERNS/backend/di-test-seam.md.
    """
    return clientes_backfill_job.run_now


@router.post("/backfill", response_model=BackfillOut)
def executar_backfill(
    auth=Depends(get_current_user_org),
    run_sweep=Depends(get_backfill_runner),
) -> BackfillOut:
    """Run the person-layer sweep NOW instead of waiting for the schedule.

    🔴 Why this endpoint exists (found in prod 2026-08-31).

    `atendimentos.cliente_id` is populated ONLY by `clientes_backfill`, an
    interval job. There was no trigger, no on-demand path, and no UI anywhere
    that could attach a person — so a lead created by hand sat with
    `cliente_id IS NULL` until the next scheduled pass, and `stage_gate`
    refuses to move a card whose atendimento has no titular. An operator who
    had just typed a name and a phone was told the card could not move, with
    no action available to them. This is that missing action.

    Deliberately runs the SAME all-orgs body as the scheduled pass rather than
    an org-scoped variant: this button means "run the job now", and a second
    org-scoped implementation of the same sweep is exactly the kind of
    near-duplicate that drifts from the original. The work done for other orgs
    is work the scheduler would have done anyway.

    Safe to expose to any authenticated org member because it is idempotent
    AND lease-guarded — a repeated press while a sweep is in flight returns
    `skipped="lease_held"` without starting a second pass, so it cannot be
    used to pile on load. Declared `def` (not `async def`) so FastAPI runs the
    synchronous, network-bound sweep in its threadpool instead of blocking the
    event loop.
    """
    _user, _token, raw_org = auth
    coerce_org_uuid(raw_org)  # rejects a malformed org claim before any work
    result = run_sweep()
    return BackfillOut(
        skipped=result.get("skipped"),
        orgs=[BackfillOrgOut(**o) for o in result.get("orgs", [])],
    )


@router.post("/revisao/merge-seguros", response_model=MergeSegurosOut)
async def merge_seguros(
    simular: bool = Query(False),
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> MergeSegurosOut:
    """Drain every group the classifier considers unambiguous, in one action.

    🔴 WHY THIS EXISTS, AND WHY IT IS STILL A BUTTON
    -------------------------------------------------
    The queue held 351 groups in production. At two clicks each that is an
    afternoon of work nobody was ever going to do, so it was not being done —
    and a review queue nobody drains is a data-quality problem that only grows.
    Widening `normalize_name` (punctuation, origin markers, handle taglines)
    moved 81 of those 351 into the auto-merge classes; this endpoint applies
    exactly those.
    
    It is deliberately NOT automatic. `identidade_incerta` rows were parked
    for a HUMAN, and folding customer records together is not reversible from
    the operator's side — so the decision stays a person's, it just costs one
    press instead of 162. Everything the classifier is unsure about (C4/C5/C6)
    is untouched and still one-by-one.

    The survivor is the candidate with the longest name, which is the
    contract's own rule for C3 (`identidade_service.longest_raw_name`) — the
    fuller spelling is the one worth keeping.

    `simular=true` counts without merging. That is how the button gets to say
    "Mesclar 81 grupos" instead of an unqualified "merge everything safe" —
    a bulk action that will not tell you its size before you press it is one
    people are right not to press.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    grupos = svc.list_review_groups(client, org_id)
    mesclados = absorvidos = 0

    for group in grupos:
        _motivo, automatico = ident.classify_names(
            [c.get("nome") for c in group["candidatos"]]
        )
        if not automatico:
            continue

        candidatos = group["candidatos"]
        # Longest name wins; the id breaks ties so two runs agree.
        sobrevivente = max(
            candidatos, key=lambda c: (len((c.get("nome") or "").strip()), str(c["id"]))
        )
        outros = [c for c in candidatos if c["id"] != sobrevivente["id"]]
        if not outros:
            continue

        if simular:
            mesclados += 1
            absorvidos += len(outros)
            continue

        for candidato in sorted(outros, key=lambda c: str(c["id"])):
            svc.merge_clientes(
                client,
                org_id,
                cliente_id_sobrevivente=UUID(str(sobrevivente["id"])),
                cliente_id_absorvido=UUID(str(candidato["id"])),
                motivo=group["motivo"],
                # `automatico=False`: a person pressed the button. Recording it
                # as a machine merge would make the audit trail claim nobody
                # decided this.
                automatico=False,
            )
            absorvidos += 1
        mesclados += 1

    return MergeSegurosOut(
        grupos_mesclados=mesclados,
        clientes_absorvidos=absorvidos,
        grupos_restantes=len(grupos) - mesclados,
    )


@router.post("/revisao/{grupo}/merge", response_model=MergeGrupoOut)
async def merge_grupo(
    grupo: str,
    body: MergeGrupoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> MergeGrupoOut:
    """Operator confirms a merge (contract §5) — folds every OTHER
    candidate in the group into `cliente_id_sobrevivente`, one
    `clientes_service.merge_clientes` call per candidate (that function
    only ever takes exactly two ids; a C6 group can have 3+ candidates)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    groups = svc.list_review_groups(client, org_id)
    group = next((g for g in groups if g["chave_canonica"] == grupo), None)
    if group is None:
        raise NotFoundError("clientes/revisao", grupo)

    candidato_ids = {c["id"] for c in group["candidatos"]}
    survivor = str(body.cliente_id_sobrevivente)
    if survivor not in candidato_ids:
        raise NotFoundError("clientes/revisao candidato", survivor)

    merged_ids: list[str] = []
    merge_ids: list[str] = []
    for candidato_id in sorted(candidato_ids - {survivor}):
        merge_id = svc.merge_clientes(
            client,
            org_id,
            cliente_id_sobrevivente=UUID(survivor),
            cliente_id_absorvido=UUID(candidato_id),
            motivo=group["motivo"],
            automatico=False,
        )
        merged_ids.append(candidato_id)
        merge_ids.append(merge_id)

    return MergeGrupoOut(
        cliente_id=UUID(survivor),
        merged_ids=[UUID(x) for x in merged_ids],
        merge_ids=[UUID(x) for x in merge_ids],
    )


@router.post("/revisao/{grupo}/manter-separados", response_model=ManterSeparadosOut)
async def manter_separados(
    grupo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> ManterSeparadosOut:
    """Operator rejects a merge (contract §5) — durable: `GET /revisao`
    never resurfaces this key again (migration `049`)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    groups = svc.list_review_groups(client, org_id)
    group = next((g for g in groups if g["chave_canonica"] == grupo), None)
    if group is None:
        raise NotFoundError("clientes/revisao", grupo)

    _reject_group(client, org_id, grupo, group["motivo"])
    return ManterSeparadosOut(chave_canonica=grupo, rejeitado=True)


@router.post("/merges/{merge_id}/desfazer", response_model=DesfazerOut)
async def desfazer_merge(
    merge_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> DesfazerOut:
    """Undo (D3)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        new_id = svc.undo_merge(client, org_id, merge_id)
    except svc.MergeNotFound as exc:
        raise NotFoundError("cliente_merges", str(merge_id)) from exc
    except svc.MergeAlreadyUndone as exc:
        raise ConflictError(str(exc), resource="cliente_merges") from exc
    return DesfazerOut(cliente_id=UUID(new_id))


@router.get("/{cliente_id}/touches", response_model=PageOut)
async def get_touches_route(
    cliente_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> PageOut:
    """The timeline feed (contract §5), chronological."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    if svc.get_cliente(client, org_id, cliente_id) is None:
        raise NotFoundError("clientes", str(cliente_id))
    result = svc.get_touches(client, org_id, cliente_id, page=page, page_size=page_size)
    return PageOut(**result)


@router.get("/{cliente_id}")
async def get_cliente_route(
    cliente_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> dict:
    """One person + negociações (active AND closed, D17) + touch count
    (contract §5). `atendimentos` has no read surface exported by
    `clientes_service.py` (Slice A's file list is the resolution engine
    + backfill; this read is Slice B's own, queried directly here — no
    write, no modification to that module)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    cliente = svc.get_cliente(client, org_id, cliente_id)
    if cliente is None:
        raise NotFoundError("clientes", str(cliente_id))

    atendimentos = (
        _t(client, "atendimentos")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []
    touches = svc.get_touches(client, org_id, cliente_id, page=1, page_size=1)

    return {
        **cliente,
        "atendimentos": atendimentos,
        "touch_count": touches["total"],
    }


@router.patch("/{cliente_id}")
async def update_cliente_route(
    cliente_id: UUID,
    body: ClientePatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_clientes_client),
) -> dict:
    """nome, ativo/arquivado (manual restore, D4).

    🔴 `mode="json"` is load-bearing, not decoration. `data_nascimento` is
    typed `Optional[date]` (above), so plain `model_dump(exclude_unset=True)`
    hands back a live `datetime.date` object for any request that actually
    sets a birthdate. That object flows straight into `svc.update_cliente`'s
    `.update(payload)`, which — on the REAL client — is `postgrest-py`
    building an `httpx` request with `json=payload`; `httpx` serializes with
    the stdlib `json` module, which has never known how to encode `date`
    (`TypeError: Object of type date is not JSON serializable`), so every
    genuine "set the birthdate" PATCH 500'd. `mode="json"` makes
    `model_dump()` return the same ISO string PostgREST/Postgres already
    round-trip on the way IN — Gênero and Profissão never hit this because
    they stay `str` after validation, which is why only the date field ever
    errored. Caught only because this project's tests spy on the payload
    handed to `.update()`; the mock client itself stores whatever Python
    object it is given and would never have caught it (`tests/routers/
    test_clientes_router.py::TestPatchCliente::
    test_patch_data_nascimento_payload_is_json_serializable`)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    updates = body.model_dump(exclude_unset=True, mode="json")
    if "ativo" in updates:
        if updates["ativo"]:
            updates["arquivado_em"] = None
            updates["inativo_em"] = None
            updates["inativo_threshold_dias"] = None
            # D16 — the manual-restore-wins signal the inactivity sweep
            # (`clientes_inactivity_service.py`) reads via
            # GREATEST(ultimo_contato_em, reativado_em). Without this, a
            # restored cliente whose most recent REAL touch is still
            # older than the org's threshold would be swept right back
            # to inactive on the very next scheduled tick.
            updates["reativado_em"] = _now()
        else:
            updates["arquivado_em"] = _now()

    try:
        return svc.update_cliente(client, org_id, cliente_id, **updates)
    except svc.ClienteNotFound as exc:
        raise NotFoundError("clientes", str(cliente_id)) from exc


__all__ = ["router"]
