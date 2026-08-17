"""Portal ROI — spend vs. results per marketing portal.

Contract: ``products/social-wiring/projects/portal-roi-PROJECT.md`` §3.
Backs ``GET /resumo`` · ``GET /campanhas`` · ``POST/PATCH/DELETE
/campanhas/{id}`` · ``GET /origens``. Reads/writes
``social_wiring.lead_campanhas`` (spend, manually entered),
``social_wiring.leads`` (volume, read-only here), and
``social_wiring.lead_vendas`` (closed deals, read-only here — this slice
ships no vendas write surface).

🔴 `investimento` / `cpl` / `roi` / `taxa_conversao` are ``None`` when
unrecorded and a real number (possibly exactly ``0``) when recorded.
Never coerce one into the other anywhere in this module — that
distinction is the entire reason this project exists (migration `047`'s
header has the full reasoning per derived column).

Read-then-write, not DB ``upsert()``
────────────────────────────────────
``noctusai_lib.testing.MockRequestBuilder.upsert()`` is a documented
no-op for propagation (returns the CURRENT data, doesn't mutate) —
mirrors ``app/modules/leads/services/dimensions_service.py``'s
established idiom in this product: every write here is
read-existing-then-insert/update, never ``upsert()``.

GENERATED columns are computed here, not trusted from the mock
─────────────────────────────────────────────────────────────────
``cpc``/``cpl``/``custo_visita`` are ``GENERATED ALWAYS AS (...) STORED``
in Postgres (migration `043`); ``MockSupabaseClient`` does not execute
generated-column expressions, so a mocked insert/update response never
carries them. :func:`_with_generated` computes the same formulas
(``investimento / NULLIF(x, 0)``) in Python so the API's response shape
is correct against BOTH the mock (tests) and the real DB (prod, where
the DB already computed them — this recomputation is idempotent, same
inputs same outputs).
"""
from __future__ import annotations

import uuid
import weakref
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, ConflictError, NotFoundError

__all__ = [
    "PortalRoiService",
    "PortalRoiValidationError",
    "build_portal_roi_service",
    "get_portal_roi_client",
]

_SCHEMA = "social_wiring"


class PortalRoiValidationError(AppException):
    """422 — ``periodo_fim < periodo_inicio``, or ``investimento < 0``.

    Subclasses ``AppException`` (not a bare ``ValueError``/``HTTPException``)
    so it rides the SAME exception-handler wiring ``create_product_app``
    already installs for ``NotFoundError``/``ConflictError``
    (``app.add_exception_handler(AppException, app_exception_handler)`` —
    Starlette dispatches by MRO, so this subclass is caught without any
    router-level ``try/except``). Every write error in this module
    therefore carries an actionable ``detail`` with zero bespoke plumbing.
    """

    def __init__(self, message: str):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422)


# ─── DI seam: schema-scoped, cached client ─────────────────────────────
#
# Mirrors ``app/modules/leads/deps.py::get_leads_client`` EXACTLY — same
# bug, same fix; see that module's docstring for the full empirically-
# verified trace. ``MockSupabaseClient.schema(name)`` returns a BRAND NEW
# wrapper with an EMPTY per-table row cache on every call (the underlying
# row list lives on the per-table ``MockRequestBuilder`` instance, which
# is only cached per ``MockSupabaseClient`` OBJECT, not globally) — a
# service that re-resolves ``.schema(SCHEMA)`` on every table access (the
# ``imoveis_service.py``/``marcas_service.py`` shape) silently discards
# every prior insert the instant two separate calls re-bind the schema.
# That is exactly what a POST-then-GET duplicate check (§3.3's 409) and a
# create-then-list flow both do, across separate HTTP requests AND within
# a single request. Binding once per underlying admin-client OBJECT and
# reusing it fixes this for the mock; a real Supabase client is stateless
# HTTP-request shaping either way, so this changes nothing in prod.
_scoped_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_portal_roi_client() -> Any:
    """FastAPI dependency — the ``social_wiring``-scoped admin client,
    cached by the underlying admin-client object (see module docstring)."""
    from app.dependencies import get_admin_client

    admin = get_admin_client()
    cached = _scoped_cache.get(admin)
    if cached is None:
        cached = admin.schema(_SCHEMA)
        _scoped_cache[admin] = cached
    return cached


def _new_id_and_created_at() -> tuple[str, str]:
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


def _to_num(value: Any) -> Optional[float]:
    """``None`` stays ``None``; anything else becomes ``float``.

    PostgREST/the mock hand back numeric columns as ``str``/``int``/
    ``float`` depending on path — this normalizes without ever turning an
    absent value into ``0``."""
    if value is None:
        return None
    return float(value)


