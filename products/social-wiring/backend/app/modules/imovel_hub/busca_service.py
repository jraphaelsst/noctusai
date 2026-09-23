"""Finding an imóvel by what a person types — over the REGISTRY, not the mirror.

WHY THIS MODULE EXISTS
----------------------
`GET /api/imoveis?search=` reads `social_wiring.imoveis`, and that table is a
cache of what Vista lists TODAY. Measured on prod 2026-08-25 the registry held
3017 imóveis against the mirror's 2008 — 35% of everything we know about was
unfindable in any UI typeahead.

🔴 And those are exactly the ones the paperwork is about. An imóvel leaves the
Vista catalog **when it is sold**, which is the moment its matrícula, its
negociação and its contract are being handled. A picker that can only offer
listed properties cannot name the property in a closed deal.

Every FK in this schema already accepts them — `imovel_dados` (076), `visitas`
(082) and `atendimento_negociacao` (077) all point at
`imovel_registry (org_id, codigo_canonical)`. Only the SEARCH was still looking
at the mirror, so the data model could hold an answer the UI could not reach.

WHERE THE ENRICHMENT CAME FROM (a move, not a second copy)
----------------------------------------------------------
`canonical` / `enriquecer` / `_imovel_out` were written for `roteiros_service`
and lived there. They are the canonical mirror-preferred-with-`snap_*`-fallback
answer for "render this código", and a second consumer is exactly the point at
which a copy stops being a judgement call (`KB § PATTERNS/architect/
project-execution.md`, the DRY recurrence rule). They now live here, next to
`dados_service.ensure_imovel`, which is the registry's other canonical
question; `roteiros_service` imports them and is otherwise untouched.

🔴 WHY THE SEARCH IS SIX QUERIES AND NOT ONE `.or_()`
-----------------------------------------------------
PostgREST would express this as one `or=(codigo.ilike.*,titulo.ilike.*,...)`
per table. It is deliberately NOT written that way: `MockRequestBuilder.or_()`
records a synthetic **match-all** predicate (see
`noctusai_lib/testing/mocks.py`) — so an `.or_()`-based search returns every
row in a test and the filtered subset in production. Every assertion about
"typing ONE9 finds ONE9001" would pass for the wrong reason, and the first
honest signal would be a user telling us the picker offers the whole catalog.

Per-field `ilike` queries evaluate identically in both worlds, and each one is
a predicate PostgREST can serve on its own. The cost is round trips on a
debounced typeahead, which is the cheap side of that trade.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import ValidationError_

from app.services import table_reads

MIRROR_TABLE = "imoveis"
REGISTRY_TABLE = "imovel_registry"
DADOS_TABLE = "imovel_dados"

#: A one-character term matches most of a 3000-row catalog, so the round trip
#: buys a list nobody can use. The frontend gates on the same number; this is
#: the backstop, and it REFUSES rather than quietly returning nothing — an
#: empty list would be indistinguishable from "no such imóvel".
TERMO_MINIMO = 2

#: Typeahead ceiling. Not a page size: this endpoint has no cursor and is not
#: a browsing surface — `GET /api/imoveis` is, and still is.
LIMITE_PADRAO = 10
LIMITE_MAXIMO = 50

#: Display fields read off the mirror when it still holds the imóvel.
_MIRROR_FIELDS = (
    "titulo", "empreendimento", "logradouro", "numero", "complemento",
    "bairro", "cidade", "uf", "cep", "foto_destaque",
)

#: The registry's delist-time snapshot. It is deliberately NARROWER than the
#: mirror — 063 snapshots what a history row needs to stay legible, not the
#: whole listing — so `logradouro`/`numero`/`cep`/`empreendimento` are simply
#: absent for a delisted imóvel and come back null. That is the honest answer,
#: not a gap to paper over.
_SNAP_MAP = {
    "titulo": "snap_titulo",
    "bairro": "snap_bairro",
    "cidade": "snap_cidade",
    "uf": "snap_uf",
    "foto_destaque": "snap_foto_destaque",
}

#: Text columns worth matching a typed term against, per source. The mirror
#: carries the live listing text; the registry carries only what was snapshot
#: at delist time, which is why a delisted imóvel is findable by its código
#: and by its last-known título/bairro and by nothing else.
#:
#: 🔴 `empreendimento`/`logradouro` added 2026-09-23 (measured live on
#: RODRIGO MORASCHI ENRIQUEZ / ONE7515 — see
#: `test_carregador_empreendimento_manual.py`'s header for the related
#: EUROVILLE-535 incident): the picker's placeholder promises "código,
#: título ou bairro" but the search itself only ever matched THREE columns,
#: and neither `empreendimento` ("Euroville - Km 23") nor `logradouro` was
#: among them — an operator searching the development's name and getting
#: zero results hand-registered a duplicate. `snap_empreendimento`/
#: `snap_logradouro` do NOT exist on the registry (063's delist-time
#: snapshot is narrower on purpose — see `_SNAP_MAP`), so a DELISTED imóvel
#: still cannot be found by empreendimento/logradouro; that gap is real and
#: tracked below (NOC-REMEDIATE), not silently worked around by inventing
#: new snapshot columns in this change.
_MIRROR_BUSCA_COLS = ("codigo", "titulo", "bairro", "empreendimento", "logradouro")
_REGISTRY_BUSCA_COLS = ("codigo_canonical", "snap_titulo", "snap_bairro")

# NOC-REMEDIATE[imovel-busca-accent-fold]: `_ilike_rows` runs `ILIKE
# %termo%` verbatim — case-insensitive (Postgres ILIKE) but NOT accent-
# insensitive ("sao paulo" will not match a stored "São Paulo"). A true fix
# needs a DB-side `unaccent()`-derived generated/indexed column on both
# `imoveis` and `imovel_registry` (the `codigo_norm` generated column,
# migration 062, is the established precedent for this shape) — deferred:
# it touches the Vista-sync mirror's schema (owned by `imoveis_service`)
# and needs the `unaccent` extension enabled + wrapped IMMUTABLE for a
# STORED generated column, which no migration in this product has done
# before. Batch with the `_REGISTRY_BUSCA_COLS` snapshot gap above when this
# class reaches N≥3 (`KB § PATTERNS/common/remediation-markers.md`). — 2026-09-23


def canonical(codigo: str) -> str:
    """Migration 062's one expression for this schema, in Python.

    `imovel_dados` normalises the same way for the same FK, and 076 verified on
    prod that `imovel_registry.codigo_canonical` and `imoveis.codigo` are both
    already uppercase everywhere (0 exceptions).
    """
    return codigo.strip().upper()


# ── enrichment (moved from `card_hub.roteiros_service`) ────────────────────


def enriquecer(client: Any, org_id: UUID, codigos: list[str]) -> dict[str, dict]:
    """`codigo -> imóvel`, one batched read per source.

    Registry first because the FK guarantees it exists — so `imovel` is never
    null and `ativo_no_vista` is always answerable. The mirror is PREFERRED for
    display fields when it still holds the imóvel; otherwise the registry's
    delist-time snapshot answers. There is deliberately NO live Vista call:
    roadmap `social-wiring-imoveis-vista-2026-08` P2.5 rules that a clean miss
    is a real, actionable fact, never a fallback.
    """
    unicos = sorted({canonical(c) for c in codigos if c})
    if not unicos:
        return {}

    registry = {
        str(r["codigo_canonical"]): r
        for r in table_reads.in_batched_rows(
            client, REGISTRY_TABLE, org_id, "codigo_canonical", unicos,
            order_col="codigo_canonical",
        )
    }
    mirror = {
        str(r["codigo"]): r
        for r in table_reads.in_batched_rows(
            client, MIRROR_TABLE, org_id, "codigo_norm", unicos, order_col="codigo",
        )
    }
    dados = {
        str(r["codigo"]): r
        for r in table_reads.in_batched_rows(
            client, DADOS_TABLE, org_id, "codigo", unicos, order_col="codigo",
        )
    }
    atores = table_reads.resolve_actors(
        {d["captador_user_id"] for d in dados.values() if d.get("captador_user_id")}
    )

    return {
        codigo: _imovel_out(
            codigo, registry.get(codigo), mirror.get(codigo), dados.get(codigo), atores
        )
        for codigo in unicos
    }


def _imovel_out(
    codigo: str,
    reg: Optional[dict],
    esp: Optional[dict],
    dad: Optional[dict],
    atores: dict,
) -> dict:
    if esp is not None:
        campos = {k: esp.get(k) for k in _MIRROR_FIELDS}
        campos["corretores"] = esp.get("corretores") or []
        fonte = "imoveis"
    else:
        campos = {k: None for k in _MIRROR_FIELDS}
        campos["corretores"] = []
        if reg is not None:
            campos.update({k: reg.get(snap) for k, snap in _SNAP_MAP.items()})
        # 🔴 "registry" ONLY when the registry actually has it. A código in
        # neither source used to come back claiming `fonte: "registry"` and
        # `ativo_no_vista: False` — byte-identical to a genuinely registered
        # property that has left the catalog. The UI then rendered "fora do
        # catálogo", which asserts we know the imóvel and it sold, and offered
        # a button whose save 404s on the FK. `nenhuma` is the honest third
        # answer, and `registrado` is what callers branch on.
        fonte = "registry" if reg is not None else "nenhuma"

    return {
        "codigo": codigo,
        **campos,
        # 🔴 The canonical model for "corretor responsável pela captação"
        # (migration 075): a USER, not a name. The commission slice is
        # attributed to it, and two spellings of a free-text name become two
        # people. NULL is the honest state for an imóvel with no recorded
        # captador — never silently reassigned to the agency.
        "captacao": table_reads.actor(atores, (dad or {}).get("captador_user_id")),
        # Real information, not bookkeeping: a corretor routing a visit to a
        # property that has left the catalog needs to know before driving
        # there, and an operator naming the imóvel of a CLOSED deal needs to
        # know the opposite — that "not in the catalog" is the expected state.
        "ativo_no_vista": bool((reg or {}).get("ativo_no_vista")),
        # 🔴 `origem_descoberta` (063's vocabulary), passed through verbatim
        # so the picker can tell "never listed, hand-registered" apart from
        # "was listed, sold" — BOTH read `ativo_no_vista: False` and BOTH
        # read `fonte: "registry"`, but they are not the same fact and the
        # picker used to badge them identically ("fora do catálogo"), which
        # is simply wrong for a property that was never in the catálogo to
        # begin with. `None` when there is no registry row at all (`fonte:
        # "nenhuma"`) — nothing discovered it, so there is no origin to name.
        "origem": (reg or {}).get("origem_descoberta"),
        # Does this código have a registry identity? Every FK in this schema
        # points at `imovel_registry`, so this is precisely "can it be SAVED".
        # A caller offering the código as a choice must consult it first —
        # otherwise it offers something the save path will refuse.
        "registrado": reg is not None,
        "fonte": fonte,
    }


# ── search ────────────────────────────────────────────────────────────────


def buscar(
    client: Any,
    org_id: UUID,
    *,
    termo: str,
    limite: int = LIMITE_PADRAO,
) -> dict:
    """Imóveis matching `termo`, from the registry AND the mirror.

    The union is the point. The mirror alone loses every sold property; the
    registry alone loses every ACTIVE property's título and bairro, because
    `snap_*` is written only at delist time (063) and is null while a listing
    is live. Neither source answers this on its own.
    """
    termo = (termo or "").strip()
    if len(termo) < TERMO_MINIMO:
        raise ValidationError_(
            f"termo de busca precisa de ao menos {TERMO_MINIMO} caracteres",
            field="q",
        )
    limite = max(1, min(int(limite), LIMITE_MAXIMO))

    codigos: set[str] = set()
    for coluna in _MIRROR_BUSCA_COLS:
        codigos.update(
            canonical(str(r["codigo"]))
            for r in _ilike_rows(client, MIRROR_TABLE, org_id, coluna, termo, limite)
            if r.get("codigo")
        )
    for coluna in _REGISTRY_BUSCA_COLS:
        codigos.update(
            canonical(str(r["codigo_canonical"]))
            for r in _ilike_rows(client, REGISTRY_TABLE, org_id, coluna, termo, limite)
            if r.get("codigo_canonical")
        )

    if not codigos:
        return {"items": [], "total": 0}

    enriquecidos = enriquecer(client, org_id, sorted(codigos))
    ordenados = sorted(enriquecidos.values(), key=_ranking(canonical(termo)))[:limite]
    # `total` is the length of what is returned, NOT a catalog count. This
    # endpoint has no cursor and never claims one: reporting a larger number
    # next to a truncated list would promise a "next page" that does not exist.
    return {"items": ordenados, "total": len(ordenados)}


def _ilike_rows(
    client: Any,
    tabela: str,
    org_id: UUID,
    coluna: str,
    termo: str,
    limite: int,
) -> list[dict]:
    """One `col ILIKE %termo%` read, org-scoped and capped.

    Capped at `limite` per (table, column) rather than globally: the ranking
    below decides what actually survives, and a cap applied before ranking on
    a single column would let one column's alphabetical head crowd out an
    exact código match from another.
    """
    coluna_saida = "codigo_canonical" if tabela == REGISTRY_TABLE else "codigo"
    rows = (
        table_reads.table(client, tabela)
        .select(coluna_saida)
        .eq("org_id", str(org_id))
        .ilike(coluna, f"%{termo}%")
        .limit(limite)
        .execute()
    ).data
    return list(rows or [])


def _ranking(termo_canonical: str):
    """Exact código first, then still-listed, then alphabetical.

    `ativo_no_vista` ordering is a UX call and not a hierarchy of truth: a
    delisted imóvel is a first-class answer here (that is the whole reason
    this endpoint exists) and it is still returned, still labelled, just
    below the listing a person typing a partial código usually means.
    """

    def chave(item: dict) -> tuple:
        codigo = str(item.get("codigo") or "")
        return (
            0 if codigo == termo_canonical else 1,
            0 if item.get("ativo_no_vista") else 1,
            codigo,
        )

    return chave


# ── near-duplicate suggestions (2026-09-23) ─────────────────────────────────
#
# A term that finds NOTHING in `buscar()` is exactly the moment
# `ImovelCodigoPicker` offers "Cadastrar '<termo>' como imóvel novo" — and
# exactly the moment a genuine duplicate gets hand-registered, because a
# zero-result search reads as "this property has no código yet" even when it
# does. Measured live 2026-09-22: EUROVILLE-535 was hand-registered as a
# duplicate of ONE7515 (`empreendimento`/`bairro` "Euroville - Km 23",
# `complemento` "535") after a search for "Euroville" came back empty (the
# `_MIRROR_BUSCA_COLS` gap above). This is the SECOND, independent net:
# even once that gap is closed, an operator typing a proposed CÓDIGO
# (`"EUROVILLE-535"`) rather than a search phrase still needs a check the
# plain column search cannot do — `complemento` is deliberately NOT a
# `buscar()` column (a bare number would match too broadly), but a trailing
# numeric run in the typed text is exactly what a `complemento` holds for a
# condo unit.
_NUMERO_FINAL_RE = re.compile(r"(\d+)\s*$")


def sugestoes_para_cadastro(
    client: Any, org_id: UUID, *, termo: str, limite: int = 5
) -> dict:
    """Imóveis that MIGHT be what `termo` is actually about, for the
    "cadastrar como novo" confirmation step — never a hard block (a genuine
    new property is a real, common case), just a "did you mean one of
    these?" the operator can dismiss.

    Two independent signals, unioned:
      1. `empreendimento` ILIKE `termo` — same building/condomínio, however
         it is currently named ON THIS imóvel's own row (this covers a
         `termo` typo/whitespace variant `buscar()`'s exact-ish ranking
         would rank low, not only the exact `_MIRROR_BUSCA_COLS` gap above).
      2. a trailing numeric run in `termo` (e.g. "535" out of
         "EUROVILLE-535") ILIKE-matched against `complemento` — the
         condo-unit-number signal the owner named explicitly.

    Mirror-only (`imoveis`, not the registry): a delisted/hand-registered
    imóvel's `complemento`/`empreendimento` are not in the registry's
    delist-time snapshot at all (see `_SNAP_MAP`) — nothing to match against
    there. Returns the same shape as `buscar()`, so the FE can render it
    with `rotuloDoImovel` unchanged.
    """
    termo_limpo = (termo or "").strip()
    if not termo_limpo:
        return {"items": [], "total": 0}
    limite = max(1, min(int(limite), LIMITE_MAXIMO))

    codigos: set[str] = set()
    codigos.update(
        canonical(str(r["codigo"]))
        for r in _ilike_rows(client, MIRROR_TABLE, org_id, "empreendimento", termo_limpo, limite)
        if r.get("codigo")
    )
    numero = _NUMERO_FINAL_RE.search(termo_limpo)
    if numero:
        codigos.update(
            canonical(str(r["codigo"]))
            for r in _ilike_rows(
                client, MIRROR_TABLE, org_id, "complemento", numero.group(1), limite
            )
            if r.get("codigo")
        )

    if not codigos:
        return {"items": [], "total": 0}
    enriquecidos = enriquecer(client, org_id, sorted(codigos))
    itens = sorted(enriquecidos.values(), key=_ranking(canonical(termo_limpo)))[:limite]
    return {"items": itens, "total": len(itens)}


__all__ = [
    "LIMITE_MAXIMO",
    "LIMITE_PADRAO",
    "TERMO_MINIMO",
    "buscar",
    "canonical",
    "enriquecer",
    "sugestoes_para_cadastro",
]
