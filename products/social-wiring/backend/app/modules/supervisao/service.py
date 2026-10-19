"""Maya supervision -- config, scorecard computation, handoff sweep, read models (maya-blocks CONTRACT §2.3/§3/§4).

Writes ONLY to the supervision tables of migration 286 (`supervisao_config`, `agente_scorecards`,
`atendimento_handoffs.status/assumido_at/expirado_at`). It never writes to leads, cards, chats, and never
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

from app.modules.supervisao import metricas as m

logger = logging.getLogger(__name__)

T_CONFIG = "supervisao_config"
T_BLOCOS = "atendimento_blocos"
T_SCORECARDS = "agente_scorecards"
T_HANDOFFS = "atendimento_handoffs"

#: The closed block list in `ordem` (CONTRACT §1) + the default agent of each block.
# NOC-REMEDIATE[maya-blocos-constante]: import BLOCOS / AGENTES_POR_BLOCO from the S2 atendimento_blocos
# module once both slices are on dev; mirrored here because S2 is not on this slice's base — 2026-10-19
BLOCOS: tuple[str, ...] = ("sdr", "atendimento", "negociacao", "juridico", "financeiro", "contador")
AGENTE_PADRAO: dict[str, Optional[str]] = {"sdr": "lead-imob"}
STATUS_HANDOFF = ("emitido", "assumido", "expirado")
HORAS_PADRAO = 24
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
def ler_config(client: Any, org_id: Any) -> dict[str, Any]:
    """Absent row = supervision off with the defaults (CONTRACT §3.3 / §5.2)."""
    rows = client.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    row = rows[0] if rows else {}
    return {
        "supervisao_ativa": bool(row.get("supervisao_ativa", False)),
        "horas_para_assumir": int(row.get("horas_para_assumir") or HORAS_PADRAO),
        "updated_at": row.get("updated_at"),
        "updated_by": row.get("updated_by"),
    }


def salvar_config(client: Any, org_id: Any, *, supervisao_ativa: bool, horas_para_assumir: int, por: Any) -> dict[str, Any]:
    if not 1 <= int(horas_para_assumir) <= 168:
        raise AppException("VALIDATION_ERROR", "horas_para_assumir deve estar entre 1 e 168.", status_code=422)
    client.table(T_CONFIG).upsert({
        "org_id": str(org_id), "supervisao_ativa": bool(supervisao_ativa), "horas_para_assumir": int(horas_para_assumir),
        "updated_by": str(por) if por else None, "updated_at": m.iso(agora_utc()),
    }, on_conflict="org_id").execute()
    return ler_config(client, org_id)


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
    """`[(bloco, agent_key)]` of the org's `ativo` blocks, in `ordem`. Absent row = not supervised."""
    rows = client.table(T_BLOCOS).select("bloco,agent_key,ativo").eq("org_id", str(org_id)).limit(len(BLOCOS)).execute().data or []
    ativos = {r["bloco"]: r.get("agent_key") for r in rows if r.get("ativo") and r.get("bloco") in BLOCOS}
    return [(b, ativos[b]) for b in BLOCOS if b in ativos]


# ── scorecards (nightly) ────────────────────────────────────────────────────
def computar_scorecards(client: Any, org_id: Any, *, agora: datetime, dias: int = DIAS_RECALCULADOS) -> list[dict[str, Any]]:
    """Upsert one scorecard per (ativo block, day) for the last `dias` SP days up to yesterday. Idempotent:
    recomputing a day overwrites its row (UNIQUE NULLS NOT DISTINCT org/bloco/agent_key/dia)."""
    config = ler_config(client, org_id)
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
    ordem = {b: i for i, b in enumerate(BLOCOS)}
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