def _with_generated(row: dict) -> dict:
    """Attach ``cpc``/``cpl``/``custo_visita`` — see module docstring."""
    investimento = _to_num(row.get("investimento"))
    cliques = row.get("cliques")
    leads = row.get("leads")
    visitas_perfil = row.get("visitas_perfil")
    out = dict(row)
    out["investimento"] = investimento
    out["cpc"] = (investimento / cliques) if (investimento is not None and cliques) else None
    out["cpl"] = (investimento / leads) if (investimento is not None and leads) else None
    out["custo_visita"] = (
        (investimento / visitas_perfil) if (investimento is not None and visitas_perfil) else None
    )
    return out


def _validate_period(periodo_inicio: date, periodo_fim: date) -> None:
    if periodo_fim < periodo_inicio:
        raise PortalRoiValidationError(
            "periodo_fim deve ser maior ou igual a periodo_inicio"
        )


def _validate_investimento(value: Any) -> None:
    if value is not None and float(value) < 0:
        raise PortalRoiValidationError("investimento não pode ser negativo")


class PortalRoiService:
    """Reads/writes over ``lead_sources`` / ``lead_campanhas`` / ``leads``
    / ``lead_vendas``. ``client`` MUST already be schema-scoped — see
    :func:`get_portal_roi_client`'s docstring for why re-resolving
    ``.schema()`` per call is the wrong shape for this service."""

    def __init__(self, client: Any):
        self._client = client

    def _table(self, name: str):
        return self._client.table(name)

    # ── pagination-safe fetch — same PostgREST-row-cap concern
    #    imoveis_service.py's `_select_all` guards against, ported here
    #    for the same reason (an unbounded `.select()` truncates past the
    #    server's default row cap with no error). Volumes here are small
    #    today (24 origens, low-hundreds of campanhas/vendas rows at
    #    most) but the guard is cheap and the failure mode (silent
    #    truncation) is exactly what this whole project exists to stop.
    def _select_all(self, table: str, columns: str, org_id: UUID, **eq_filters: Any) -> list[dict]:
        page_size = 1000
        out: list[dict] = []
        start = 0
        while True:
            query = self._table(table).select(columns).eq("org_id", str(org_id))
            for col, val in eq_filters.items():
                if val is not None:
                    query = query.eq(col, val)
            result = query.range(start, start + page_size - 1).execute()
            rows = result.data or []
            out.extend(rows)
            if len(rows) < page_size:
                return out
            start += page_size

    # ── origens ───────────────────────────────────────────────────────

    def list_origens(self, org_id: UUID) -> list[dict]:
        rows = self._select_all("lead_sources", "id,slug,label,categoria", org_id)
        rows.sort(key=lambda r: r.get("label") or "")
        return rows

    def _get_origem(self, org_id: UUID, origem_id: UUID) -> Optional[dict]:
        resp = (
            self._table("lead_sources")
            .select("id,slug,label,categoria")
            .eq("org_id", str(org_id))
            .eq("id", str(origem_id))
            .execute()
        )
        rows = list(resp.data or [])
        return rows[0] if rows else None

    # ── resumo ────────────────────────────────────────────────────────

    def resumo(
        self,
        org_id: UUID,
        periodo_inicio: Optional[date] = None,
        periodo_fim: Optional[date] = None,
    ) -> dict:
        """Per-portal + platform-wide totals, mirroring
        ``vw_portal_roi``'s join shape (lifetime, when no period is
        given) or a period-scoped equivalent computed directly (when
        either bound is given) — ONE code path either way (period
        filters, when absent, simply match every row), so there is never
        a second formula that could silently disagree with the first.
        """
        sources = self._select_all("lead_sources", "id,slug,label,categoria", org_id)

        campanhas = self._fetch_campanhas_rows(org_id, None, periodo_inicio, periodo_fim)
        # `investimento_by_origem` uses PRESENCE-in-dict as the "recorded"
        # signal — an origem absent here got NO row in range, and stays
        # None (unrecorded). An origem present with a summed 0.00 got a
        # real row (or rows) that summed to zero — a genuine fact.
        investimento_by_origem: dict[str, float] = {}
        for row in campanhas:
            oid = row["origem_id"]
            investimento_by_origem[oid] = investimento_by_origem.get(oid, 0.0) + float(
                row["investimento"]
            )

        leads_by_origem = self._count_leads_by_origem(org_id, periodo_inicio, periodo_fim)
        vendas_by_origem = self._aggregate_vendas_by_origem(org_id, periodo_inicio, periodo_fim)

        portais: list[dict] = []
        for s in sources:
            oid = s["id"]
            investimento = investimento_by_origem.get(oid)  # None = unrecorded
            total_leads = leads_by_origem.get(oid, 0)
            v = vendas_by_origem.get(oid, (0, 0.0))
            total_vendas, valor_vendas = v
            portais.append(
                {
                    "origem_id": oid,
                    "slug": s["slug"],
                    "label": s["label"],
                    "categoria": s["categoria"],
                    "investimento": investimento,
                    "total_leads": total_leads,
                    "total_vendas": total_vendas,
                    "valor_vendas": valor_vendas,
                    "cpl": _cpl(investimento, total_leads),
                    "roi": _roi(investimento, valor_vendas),
                    "taxa_conversao": _taxa_conversao(total_vendas, total_leads),
                }
            )
        portais.sort(key=lambda p: p["label"] or "")

        # `recorded` — origens that DID get at least one campanha row in
        # range. Summing only those (never the None ones as 0) is what
        # keeps `totais.investimento` honest: if NO portal has any
        # recorded spend in range, the platform total is unrecorded too,
        # not a confident "R$ 0,00".
        recorded = [p["investimento"] for p in portais if p["investimento"] is not None]
        total_investimento = sum(recorded) if recorded else None
        total_leads = sum(p["total_leads"] for p in portais)
        total_vendas = sum(p["total_vendas"] for p in portais)
        total_valor_vendas = sum(p["valor_vendas"] for p in portais)

        periodo = None
        if periodo_inicio is not None or periodo_fim is not None:
            periodo = {
                "inicio": periodo_inicio.isoformat() if periodo_inicio else None,
                "fim": periodo_fim.isoformat() if periodo_fim else None,
            }

        return {
            "periodo": periodo,
            "totais": {
                "investimento": total_investimento,
                "total_leads": total_leads,
                "total_vendas": total_vendas,
                "valor_vendas": total_valor_vendas,
                "cpl": _cpl(total_investimento, total_leads),
                "roi": _roi(total_investimento, total_valor_vendas),
                "taxa_conversao": _taxa_conversao(total_vendas, total_leads),
            },
            "portais": portais,
        }

    # ── campanhas (spend entries) ────────────────────────────────────

    def _fetch_campanhas_rows(
        self,
        org_id: UUID,
        origem_id: Optional[UUID],
        periodo_inicio: Optional[date],
        periodo_fim: Optional[date],
    ) -> list[dict]:
        page_size = 1000
        out: list[dict] = []
        start = 0
        while True:
            query = self._table("lead_campanhas").select("*").eq("org_id", str(org_id))
            if origem_id is not None:
                query = query.eq("origem_id", str(origem_id))
            if periodo_inicio is not None:
                query = query.gte("periodo_inicio", periodo_inicio.isoformat())
            if periodo_fim is not None:
                query = query.lte("periodo_fim", periodo_fim.isoformat())
            result = query.range(start, start + page_size - 1).execute()
            rows = result.data or []
            out.extend(rows)
            if len(rows) < page_size:
                break
            start += page_size
        return out

    def _count_leads_by_origem(
        self, org_id: UUID, periodo_inicio: Optional[date], periodo_fim: Optional[date]
    ) -> dict[str, int]:
        query = (
            self._table("leads")
            .select("origem_id")
            .eq("org_id", str(org_id))
            .not_.is_("origem_id", "null")
        )
        if periodo_inicio is not None:
            query = query.gte("data_entrada", periodo_inicio.isoformat())
        if periodo_fim is not None:
            query = query.lte("data_entrada", periodo_fim.isoformat())
        rows = _paginate(query)
        counts: dict[str, int] = {}
        for row in rows:
            oid = row.get("origem_id")
            if oid:
                counts[oid] = counts.get(oid, 0) + 1
        return counts

    def _aggregate_vendas_by_origem(
        self, org_id: UUID, periodo_inicio: Optional[date], periodo_fim: Optional[date]
    ) -> dict[str, tuple[int, float]]:
        query = self._table("lead_vendas").select("origem_id,valor").eq("org_id", str(org_id))
        if periodo_inicio is not None:
            query = query.gte("data_venda", periodo_inicio.isoformat())
        if periodo_fim is not None:
            query = query.lte("data_venda", periodo_fim.isoformat())
        rows = _paginate(query)
        agg: dict[str, tuple[int, float]] = {}
        for row in rows:
            oid = row.get("origem_id")
            if not oid:
                continue
            count, total = agg.get(oid, (0, 0.0))
            agg[oid] = (count + 1, total + float(row.get("valor") or 0))
        return agg

    def list_campanhas(
        self,
        org_id: UUID,
        *,
        origem_id: Optional[UUID] = None,
        periodo_inicio: Optional[date] = None,
        periodo_fim: Optional[date] = None,
    ) -> list[dict]:
        rows = self._fetch_campanhas_rows(org_id, origem_id, periodo_inicio, periodo_fim)
        labels = {s["id"]: s["label"] for s in self.list_origens(org_id)}
        rows = [
            {**_with_generated(r), "origem_label": labels.get(r["origem_id"], "")}
            for r in rows
        ]
        rows.sort(key=lambda r: r.get("periodo_inicio") or "", reverse=True)
        return rows

    def _get_campanha(self, org_id: UUID, campanha_id: UUID) -> Optional[dict]:
        resp = (
            self._table("lead_campanhas")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("id", str(campanha_id))
            .execute()
        )
        rows = list(resp.data or [])
        return rows[0] if rows else None

    def _find_duplicate(
        self,
        org_id: UUID,
        origem_id: UUID,
        periodo_inicio: date,
        periodo_fim: date,
        *,
        exclude_id: Optional[UUID] = None,
    ) -> Optional[dict]:
        resp = (
            self._table("lead_campanhas")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("origem_id", str(origem_id))
            .eq("periodo_inicio", periodo_inicio.isoformat())
            .eq("periodo_fim", periodo_fim.isoformat())
            .execute()
        )
        rows = list(resp.data or [])
        if exclude_id is not None:
            rows = [r for r in rows if r.get("id") != str(exclude_id)]
        return rows[0] if rows else None

    def _raise_conflict(self, dup: dict) -> None:
        exc = ConflictError(
            f"já existe um registro de investimento para esta origem "
            f"neste período (id={dup['id']})",
            resource="lead_campanhas",
        )
        exc.details["id"] = dup["id"]
        raise exc

    def create_campanha(
        self,
        org_id: UUID,
        *,
        origem_id: UUID,
        periodo_inicio: date,
        periodo_fim: date,
        investimento: float = 0,
        impressoes: Optional[int] = None,
        cliques: Optional[int] = None,
        leads: Optional[int] = None,
        visitas_perfil: Optional[int] = None,
        engajamento: Optional[int] = None,
        observacoes: Optional[str] = None,
    ) -> dict:
        if self._get_origem(org_id, origem_id) is None:
            raise NotFoundError("lead_sources", str(origem_id))
        _validate_period(periodo_inicio, periodo_fim)
        _validate_investimento(investimento)
        dup = self._find_duplicate(org_id, origem_id, periodo_inicio, periodo_fim)
        if dup is not None:
            self._raise_conflict(dup)

        row_id, created_at = _new_id_and_created_at()
        payload = {
            "id": row_id,
            "org_id": str(org_id),
            "origem_id": str(origem_id),
            "periodo_inicio": periodo_inicio.isoformat(),
            "periodo_fim": periodo_fim.isoformat(),
            "investimento": float(investimento),
            "impressoes": impressoes,
            "cliques": cliques,
            "leads": leads,
            "visitas_perfil": visitas_perfil,
            "engajamento": engajamento,
            "observacoes": observacoes,
            "created_at": created_at,
            "updated_at": None,
        }
        resp = self._table("lead_campanhas").insert(payload).execute()
        rows = list(resp.data or [])
        row = rows[0] if rows else payload
        origem = self._get_origem(org_id, origem_id)
        out = _with_generated(row)
        out["origem_label"] = origem["label"] if origem else ""
        return out

    def update_campanha(self, org_id: UUID, campanha_id: UUID, **patch: Any) -> dict:
        """``patch`` keys PRESENT mean the caller explicitly sent them
        (router calls with ``model_dump(exclude_unset=True)``) — mirrors
        ``dimensions_service.update_source``'s contract."""
        existing = self._get_campanha(org_id, campanha_id)
        if existing is None:
            raise NotFoundError("lead_campanhas", str(campanha_id))

        eff_origem_id = str(patch.get("origem_id", existing["origem_id"]))
        eff_periodo_inicio = patch.get("periodo_inicio", date.fromisoformat(existing["periodo_inicio"]))
        eff_periodo_fim = patch.get("periodo_fim", date.fromisoformat(existing["periodo_fim"]))
        eff_investimento = patch.get("investimento", existing["investimento"])

        if isinstance(eff_periodo_inicio, str):
            eff_periodo_inicio = date.fromisoformat(eff_periodo_inicio)
        if isinstance(eff_periodo_fim, str):
            eff_periodo_fim = date.fromisoformat(eff_periodo_fim)

        _validate_period(eff_periodo_inicio, eff_periodo_fim)
        _validate_investimento(eff_investimento)

        if "origem_id" in patch and self._get_origem(org_id, patch["origem_id"]) is None:
            raise NotFoundError("lead_sources", str(patch["origem_id"]))

        if {"origem_id", "periodo_inicio", "periodo_fim"} & patch.keys():
            dup = self._find_duplicate(
                org_id,
                UUID(eff_origem_id),
                eff_periodo_inicio,
                eff_periodo_fim,
                exclude_id=campanha_id,
            )
            if dup is not None:
                self._raise_conflict(dup)

        clean: dict[str, Any] = {}
        for key, value in patch.items():
            if key in ("origem_id",):
                clean[key] = str(value)
            elif key in ("periodo_inicio", "periodo_fim"):
                clean[key] = value.isoformat() if hasattr(value, "isoformat") else value
            elif key == "investimento":
                clean[key] = float(value)
            else:
                clean[key] = value

        if not clean:
            origem = self._get_origem(org_id, UUID(eff_origem_id))
            out = _with_generated(existing)
            out["origem_label"] = origem["label"] if origem else ""
            return out

        resp = (
            self._table("lead_campanhas")
            .update(clean)
            .eq("id", str(campanha_id))
            .execute()
        )
        rows = list(resp.data or [])
        row = rows[0] if rows else {**existing, **clean}
        origem = self._get_origem(org_id, UUID(eff_origem_id))
        out = _with_generated(row)
        out["origem_label"] = origem["label"] if origem else ""
        return out

    def delete_campanha(self, org_id: UUID, campanha_id: UUID) -> bool:
        existing = self._get_campanha(org_id, campanha_id)
        if existing is None:
            return False
        self._table("lead_campanhas").delete().eq("id", str(campanha_id)).execute()
        return True


