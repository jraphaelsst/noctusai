"""Map ``social_wiring.meta_ads_leads`` rows (the lossless Meta Lead-Ads
ledger, migration 033) onto the unified ``leads`` base — so a campaign
lead shows up alongside every spreadsheet/manual lead with the same
origem/corretor/analytics surface, while ``meta_ads_leads`` stays the raw
record of exactly what Meta sent.

Why a SERVICE and not a DB trigger
───────────────────────────────────
Migration 034's Funil card spawn is deliberately trigger-based — but that
mapping is a straight 1:1 copy of a card's own columns. This one needs
the alias/source resolution that lives in Python
(``importer.resolvers``/``services.dimensions_service``), the same
reasoning ``leads_service``/``import_service`` already follow for every
other lead-creation path on this table. Decided; not re-litigated here.

Two entry points, one mapping
──────────────────────────────
* :func:`ingest_meta_lead` — single-lead, idempotent. The Meta Lead-Ads
  webhook receiver (a peer module/migration, not this one) calls this
  per lead as it arrives.
* :func:`backfill_meta_ads_leads` — the one-off, explicit, logged bulk
  pass over every ``meta_ads_leads`` row an org already has (958 rows at
  authoring time — synced before this mapping existed). NEVER called
  from an import/sync path automatically; a real trigger (today: the
  ``POST /api/leads/meta-ingest/backfill`` route) is required.

Idempotency is the DB's job, not this module's: both entry points key on
``(org_id, meta_lead_id)`` — migration 041's
``uq_sw_leads_org_meta_lead_id`` partial unique index — via a
read-then-skip check before ever inserting, mirroring
``dimensions_service``'s "read-then-write, not DB ``upsert()``" idiom
(``MockRequestBuilder.upsert()`` is a documented no-op for propagation).

Field mapping (brief, §2)
──────────────────────────
* ``cliente_nome`` <- ``full_name``
* ``contato``      <- ``phone`` (migration 037's
  ``canonicalize_meta_lead_phone_trigger`` already canonicalizes this to
  E.164 on ``meta_ads_leads`` itself — this module does NOT re-normalize
  it; ``leads_service.create_lead``'s own ``_derive_contato_fields``
  re-derives ``contato_norm``/``contato_tipo`` from whatever ``contato``
  holds, which is a no-op re-run of the SAME canonicalization, not a
  second blind normalization pass).
* ``origem_id``    <- the org's canonical ``meta-lead-ads`` source
  (``seed_data.CANONICAL_SOURCES``, provisioned by
  ``dimensions_service.ensure_default_dimensions``)
* ``origem_raw``   <- the campaign name (provenance survives the join)
* ``data_entrada`` <- ``created_time`` (Meta's submission timestamp), the
  DATE part
* ``observacoes``  <- the qualifying ``answers`` (the ones NOT already
  promoted to a typed core column), rendered as one ``label: value`` line
  per answer — see :func:`render_answers_pt_br`
* ``corretor_id``  <- resolved ONLY when an answer value itself matches
  an existing corretor alias (``resolvers.resolve_corretor``); otherwise
  left ``NULL``. An unassigned lead is honest, a guessed corretor is not
  (brief, §2) — this module never invents one from unstructured text.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence import iter_paged_rows

from app.modules.imovel_hub import atendimento_imoveis_service, busca_service, interesses_service
from app.modules.leads.importer.resolvers import resolve_corretor
from app.modules.meta_ads.services.campanha_resolucao import resolver_campanha
from app.modules.leads.services import dimensions_service, leads_service
from app.modules.leads.services.query import backfill_generated_columns
from app.services import clientes_service

logger = logging.getLogger(__name__)

_META_LEAD_ADS_SLUG = "meta-lead-ads"

#: Question TYPES ``app.modules.meta_ads.services.leads_sync_service``
#: already promotes to a typed ``meta_ads_leads`` column
#: (``_PROMOTE_BY_TYPE``'s keys). Duplicated here rather than imported —
#: this module's zone excludes ``app/modules/meta_ads/**`` — so an answer
#: of one of these types is excluded from ``observacoes`` (it is already
#: captured by ``cliente_nome``/``contato`` above; repeating it would be
#: noise, not a qualifying answer).
_PROMOTED_QUESTION_TYPES = frozenset({"FULL_NAME", "EMAIL", "PHONE"})

#: PostgREST page size for the bulk backfill's paged read over
#: ``meta_ads_leads`` — mirrors ``query.py``'s ``_PAGE_SIZE`` pager shape
#: (a bare ``.select().execute()`` silently caps at PostgREST's default
#: page size; see that module's header for the incident this class of
#: bug caused elsewhere in this product).
_BACKFILL_PAGE_SIZE = 500


def _table(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see
    # `app/modules/leads/deps.py::get_leads_client`'s docstring.
    return client.table(name)


# ─── pure mapping (no DB access — fully unit-testable) ─────────────────

def _created_time_to_date(value: Any) -> Optional[date]:
    """``meta_ads_leads.created_time`` -> the DATE Postgres/PostgREST or
    the Meta SDK hands back: a ``datetime``/``date`` object, or an
    ISO-8601 string (``"2026-07-27T10:00:00+00:00"``). Returns ``None``
    when unparseable — never guesses a date, same contract as every
    parser in ``importer/parsers.py``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def render_answers_pt_br(
    answers: Optional[dict[str, Any]],
    *,
    question_types: Optional[dict[str, str]] = None,
    question_labels: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """The qualifying ``answers`` (everything NOT already promoted to
    ``full_name``/``email``/``phone``), one ``label: value`` line each.

    ``question_types``/``question_labels`` come from the owning form's
    persisted ``meta_ads_lead_forms.questions`` (``{key: type}`` /
    ``{key: label}}``) — when the caller has neither (form not synced, or
    a form_id the ledger no longer references), every answer is rendered
    keyed by its raw field name rather than silently dropped; nothing in
    ``answers`` is ever lost, only unlabeled. Returns ``None`` for an
    empty/absent ``answers`` dict — never an empty string (keeps
    ``observacoes IS NULL`` meaning "nothing to show", consistent with
    every other optional text column on ``leads``)."""
    if not answers:
        return None
    question_types = question_types or {}
    question_labels = question_labels or {}
    lines: list[str] = []
    for key, value in answers.items():
        if question_types.get(key) in _PROMOTED_QUESTION_TYPES:
            continue
        if value is None:
            continue
        rendered = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        rendered = rendered.strip()
        if not rendered:
            continue
        label = question_labels.get(key) or key
        lines.append(f"{label}: {rendered}")
    return "\n".join(lines) or None


def _resolve_corretor_from_answers(
    answers: Optional[dict[str, Any]], corretor_map: dict[str, str]
) -> tuple[Optional[str], Optional[str]]:
    """Only match a corretor when an answer VALUE resolves through the
    org's existing alias map — never a guess. Returns
    ``(corretor_id, corretor_raw)``, both ``None`` when nothing matches
    (or the org has no corretor aliases at all, e.g. a fresh org whose
    dimensions haven't been provisioned yet)."""
    if not answers or not corretor_map:
        return None, None
    for value in answers.values():
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not candidate or not isinstance(candidate, str):
                continue
            corretor_id = resolve_corretor(candidate, corretor_map)
            if corretor_id:
                return corretor_id, candidate
    return None, None


def _codigo_do_meta_lead(meta_lead: dict[str, Any]) -> Optional[str]:
    """The imóvel código a Meta lead is about: the 180 column when set, else
    the form answer `REF`. `None` (never a blank string) when absent — an
    unreferenced lead is accepted and surfaces as `imovel_pendente`."""
    direto = meta_lead.get("codigo_imovel")
    answers = meta_lead.get("answers")
    ref = answers.get("REF") if isinstance(answers, dict) else None
    for candidato in (direto, ref):
        if isinstance(candidato, str) and candidato.strip():
            return candidato.strip()
    return None


#: Shown on the card's timeline (the touch's ``origem_rotulo`` is ``leads.origem_raw``)
#: for a row created by ``POST /api/meta/leadgen/simular`` — a rehearsal is never
#: mistaken for a real Meta lead (CONTRACT sw-lead-to-contract §1.4).
SIMULADO_ROTULO = "Lead simulado"


def _origem_raw(meta_lead: dict[str, Any]) -> Optional[str]:
    campanha = meta_lead.get("campaign_name")
    if meta_lead.get("simulado"):
        return f"{SIMULADO_ROTULO} · {campanha}" if campanha else SIMULADO_ROTULO
    return campanha


def map_meta_lead_to_lead_payload(
    meta_lead: dict[str, Any],
    *,
    origem_source_id: str,
    corretor_map: Optional[dict[str, str]] = None,
    question_types: Optional[dict[str, str]] = None,
    question_labels: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Pure mapping: one ``meta_ads_leads`` row -> the payload
    ``leads_service.create_lead`` expects. Raises ``ValueError`` when
    ``created_time`` is missing/unparseable — ``data_entrada`` is
    ``NOT NULL`` on ``leads`` (migration 025) and this module never
    invents a date to satisfy that constraint; an un-ingestable lead is a
    named failure the caller (``ingest_meta_lead`` /
    ``backfill_meta_ads_leads``) surfaces, not a silent skip."""
    meta_lead_id = meta_lead.get("id")
    if not meta_lead_id:
        raise ValueError("map_meta_lead_to_lead_payload: meta_lead['id'] is required")

    data_entrada = _created_time_to_date(meta_lead.get("created_time"))
    if data_entrada is None:
        raise ValueError(
            f"map_meta_lead_to_lead_payload: meta_lead {meta_lead_id!r} has a "
            f"missing/unparseable created_time ({meta_lead.get('created_time')!r}) "
            "— data_entrada is NOT NULL on leads, refusing to guess"
        )

    answers = meta_lead.get("answers") or {}
    corretor_id, corretor_raw = _resolve_corretor_from_answers(answers, corretor_map or {})

    return {
        "meta_lead_id": meta_lead_id,
        # Owner decision D1 (2026-10-01): the form answer `REF` IS the imóvel
        # código (100% of 1,895 rows). Migration 180 puts the same value on
        # `meta_ads_leads.codigo_imovel`; the canonical `leads` row carries it
        # too so every lead-keyed read (Interessados, analytics) sees it.
        "codigo_imovel": _codigo_do_meta_lead(meta_lead),
        "data_entrada": data_entrada,
        "origem_id": origem_source_id,
        "origem_raw": _origem_raw(meta_lead),
        # A Meta Lead-Ads submission is definitionally a first contact —
        # unlike the spreadsheet import, there's no "retorno" signal to
        # detect, so this is an explicit `novo`, not the default
        # `desconhecido` `create_lead` would otherwise stamp.
        "tipo_lead": "novo",
        "cliente_nome": meta_lead.get("full_name"),
        "contato": meta_lead.get("phone"),
        "observacoes": render_answers_pt_br(
            answers, question_types=question_types, question_labels=question_labels
        ),
        "corretor_id": corretor_id,
        "corretor_raw": corretor_raw,
    }


# ─── DB-facing entry points ─────────────────────────────────────────────

def _find_existing_by_meta_lead_id(
    client: Any, org_id: UUID, meta_lead_id: str
) -> Optional[dict]:
    resp = (
        _table(client, "leads")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("meta_lead_id", meta_lead_id)
        .execute()
    )
    rows = list(resp.data or [])
    return rows[0] if rows else None


def _get_or_create_meta_lead_ads_source(client: Any, org_id: UUID) -> dict:
    """The canonical ``meta-lead-ads`` ``lead_sources`` row for this org.
    Provisioned the same idempotent way every other canonical source is
    (``ensure_default_dimensions`` — see ``seed_data.py``); called here
    too because this is a real write path (a lead insert), not a bare
    GET, the same rule ``import_service.commit`` follows."""
    for row in dimensions_service.list_sources(client, org_id):
        if row["slug"] == _META_LEAD_ADS_SLUG:
            return row
    dimensions_service.ensure_default_dimensions(client, org_id)
    for row in dimensions_service.list_sources(client, org_id):
        if row["slug"] == _META_LEAD_ADS_SLUG:
            return row
    raise RuntimeError(
        f"meta_ingest_service: {_META_LEAD_ADS_SLUG!r} source missing after "
        "ensure_default_dimensions — seed_data.CANONICAL_SOURCES drifted"
    )


def _form_question_maps(client: Any, form_id: Optional[str]) -> tuple[dict[str, str], dict[str, str]]:
    """``{key: type}`` / ``{key: label}`` from the owning form's
    persisted ``meta_ads_lead_forms.questions`` — empty maps (never a
    KeyError/None) when ``form_id`` is absent or the form row doesn't
    exist, so callers always get a dict back."""
    if not form_id:
        return {}, {}
    resp = (
        _table(client, "meta_ads_lead_forms")
        .select("questions")
        .eq("id", form_id)
        .execute()
    )
    rows = list(resp.data or [])
    questions = (rows[0].get("questions") if rows else None) or []
    types = {q["key"]: q.get("type") for q in questions if q.get("key")}
    labels = {
        q["key"]: q.get("label") for q in questions if q.get("key") and q.get("label")
    }
    return types, labels


def ingest_meta_lead(
    client: Any,
    org_id: UUID,
    meta_lead: dict[str, Any],
    *,
    corretor_map: Optional[dict[str, str]] = None,
    question_types: Optional[dict[str, str]] = None,
    question_labels: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Idempotent single-lead ingest: one ``meta_ads_leads``-shaped row
    (dict with at least ``id``/``full_name``/``phone``/``created_time``/
    ``campaign_name``/``answers``) -> one ``leads`` row.

    Called per-lead by the Meta Lead-Ads webhook receiver. Re-running with
    the same ``meta_lead["id"]`` is a no-op — this checks
    ``(org_id, meta_lead_id)`` BEFORE inserting (migration 041's
    ``uq_sw_leads_org_meta_lead_id`` is the DB-level backstop, not the
    only guard) and returns the EXISTING row rather than a duplicate.

    ``corretor_map``/``question_types``/``question_labels`` are optional
    caller-supplied caches (the bulk backfill builds them once per org /
    per form instead of once per lead); omitted, this resolves the
    corretor map itself and renders ``observacoes`` unlabeled.
    """
    meta_lead_id = meta_lead.get("id")
    if not meta_lead_id:
        raise ValueError("ingest_meta_lead: meta_lead['id'] is required")

    existing = _find_existing_by_meta_lead_id(client, org_id, meta_lead_id)
    if existing is not None:
        return {"lead": backfill_generated_columns(existing), "created": False}

    if corretor_map is None:
        _, corretor_map = dimensions_service.build_resolution_maps(client, org_id)

    source = _get_or_create_meta_lead_ads_source(client, org_id)
    payload = map_meta_lead_to_lead_payload(
        meta_lead,
        origem_source_id=source["id"],
        corretor_map=corretor_map,
        question_types=question_types,
        question_labels=question_labels,
    )
    lead = leads_service.create_lead(client, org_id, payload)
    # §1.3 — the card's titular exists before this returns (the same synchronous
    # attach the manual "Novo lead" uses). Never raises; the sweep is the net.
    cliente_id = clientes_service.attach_lead_now(client, org_id, lead)

    # §1.2 — the imóvel comes from the CAMPAIGN first; the form's REF answer is
    # the fallback; neither ⇒ imovel_pendente. Never a guess.
    campanha = resolver_campanha(client, org_id, meta_lead)
    if campanha is not None:
        imoveis = _vincular_campanha(
            client, org_id, lead, meta_lead, campanha, cliente_id=cliente_id
        )
        # The lead's own REF answer: the campanha link wins when REF is one of
        # the campanha's imóveis (one link per (atendimento, código), never a
        # second origem='lead' row — and `reconcile` is pair-idempotent, so the
        # sweep adds none either). A REF OUTSIDE the campanha is real info the
        # lead gave: link it too, origem='lead'.
        ref = busca_service.canonical(_codigo_do_meta_lead(meta_lead) or "")
        if ref and ref not in campanha["codigos"]:
            ligado = atendimento_imoveis_service.vincular_lead_seguro(
                client, org_id, lead_id=lead["id"], contexto="meta_ingest"
            )
            if (ligado or {}).get("codigo") and (ligado or {}).get("atendimentos"):
                imoveis.append({"codigo": ligado["codigo"], "origem": "lead"})
    else:
        # Links the lead's REF imóvel to the card(s) it spawned (origem='lead')
        # and the cliente's interesses now that the cliente is attached.
        ligado = atendimento_imoveis_service.vincular_lead_seguro(
            client, org_id, lead_id=lead["id"], contexto="meta_ingest"
        )
        codigo = (ligado or {}).get("codigo")
        imoveis = (
            [{"codigo": codigo, "origem": "lead"}]
            if codigo and (ligado or {}).get("atendimentos")
            else []
        )
    return {
        "lead": lead,
        "created": True,
        "cliente_id": cliente_id,
        "atendimento_id": _atendimento_do_lead(client, org_id, lead, meta_lead),
        "campanha": campanha,
        "imoveis": imoveis,
    }


def _atendimentos_do_lead(
    client: Any, org_id: UUID, lead: dict, meta_lead: dict[str, Any]
) -> list[dict]:
    # Reuses the junction service's own lookup (the cards the lead spawned).
    return atendimento_imoveis_service._atendimentos_do_lead(client, org_id, lead, meta_lead)


def _atendimento_do_lead(
    client: Any, org_id: UUID, lead: dict, meta_lead: dict[str, Any]
) -> Optional[str]:
    """The card of the canonical ``leads`` row (the one ``attach_lead_now``
    attaches the titular to), else any card the lead spawned."""
    cards = _atendimentos_do_lead(client, org_id, lead, meta_lead)
    proprios = [a for a in cards if str(a.get("lead_id") or "") == str(lead["id"])]
    escolhido = (proprios or cards or [None])[0]
    return str(escolhido["id"]) if escolhido else None


def _vincular_campanha(
    client: Any,
    org_id: UUID,
    lead: dict,
    meta_lead: dict[str, Any],
    campanha: dict[str, Any],
    *,
    cliente_id: Optional[str] = None,
) -> list[dict[str, str]]:
    """Link EVERY imóvel of the campanha to each card the lead spawned,
    ``origem='campanha'``. Never raises (the lead is already committed; a
    failure is logged and left for a retry, same posture as
    ``vincular_lead_seguro``). ``garantir_vinculo`` is idempotent, so a
    re-drive cannot duplicate."""
    ligados: list[dict[str, str]] = []
    try:
        cards = _atendimentos_do_lead(client, org_id, lead, meta_lead)
        for codigo in campanha["codigos"]:
            for card in cards:
                atendimento_imoveis_service.garantir_vinculo(
                    client, org_id, card["id"], codigo, origem="campanha"
                )
            if cards:
                ligados.append({"codigo": codigo, "origem": "campanha"})
            # Same mechanism as the REF path: the cliente's interesse (needs
            # the cliente `attach_lead_now` just attached; else `reconcile`
            # completes it from the lead's own código only — campanha
            # interesses exist only when written here).
            if cliente_id and meta_lead.get("id"):
                interesses_service.registrar_de_lead(
                    client,
                    org_id,
                    UUID(str(cliente_id)),
                    codigo,
                    meta_ads_lead_id=str(meta_lead["id"]),
                    criado_em=meta_lead.get("created_time") or meta_lead.get("created_at"),
                )
    except Exception:
        logger.error(
            "meta_ingest: linking campanha %s imóveis failed for lead %s org=%s",
            campanha.get("campanha_id"), lead.get("id"), org_id, exc_info=True,
        )
    return ligados


def backfill_meta_ads_leads(
    client: Any, org_id: UUID, *, page_size: int = _BACKFILL_PAGE_SIZE
) -> dict[str, Any]:
    """One-off, explicit, idempotent backfill of EVERY existing
    ``meta_ads_leads`` row for ``org_id`` into ``leads``. NOT called from
    any import/sync path automatically — a real trigger (today:
    ``POST /api/leads/meta-ingest/backfill``) is required every time.

    Builds the corretor-alias map and the per-form question maps ONCE
    (not once per lead) and reuses :func:`ingest_meta_lead` for the
    per-row idempotency check + mapping — same reasoning as
    ``leads_service.build_refs``: N+1 avoided by threading a shared cache
    through the loop, not by a different code path.

    Paged read over ``meta_ads_leads`` (mirrors ``query.py``'s
    ">1000 rows silently truncated" caution — a bare ``.select().
    execute()`` here would silently backfill only PostgREST's default
    page and report success). The loop itself is the seed's
    ``iter_paged_rows``: its termination does not depend on the backend
    honouring ``range()``, which an offset-only ``while True`` here did.
    """
    _, corretor_map = dimensions_service.build_resolution_maps(client, org_id)
    forms_cache: dict[str, tuple[dict[str, str], dict[str, str]]] = {}

    ingested = 0
    skipped_existing = 0
    errors: list[dict[str, Any]] = []

    def fetch_page(start: int, end: int):
        return (
            _table(client, "meta_ads_leads")
            .select("*")
            .eq("org_id", str(org_id))
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    for row in iter_paged_rows(
        fetch_page,
        page_size=page_size,
        label=f"meta_ads_leads backfill for org_id={org_id}",
    ):
        form_id = row.get("form_id")
        if form_id not in forms_cache:
            forms_cache[form_id] = _form_question_maps(client, form_id)
        question_types, question_labels = forms_cache[form_id]
        try:
            result = ingest_meta_lead(
                client,
                org_id,
                row,
                corretor_map=corretor_map,
                question_types=question_types,
                question_labels=question_labels,
            )
        except ValueError as exc:
            errors.append({"meta_lead_id": row.get("id"), "error": str(exc)})
            continue
        if result["created"]:
            ingested += 1
        else:
            skipped_existing += 1

    logger.info(
        "meta_ingest_service.backfill_meta_ads_leads: org=%s ingested=%s "
        "skipped_existing=%s errors=%s",
        org_id, ingested, skipped_existing, len(errors),
    )
    return {
        "ingested": ingested,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }


__all__ = [
    "render_answers_pt_br",
    "map_meta_lead_to_lead_payload",
    "ingest_meta_lead",
    "backfill_meta_ads_leads",
]
