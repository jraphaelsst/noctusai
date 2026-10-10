"""``public.transcricoes_api`` access — Protocol + Fake + Supabase.

Sync (core's convention: routers talk to the service-role client directly).
Callers never reach PostgREST; every path here is service-role and every
caller-facing read is scoped by ``(caller_kind, caller_id)``.

Row dicts use the migration's column names verbatim. Timestamps are ISO
strings on the wire (Supabase) and parsed with :func:`parse_ts`.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Protocol

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

TABLE = "transcricoes_api"
RESERVE_RPC = "reservar_transcricao_api"

ACTIVE = ("na_fila", "processando")
TERMINAL = ("concluida", "falhou", "cancelada")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class TranscricaoRepo(Protocol):
    def reservar(self, *, caller_kind: str, caller_id: str, org_id: str, duracao_s: float) -> dict:
        """The atomic quota RPC. ``{"ok": True, "id"}`` or
        ``{"ok": False, "codigo", "retry_after_s"}``."""

    def get(self, transcricao_id: str) -> Optional[dict]: ...

    def get_for_caller(self, transcricao_id: str, caller_kind: str, caller_id: str) -> Optional[dict]: ...

    def list_for_caller(
        self, caller_kind: str, caller_id: str, *, status: Optional[str], limit: int,
        before: Optional[datetime],
    ) -> list[dict]:
        """Newest first, ``criado_em < before`` when given, at most ``limit``."""

    def update(self, transcricao_id: str, fields: dict) -> None:
        """Unconditional field update (no status guard)."""

    def transition(
        self, transcricao_id: str, *, from_status: Iterable[str], fields: dict
    ) -> bool:
        """Update ONLY if the row is currently in ``from_status``. ``True``
        when it applied — the compare-and-set every status change goes through."""

    def refund(self, transcricao_id: str) -> bool:
        """Set ``minutos_reembolsados``; ``True`` only the first time."""

    def fila_a_frente(self, transcricao_id: str) -> tuple[int, float]:
        """``(jobs ahead, their summed duracao_s)`` — queued older than this
        row plus everything processing."""

    def audio_para_apagar(self, *, before: datetime, limit: int) -> list[dict]:
        """``falhou``/``cancelada`` rows with audio still stored whose terminal
        time (``concluido_em`` else ``criado_em``) is older than ``before``."""

    def textos_expirados(self, *, now: datetime, limit: int) -> list[dict]:
        """``concluida`` rows with ``expira_em <= now`` and text still present."""

    def ativos_antigos(self, *, criado_antes: datetime, limit: int) -> list[dict]:
        """Active rows created before ``criado_antes`` (candidates for the
        stuck-job sweep; the precise per-row deadline is applied by the caller)."""

    def estatisticas(self, *, since: datetime) -> dict:
        """``{"fila", "processando", "minutos_global", "minutos_por_org": {org: min}}``
        over rows created since ``since``, refunded rows excluded from minutes."""


# ---------------------------------------------------------------------------
# Supabase (Real)
# ---------------------------------------------------------------------------


class SupabaseTranscricaoRepo:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self):
        return self._client.table(TABLE)

    def reservar(self, *, caller_kind, caller_id, org_id, duracao_s) -> dict:
        res = self._client.rpc(
            RESERVE_RPC,
            {
                "p_caller_kind": caller_kind,
                "p_caller_id": str(caller_id),
                "p_org_id": str(org_id),
                "p_duracao_s": duracao_s,
            },
        ).execute()
        data = res.data
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise RuntimeError("reservar_transcricao_api returned no result")
        return data

    def get(self, transcricao_id):
        rows = self._t().select("*").eq("id", str(transcricao_id)).limit(1).execute().data or []
        return rows[0] if rows else None

    def get_for_caller(self, transcricao_id, caller_kind, caller_id):
        rows = (
            self._t().select("*").eq("id", str(transcricao_id))
            .eq("caller_kind", caller_kind).eq("caller_id", str(caller_id))
            .limit(1).execute().data or []
        )
        return rows[0] if rows else None

    def list_for_caller(self, caller_kind, caller_id, *, status, limit, before):
        q = (
            self._t().select("*")
            .eq("caller_kind", caller_kind).eq("caller_id", str(caller_id))
        )
        if status:
            q = q.eq("status", status)
        if before is not None:
            q = q.lt("criado_em", iso(before))
        return q.order("criado_em", desc=True).limit(limit).execute().data or []

    def update(self, transcricao_id, fields):
        self._t().update(fields).eq("id", str(transcricao_id)).execute()

    def transition(self, transcricao_id, *, from_status, fields) -> bool:
        res = (
            self._t().update(fields).eq("id", str(transcricao_id))
            .in_("status", list(from_status)).execute()
        )
        return bool(res.data)

    def refund(self, transcricao_id) -> bool:
        res = (
            self._t().update({"minutos_reembolsados": True})
            .eq("id", str(transcricao_id)).eq("minutos_reembolsados", False).execute()
        )
        return bool(res.data)

    def fila_a_frente(self, transcricao_id):
        row = self.get(transcricao_id)
        if row is None:
            return 0, 0.0
        ahead = 0
        total = 0.0
        for r in iter_paged_rows(
            lambda a, b: self._t().select("id, duracao_s, status, criado_em")
            .in_("status", list(ACTIVE)).lte("criado_em", row["criado_em"])
            .order("id").range(a, b).execute().data,
            label="transcricoes_api fila",
        ):
            if r["id"] == row["id"]:
                continue
            ahead += 1
            total += float(r.get("duracao_s") or 0)
        return ahead, total

    def audio_para_apagar(self, *, before, limit):
        rows = (
            self._t().select("*").in_("status", ["falhou", "cancelada"])
            .is_("audio_apagado_em", "null").not_.is_("storage_path", "null")
            .lt("criado_em", iso(before)).order("criado_em").limit(limit).execute().data or []
        )
        out = []
        for r in rows:
            ref = parse_ts(r.get("concluido_em")) or parse_ts(r.get("criado_em"))
            if ref is not None and ref < before:
                out.append(r)
        return out

    def textos_expirados(self, *, now, limit):
        return (
            self._t().select("*").eq("status", "concluida")
            .lte("expira_em", iso(now)).not_.is_("texto", "null")
            .order("expira_em").limit(limit).execute().data or []
        )

    def ativos_antigos(self, *, criado_antes, limit):
        return (
            self._t().select("*").in_("status", list(ACTIVE))
            .lt("criado_em", iso(criado_antes)).order("criado_em").limit(limit).execute().data or []
        )

    def estatisticas(self, *, since):
        fila = proc = 0
        minutos = 0.0
        por_org: dict[str, float] = {}
        for r in iter_paged_rows(
            lambda a, b: self._t().select("id, org_id, status, duracao_s, minutos_reembolsados")
            .gte("criado_em", iso(since)).order("id").range(a, b).execute().data,
            label="transcricoes_api stats",
        ):
            if r["status"] == "na_fila":
                fila += 1
            elif r["status"] == "processando":
                proc += 1
            if not r.get("minutos_reembolsados"):
                m = float(r.get("duracao_s") or 0) / 60.0
                minutos += m
                por_org[r["org_id"]] = por_org.get(r["org_id"], 0.0) + m
        return {"fila": fila, "processando": proc, "minutos_global": minutos, "minutos_por_org": por_org}


# ---------------------------------------------------------------------------
# Fake (in-memory) — same semantics as the Real, quota RPC scriptable
# ---------------------------------------------------------------------------


class FakeTranscricaoRepo:
    """Deterministic in-memory repo. ``reservar`` accepts by default (inserting
    the ``na_fila`` row exactly as the RPC does) unless ``script_reservar``
    holds a queued refusal — the real quota arithmetic lives in SQL and is
    covered by the migration's own tests, so the fake only scripts outcomes."""

    def __init__(self, *, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock
        self.rows: dict[str, dict] = {}
        self.script_reservar: list[dict] = []
        self.reservas: list[dict] = []

    def reservar(self, *, caller_kind, caller_id, org_id, duracao_s) -> dict:
        self.reservas.append(
            {"caller_kind": caller_kind, "caller_id": str(caller_id), "org_id": str(org_id), "duracao_s": duracao_s}
        )
        if self.script_reservar:
            return dict(self.script_reservar.pop(0))
        tid = str(uuid.uuid4())
        self.rows[tid] = {
            "id": tid, "org_id": str(org_id), "caller_kind": caller_kind, "caller_id": str(caller_id),
            "rotulo": None, "idioma": "pt", "storage_path": None, "bytes": None,
            "duracao_s": duracao_s, "formato": None, "status": "na_fila", "texto": None,
            "segmentos": None, "erro_codigo": None, "modelo": None, "rtf": None,
            "criado_em": iso(self._clock()), "iniciado_em": None, "concluido_em": None,
            "expira_em": None, "audio_apagado_em": None, "minutos_reembolsados": False,
        }
        return {"ok": True, "id": tid}

    def _copy(self, row):
        return copy.deepcopy(row) if row is not None else None

    def get(self, transcricao_id):
        return self._copy(self.rows.get(str(transcricao_id)))

    def get_for_caller(self, transcricao_id, caller_kind, caller_id):
        r = self.rows.get(str(transcricao_id))
        if r and r["caller_kind"] == caller_kind and r["caller_id"] == str(caller_id):
            return self._copy(r)
        return None

    def list_for_caller(self, caller_kind, caller_id, *, status, limit, before):
        rs = [
            r for r in self.rows.values()
            if r["caller_kind"] == caller_kind and r["caller_id"] == str(caller_id)
            and (not status or r["status"] == status)
            and (before is None or parse_ts(r["criado_em"]) < before)
        ]
        rs.sort(key=lambda r: parse_ts(r["criado_em"]), reverse=True)
        return [self._copy(r) for r in rs[:limit]]

    def update(self, transcricao_id, fields):
        self.rows[str(transcricao_id)].update(copy.deepcopy(fields))

    def transition(self, transcricao_id, *, from_status, fields) -> bool:
        r = self.rows.get(str(transcricao_id))
        if r is None or r["status"] not in tuple(from_status):
            return False
        r.update(copy.deepcopy(fields))
        return True

    def refund(self, transcricao_id) -> bool:
        r = self.rows.get(str(transcricao_id))
        if r is None or r["minutos_reembolsados"]:
            return False
        r["minutos_reembolsados"] = True
        return True

    def fila_a_frente(self, transcricao_id):
        me = self.rows.get(str(transcricao_id))
        if me is None:
            return 0, 0.0
        ahead = [
            r for r in self.rows.values()
            if r["id"] != me["id"] and r["status"] in ACTIVE
            and parse_ts(r["criado_em"]) <= parse_ts(me["criado_em"])
        ]
        return len(ahead), sum(float(r["duracao_s"]) for r in ahead)

    def audio_para_apagar(self, *, before, limit):
        out = []
        for r in self.rows.values():
            if r["status"] not in ("falhou", "cancelada") or r["audio_apagado_em"] or not r["storage_path"]:
                continue
            ref = parse_ts(r["concluido_em"]) or parse_ts(r["criado_em"])
            if ref < before:
                out.append(self._copy(r))
        return out[:limit]

    def textos_expirados(self, *, now, limit):
        out = [
            self._copy(r) for r in self.rows.values()
            if r["status"] == "concluida" and r["texto"] is not None
            and r["expira_em"] and parse_ts(r["expira_em"]) <= now
        ]
        return out[:limit]

    def ativos_antigos(self, *, criado_antes, limit):
        out = [
            self._copy(r) for r in self.rows.values()
            if r["status"] in ACTIVE and parse_ts(r["criado_em"]) < criado_antes
        ]
        return out[:limit]

    def estatisticas(self, *, since):
        fila = proc = 0
        minutos = 0.0
        por_org: dict[str, float] = {}
        for r in self.rows.values():
            if parse_ts(r["criado_em"]) < since:
                continue
            fila += r["status"] == "na_fila"
            proc += r["status"] == "processando"
            if not r["minutos_reembolsados"]:
                m = float(r["duracao_s"]) / 60.0
                minutos += m
                por_org[r["org_id"]] = por_org.get(r["org_id"], 0.0) + m
        return {"fila": fila, "processando": proc, "minutos_global": minutos, "minutos_por_org": por_org}


__all__ = [
    "ACTIVE", "TERMINAL", "FakeTranscricaoRepo", "SupabaseTranscricaoRepo",
    "TranscricaoRepo", "iso", "parse_ts", "utcnow",
]
