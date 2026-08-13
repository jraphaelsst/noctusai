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
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.real_estate import Imovel, PropertyData, imovel_to_property_data
from noctusai_lib.integrations import rate_limit

logger = logging.getLogger(__name__)

__all__ = [
    "ImoveisService",
    "ImovelSyncService",
    "ImoveisLookupError",
    "SyncReport",
    "build_imoveis_service",
    "build_sync_service",
]

# Row columns that are persistence-only (added by `_imovel_to_row`, not part
# of the `Imovel` model) — stripped before reconstituting `Imovel(**row)`.
_ROW_ONLY_COLUMNS = frozenset({"org_id", "sincronizado_em"})


class ImoveisLookupError(Exception):
    """The local `imoveis` lookup itself failed (a DB/transport problem —
    e.g. PostgREST unreachable), as distinct from a clean miss (`None`,
    meaning: not in the catalog). Callers that need to tell "couldn't ask"
    apart from "asked, not there" catch this specifically."""

_SCHEMA = "social_wiring"
_TABLE = "imoveis"

# Vista tolerated concurrency 8 with no throttling in the 2026-08-03
# measurement (24-call batches: 20.1s serial → 4.3s at 4 → 3.1s at 8, zero
# errors at every level). 6 is deliberately below the proven ceiling — the
# measurement was one tenant on one day, and a sync that finishes in 5
# minutes instead of 4 is not worth discovering their rate limit in
# production.
DEFAULT_SYNC_CONCURRENCY = 6
VISTA_RATE_BUCKET = "vista"


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

    @property
    def complete(self) -> bool:
        """True only when nothing was skipped anywhere."""
        return not self.page_failures and not self.detalhes_failed

    def as_dict(self) -> dict:
        return {
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
        "corretores": [c.model_dump() for c in imovel.corretores],
        "construtora": imovel.construtora,
        "data_cadastro": imovel.data_cadastro.isoformat() if imovel.data_cadastro else None,
        "data_atualizacao": (
            imovel.data_atualizacao.isoformat() if imovel.data_atualizacao else None
        ),
        "caracteristicas": sorted(imovel.caracteristicas),
        "caracteristicas_raw": imovel.caracteristicas_raw,
        "vista_raw": imovel.vista_raw,
        "sincronizado_em": synced_at,
    }


class ImoveisService:
    """Read/query `social_wiring.imoveis`. Every query filters `org_id`
    explicitly — defense in depth on top of RLS."""

    def __init__(self, client: Any):
        self._client = client

    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

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
    ) -> dict:
        query = self._table().select("*", count="exact").eq("org_id", str(org_id))
        if status:
            query = query.eq("status", status)
        if categoria:
            query = query.eq("categoria", categoria)
        if cidade:
            query = query.eq("cidade", cidade)
        if bairro:
            query = query.eq("bairro", bairro)
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
        rows = result.data or []
        total = getattr(result, "count", None)
        total = len(rows) if total is None else total
        pages = max(1, (total + page_size - 1) // page_size)
        return {"items": rows, "total": total, "page": page, "pages": pages}

    def get(self, org_id: UUID, codigo: str) -> Optional[dict]:
        result = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
            .eq("codigo", codigo)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

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
        roadmap `social-wiring-imoveis-vista-2026-08`, Phase 2 follow-up.
        """
        page_size = 1000
        out: list[dict] = []
        start = 0
        while True:
            result = (
                self._table()
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
        """
        counts: dict[str, int] = {}
        for row in self._select_all("caracteristicas", org_id):
            for slug in row.get("caracteristicas") or []:
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
    ):
        self._client = client
        self._adapter = adapter
        self._concurrency = max(1, concurrency)

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

        first = await self._fetch_page(1, page_size, report)
        if first is None:
            report.finished_at = datetime.now(timezone.utc).isoformat()
            return report

        report.total_reported = first.total
        pages = first.pages
        synced_at = started.isoformat()

        await self._process_page(first.items, org_id, synced_at, with_detalhes, report)

        sem = asyncio.Semaphore(self._concurrency)

        async def one_page(page_no: int) -> None:
            async with sem:
                page = await self._fetch_page(page_no, page_size, report)
                if page is None:
                    return
                await self._process_page(
                    page.items, org_id, synced_at, with_detalhes, report
                )

        await asyncio.gather(*(one_page(p) for p in range(2, pages + 1)))

        finished = datetime.now(timezone.utc)
        report.finished_at = finished.isoformat()
        report.duration_seconds = (finished - started).total_seconds()

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

    async def _fetch_page(self, page_no: int, page_size: int, report: SyncReport):
        await rate_limit.acquire_async(VISTA_RATE_BUCKET)
        try:
            page = await self._adapter.list_imoveis(
                page=page_no, page_size=page_size, with_detalhes=False
            )
        except Exception as exc:
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
    ) -> None:
        if with_detalhes:
            imoveis = await self._enrich(imoveis, report)
        rows = [_imovel_to_row(i, org_id, synced_at) for i in imoveis]
        if not rows:
            return
        self._table().upsert(rows, on_conflict="org_id,codigo").execute()
        report.upserted += len(rows)

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
