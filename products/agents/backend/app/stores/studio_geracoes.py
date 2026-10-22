"""Store of the AI draft generation runs (049): ``agents.geracoes`` + ``agents.geracao_areas``.

One run per agent in flight (``pendente|executando``; the partial unique index maps to
``StudioConflict('geracao_em_andamento')``), one area row per requested area. Status writes are CONDITIONAL
(``only_if_status``): a cancelled run is never flipped back to ``concluida`` by a worker that finished late.
Fake and Real share the validation; the Real goes through :func:`app.stores._db_errors.exec_query`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

__all__ = [
    "AREAS",
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "LIMITE_USD_MAX",
    "GeracaoRecord",
    "GeracaoAreaRecord",
    "GeracaoStore",
    "FakeGeracaoStore",
    "SupabaseGeracaoStore",
    "get_geracao_store",
]

_SCHEMA = "agents"
AREAS = ("secoes", "textos", "ferramentas", "decisoes", "specs", "skills", "configuracoes")
ACTIVE_STATUSES = ("pendente", "executando")
TERMINAL_STATUSES = ("concluida", "parcial", "falhou", "cancelada")
LIMITE_USD_MAX = 5.0
_GERACAO_FIELDS = frozenset({
    "status", "versao_gerador", "plano", "custo_usd", "erro", "aprendizado", "iniciado_em", "concluido_em", "forcar",
})
_AREA_FIELDS = frozenset({
    "status", "erro", "custo_usd", "tokens_entrada", "tokens_saida", "saida", "itens", "lacunas", "concluido_em",
})


@dataclass(frozen=True)
class GeracaoRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    status: str
    briefing: dict[str, Any]
    areas_solicitadas: tuple[str, ...]
    forcar: bool
    versao_gerador: int | None
    modelo: str
    provider: str
    plano: dict[str, Any] | None
    custo_usd: float
    limite_usd: float
    erro: str | None
    aprendizado: dict[str, Any] | None
    criado_por: UUID
    iniciado_em: datetime | None
    concluido_em: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class GeracaoAreaRecord:
    id: UUID
    org_id: UUID
    geracao_id: UUID
    area: str
    status: str
    erro: str | None = None
    custo_usd: float = 0.0
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    #: The raw (validated) model output of the area.
    saida: dict[str, Any] | None = None
    #: ``[{"chave": str, "hash": str}]`` -- what the area wrote, hashed at write time (the "gerado vs editado" base).
    itens: list[dict[str, str]] = field(default_factory=list)
    lacunas: list[str] = field(default_factory=list)
    concluido_em: datetime | None = None


class GeracaoStore(Protocol):
    def create_geracao(
        self, org_id: UUID, agent_id: UUID, *, briefing: dict[str, Any], areas: list[str], forcar: bool,
        modelo: str, provider: str, limite_usd: float, versao_gerador: int | None, criado_por: UUID,
    ) -> GeracaoRecord:
        """The run (``pendente``) + one ``pendente`` row per area. ``StudioConflict('geracao_em_andamento')`` when the
        agent already has a ``pendente|executando`` run; ``ValueError`` for a bad area / a cap above US$ 5."""
        ...
    def get_geracao(self, org_id: UUID, geracao_id: UUID) -> GeracaoRecord: ...
    def list_geracoes(self, org_id: UUID, agent_id: UUID, limit: int = 20) -> list[GeracaoRecord]:
        """Newest first."""
        ...
    def list_areas(self, org_id: UUID, geracao_id: UUID) -> list[GeracaoAreaRecord]:
        """In :data:`AREAS` order."""
        ...
    def update_geracao(
        self, org_id: UUID, geracao_id: UUID, fields: dict[str, Any], *, only_if_status: tuple[str, ...] | None = None,
    ) -> GeracaoRecord | None:
        """``None`` when ``only_if_status`` is given and the run is in another status (nothing written)."""
        ...
    def update_area(
        self, org_id: UUID, geracao_id: UUID, area: str, fields: dict[str, Any], *,
        only_if_status: tuple[str, ...] | None = None,
    ) -> GeracaoAreaRecord | None: ...
    def list_sem_aprendizado(self, org_id: UUID, agent_id: UUID) -> list[GeracaoRecord]:
        """Finished (``concluida|parcial``) runs whose ``aprendizado`` is still NULL, oldest first."""
        ...
    def fail_orphans(self, *, erro: str) -> int:
        """Startup sweep: every run still ``pendente|executando`` -> ``falhou`` (its worker died with the previous
        process); its unfinished areas -> ``falhou`` with the same ``erro``. Returns the number of runs."""
        ...


def _check_create(areas: list[str], limite_usd: float) -> None:
    if not areas or len(set(areas)) != len(areas):
        raise ValueError("areas must be a non-empty list without repeats")
    bad = [a for a in areas if a not in AREAS]
    if bad:
        raise ValueError(f"unknown areas: {bad}")
    if not (0 < limite_usd <= LIMITE_USD_MAX):
        raise ValueError(f"limite_usd must be in (0, {LIMITE_USD_MAX}]")


def _check_fields(fields: dict[str, Any], allowed: frozenset[str], what: str) -> None:
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown {what} fields: {sorted(unknown)}")


def _ordered(areas: list[GeracaoAreaRecord]) -> list[GeracaoAreaRecord]:
    return sorted(areas, key=lambda a: AREAS.index(a.area))


class FakeGeracaoStore:
    def __init__(self) -> None:
        self._geracoes: dict[UUID, GeracaoRecord] = {}
        self._areas: dict[tuple[UUID, str], GeracaoAreaRecord] = {}

    def create_geracao(
        self, org_id, agent_id, *, briefing, areas, forcar, modelo, provider, limite_usd, versao_gerador, criado_por,
    ):
        _check_create(areas, limite_usd)
        if any(g.agent_id == agent_id and g.status in ACTIVE_STATUSES for g in self._geracoes.values()):
            raise StudioConflict("geracao_em_andamento", "the agent already has a generation in flight")
        now = utcnow()
        rec = GeracaoRecord(
            id=uuid4(), org_id=org_id, agent_id=agent_id, status="pendente", briefing=dict(briefing),
            areas_solicitadas=tuple(areas), forcar=forcar, versao_gerador=versao_gerador, modelo=modelo,
            provider=provider, plano=None, custo_usd=0.0, limite_usd=float(limite_usd), erro=None,
            aprendizado=None, criado_por=criado_por, iniciado_em=None, concluido_em=None, created_at=now,
            updated_at=now,
        )
        self._geracoes[rec.id] = rec
        for a in areas:
            self._areas[(rec.id, a)] = GeracaoAreaRecord(id=uuid4(), org_id=org_id, geracao_id=rec.id, area=a, status="pendente")
        return rec

    def get_geracao(self, org_id, geracao_id):
        rec = self._geracoes.get(geracao_id)
        if rec is None or rec.org_id != org_id:
            raise NotFound(f"geracao {geracao_id} not found")
        return rec

    def list_geracoes(self, org_id, agent_id, limit=20):
        rows = [g for g in self._geracoes.values() if g.org_id == org_id and g.agent_id == agent_id]
        return sorted(rows, key=lambda g: g.created_at, reverse=True)[:limit]

    def list_areas(self, org_id, geracao_id):
        self.get_geracao(org_id, geracao_id)
        return _ordered([a for (gid, _), a in self._areas.items() if gid == geracao_id])

    def update_geracao(self, org_id, geracao_id, fields, *, only_if_status=None):
        _check_fields(fields, _GERACAO_FIELDS, "geracao")
        rec = self.get_geracao(org_id, geracao_id)
        if only_if_status is not None and rec.status not in only_if_status:
            return None
        novo = fields.get("status", rec.status)
        if novo in ACTIVE_STATUSES and any(
            g.agent_id == rec.agent_id and g.id != rec.id and g.status in ACTIVE_STATUSES
            for g in self._geracoes.values()
        ):
            raise StudioConflict("geracao_em_andamento", "the agent already has a generation in flight")
        rec = replace(rec, **fields, updated_at=utcnow())
        self._geracoes[geracao_id] = rec
        return rec

    def update_area(self, org_id, geracao_id, area, fields, *, only_if_status=None):
        _check_fields(fields, _AREA_FIELDS, "geracao_area")
        self.get_geracao(org_id, geracao_id)
        cur = self._areas.get((geracao_id, area))
        if cur is None:
            raise NotFound(f"area {area!r} of geracao {geracao_id} not found")
        if only_if_status is not None and cur.status not in only_if_status:
            return None
        rec = replace(cur, **fields)
        self._areas[(geracao_id, area)] = rec
        return rec

    def list_sem_aprendizado(self, org_id, agent_id):
        rows = [
            g for g in self._geracoes.values()
            if g.org_id == org_id and g.agent_id == agent_id and g.status in ("concluida", "parcial")
            and g.aprendizado is None
        ]
        return sorted(rows, key=lambda g: g.created_at)

    def fail_orphans(self, *, erro):
        n = 0
        for gid, g in list(self._geracoes.items()):
            if g.status not in ACTIVE_STATUSES:
                continue
            now = utcnow()
            self._geracoes[gid] = replace(g, status="falhou", erro=erro, concluido_em=now, updated_at=now)
            for (agid, area), a in list(self._areas.items()):
                if agid == gid and a.status in ("pendente", "executando"):
                    self._areas[(agid, area)] = replace(a, status="falhou", erro=erro, concluido_em=now)
            n += 1
        return n


def _float(v: Any) -> float:
    return float(Decimal(str(v)))


class SupabaseGeracaoStore:
    """Real :class:`GeracaoStore`. Bare table names through ``client.schema("agents")``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    @staticmethod
    def _geracao(r: dict[str, Any]) -> GeracaoRecord:
        return GeracaoRecord(
            id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), agent_id=UUID(str(r["agent_id"])),
            status=r["status"], briefing=dict(r["briefing"]), areas_solicitadas=tuple(r["areas_solicitadas"]),
            forcar=bool(r.get("forcar")), versao_gerador=r.get("versao_gerador"), modelo=r["modelo"],
            provider=r["provider"], plano=r.get("plano"), custo_usd=_float(r.get("custo_usd") or 0),
            limite_usd=_float(r["limite_usd"]), erro=r.get("erro"), aprendizado=r.get("aprendizado"),
            criado_por=UUID(str(r["criado_por"])), iniciado_em=r.get("iniciado_em"),
            concluido_em=r.get("concluido_em"), created_at=r["created_at"], updated_at=r["updated_at"],
        )

    @staticmethod
    def _area(r: dict[str, Any]) -> GeracaoAreaRecord:
        return GeracaoAreaRecord(
            id=UUID(str(r["id"])), org_id=UUID(str(r["org_id"])), geracao_id=UUID(str(r["geracao_id"])),
            area=r["area"], status=r["status"], erro=r.get("erro"), custo_usd=_float(r.get("custo_usd") or 0),
            tokens_entrada=r.get("tokens_entrada"), tokens_saida=r.get("tokens_saida"), saida=r.get("saida"),
            itens=list(r.get("itens") or []), lacunas=list(r.get("lacunas") or []), concluido_em=r.get("concluido_em"),
        )

    def create_geracao(
        self, org_id, agent_id, *, briefing, areas, forcar, modelo, provider, limite_usd, versao_gerador, criado_por,
    ):
        _check_create(areas, limite_usd)
        resp = exec_query(self._t("geracoes").insert({
            "org_id": str(org_id), "agent_id": str(agent_id), "status": "pendente", "briefing": briefing,
            "areas_solicitadas": list(areas), "forcar": forcar, "versao_gerador": versao_gerador, "modelo": modelo,
            "provider": provider, "limite_usd": float(limite_usd), "criado_por": str(criado_por),
        }), unique_code="geracao_em_andamento")
        rec = self._geracao(resp.data[0])
        exec_query(self._t("geracao_areas").insert([
            {"org_id": str(org_id), "geracao_id": str(rec.id), "area": a, "status": "pendente"} for a in areas
        ]))
        return rec

    def get_geracao(self, org_id, geracao_id):
        resp = self._t("geracoes").select("*").eq("org_id", str(org_id)).eq("id", str(geracao_id)).execute()
        if not resp.data:
            raise NotFound(f"geracao {geracao_id} not found")
        return self._geracao(resp.data[0])

    def list_geracoes(self, org_id, agent_id, limit=20):
        resp = (
            self._t("geracoes").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            .order("created_at", desc=True).limit(limit).execute()
        )
        return [self._geracao(r) for r in resp.data or []]

    def list_areas(self, org_id, geracao_id):
        resp = (
            self._t("geracao_areas").select("*").eq("org_id", str(org_id)).eq("geracao_id", str(geracao_id)).execute()
        )  # postgrest-unbounded-ok: at most len(AREAS)=7 rows per run (UNIQUE geracao_id, area)
        return _ordered([self._area(r) for r in resp.data or []])

    def update_geracao(self, org_id, geracao_id, fields, *, only_if_status=None):
        _check_fields(fields, _GERACAO_FIELDS, "geracao")
        q = self._t("geracoes").update(_jsonable(fields)).eq("org_id", str(org_id)).eq("id", str(geracao_id))
        if only_if_status is not None:
            q = q.in_("status", list(only_if_status))
        rows = exec_query(q, unique_code="geracao_em_andamento").data or []
        if rows:
            return self._geracao(rows[0])
        self.get_geracao(org_id, geracao_id)  # NotFound for an unknown id
        return None

    def update_area(self, org_id, geracao_id, area, fields, *, only_if_status=None):
        _check_fields(fields, _AREA_FIELDS, "geracao_area")
        q = (
            self._t("geracao_areas").update(_jsonable(fields)).eq("org_id", str(org_id))
            .eq("geracao_id", str(geracao_id)).eq("area", area)
        )
        if only_if_status is not None:
            q = q.in_("status", list(only_if_status))
        rows = exec_query(q).data or []
        if rows:
            return self._area(rows[0])
        if not any(a.area == area for a in self.list_areas(org_id, geracao_id)):
            raise NotFound(f"area {area!r} of geracao {geracao_id} not found")
        return None

    def list_sem_aprendizado(self, org_id, agent_id):
        resp = (
            self._t("geracoes").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            .in_("status", ["concluida", "parcial"]).is_("aprendizado", "null").order("created_at").limit(50).execute()
        )
        return [self._geracao(r) for r in resp.data or []]

    def fail_orphans(self, *, erro):
        now = utcnow_iso()
        runs = exec_query(
            self._t("geracoes").update({"status": "falhou", "erro": erro, "concluido_em": now})
            .in_("status", list(ACTIVE_STATUSES))
        ).data or []
        for r in runs:
            exec_query(
                self._t("geracao_areas").update({"status": "falhou", "erro": erro, "concluido_em": now})
                .eq("geracao_id", r["id"]).in_("status", ["pendente", "executando"])
            )
        return len(runs)


def _jsonable(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items()}


def get_geracao_store(settings: Any) -> GeracaoStore:
    """Real when a Supabase service-role key is configured, Fake otherwise (the product-wide factory signal)."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeGeracaoStore()
    from app.database import get_admin_client

    return SupabaseGeracaoStore(get_admin_client())
