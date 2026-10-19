"""Maya supervision -- config writes, scorecard computation, read models (maya-blocks CONTRACT §3/§4).

The block list, the effective block configuration, the ONE `supervisao_config` reader and the handoff status
machine (`handoffs.varrer`, scheduled by `scheduler.py`) live in `app.modules.atendimento_blocos`; this module
owns the config WRITE. Writes ONLY to `supervisao_config` and `agente_scorecards`. It never writes to leads,
cards, chats, and never
sends anything to a lead (CONTRACT §5). `client` is the schema-scoped service-role client; every query is
org-filtered explicitly.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.modules.atendimento_blocos import repository as blocos_repo
from app.modules.atendimento_blocos.blocos import NOMES_BLOCOS
from app.modules.supervisao import metricas as m

logger = logging.getLogger(__name__)

T_CONFIG = blocos_repo.T_SUPERVISAO
T_SCORECARDS = "agente_scorecards"
T_HANDOFFS = "atendimento_handoffs"

STATUS_HANDOFF = ("emitido", "assumido", "expirado")
DIAS_RECALCULADOS = 7
LIMITE_PADRAO = 50
LOTE_IN = 100


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _paginado(build: Any, label: str, id_key: str = "id") -> list[dict[str, Any]]:
    def fetch(start: int, end: int) -> Any:
        return build().order(id_key).range(start, end).execute().data

    return list(iter_paged_rows(fetch, label=label, id_key=id_key))


def _lotes(valores: Iterable[str]) -> Iterable[list[str]]:
    lista = sorted({v for v in valores if v})
    for i in range(0, len(lista), LOTE_IN):
        yield lista[i:i + LOTE_IN]


# ── config ──────────────────────────────────────────────────────────────────
def salvar_config(client: Any, org_id: Any, *, supervisao_ativa: bool, horas_para_assumir: int, por: Any) -> dict[str, Any]:
    if not 1 <= int(horas_para_assumir) <= 168:
        raise AppException("VALIDATION_ERROR", "horas_para_assumir deve estar entre 1 e 168.", status_code=422)
    client.table(T_CONFIG).upsert({
        "org_id": str(org_id), "supervisao_ativa": bool(supervisao_ativa), "horas_para_assumir": int(horas_para_assumir),
        "updated_by": str(por) if por else None, "updated_at": m.iso(agora_utc()),
    }, on_conflict="org_id").execute()
    return blocos_repo.ler_supervisao(client, org_id)


def supervisionado_desde(config: dict[str, Any]) -> Optional[datetime]:
    """Earliest moment handoffs are known to have been recorded. 286 has no activation timestamp, so the last
    config save is the conservative anchor (a later edit only makes it LATER: fewer days scored, never a
    fabricated 0)."""
    if not config["supervisao_ativa"]:
        return None
    return m.parse_ts(config.get("updated_at"))


def orgs_supervisionadas(client: Any) -> list[str]:
    rows = _paginado(lambda: client.table(T_CONFIG).select("org_id").eq("supervisao_ativa", True),
                     "supervisao orgs", id_key="org_id")
    return sorted({str(r["org_id"]) for r in rows})


def blocos_ativos(client: Any, org_id: Any) -> list[tuple[str, Optional[str]]]:
    """`[(bloco, agent_key)]` of the org's `ativo` blocks, in `ordem` -- over the effective configuration
    (an absent row is the code default, which is never `ativo`)."""
    efetiva = blocos_repo.configuracao_efetiva(client, org_id)
    return [(b, efetiva[b].agent_key) for b in NOMES_BLOCOS if efetiva[b].ativo]


# ── scorecards (nightly) ────────────────────────────────────────────────────
def computar_scorecards(client: Any, org_id: Any, *, agora: datetime, dias: int = DIAS_RECALCULADOS) -> list[dict[str, Any]]:
    """Upsert one scorecard per (ativo block, day) for the last `dias` SP days up to yesterday. Idempotent:
    recomputing a day overwrites its row (UNIQUE NULLS NOT DISTINCT org/bloco/agent_key/dia)."""
    config = blocos_repo.ler_supervisao(client, org_id)
    if not config["supervisao_ativa"]:
        return []
    desde = supervisionado_desde(config)
    ontem = m.hoje_sp(agora) - timedelta(days=1)
    escritos: list[dict[str, Any]] = []
    for bloco, agent_key in blocos_ativos(client, org_id):
        for k in range(dias - 1, -1, -1):
            dia = ontem - timedelta(days=k)
            try:
                metricas = m.calcular(client, org_id, bloco, dia, horas_para_assumir=config["horas_para_assumir"],
                                      calculado_at=agora, supervisionado_desde=desde)
            except Exception:
                logger.exception("supervisao: scorecard NOT computed (org=%s bloco=%s dia=%s) -- left missing",
                                 org_id, bloco, dia)
                continue
            row = {"org_id": str(org_id), "bloco": bloco, "agent_key": agent_key, "dia": dia.isoformat(),
                   "metricas": metricas, "rubrica_versao": m.rubrica(bloco), "calculado_at": m.iso(agora)}
            client.table(T_SCORECARDS).upsert(row, on_conflict="org_id,bloco,agent_key,dia").execute()
            escritos.append(row)
    return escritos


def listar_scorecards(client: Any, org_id: Any, dia: date) -> list[dict[str, Any]]:
    rows = (client.table(T_SCORECARDS).select("bloco,agent_key,rubrica_versao,calculado_at,metricas,dia")
            .eq("org_id", str(org_id)).eq("dia", dia.isoformat()).limit(100).execute().data or [])
    ordem = {b: i for i, b in enumerate(NOMES_BLOCOS)}
    rows.sort(key=lambda r: (ordem.get(r.get("bloco"), 99), str(r.get("agent_key") or "")))
    return [{"bloco": r["bloco"], "agent_key": r.get("agent_key"), "rubrica_versao": r["rubrica_versao"],
             "calculado_at": r.get("calculado_at"), "metricas": r.get("metricas") or {}} for r in rows]


def parse_dia(valor: Optional[str], *, agora: datetime) -> date:
    """CONTRACT §4.3: default yesterday (SP); 422 `dia_invalido` / `dia_futuro` (>= today SP)."""
    hoje = m.hoje_sp(agora)
    if valor is None:
        return hoje - timedelta(days=1)
    try:
        dia = date.fromisoformat(valor)
    except ValueError:
        raise AppException("dia_invalido", "Use dia=YYYY-MM-DD.", status_code=422) from None
    if dia >= hoje:
        raise AppException("dia_futuro", "O dia ainda não terminou: escolha um dia anterior a hoje.", status_code=422)
    return dia


# ── handoffs read model (GET /api/supervisao/handoffs) ──────────────────────
def _filtro_invalido(msg: str) -> AppException:
    return AppException("filtro_invalido", msg, status_code=422)


def _cursor_encode(row: dict[str, Any]) -> str:
    raw = json.dumps({"c": row["created_at"], "i": str(row["id"])}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _cursor_decode(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        obj = json.loads(raw)
        ts = m.parse_ts(obj["c"])
        if ts is None:
            raise ValueError("cursor sem data")
        return ts, str(obj["i"])
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise _filtro_invalido("cursor inválido.") from None


def listar_handoffs(client: Any, org_id: Any, *, agora: datetime, status: Optional[str] = None,
                    de_bloco: Optional[str] = None, para_bloco: Optional[str] = None, desde: Optional[str] = None,
                    ate: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> dict[str, Any]:
    if status is not None and status not in STATUS_HANDOFF:
        raise _filtro_invalido("status inválido.")
    for b in (de_bloco, para_bloco):
        if b is not None and b not in NOMES_BLOCOS:
            raise _filtro_invalido("bloco inválido.")
    limite = LIMITE_PADRAO if limit is None else limit
    if not 1 <= limite <= 100:
        raise _filtro_invalido("limit deve estar entre 1 e 100.")
    hoje = m.hoje_sp(agora)
    try:
        d_ate = date.fromisoformat(ate) if ate else hoje
        d_desde = date.fromisoformat(desde) if desde else d_ate - timedelta(days=6)
    except ValueError:
        raise _filtro_invalido("Use datas YYYY-MM-DD.") from None
    if d_desde > d_ate:
        raise _filtro_invalido("`desde` não pode ser depois de `ate`.")
    pos = _cursor_decode(cursor) if cursor else None

    config = blocos_repo.ler_supervisao(client, org_id)
    if not config["supervisao_ativa"]:
        return {"itens": [], "proximo_cursor": None}
    inicio, _ = m.janela(d_desde)
    _, fim = m.janela(d_ate)

    def build() -> Any:
        q = (client.table(T_HANDOFFS).select("*").eq("org_id", str(org_id))
             .gte("created_at", m.iso(inicio)).lt("created_at", m.iso(fim)))
        if status:
            q = q.eq("status", status)
        if de_bloco:
            q = q.eq("de_bloco", de_bloco)
        if para_bloco:
            q = q.eq("para_bloco", para_bloco)
        return q

    rows = [r for r in _paginado(build, "supervisao handoffs")
            if (t := m.parse_ts(r.get("created_at"))) is not None and inicio <= t < fim]
    rows.sort(key=lambda r: (m.parse_ts(r["created_at"]), str(r["id"])), reverse=True)
    if pos is not None:
        rows = [r for r in rows if (m.parse_ts(r["created_at"]), str(r["id"])) < pos]
    pagina, resto = rows[:limite], rows[limite:]

    titulos: dict[str, Any] = {}
    for lote in _lotes(str(r["atendimento_id"]) for r in pagina if r.get("atendimento_id")):
        for a in (client.table("atendimentos").select("id,titulo").eq("org_id", str(org_id)).in_("id", lote)
                  .execute().data or []):
            titulos[str(a["id"])] = a.get("titulo")
    horas = timedelta(hours=config["horas_para_assumir"])
    itens = []
    for r in pagina:
        at_id = str(r["atendimento_id"]) if r.get("atendimento_id") else None
        itens.append({
            "id": str(r["id"]), "de_bloco": r["de_bloco"], "para_bloco": r["para_bloco"], "gatilho": r["gatilho"],
            "status": r["status"],
            "atrasado": r["status"] == "emitido" and agora >= m.parse_ts(r["created_at"]) + horas,
            "created_at": r["created_at"], "assumido_at": r.get("assumido_at"), "expirado_at": r.get("expirado_at"),
            "de_agent_key": r.get("de_agent_key"), "para_agent_key": r.get("para_agent_key"),
            "referencias": {k: (str(r[k]) if r.get(k) else None)
                            for k in ("contato_id", "lead_id", "atendimento_id", "atribuicao_id", "entrega_id")},
            "card": ({"titulo": titulos[at_id], "link": f"/funil?card={at_id}"} if at_id in titulos else None),
        })
    return {"itens": itens, "proximo_cursor": _cursor_encode(pagina[-1]) if resto else None}


__all__ = ["blocos_ativos", "computar_scorecards", "listar_handoffs", "listar_scorecards",
           "orgs_supervisionadas", "parse_dia", "salvar_config"]