# ── handoff sweep (every 15 min) ────────────────────────────────────────────
def _cards_por_atendimento(client: Any, org_id: Any, atendimento_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """`{atendimento_id: {"entidades": {atendimento + its processos}, "cliente_id"}}`."""
    out: dict[str, dict[str, Any]] = {}
    for lote in _lotes(atendimento_ids):
        for a in (client.table("atendimentos").select("id,cliente_id").eq("org_id", str(org_id))
                  .in_("id", lote).execute().data or []):
            out[str(a["id"])] = {"entidades": {str(a["id"])}, "cliente_id": a.get("cliente_id")}
        for p in (client.table("processos_venda").select("id,atendimento_id").eq("org_id", str(org_id))
                  .in_("atendimento_id", lote).execute().data or []):
            if str(p.get("atendimento_id")) in out:
                out[str(p["atendimento_id"])]["entidades"].add(str(p["id"]))
    return out


def _primeiro_sinal(client: Any, org_id: Any, h: dict[str, Any], card: Optional[dict[str, Any]]) -> Optional[datetime]:
    """First take-over signal after the handoff (CONTRACT §2.3): a stage move on the card, or a human note
    (`autor_id IS NOT NULL`) on the card's cliente. Julia's notes (`autor_id NULL`) never count."""
    if not card:
        return None
    criado = m.parse_ts(h["created_at"])
    candidatos: list[datetime] = []
    movs = _paginado(lambda: client.table("pipeline_movimentos").select("id,entidade_id,created_at")
                     .eq("org_id", str(org_id)).in_("entidade_id", sorted(card["entidades"]))
                     .gt("created_at", m.iso(criado)), "supervisao movimentos")
    for mv in movs:
        t = m.parse_ts(mv.get("created_at"))
        if str(mv.get("id")) != str(h.get("origem_evento")) and t is not None and t > criado:
            candidatos.append(t)
    if card.get("cliente_id"):
        notas = _paginado(lambda: client.table("cliente_notas").select("id,autor_id,created_at")
                          .eq("org_id", str(org_id)).eq("cliente_id", str(card["cliente_id"]))
                          .gt("created_at", m.iso(criado)), "supervisao notas")
        for n in notas:
            t = m.parse_ts(n.get("created_at"))
            if n.get("autor_id") and t is not None and t > criado:
                candidatos.append(t)
    return min(candidatos) if candidatos else None


def varrer_handoffs(client: Any, org_id: Any, *, agora: datetime) -> dict[str, int]:
    """emitido -> assumido (first signal, before the deadline) | expirado (deadline passed). Terminal states are
    never touched; the conditional `status=emitido` update makes a concurrent sweep a no-op."""
    config = ler_config(client, org_id)
    out = {"assumidos": 0, "expirados": 0}
    if not config["supervisao_ativa"]:
        return out
    horas = timedelta(hours=config["horas_para_assumir"])
    abertos = _paginado(lambda: client.table(T_HANDOFFS).select("id,created_at,atendimento_id,origem_evento,status")
                        .eq("org_id", str(org_id)).eq("status", "emitido"), "supervisao handoffs abertos")
    cards = _cards_por_atendimento(client, org_id, [str(h["atendimento_id"]) for h in abertos if h.get("atendimento_id")])
    for h in abertos:
        prazo = m.parse_ts(h["created_at"]) + horas
        sinal = _primeiro_sinal(client, org_id, h, cards.get(str(h.get("atendimento_id"))))
        if sinal is not None and sinal < prazo:
            mudanca = {"status": "assumido", "assumido_at": m.iso(sinal)}
            chave = "assumidos"
        elif agora >= prazo:
            mudanca = {"status": "expirado", "expirado_at": m.iso(agora)}
            chave = "expirados"
        else:
            continue
        res = (client.table(T_HANDOFFS).update(mudanca).eq("id", str(h["id"])).eq("org_id", str(org_id))
               .eq("status", "emitido").execute())
        if res.data:
            out[chave] += 1
    return out


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
        if b is not None and b not in BLOCOS:
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

    config = ler_config(client, org_id)
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


__all__ = ["BLOCOS", "blocos_ativos", "computar_scorecards", "ler_config", "listar_handoffs", "listar_scorecards",
           "orgs_supervisionadas", "parse_dia", "salvar_config", "varrer_handoffs"]
