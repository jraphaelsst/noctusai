"""Imóveis — read access over `social_wiring.imoveis` + the Vista full-pull sync.

Two responsibilities, deliberately in one module because they share the row
shape and nothing else consumes either half:

- `ImoveisService`  — query the local mirror (the page reads this, never Vista)
- `ImovelSyncService` — refresh the mirror from Vista

**Why a mirror at all, rather than proxying Vista per request.** Ratified as
D1: a scheduled full pull plus a manual refresh button. The catalog is 1919
imóveis; a page that proxied Vista would pay a round-trip per view, could not
filter or sort server-side across the whole catalog, and would break entirely
whenever Vista is down. The mirror also makes `leads.codigo_imovel` joinable.

**Why a FULL pull rather than incremental.** `DataAtualizacao` IS a real
per-imóvel change marker (36 distinct dates across the catalog — an earlier
reading that called it a feed timestamp was a page-1 recency-ordering
artifact). But the oldest value is only ~6 weeks back while `DataCadastro`
reaches 2012, so the tenant touches every listing inside a ~6-week window
regardless: an incremental sync keyed on it converges to a full pull anyway,
while adding a staleness-tracking failure mode. Full pull, measured at
4–6 minutes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.real_estate import Imovel, PropertyData, imovel_to_property_data, parse_corretores
from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.vista.client import VistaNotFound, VistaRecordUnpublished

from app.services import corretores_enriquecimento, imoveis_descoberta, imovel_ref_avisos, vista_divergencias

logger = logging.getLogger(__name__)

__all__ = [
    "ImoveisService",
    "ImovelSyncService",
    "ImoveisLookupError",
    "RefreshCodigo",
    "SyncReport",
    "DETALHE_OK",
    "DETALHE_SUMIU",
    "DETALHE_OCULTO",
    "DETALHE_FALHOU",
    "build_imoveis_service",
    "build_sync_service",
]

# Row columns that are persistence-only (added by `_imovel_to_row`, not part
# of the `Imovel` model) — stripped before reconstituting `Imovel(**row)`.
# `codigo_norm` is a STORED generated column (migration 062) and exists only
# so the case-insensitive join is indexed — it is derived from `codigo`,
# which the model already carries, so passing it through would add a second
# spelling of the same fact to the domain object.
_ROW_ONLY_COLUMNS = frozenset({"org_id", "sincronizado_em", "codigo_norm"})


#: THE columns the sync may write on `social_wiring.imoveis` -- Vista-sourced ONLY. Everything WE own lives in other tables
#: (imovel_dados 118/149/158/202/300, imovel_captacao 226, the duplicate pairs, proprietario links, documents,
#: julia_proprietarios_contatos) and in `created_at` / `updated_at` / `codigo_norm` of this one; the upsert refuses a
#: row carrying anything outside this set (`_assert_so_vista`), so a future column can never be written by accident.
COLUNAS_VISTA = frozenset({
    "org_id", "codigo", "codigo_imobiliaria", "titulo", "categoria", "status", "finalidades", "cep", "logradouro",
    "numero", "complemento", "bairro", "cidade", "uf", "empreendimento", "latitude", "longitude", "valor_venda",
    "valor_locacao", "area_total", "area_privativa", "area_construida", "dormitorios", "suites", "vagas",
    "banheiro_social", "foto_destaque", "fotos", "corretores", "construtora", "data_cadastro", "data_atualizacao",
    "caracteristicas", "caracteristicas_raw", "vista_raw", "sincronizado_em", "descricao_web", "observacoes",
    "valor_condominio", "valor_iptu", "ano_construcao", "situacao", "ocupacao", "pavimentos", "posicao", "elevador",
    "portaria", "exclusivo", "aceita_permuta", "aceita_financiamento", "destaque_web", "super_destaque_web",
    "exibir_no_site", "chave", "zona", "regiao", "area_terreno", "closet", "frente", "fundos", "referencia",
    "matricula_vista", "inscricao_municipal", "video_destaque", "tour_360",
})


def _assert_so_vista(rows: list[dict]) -> None:
    """Refuse (loudly) a row that carries a column the sync does not own."""
    for row in rows:
        extra = set(row) - COLUNAS_VISTA
        if extra:
            raise ValueError(f"imoveis sync: refusing to write non-Vista column(s) {sorted(extra)} on social_wiring.imoveis")


class ImoveisLookupError(Exception):
    """The local `imoveis` lookup itself failed (a DB/transport problem —
    e.g. PostgREST unreachable), as distinct from a clean miss (`None`,
    meaning: not in the catalog). Callers that need to tell "couldn't ask"
    apart from "asked, not there" catch this specifically."""

_SCHEMA = "social_wiring"
_TABLE = "imoveis"
# Vista mirror ∪ manual captação (migration 226): what the LIST and the filter
# dropdowns read, so a manual imóvel appears with exact filters / count / order
# / pages from ONE PostgREST query. Single-imóvel `get` stays on the mirror.
_CATALOGO = "imoveis_catalogo"
# Our permanent imóvel identity (migration 063). `imoveis` is a disposable
# mirror of the ACTIVE Vista catalog; this survives an imóvel leaving it, and
# is what leads/vendas/campanhas actually reference.
_REGISTRY_TABLE = "imovel_registry"

# Vista tolerated concurrency 8 with no throttling in the 2026-08-03
# measurement (24-call batches: 20.1s serial → 4.3s at 4 → 3.1s at 8, zero
# errors at every level). 6 is deliberately below the proven ceiling — the
# measurement was one tenant on one day, and a sync that finishes in 5
# minutes instead of 4 is not worth discovering their rate limit in
# production.
DEFAULT_SYNC_CONCURRENCY = 6
VISTA_RATE_BUCKET = "vista"
#: The per-code refresh runs 4 at a time (owner/coordinator 2026-11-03): ~2k detalhes calls per tier, not a burst.
DETALHES_CONCURRENCY = 4
#: A listing is "vitrine" (shown to the public, refreshed every run) when its Status is one of these and it is not hidden.
STATUS_VITRINE = frozenset({"venda", "aluguel", "venda e aluguel"})
#: Circuit breaker for the per-code path (the twin of migration 064's): never mark more than this share (and at least
#: this many) of the walked codes as removed in one run -- a Vista hiccup must not delist the catalog.
REMOVIDOS_MAX_PCT = 20.0
REMOVIDOS_MIN_ABS = 50
_LOTE = 100
#: Fields only `listar` carries: a detalhes-only refresh keeps the mirror's existing value for them.
_CAMPOS_SO_LISTAR = ("foto_destaque", "banheiro_social", "codigo_imobiliaria")

# `Imovel` field name → the Vista wire key it was coerced from, for the two
# fields `normalize_place_name` canonicalizes (seed
# `noctusai_lib.domain.real_estate.imovel`). Used only to detect + log a
# place-name merge once per sync (roadmap `social-wiring-imoveis-vista-
# 2026-08` Q4, extended from `Caracteristicas` to `Cidade`/`Empreendimento`
# 2026-08-13) — never to re-derive the canonical value, which the seed
# normalizer already owns.
_PLACE_NAME_WIRE_KEYS = {"cidade": "Cidade", "empreendimento": "Empreendimento"}

# Contract §3: `caracteristicas_raw` mixes the four solar-orientation flags
# in with real amenities — Vista sends them as just another Sim/Nao key, but
# a compass direction is not something an imóvel HAS the way a piscina is.
# Slugged the same way `caracteristica_slug` would fold them (lowercase,
# whitespace-collapsed) since they carry no internal whitespace to begin
# with — `caracteristica_slug("Norte") == "norte"`.
_ORIENTACAO_SOLAR_SLUGS = frozenset({"norte", "sul", "leste", "oeste"})


def _split_orientacao_solar(caracteristicas: Optional[list]) -> tuple[list[str], list[str]]:
    """Split the four solar-orientation slugs out of the amenity list.

    Returns `(amenidades_sem_orientacao, orientacao_solar)`, both sorted so
    the split is stable across re-reads of the same row.
    """
    values = caracteristicas or []
    orientacao = sorted(v for v in values if v in _ORIENTACAO_SOLAR_SLUGS)
    amenidades = sorted(v for v in values if v not in _ORIENTACAO_SOLAR_SLUGS)
    return amenidades, orientacao


def _dias_desde_atualizacao(vista_raw: Any) -> Optional[int]:
    """`DataAtualizacaoDias` — already stored inside `vista_raw` on every
    row (detalhes-only on the wire), never surfaced until CONTRACT §3.

    Coerced defensively: this is a display nicety, not a value anything
    downstream keys on, so a missing/malformed source value yields `None`
    rather than raising — never an exception for a stale-but-cosmetic field.
    """
    if not isinstance(vista_raw, dict):
        return None
    raw = vista_raw.get("DataAtualizacaoDias")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _augment_row_derived(row: dict) -> dict:
    """Add the presentation-only derived fields from CONTRACT §3 to a row
    as `SELECT *` returned it: split `orientacao_solar` out of
    `caracteristicas`, and expose `dias_desde_atualizacao`. Neither is a
    stored column — both are computed at read time from columns the row
    already carries (`caracteristicas`, `vista_raw`).

    Safe to run on the result of `ImoveisService.get`, whose OTHER consumer
    (`get_property_data` → `Imovel(**row)`) never reads `caracteristicas`
    (see `noctusai_lib.domain.real_estate.metadata.imovel_to_property_data`)
    and silently ignores unrecognized extra keys (pydantic's default
    `extra='ignore'`) — so augmenting unconditionally here, rather than
    forking a display-only variant of `get`, does not change that path's
    behaviour.
    """
    amenidades, orientacao = _split_orientacao_solar(row.get("caracteristicas"))
    row["caracteristicas"] = amenidades
    row["orientacao_solar"] = orientacao
    row["dias_desde_atualizacao"] = _dias_desde_atualizacao(row.get("vista_raw"))
    return row


#: Outcomes of one `/imoveis/detalhes` read (`ImovelSyncService.buscar_detalhe`).
DETALHE_OK = "ok"
DETALHE_SUMIU = "sumiu"  # Vista answered: the code does not exist
DETALHE_OCULTO = "oculto"  # Vista answered: the record exists but is unpublished
DETALHE_FALHOU = "falhou"  # transport / auth / 5xx: NOT evidence about the code


def _difere(a: Any, b: Any) -> bool:
    """Whether two mirror-column values differ, ignoring numeric representation (1250000 == 1250000.0 == '1250000.00')."""
    if a == b:
        return False
    try:
        return float(a) != float(b)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(a) != str(b)


@dataclass
class RefreshCodigo:
    """What `ImovelSyncService.refresh_codigo` did for one code."""

    codigo: str
    desfecho: str
    report: "SyncReport"
    imovel: Optional[Imovel] = None
    existia: bool = False
    #: brokers of an unpublished record (`DETALHE_OCULTO`): the stub body keeps the `Corretor` relation.
    corretores_oculto: list = field(default_factory=list)
    #: mirror columns Vista changed vs what we had: `{campo: {antes, depois}}` (empty for a new row).
    mudancas: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def divergencias(self) -> list[dict]:
        return list(self.report.divergencias_linhas)


@dataclass
class SyncReport:
    """What a sync actually did — the honest version.

    `detalhes_failed` exists so a report can never claim a clean run it did
    not have. An imóvel whose detalhes call failed is still upserted from its
    listar row (better a partial imóvel than a missing one), but it lands
    WITHOUT caracteristicas, so silently counting it as synced would make the
    amenity filter quietly incomplete.
    """

    total_reported: int = 0
    pages_fetched: int = 0
    upserted: int = 0
    detalhes_fetched: int = 0
    detalhes_failed: list[str] = field(default_factory=list)
    page_failures: list[str] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0
    # Registry maintenance (migration 063). Kept OUT of `complete` on
    # purpose — see the property below.
    registry_ativos: int = 0
    registry_delistados: int = 0
    registry_failures: list[str] = field(default_factory=list)
    # Which path ran and how it ended (the Vista `listar` outage made the path a fact worth reporting).
    caminho: str = "listar"  # listar | detalhes
    escopo: Optional[str] = None  # detalhes path: vitrine | resto | todos
    status: str = ""  # "" = derive from `complete`; ok | incompleto | listar_vazio | removidos_excessivos
    listar_vazio_pagina: bool = False
    novos: int = 0
    atualizados: int = 0
    inalterados: int = 0
    removidos: int = 0
    removidos_codigos: list[str] = field(default_factory=list)
    descobertos: list[str] = field(default_factory=list)
    sonda_falhas: list[str] = field(default_factory=list)
    chamadas: dict[str, int] = field(default_factory=dict)
    # Vista-vs-ours divergences opened this run (TRANSITIONAL -- `vista_divergencias`, NOC-REMEDIATE[transicao-vista-divergencias]).
    divergencias_linhas: list[dict] = field(default_factory=list)
    divergencias_erros: list[str] = field(default_factory=list)
    divergencias_comparadas: int = 0

    @property
    def complete(self) -> bool:
        """True only when the CATALOG PULL skipped nothing.

        `registry_failures` is deliberately excluded. `complete` gates the
        registry sweep itself — folding registry errors into it would mean a
        failed sweep marks the run incomplete, which on the next run would
        skip the sweep that was trying to repair it. The registry is
        reported separately by `as_dict` and logged loudly; it is never
        hidden, just not self-referential.
        """
        return not self.page_failures and not self.detalhes_failed

    @property
    def status_final(self) -> str:
        return self.status or ("ok" if self.complete else "incompleto")

    def as_dict(self) -> dict:
        return {
            "caminho": self.caminho,
            "escopo": self.escopo,
            "status": self.status_final,
            "novos": self.novos,
            "atualizados": self.atualizados,
            "inalterados": self.inalterados,
            "removidos": self.removidos,
            "removidos_codigos": self.removidos_codigos[:100],
            "falhas": len(self.detalhes_failed) + len(self.page_failures),
            "descobertos": self.descobertos,
            "sonda_falhas": self.sonda_falhas,
            "chamadas": dict(self.chamadas),
            "divergencias_novas": len(self.divergencias_linhas),
            "divergencias": [{"codigo": r["codigo"], "campo": r["campo"]} for r in self.divergencias_linhas[:50]],
            "divergencias_erros": self.divergencias_erros[:20],
            "divergencias_comparadas": self.divergencias_comparadas,
            "total_reported": self.total_reported,
            "pages_fetched": self.pages_fetched,
            "upserted": self.upserted,
            "detalhes_fetched": self.detalhes_fetched,
            "detalhes_failed": self.detalhes_failed,
            "detalhes_failed_count": len(self.detalhes_failed),
            "page_failures": self.page_failures,
            "complete": self.complete,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "registry_ativos": self.registry_ativos,
            "registry_delistados": self.registry_delistados,
            "registry_failures": self.registry_failures,
            "registry_failures_count": len(self.registry_failures),
        }


def _imovel_to_row(imovel: Imovel, org_id: UUID, synced_at: str) -> dict:
    """Flatten an `Imovel` into a `social_wiring.imoveis` row.

    `finalidades` / `caracteristicas` are frozensets in the model and arrays
    in the column — sorted on the way out so a re-sync of unchanged data
    produces an identical row rather than a spurious UPDATE.
    """
    return {
        "org_id": str(org_id),
        "codigo": imovel.codigo,
        "codigo_imobiliaria": imovel.codigo_imobiliaria,
        "titulo": imovel.titulo,
        "categoria": imovel.categoria,
        "status": imovel.status,
        "finalidades": sorted(imovel.finalidades),
        "cep": imovel.cep,
        "logradouro": imovel.logradouro,
        "numero": imovel.numero,
        "complemento": imovel.complemento,
        "bairro": imovel.bairro,
        "cidade": imovel.cidade,
        "uf": imovel.uf,
        "empreendimento": imovel.empreendimento,
        "latitude": imovel.latitude,
        "longitude": imovel.longitude,
        "valor_venda": imovel.valor_venda,
        "valor_locacao": imovel.valor_locacao,
        "area_total": imovel.area_total,
        "area_privativa": imovel.area_privativa,
        "area_construida": imovel.area_construida,
        "dormitorios": imovel.dormitorios,
        "suites": imovel.suites,
        "vagas": imovel.vagas,
        "banheiro_social": imovel.banheiro_social,
        "foto_destaque": imovel.foto_destaque,
        "fotos": list(imovel.fotos),
        "corretores": [c.model_dump(mode="json") for c in imovel.corretores],
        "construtora": imovel.construtora,
        "data_cadastro": imovel.data_cadastro.isoformat() if imovel.data_cadastro else None,
        "data_atualizacao": (
            imovel.data_atualizacao.isoformat() if imovel.data_atualizacao else None
        ),
        "caracteristicas": sorted(imovel.caracteristicas),
        "caracteristicas_raw": imovel.caracteristicas_raw,
        "vista_raw": imovel.vista_raw,
        "sincronizado_em": synced_at,
        # ── the 29 fields from CONTRACT §1 (imoveis-vista-field-surface) ──
        # Direct attribute access, NOT `getattr(..., None)`. The dispatch
        # that wrote this slice used a `getattr` bridge because the seed
        # `Imovel` dataclass was still landing on a sibling branch; both are
        # merged now, so the bridge is gone. It had to go: a `None` default
        # turns a typo'd or removed field name into a silently-NULL column,
        # which reads downstream as "Vista does not populate this" — exactly
        # the silent-error shape the amenity/photo investigation had to
        # untangle by hand. Direct access fails loudly at the first row
        # instead. Column order mirrors CONTRACT §1's table.
        #
        # 🔴 CORRECTION 2026-09-04: `lavabo`/`copa`/`escritorio` are
        # DELIBERATELY absent — Vista shadows all three (returns `null` at
        # the top level) whenever `Caracteristicas` rides in the same
        # request, which our sync always does. The values are correct and
        # already present in `caracteristicas`/`caracteristicas_raw` — a
        # column here would just be permanently NULL. `elevador`/`portaria`
        # were checked against the same collision and are NOT shadowed.
        "descricao_web": imovel.descricao_web,
        "observacoes": imovel.observacoes,
        "valor_condominio": imovel.valor_condominio,
        "valor_iptu": imovel.valor_iptu,
        "ano_construcao": imovel.ano_construcao,
        "situacao": imovel.situacao,
        "ocupacao": imovel.ocupacao,
        "pavimentos": imovel.pavimentos,
        "posicao": imovel.posicao,
        "elevador": imovel.elevador,
        "portaria": imovel.portaria,
        "exclusivo": imovel.exclusivo,
        "aceita_permuta": imovel.aceita_permuta,
        "aceita_financiamento": imovel.aceita_financiamento,
        "destaque_web": imovel.destaque_web,
        "super_destaque_web": imovel.super_destaque_web,
        "exibir_no_site": imovel.exibir_no_site,
        "chave": imovel.chave,
        "zona": imovel.zona,
        "regiao": imovel.regiao,
        "area_terreno": imovel.area_terreno,
        "closet": imovel.closet,
        "frente": imovel.frente,
        "fundos": imovel.fundos,
        "referencia": imovel.referencia,
        "matricula_vista": imovel.matricula_vista,
        "inscricao_municipal": imovel.inscricao_municipal,
        "video_destaque": imovel.video_destaque,
        "tour_360": imovel.tour_360,
    }


def _record_place_name_variants(
    imovel: Imovel, variants: dict[str, dict[str, set[str]]]
) -> None:
    """Accumulate raw→canonical place-name spellings seen so far this sync.

    Doesn't log anything — `sync()` logs ONCE, after the whole catalog has
    been walked, so a 1919-imóvel sync doesn't produce a line per row for
    the same collision (Q4's "log the merge once at sync time, not once per
    row", extended from `Caracteristicas` to `Cidade`/`Empreendimento`).
    Keyed by the CANONICAL value so multiple raw spellings that fold to it
    accumulate in one bucket; a bucket with >1 raw spelling is a merge.
    """
    for field_name, wire_key in _PLACE_NAME_WIRE_KEYS.items():
        canonical = getattr(imovel, field_name)
        raw = imovel.vista_raw.get(wire_key)
        if not canonical or not isinstance(raw, str):
            continue
        raw_clean = raw.strip()
        if not raw_clean:
            continue
        variants[field_name].setdefault(canonical, set()).add(raw_clean)


def _log_place_name_merges(
    org_id: UUID, variants: dict[str, dict[str, set[str]]]
) -> None:
    """Surface any place-name spelling this sync merged — a live tenant
    data-quality issue (roadmap Q4), not silently absorbed by the
    normalizer. One line per (field, canonical value), not per row.
    """
    for field_name, by_canonical in variants.items():
        for canonical, raw_variants in by_canonical.items():
            if len(raw_variants) > 1:
                logger.warning(
                    "imoveis sync: org=%s merged %d %s spelling(s) into %r — %s",
                    org_id, len(raw_variants), field_name, canonical,
                    sorted(raw_variants),
                )


class ImoveisService:
    """Read/query `social_wiring.imoveis`. Every query filters `org_id`
    explicitly — defense in depth on top of RLS."""

    def __init__(self, client: Any):
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _catalogo(self):
        return self._client.schema(_SCHEMA).table(_CATALOGO)

    def list(
        self,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 24,
        status: Optional[str] = None,
        categoria: Optional[str] = None,
        cidade: Optional[str] = None,
        bairro: Optional[str] = None,
        search: Optional[str] = None,
        caracteristicas: Optional[list[str]] = None,
        possivel_duplicado: Optional[bool] = None,
    ) -> dict:
        query = self._catalogo().select("*", count="exact").eq("org_id", str(org_id))
        if status:
            query = query.eq("status", status)
        if categoria:
            query = query.eq("categoria", categoria)
        if cidade:
            query = query.eq("cidade", cidade)
        if bairro:
            query = query.eq("bairro", bairro)
        if possivel_duplicado is not None:
            # View column (migration 228): a pending duplicate pair involves it.
            query = query.eq("possivel_duplicado", possivel_duplicado)
        if caracteristicas:
            # Array containment — the GIN index on `caracteristicas` serves
            # this. Semantics are AND (has ALL of them), which is what a
            # buyer filtering "piscina + churrasqueira" means.
            query = query.contains("caracteristicas", caracteristicas)
        if search:
            term = f"%{search}%"
            query = query.or_(
                f"codigo.ilike.{term},titulo.ilike.{term},bairro.ilike.{term}"
            )

        start = max(0, (page - 1) * page_size)
        result = (
            query.order("data_atualizacao", desc=True)
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = [_augment_row_derived(row) for row in (result.data or [])]
        total = getattr(result, "count", None)
        total = len(rows) if total is None else total
        pages = max(1, (total + page_size - 1) // page_size)
        return {"items": rows, "total": total, "page": page, "pages": pages}

    def get(self, org_id: UUID, codigo: str) -> Optional[dict]:
        """Resolve one imóvel by código, case-insensitively.

        Matches `codigo_norm` (migration 062), NOT `codigo`. The codes
        reaching this method come from human-typed and portal-supplied
        sources — WhatsApp messages, XLSX cells, webhook payloads — and an
        exact match silently missed every one whose case differed: 2406
        leads on the live tenant. `codigo_norm` is a STORED generated
        column, so this is an indexed equality, not a scan.
        """
        result = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("codigo_norm", codigo.strip().upper())
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return _augment_row_derived(rows[0]) if rows else None

    def get_property_data(self, org_id: UUID, codigo: str) -> Optional[PropertyData]:
        """Resolve `codigo` against the local mirror, shaped as
        `PropertyData` — the YouTube-metadata carrier WhatsApp intake and
        the youtube-dashboard upload path both consume.

        `None` means a clean miss: `codigo` is not in `social_wiring.imoveis`
        for this org (either it doesn't exist on the tenant, or the sync
        hasn't run yet) — a real, actionable fact, never silently patched
        over with a live Vista call (roadmap
        `social-wiring-imoveis-vista-2026-08`, P2.5: no fallback branch).

        Raises `ImoveisLookupError` when the lookup ITSELF fails (the query
        errored — a DB/transport problem), which is a different failure
        mode from "not there" and must not be reported to the caller as a
        plain miss.
        """
        from postgrest.exceptions import APIError as PostgrestAPIError

        try:
            row = self.get(org_id, codigo)
        except PostgrestAPIError as exc:
            raise ImoveisLookupError(
                f"local imoveis lookup failed for {codigo!r}: {exc}"
            ) from exc
        if row is None:
            return None
        imovel = Imovel(**{k: v for k, v in row.items() if k not in _ROW_ONLY_COLUMNS})
        return imovel_to_property_data(imovel)

    def _select_all(self, columns: str, org_id: UUID) -> list[dict]:
        """Fetch EVERY matching row, paginating past PostgREST's row cap.

        **This exists because of a measured bug, not a hypothetical one.**
        PostgREST caps an unpaginated `select` at its configured maximum
        (1000 by default). A bare `.select(...).execute()` over a
        1919-imovel catalog therefore returns the first 1000 rows and reports
        no error at all — the caller cannot distinguish a complete answer
        from a truncated one.

        Verified live 2026-08-03 against the real catalog: the aggregate
        helpers below reported 19 categorias and 16 cidades where the true
        counts are 20 and 18. Two whole categories and two whole cities were
        missing from the filter dropdowns, silently, because they only occur
        in the tail of the table.

        That is exactly the shape this codebase treats as a defect — an
        incomplete answer presented as a complete one.

        NOC-REMEDIATE[query-efficiency]: `filter_options` and
        `caracteristica_counts` pull every row to aggregate in Python. At
        ~1919 rows that is fine; at 50k it is not. Replace with a
        Postgres-side aggregate (a view or RPC returning distinct values and
        slug counts) rather than raising the page size. Named destination:
        roadmap `social-wiring-imoveis-vista-2026-08`, Phase 2 follow-up. — 2026-08-04
        """
        page_size = 1000
        out: list[dict] = []
        start = 0
        while True:
            result = (
                self._catalogo()
                .select(columns)
                .eq("org_id", str(org_id))
                .range(start, start + page_size - 1)
                .execute()
            )
            rows = result.data or []
            out.extend(rows)
            if len(rows) < page_size:
                return out
            start += page_size

    def filter_options(self, org_id: UUID) -> dict:
        """Distinct values for the filter dropdowns, derived from stored rows.

        Derived, never hardcoded — the same rule as the Vista field
        calibration. A frozen list goes stale the moment the tenant adds a
        categoria, and it would go stale silently.
        """
        rows = self._select_all("status,categoria,cidade,bairro", org_id)
        out: dict[str, list[str]] = {}
        for key in ("status", "categoria", "cidade", "bairro"):
            values = {r.get(key) for r in rows if r.get(key)}
            out[key] = sorted(values)
        return out

    def caracteristica_counts(self, org_id: UUID) -> dict[str, int]:
        """How many imóveis carry each amenity slug.

        Powers a usage-ordered filter UI. The census found 28 of the 76
        tenant keys are never `Sim` — surfacing them would be 28 filters
        that always return nothing, so the UI orders by this and drops the
        zeroes.

        Excludes the four solar-orientation slugs (CONTRACT §3) — `norte`/
        `sul`/`leste`/`oeste` are not amenities and must not appear in the
        amenity-filter counts, the same split `_augment_row_derived` applies
        to a single row's `caracteristicas`.
        """
        counts: dict[str, int] = {}
        for row in self._select_all("caracteristicas", org_id):
            for slug in row.get("caracteristicas") or []:
                if slug in _ORIENTACAO_SOLAR_SLUGS:
                    continue
                counts[slug] = counts.get(slug, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


class ImovelSyncService:
    """Full-catalog pull from Vista into `social_wiring.imoveis`."""

    def __init__(
        self,
        client: Any,
        adapter: Any,
        *,
        concurrency: int = DEFAULT_SYNC_CONCURRENCY,
        duplicate_detector: Optional[Callable[..., Any]] = None,
        sonda_max_falhas: int = imoveis_descoberta.SONDA_MAX_FALHAS_PADRAO,
    ):
        self._client = client
        self._adapter = adapter
        self._concurrency = max(1, concurrency)
        # DI seam for the possível-duplicado step (CONTRACT §8.6); `None` =
        # `duplicatas_service.detectar`.
        self._duplicate_detector = duplicate_detector
        self._sonda_max_falhas = max(1, sonda_max_falhas)
        self._div: Optional[vista_divergencias.Execucao] = None
        # Ref-divergence notices (migration 333): codes Vista has and we did not, collected over a run, flushed once at its end.
        self._novas_run: list[str] = []
        self._tinha_espelho: Optional[bool] = False
        #: code -> the `Corretor` relation of an UNPUBLISHED record's stub body (read by `refresh_codigo`)
        self.corretores_ocultos: dict[str, list] = {}

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    async def sync(
        self, org_id: UUID, *, with_detalhes: bool = True, page_size: int = 50
    ) -> SyncReport:
        """Walk the whole catalog and upsert every imóvel.

        Idempotent by `(org_id, codigo)` — running it twice leaves 1919 rows,
        not 3838.

        `with_detalhes=True` (the default, ratified as D2) costs one extra
        call per imóvel. That is the only way to get `caracteristicas` and
        `FinalidadeStatus`, both of which are detalhes-only on the wire —
        without it the amenity filter has nothing to filter on.
        """
        report = SyncReport()
        started = datetime.now(timezone.utc)
        report.started_at = started.isoformat()
        self._div = vista_divergencias.iniciar(self._client.schema(_SCHEMA), org_id)
        self._novas_run, self._tinha_espelho = [], None  # `None` = decided lazily, BEFORE the first upsert of the run
        # {"cidade": {canonical: {raw spellings seen}}, "empreendimento": {...}}
        place_name_variants: dict[str, dict[str, set[str]]] = {
            field_name: {} for field_name in _PLACE_NAME_WIRE_KEYS
        }

        first = await self._fetch_page(1, page_size, report)
        vazio_com_espelho = (
            (first is None and report.listar_vazio_pagina) or (first is not None and not first.items)
        ) and self._mirror_tem_linhas(org_id)
        if first is None or vazio_com_espelho:
            report.finished_at = datetime.now(timezone.utc).isoformat()
            if vazio_com_espelho:
                # 🔴 `listar` says "nothing" while the mirror holds the catalog: that is Vista going silent (2026-10-23
                # on), not an empty agency. Refuse to go on -- the registry sweep would mark the WHOLE catalog removed.
                report.status = "listar_vazio"
                logger.error(
                    "imoveis sync: Vista `listar` returned NO rows for org=%s while the mirror has rows -- refusing to "
                    "sweep the registry (it would delist the whole catalog). status=listar_vazio", org_id,
                )
            return report

        report.total_reported = first.total
        pages = first.pages
        synced_at = started.isoformat()

        await self._process_page(
            first.items, org_id, synced_at, with_detalhes, report, place_name_variants
        )

        sem = asyncio.Semaphore(self._concurrency)

        async def one_page(page_no: int) -> None:
            async with sem:
                page = await self._fetch_page(page_no, page_size, report)
                if page is None:
                    return
                await self._process_page(
                    page.items, org_id, synced_at, with_detalhes, report,
                    place_name_variants,
                )

        await asyncio.gather(*(one_page(p) for p in range(2, pages + 1)))

        finished = datetime.now(timezone.utc)
        report.finished_at = finished.isoformat()
        report.duration_seconds = (finished - started).total_seconds()

        _log_place_name_merges(org_id, place_name_variants)
        self._fechar_divergencias(report)

        # Registry sweep — AFTER the upserts, and only on a complete run.
        #
        # Gated on `report.complete` deliberately. The sweep infers "this
        # imóvel left the catalog" from "the sync did not touch it this
        # run". On a run that dropped pages, thousands of untouched imóveis
        # are untouched because the FETCH failed, not because they were
        # sold — sweeping then would delist the catalog wholesale and stamp
        # snapshots over live listings. A skipped sweep costs one night of
        # lag; a wrong sweep costs the truth.
        if report.complete and report.upserted == 0 and self._mirror_tem_linhas(org_id):
            report.status = "listar_vazio"
            logger.error(
                "imoveis sync: `listar` pages upserted NOTHING for org=%s while the mirror has rows -- refusing to sweep "
                "the registry. status=listar_vazio", org_id,
            )
        elif report.complete:
            ativos_antes = self._avisos(report, "ativos_antes", self._ativos_do_registro, org_id)
            self._sweep_registry(org_id, synced_at, report)
            if ativos_antes is not None:
                ativos_depois = self._avisos(report, "ativos_depois", self._ativos_do_registro, org_id)
                sumiram = sorted(ativos_antes - ativos_depois) if ativos_depois is not None else []
                if sumiram:
                    self._avisos(report, "sumiram", imovel_ref_avisos.registrar_sumiram, org_id, sumiram, origem="listar (sweep)")
            self._detect_duplicates(org_id)
        else:
            logger.warning(
                "imoveis sync: skipping registry sweep for org=%s — the run "
                "was incomplete, so 'not seen' does not mean 'delisted'.",
                org_id,
            )

        self._fim_de_run_avisos(org_id, report, [])
        if not report.complete:
            # Loud, not silent. A partially-complete sync that reports success
            # is how an amenity filter quietly stops matching.
            logger.warning(
                "imoveis sync incomplete for org=%s — %d page failure(s), "
                "%d detalhes failure(s); %d/%d upserted",
                org_id, len(report.page_failures), len(report.detalhes_failed),
                report.upserted, report.total_reported,
            )
        else:
            logger.info(
                "imoveis sync complete for org=%s — %d upserted in %.1fs",
                org_id, report.upserted, report.duration_seconds,
            )
        return report


    # ─── Per-code refresh (modo="detalhes") ─────────────────────────────
    #
    # `/imoveis/listar` is the only endpoint that enumerates the catalog; when Vista leaves it silent (2026-10-23 on) the
    # mirror is kept current one CODE at a time from `/imoveis/detalhes`, through the same `vista_to_imovel` mapping and
    # the same `_imovel_to_row` upsert as the listar path. The tiers keep the call volume sane: every 2h only the
    # "vitrine" (public, still listed) codes + discovery; once a day the rest (sold / suspended / hidden / removed).

    def _mirror_tem_linhas(self, org_id: UUID) -> bool:
        resp = (
            self._table().select("codigo").eq("org_id", str(org_id)).limit(1).execute()
        )
        return bool(resp.data)

    def _paginado(self, tabela: Callable[[], Any], colunas: str, org_id: UUID, ordem: str, filtro: Optional[Callable[[Any], Any]] = None) -> list[dict]:
        saida: list[dict] = []
        inicio = 0
        while True:
            q = tabela().select(colunas).eq("org_id", str(org_id))
            if filtro:
                q = filtro(q)
            rows = q.order(ordem).range(inicio, inicio + 999).execute().data or []
            saida.extend(rows)
            if len(rows) < 1000:
                return saida
            inicio += 1000

    def _indice_espelho(self, org_id: UUID) -> dict[str, dict]:
        """norm(codigo) -> the mirror columns the refresh needs (paged: PostgREST caps a select at 1000 rows)."""
        rows = self._paginado(
            self._table, "codigo, status, exibir_no_site, data_atualizacao, sincronizado_em, "
            + ", ".join(_CAMPOS_SO_LISTAR), org_id, "codigo",
        )
        return {r["codigo"].strip().upper(): r for r in rows if r.get("codigo")}

    def _removidos_no_registro(self, org_id: UUID) -> set[str]:
        rows = self._paginado(
            self._registry_table, "codigo_canonical", org_id, "codigo_canonical",
            filtro=lambda q: q.eq("ativo_no_vista", False).not_.is_("delistado_em", "null"),
        )
        return {r["codigo_canonical"] for r in rows}

    @staticmethod
    def _e_vitrine(linha: dict) -> bool:
        return (linha.get("status") or "").strip().lower() in STATUS_VITRINE and linha.get("exibir_no_site") is not False

    async def sync_detalhes(
        self,
        org_id: UUID,
        *,
        escopo: str = "vitrine",
        descobrir: bool = True,
        descobridores: Optional[list[imoveis_descoberta.Descobridor]] = None,
        forcar: bool = False,
    ) -> SyncReport:
        """Refresh the mirror code by code from `/imoveis/detalhes`.

        `escopo`: `vitrine` (public listings still listed), `resto` (everything else in the mirror: sold, suspended,
        hidden, removed -- so a come-back is noticed) or `todos`. Discovery of NEW codes runs with `vitrine`/`todos`
        when `descobrir` (default seams: `/imoveis/destaques` + the forward probe).

        Writes ONLY Vista columns of `imoveis` (`_assert_so_vista`) and the lifecycle columns of `imovel_registry`;
        never deletes a row. A code Vista no longer has is marked removed in the registry the way the sweep marks it
        (`ativo_no_vista=false`, `delistado_em`, snapshot) -- behind a circuit breaker -- and a transport failure is a
        reported failure, never a removal. A code whose detalhes `DataAtualizacao` equals the mirror's is only touched
        (`sincronizado_em`), unless `forcar`.
        """
        if escopo not in ("vitrine", "resto", "todos"):
            raise ValueError(f"escopo must be vitrine|resto|todos, got {escopo!r}")
        report = SyncReport(caminho="detalhes", escopo=escopo)
        started = datetime.now(timezone.utc)
        report.started_at = synced_at = started.isoformat()
        self._div = vista_divergencias.iniciar(self._client.schema(_SCHEMA), org_id)
        place_name_variants: dict[str, dict[str, set[str]]] = {k: {} for k in _PLACE_NAME_WIRE_KEYS}

        espelho = self._indice_espelho(org_id)
        fora = self._removidos_no_registro(org_id)
        alvo: list[str] = []
        for norm, linha in espelho.items():
            vitrine = self._e_vitrine(linha) and norm not in fora
            if escopo == "todos" or (escopo == "vitrine") == vitrine:
                alvo.append(linha["codigo"])

        buscados: dict[str, Optional[Imovel]] = {c: None for c in alvo}
        if descobrir and escopo in ("vitrine", "todos"):
            conhecidos = set(espelho)
            for descobridor in (descobridores if descobridores is not None else self._descobridores_padrao()):
                try:
                    achados = await descobridor(self._adapter, conhecidos, report)
                except Exception as exc:
                    report.sonda_falhas.append(f"{getattr(descobridor, '__name__', 'descobridor')}: {type(exc).__name__}")
                    logger.warning("imoveis discovery %s failed for org=%s: %s", getattr(descobridor, "__name__", "?"), org_id, exc)
                    continue
                for codigo, imovel in achados.items():
                    if codigo.strip().upper() not in conhecidos and codigo not in buscados:
                        buscados[codigo] = imovel
                        report.descobertos.append(codigo)

        obtidos: dict[str, Imovel] = {c: i for c, i in buscados.items() if i is not None}
        sumiram: list[str] = []
        ocultos: list[str] = []
        sem = asyncio.Semaphore(min(self._concurrency, DETALHES_CONCURRENCY))

        async def um(codigo: str) -> None:
            async with sem:
                imovel, desfecho = await self.buscar_detalhe(codigo, report)
                if desfecho == DETALHE_OK and imovel is not None:
                    obtidos[codigo] = imovel
                elif desfecho == DETALHE_SUMIU:
                    sumiram.append(codigo)
                elif desfecho == DETALHE_OCULTO:
                    ocultos.append(codigo)

        await asyncio.gather(*(um(c) for c, i in buscados.items() if i is None))
        report.total_reported = len(buscados)
        report.detalhes_fetched = len(obtidos)

        mudaram: list[Imovel] = []
        iguais: list[str] = []
        self._novas_run, self._tinha_espelho = [], bool(espelho)
        for codigo, imovel in obtidos.items():
            atual = espelho.get(codigo.strip().upper())
            if atual is None:
                report.novos += 1
                self._novas_run.append(imovel.codigo)
                mudaram.append(imovel)
                continue
            imovel = self._mesclar_com_espelho(imovel, atual)
            if (
                not forcar and imovel.data_atualizacao is not None and atual.get("sincronizado_em")
                and str(atual.get("data_atualizacao") or "")[:10] == imovel.data_atualizacao.isoformat()
            ):
                iguais.append(imovel.codigo)
            else:
                report.atualizados += 1
                mudaram.append(imovel)
        report.inalterados = len(iguais)

        for imovel in mudaram:
            _record_place_name_variants(imovel, place_name_variants)
        self.gravar_imoveis(org_id, mudaram, synced_at, report)
        for i in range(0, len(iguais), _LOTE):
            self._table().update({"sincronizado_em": synced_at}).eq("org_id", str(org_id)).in_("codigo", iguais[i:i + _LOTE]).execute()
        self._reativar_registro(org_id, [im.codigo for im in obtidos.values()], synced_at, report)
        self._divergencias(list(obtidos.values()))
        self._fechar_divergencias(report)

        self._marcar_removidos(org_id, sumiram, ocultos, espelho, synced_at, report, caminhados=len(buscados))
        self._fim_de_run_avisos(org_id, report, [im.codigo for im in obtidos.values()])

        finished = datetime.now(timezone.utc)
        report.finished_at = finished.isoformat()
        report.duration_seconds = (finished - started).total_seconds()
        _log_place_name_merges(org_id, place_name_variants)
        if report.complete and (report.novos or report.atualizados):
            self._detect_duplicates(org_id)
        log = logger.info if report.status_final == "ok" else logger.warning
        log(
            "imoveis refresh (detalhes/%s) org=%s: %s — new=%d updated=%d unchanged=%d removed=%d failed=%d calls=%s",
            escopo, org_id, report.status_final, report.novos, report.atualizados, report.inalterados, report.removidos,
            len(report.detalhes_failed), report.chamadas,
        )
        return report

    async def buscar_detalhe(self, codigo: str, report: Optional[SyncReport] = None) -> tuple[Optional[Imovel], str]:
        """THE per-code Vista read (`/imoveis/detalhes`), paced by the shared `vista` bucket. Returns `(imovel, desfecho)`,
        `desfecho` one of `DETALHE_OK | DETALHE_SUMIU | DETALHE_OCULTO | DETALHE_FALHOU`. A transport/auth failure is
        `DETALHE_FALHOU` (recorded on `report.detalhes_failed` when given) -- NEVER read as the code being gone. Shared by
        `sync_detalhes` and `refresh_codigo`."""
        await rate_limit.acquire_async(VISTA_RATE_BUCKET)
        if report is not None:
            report.chamadas["detalhes"] = report.chamadas.get("detalhes", 0) + 1
        try:
            return await self._adapter.refresh_imovel(codigo), DETALHE_OK
        except VistaNotFound:
            return None, DETALHE_SUMIU
        except VistaRecordUnpublished as exc:
            # The stub body keeps the persistent `Corretor` relation: remember it (the ad-lead intake still records the brokers).
            self.corretores_ocultos[codigo] = parse_corretores((getattr(exc, "payload", None) or {}).get("Corretor"))
            return None, DETALHE_OCULTO
        except Exception as exc:
            if report is not None:
                report.detalhes_failed.append(codigo)
            logger.warning("imoveis refresh: detalhes failed for %s (%s)", codigo, type(exc).__name__)
            return None, DETALHE_FALHOU

    @staticmethod
    def _mesclar_com_espelho(imovel: Imovel, atual: Optional[dict]) -> Imovel:
        """A detalhes-only read has none of `_CAMPOS_SO_LISTAR`: keep what the mirror already has."""
        for campo in _CAMPOS_SO_LISTAR:
            if atual and getattr(imovel, campo) is None and atual.get(campo) is not None:
                imovel = imovel.model_copy(update={campo: atual[campo]})
        return imovel

    def gravar_imoveis(self, org_id: UUID, imoveis: list[Imovel], synced_at: str, report: SyncReport) -> None:
        """Upsert the Vista columns of `imoveis` + the registry identity, in batches (the one write path of the per-code
        refresh). Writes Vista columns ONLY (`_assert_so_vista`); the registry insert is `DO NOTHING` on conflict."""
        for i in range(0, len(imoveis), _LOTE):
            lote = imoveis[i:i + _LOTE]
            rows = [_imovel_to_row(im, org_id, synced_at) for im in lote]
            self._aplicar_pausa(org_id, rows, report)
            _assert_so_vista(rows)
            self._table().upsert(rows, on_conflict="org_id,codigo").execute()
            report.upserted += len(rows)
            self._upsert_registry(lote, org_id, synced_at, report)
            self._enriquecer_corretores(org_id, lote, report)

    def _linha_espelho(self, org_id: UUID, codigo: str) -> Optional[dict]:
        """The mirror row of ONE code (the columns the refresh compares), by the normalised code -- never the whole mirror."""
        norm = codigo.strip().upper()
        rows = (
            self._table().select("*").eq("org_id", str(org_id)).eq("codigo_norm", norm).limit(1).execute().data or []
        )
        return rows[0] if rows else None

    async def refresh_codigo(self, org_id: UUID, codigo: str) -> "RefreshCodigo":
        """Refresh ONE code from Vista, ALWAYS (no `data_atualizacao` short-circuit -- the caller wants it compared NOW):
        fetch detalhes -> upsert the Vista columns of `imoveis` + the registry identity -> record the Vista-vs-ours
        divergences through `vista_divergencias` -> report which mirror columns changed. The public per-code seam the
        ad-lead intake uses; `sync_detalhes` shares `buscar_detalhe` / `gravar_imoveis` / `_divergencias` with it.

        Never raises for a Vista outcome: `desfecho` carries it (`DETALHE_FALHOU` => the caller records a retryable failure)."""
        report = SyncReport(caminho="detalhes", escopo=None)
        agora = datetime.now(timezone.utc)
        report.started_at = synced_at = agora.isoformat()
        self._div = vista_divergencias.iniciar(self._client.schema(_SCHEMA), org_id)
        imovel, desfecho = await self.buscar_detalhe(codigo, report)
        saida = RefreshCodigo(codigo=codigo, desfecho=desfecho, report=report, corretores_oculto=self.corretores_ocultos.pop(codigo, []))
        self._novas_run, self._tinha_espelho = [], self._mirror_tem_linhas(org_id)
        if imovel is None:
            if desfecho == DETALHE_SUMIU:
                # We may hold it, Vista does not: keep every datum, pause it, open the notice (a code we never had gets none).
                self._marcar_removidos(org_id, [codigo], [], {}, synced_at, report, caminhados=1)
                self._fim_de_run_avisos(org_id, report, [])
            report.finished_at = datetime.now(timezone.utc).isoformat()
            return saida
        atual = self._linha_espelho(org_id, imovel.codigo)
        if atual is None:
            self._novas_run.append(imovel.codigo)
        imovel = self._mesclar_com_espelho(imovel, atual)
        novo_row = _imovel_to_row(imovel, org_id, synced_at)
        saida.imovel = imovel
        saida.existia = atual is not None
        saida.mudancas = {
            c: {"antes": atual.get(c), "depois": novo_row.get(c)}
            for c in sorted(COLUNAS_VISTA - _ROW_ONLY_COLUMNS)  # bookkeeping (`sincronizado_em`) is not a Vista change
            if atual is not None and c in novo_row and _difere(atual.get(c), novo_row.get(c))
        }
        self.gravar_imoveis(org_id, [imovel], synced_at, report)
        self._reativar_registro(org_id, [imovel.codigo], synced_at, report)
        self._divergencias([imovel])
        self._fechar_divergencias(report)
        self._fim_de_run_avisos(org_id, report, [imovel.codigo])
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return saida

    # ─── Ref-divergence notices: the sync never erases our data, it WARNS (imovel_ref_avisos, migration 333) ────────────
    def _avisos_db(self):
        return self._client.schema(_SCHEMA)

    def _avisos(self, report: SyncReport, o_que: str, fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
        """Run one notice operation; a failure is LOUD (ERROR + `report.registry_failures`) and never fails the sync -- the catalog
        pull must not die because the notices table is unreadable (e.g. migration 333 not applied yet)."""
        try:
            return fn(self._avisos_db(), *args, **kw)
        except Exception as exc:
            report.registry_failures.append(f"avisos {o_que}: {type(exc).__name__}: {exc}")
            logger.error("imoveis sync: ref notice step %r failed (%s)", o_que, exc, exc_info=True)
            return None

    def _aplicar_pausa(self, org_id: UUID, rows: list[dict], report: SyncReport) -> None:
        """A code with an open (or confirmed-gone) `ref_sumiu_no_vista` notice stays PAUSED: the upsert must not flip `exibir_no_site`
        back from Vista. Vista's value is not applied; a human restores or confirms (`imovel_ref_avisos.resolver`)."""
        pausados = self._avisos(report, "pausados", imovel_ref_avisos.codigos_pausados, org_id)
        if not pausados:
            return
        for row in rows:
            if str(row.get("codigo") or "").strip().upper() in pausados:
                row["exibir_no_site"] = False

    def _ativos_do_registro(self, _db: Any, org_id: UUID) -> set[str]:
        """Canonical codes the registry currently has as active in Vista (paged: PostgREST caps a select at 1000 rows)."""
        rows = self._paginado(self._registry_table, "codigo_canonical", org_id, "codigo_canonical", filtro=lambda q: q.eq("ativo_no_vista", True))
        return {str(r["codigo_canonical"]) for r in rows}

    def _detectar_novas(self, org_id: UUID, rows: list[dict], report: SyncReport) -> list[str]:
        """Codes of this page the mirror does not have yet (called BEFORE the upsert). Never fails the sync: on a read error it logs, records
        it and reports none. An org's very first import (empty mirror) never produces `ref_nova` notices."""
        try:
            if self._tinha_espelho is None:
                self._tinha_espelho = self._mirror_tem_linhas(org_id)
            if not self._tinha_espelho:
                return []
            codigos = [str(r["codigo"]).strip().upper() for r in rows]
            existentes = {
                str(r["codigo_norm"]) for r in (
                    self._table().select("codigo_norm").eq("org_id", str(org_id)).in_("codigo_norm", codigos).execute().data or []
                )
            }
            return [str(r["codigo"]) for r in rows if str(r["codigo"]).strip().upper() not in existentes]
        except Exception as exc:
            report.registry_failures.append(f"avisos novas: {type(exc).__name__}: {exc}")
            logger.error("imoveis sync: could not detect new refs (%s)", exc, exc_info=True)
            return []

    def _enriquecer_corretores(self, org_id: UUID, imoveis: list[Imovel], report: SyncReport) -> None:
        """The `Corretor` relation of every property read fills the EMPTY fields of the matching `lead_corretores` (never overwrites).
        Best effort: a failure is recorded and logged, never fails the catalog pull."""
        entradas = [c for i in imoveis for c in i.corretores]
        if entradas:
            self._avisos(report, "corretores", corretores_enriquecimento.enriquecer, org_id, entradas)

    def _fim_de_run_avisos_parcial(self, org_id: UUID, report: SyncReport, vistos: list[str]) -> None:
        if vistos:
            self._avisos(report, "reaparecimentos", imovel_ref_avisos.anotar_reaparecimentos, org_id, vistos)

    def _fim_de_run_avisos(self, org_id: UUID, report: SyncReport, vistos: list[str]) -> None:
        """Codes Vista answered for: a paused ref that reappeared gets a NOTE (never restored). New refs: ONE batch notice per run."""
        if vistos:
            self._avisos(report, "reaparecimentos", imovel_ref_avisos.anotar_reaparecimentos, org_id, vistos)
        if self._novas_run:
            self._avisos(report, "novas", imovel_ref_avisos.registrar_novas, org_id, self._novas_run)
        self._novas_run = []

    def _divergencias(self, imoveis: list[Imovel]) -> None:
        """THE call site of the transitional Vista-vs-ours divergence check (no-op when the org's flag is off)."""
        if self._div is None or not imoveis:
            return
        link = None
        try:
            from app.services import julia_conhecimento_service

            link = julia_conhecimento_service.link_imovel_fn(self._client.schema(_SCHEMA), self._div.org_id)
        except Exception as exc:  # a link is a convenience; the divergence is not
            logger.warning("vista divergences: site link unavailable (%s)", type(exc).__name__)
        vista_divergencias.verificar(self._div, imoveis, link_site=link)

    def _fechar_divergencias(self, report: SyncReport) -> None:
        if self._div is not None:
            report.divergencias_linhas = list(self._div.novas)
            report.divergencias_erros = list(self._div.erros)
            report.divergencias_comparadas = self._div.comparadas

    def _descobridores_padrao(self) -> list[imoveis_descoberta.Descobridor]:
        return [imoveis_descoberta.por_destaques, imoveis_descoberta.criar_sonda(self._sonda_max_falhas)]

    def _reativar_registro(self, org_id: UUID, codigos: list[str], synced_at: str, report: SyncReport) -> None:
        """Seen at Vista this run => active again (the sweep's step 1, per code). Lifecycle columns ONLY."""
        canon = sorted({c.strip().upper() for c in codigos if c and c.strip()})
        for i in range(0, len(canon), _LOTE):
            try:
                (
                    self._registry_table()
                    .update({"ativo_no_vista": True, "ultimo_visto_no_vista_em": synced_at, "delistado_em": None})
                    .eq("org_id", str(org_id)).in_("codigo_canonical", canon[i:i + _LOTE]).execute()
                )
            except Exception as exc:
                report.registry_failures.append(f"reativar: {type(exc).__name__}: {exc}")
                logger.warning("imoveis refresh: registry reactivation failed for org=%s: %s", org_id, exc)

    def _marcar_removidos(
        self, org_id: UUID, sumiram: list[str], ocultos: list[str], espelho: dict[str, dict],
        synced_at: str, report: SyncReport, *, caminhados: int,
    ) -> None:
        """Mark what Vista no longer shows, the way the sweep does (registry: inactive + `delistado_em` + snapshot).
        Never deletes. Refused (status `removidos_excessivos`) past the circuit breaker."""
        todos = sorted({c for c in [*sumiram, *ocultos]})
        if not todos:
            return
        limite = max(REMOVIDOS_MIN_ABS, caminhados * REMOVIDOS_MAX_PCT / 100.0)
        if len(todos) > limite:
            report.status = "removidos_excessivos"
            logger.error(
                "imoveis refresh: %d of %d codes look removed for org=%s (> %.0f%%/%d) -- refusing to mark them; this is "
                "a Vista fault until proven otherwise", len(todos), caminhados, org_id, REMOVIDOS_MAX_PCT, REMOVIDOS_MIN_ABS,
            )
            return
        em_espelho_sumiram: list[str] = []
        for codigo in todos:
            canon = codigo.strip().upper()
            linhas_espelho = (
                self._table().select("titulo, categoria, status, bairro, cidade, uf, valor_venda, valor_locacao, dormitorios, area_total, foto_destaque")
                .eq("org_id", str(org_id)).eq("codigo", codigo).limit(1).execute().data or []
            )
            linha = linhas_espelho[0] if linhas_espelho else {}
            if linhas_espelho and codigo in sumiram:
                em_espelho_sumiram.append(canon)
            snap = {f"snap_{k}": v for k, v in linha.items()}
            try:
                (
                    self._registry_table()
                    .update({"ativo_no_vista": False, "delistado_em": synced_at, "snap_em": synced_at, **snap})
                    .eq("org_id", str(org_id)).eq("codigo_canonical", canon).eq("ativo_no_vista", True).execute()
                )
            except Exception as exc:
                report.registry_failures.append(f"remover {codigo}: {type(exc).__name__}: {exc}")
                continue
            report.removidos += 1
            report.removidos_codigos.append(codigo)
        if em_espelho_sumiram:
            # We have it, Vista does not: KEEP every datum, PAUSE it, open the notice (never a delete, never silent).
            self._avisos(report, "sumiram", imovel_ref_avisos.registrar_sumiram, org_id, em_espelho_sumiram, origem="detalhes")
        if ocultos:
            # Vista says ExibirNoSite=Nao: the one Vista-sourced column that tells every reader of the mirror to hide it.
            for i in range(0, len(ocultos), _LOTE):
                self._table().update({"exibir_no_site": False, "sincronizado_em": synced_at}).eq("org_id", str(org_id)).in_(
                    "codigo", ocultos[i:i + _LOTE]).execute()

    def _detect_duplicates(self, org_id: UUID) -> None:
        """Possível-duplicado detection (manual imóveis vs the fresh catalog) —
        a SEPARATE step after a COMPLETE sync (an incomplete run has a partial
        catalog to compare against). Its failure is logged loudly by
        `detectar_sem_falhar` and NEVER fails the sync."""
        from app.modules.imovel_hub import duplicatas_service

        duplicatas_service.detectar_sem_falhar(
            self._client.schema(_SCHEMA), org_id,
            detector=self._duplicate_detector, origem="vista sync",
        )

    async def _fetch_page(self, page_no: int, page_size: int, report: SyncReport):
        await rate_limit.acquire_async(VISTA_RATE_BUCKET)
        report.chamadas["listar"] = report.chamadas.get("listar", 0) + 1
        try:
            page = await self._adapter.list_imoveis(
                page=page_no, page_size=page_size, with_detalhes=False
            )
        except Exception as exc:
            if page_no == 1 and isinstance(exc, VistaNotFound):
                report.listar_vazio_pagina = True
            # Recorded, never swallowed — `report.complete` goes False and
            # the caller sees which pages are missing.
            report.page_failures.append(f"page {page_no}: {type(exc).__name__}: {exc}")
            logger.warning("imoveis sync: page %d failed: %s", page_no, exc)
            return None
        report.pages_fetched += 1
        return page

    async def _process_page(
        self,
        imoveis: list[Imovel],
        org_id: UUID,
        synced_at: str,
        with_detalhes: bool,
        report: SyncReport,
        place_name_variants: dict[str, dict[str, set[str]]],
    ) -> None:
        if with_detalhes:
            imoveis = await self._enrich(imoveis, report)
        for imovel in imoveis:
            _record_place_name_variants(imovel, place_name_variants)
        rows = [_imovel_to_row(i, org_id, synced_at) for i in imoveis]
        if not rows:
            return
        self._aplicar_pausa(org_id, rows, report)
        novas = self._detectar_novas(org_id, rows, report)
        _assert_so_vista(rows)
        self._table().upsert(rows, on_conflict="org_id,codigo").execute()
        report.upserted += len(rows)
        self._novas_run.extend(novas)
        self._enriquecer_corretores(org_id, imoveis, report)
        self._fim_de_run_avisos_parcial(org_id, report, [i.codigo for i in imoveis])

        # Registry rows for anything we have not seen before. `DO NOTHING` on
        # conflict, so an imóvel that already has an identity keeps its
        # original `primeiro_visto_em` and `origem_descoberta` — a row first
        # discovered via a LEAD must not be rewritten as `vista_sync` just
        # because the catalog later showed it to us. The sweep, not this,
        # maintains the lifecycle columns.
        self._upsert_registry(imoveis, org_id, synced_at, report)
        self._divergencias(imoveis)

    def _registry_table(self):
        return self._client.schema(_SCHEMA).table(_REGISTRY_TABLE)

    def _upsert_registry(
        self, imoveis: list[Imovel], org_id: UUID, synced_at: str, report: SyncReport
    ) -> None:
        rows = [
            {
                "org_id": str(org_id),
                "codigo_canonical": i.codigo.strip().upper(),
                "codigo_display": i.codigo,
                "ultimo_visto_no_vista_em": synced_at,
                "ativo_no_vista": True,
                "origem_descoberta": "vista_sync",
            }
            for i in imoveis
            if i.codigo and i.codigo.strip()
        ]
        if not rows:
            return
        try:
            (
                self._registry_table()
                .upsert(
                    rows,
                    on_conflict="org_id,codigo_canonical",
                    ignore_duplicates=True,
                )
                .execute()
            )
        except Exception as exc:
            # Recorded, not swallowed, and NOT fatal: the catalog upsert above
            # already succeeded, and a registry that lags by one page is
            # repaired by the next run. Losing the whole sync over it would be
            # the worse trade.
            report.registry_failures.append(f"{type(exc).__name__}: {exc}")
            logger.warning(
                "imoveis sync: registry upsert failed for org=%s: %s", org_id, exc,
            )

    def _sweep_registry(self, org_id: UUID, synced_at: str, report: SyncReport) -> None:
        """Mark what this run saw as active; delist + snapshot what it did not.

        Delegates to `social_wiring.sweep_imovel_registry` (migration 063)
        rather than reproducing the logic here: the snapshot copy is a
        correlated UPDATE across two tables, which is one statement in SQL
        and a read-modify-write race in Python.
        """
        try:
            resp = self._client.rpc(
                "sweep_imovel_registry",
                {"p_org_id": str(org_id), "p_run_at": synced_at},
            ).execute()
        except Exception as exc:
            report.registry_failures.append(f"sweep: {type(exc).__name__}: {exc}")
            logger.error(
                "imoveis sync: registry sweep FAILED for org=%s: %s — imóveis "
                "that left the catalog keep a stale ativo_no_vista until the "
                "next successful run.", org_id, exc, exc_info=True,
            )
            return

        data = resp.data if isinstance(resp.data, list) else [resp.data or {}]
        first = data[0] if data else {}
        report.registry_ativos = int(first.get("marcados_ativos") or 0)
        report.registry_delistados = int(first.get("marcados_delistados") or 0)
        log = logger.warning if report.registry_delistados else logger.info
        log(
            "imoveis registry sweep org=%s: %d ativo(s), %d delistado(s)",
            org_id, report.registry_ativos, report.registry_delistados,
        )

    async def _enrich(self, imoveis: list[Imovel], report: SyncReport) -> list[Imovel]:
        """Re-fetch each imóvel with detalhes, in place.

        A failure here downgrades ONE imóvel to its listar-only shape and is
        recorded in `report.detalhes_failed` — it never drops the imóvel and
        never aborts the page.
        """
        sem = asyncio.Semaphore(self._concurrency)
        out: list[Imovel] = list(imoveis)

        async def enrich_one(index: int, imovel: Imovel) -> None:
            async with sem:
                await rate_limit.acquire_async(VISTA_RATE_BUCKET)
                report.chamadas["listar"] = report.chamadas.get("listar", 0) + 1  # get_imovel = one listar row ...
                report.chamadas["detalhes"] = report.chamadas.get("detalhes", 0) + 1  # ... + one detalhes
                try:
                    full = await self._adapter.get_imovel(imovel.codigo)
                except Exception as exc:
                    report.detalhes_failed.append(imovel.codigo)
                    logger.warning(
                        "imoveis sync: detalhes failed for %s (%s) — "
                        "storing listar-only row without caracteristicas",
                        imovel.codigo, type(exc).__name__,
                    )
                    return
                if full is not None:
                    out[index] = full
                    report.detalhes_fetched += 1
                else:
                    report.detalhes_failed.append(imovel.codigo)

        await asyncio.gather(*(enrich_one(i, im) for i, im in enumerate(imoveis)))
        return out


def build_imoveis_service(client: Any) -> ImoveisService:
    return ImoveisService(client)


def build_sync_service(client: Any, adapter: Any, **kwargs: Any) -> ImovelSyncService:
    return ImovelSyncService(client, adapter, **kwargs)