_PAGE = 1000


def _paginate(query, *, page_size: int | None = None) -> list[dict]:
    """Drain a PostgREST query past its row cap.

    🔴 An unpaginated `.execute()` silently returns AT MOST 1 000 rows and
    reports success. On 2026-08-14 that made `/portal-roi` display **1 000
    leads instead of 13 255** — every per-portal count, and every CPL derived
    from one, was wrong, with no error anywhere. Same class as
    `imoveis_service.filter_options` (c5a34390) and the negociações repoint
    (98377d26); this file already paginated `_fetch_campanhas_rows` and
    `_select_all` while two sibling queries did not.

    Any query whose result set is not provably bounded below 1 000 goes
    through here.
    """
    page_size = page_size or _PAGE
    out: list[dict] = []
    start = 0
    while True:
        rows = query.range(start, start + page_size - 1).execute().data or []
        out.extend(rows)
        if len(rows) < page_size:
            return out
        start += page_size


def _cpl(investimento: Optional[float], total_leads: int) -> Optional[float]:
    """``None`` investimento -> ``None`` cpl (unrecorded). A real,
    possibly-zero investimento with leads > 0 -> a real, possibly-zero
    cpl — NOT the same claim as unrecorded. Mirrors migration `047`."""
    if investimento is None or total_leads <= 0:
        return None
    return investimento / total_leads


def _roi(investimento: Optional[float], valor_vendas: float) -> Optional[float]:
    """Division by zero is undefined whether that zero is "unrecorded"
    or "genuinely zero spend" — both collapse to ``None`` here, matching
    ``vw_portal_roi.roi`` (untouched by migration `047`, already
    correct)."""
    if not investimento:
        return None
    return valor_vendas / investimento


def _taxa_conversao(total_vendas: int, total_leads: int) -> Optional[float]:
    """A genuine 0% is reported as 0, matching ``total_vendas``'s own
    already-decided COALESCE-to-0 treatment. See migration `047`'s
    header for why this is a documented, accepted limitation rather than
    a NULLIF-guarded numerator: `lead_vendas` has no coverage marker
    (unlike `lead_campanhas`' periodo_inicio/periodo_fim), so zero rows
    cannot be told apart from "not tracked" at the SQL layer either way —
    guarding the numerator here would not resolve that ambiguity, only
    hide a genuine zero-conversion fact behind "não informado"."""
    if total_leads <= 0:
        return None
    return total_vendas / total_leads


def build_portal_roi_service(client: Any) -> PortalRoiService:
    return PortalRoiService(client)
