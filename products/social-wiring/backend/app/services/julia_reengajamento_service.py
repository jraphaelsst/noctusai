"""Julia wave 4 -- Reengajamento: default tiers (minutos / horas) + reguas (contract 6).

Three jobs on the seed queue, each stale-guarded by `julia_contatos.gen` (contract 0.2) -- there is no
queue cancel, so every job re-reads the contato at fire time and completes as `obsoleto` when `gen`
moved (an inbound, `encerrar`, a pause or a handoff all bump it):

  julia_reengajar_minutos   any hour; only for a lead who interacted and then stopped
  julia_reengajar_horas     only inside the org's business hours (default 08:00-19:59 Sao Paulo; outside: RescheduleLater to the next opening); ALSO covers a
                           lead who never replied
  julia_regua_tentativa     one attempt of a regua, only inside the org's business hours like the hours tier (Lais' regua
                           card: "Das 8h as 20h"); the regua starts after the LAST enabled default tier
                           (no default tier => straight after the outbound); the next attempt is enqueued
                           when this one fires; after the last attempt the cold-lead hook runs

Enqueued on each Julia outbound (`agendar_apos_outbound`, called from the lead turn's post-step), never
for an encerrado contato. A tier's dedupe key is `(tier, contato, gen)`, so the re-engagement message's
own outbound never re-arms the same tier (no loop). A re-engagement turn is a turn with `gatilho="reengajamento"` and the
tier as DATA (`reengajamento: {tier, texto_base?}` -- the regua text, never an instruction: agents renders its own from
its DB); a template attempt is
sent through the Cloud transport (wave 12, `julia_transporte`) when the connection is a configured Cloud one with an
approved modelo; otherwise skipped with event `regua_sem_transporte` (WAHA free text never stands in for a template).

The CRUD half (config + reguas + tentativas) lives here too; the router is a thin shell over it. Every
query is scoped by `org_id`; the 409s mirror the DB guards (migration 271) so the user gets a code, not a
constraint error.
"""
from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from noctusai_lib.domain.jobs import Job
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_contatos_service, julia_envio_gate, julia_eventos_service

logger = logging.getLogger(__name__)

T_CONFIG = "julia_reengajamento_config"
T_REGUAS = "julia_reguas"
T_TENTATIVAS = "julia_regua_tentativas"

JOB_MINUTOS = "julia_reengajar_minutos"
JOB_HORAS = "julia_reengajar_horas"
JOB_REGUA = "julia_regua_tentativa"
JOB_TYPES: tuple[str, ...] = (JOB_MINUTOS, JOB_HORAS, JOB_REGUA)

FUSO = ZoneInfo("America/Sao_Paulo")
HORA_ABERTURA = 8
HORA_FECHAMENTO = 20  # exclusive: 20:00 is already outside
MAX_TENTATIVAS = 3
MINUTOS_VALIDOS = tuple(range(5, 65, 5))
HORAS_VALIDAS = tuple(range(1, 12))
UNIDADES = ("minutos", "horas", "dias")
TEXTO_MAX = 1024
MSG_TIMELINE = "Lead não respondeu mais. Julia reativou a conversa"
JOB_MAX_RETRIES = 2

#: Lais study S4 (owner 2026-11-17): the default cadence is a nudge after 15 minutes of silence, then another after 240 minutes
#: (4 h), only inside business hours (`HORA_ABERTURA`..`HORA_FECHAMENTO`, 08-20 h). The two switches stay OFF: turning on
#: automatic outbound for every org is the owner's call per org (NOC-REMEDIATE[reengajamento-default-on] -- owner decision, 2026-11-17).
#: An org that saved its own row keeps it.
CONFIG_PADRAO: dict[str, Any] = {
    "minutos_ativo": False, "minutos_intervalo": 15, "horas_ativo": False, "horas_intervalo": 4,
    #: Lais study S1: Julia opens the conversation with a new portal (OLX / ImovelWeb) lead. Off until the owner enables it.
    "portal_primeiro_contato_ativo": False,
    #: Per-org business hours (migration 359; the defaults are the former fixed 08-20 h, every day) and the portal opener's own
    #: text (None = the org's `mensagem_inicial`).
    "horario_abertura": "08:00", "horario_fechamento": "20:00", "dias_atendimento": [1, 2, 3, 4, 5, 6, 7],
    "portal_primeiro_contato_texto": None,
}
CHAVES_HORARIO = ("horario_abertura", "horario_fechamento", "dias_atendimento")
PORTAL_TEXTO_MAX = 1024
#: Placeholders the opener understands (filled by `julia_agente_service.mensagem_inicial_pronta`); anything else would go out literally.
PORTAL_TEXTO_TOKENS = ("{link}", "{agente}", "{empresa}")


def _now(agora: Optional[datetime] = None) -> datetime:
    return agora or datetime.now(timezone.utc)


# ── business hours (per org) ────────────────────────────────────────────────
@dataclass(frozen=True)
class Horario:
    """An org's business window in America/Sao_Paulo: `abertura <= local time < fechamento` on the ISO weekdays in `dias`."""
    abertura: dtime = dtime(HORA_ABERTURA, 0)
    fechamento: dtime = dtime(HORA_FECHAMENTO, 0)
    dias: frozenset[int] = frozenset(range(1, 8))


HORARIO_PADRAO = Horario()


def _hhmm(valor: Any) -> dtime:
    """`'08:00'` / `'08:00:00'` / `time` -> `time`. Anything else raises `ValueError` (never a silent default)."""
    if isinstance(valor, dtime):
        return valor.replace(second=0, microsecond=0, tzinfo=None)
    texto = str(valor or "").strip()
    try:
        t = dtime.fromisoformat(texto)
    except ValueError as exc:
        raise ValueError(f"horário inválido: {valor!r}") from exc
    return t.replace(second=0, microsecond=0, tzinfo=None)


def _fmt(t: dtime) -> str:
    return t.strftime("%H:%M")


def horario_da_config(cfg: dict[str, Any]) -> Horario:
    """The `Horario` of a config dict (`obter_config` output / a row). Raises when the stored values are unreadable."""
    return Horario(_hhmm(cfg["horario_abertura"]), _hhmm(cfg["horario_fechamento"]), frozenset(int(d) for d in cfg["dias_atendimento"]))


def horario_da_org(db: Any, org_id: UUID | str) -> Horario:
    return horario_da_config(obter_config(db, org_id))


def dentro_do_horario(agora: datetime, horario: Horario = HORARIO_PADRAO) -> bool:
    """True inside the org's window (default 08:00-19:59, every day) in America/Sao_Paulo."""
    local = agora.astimezone(FUSO)
    return local.isoweekday() in horario.dias and horario.abertura <= local.time().replace(tzinfo=None) < horario.fechamento


def proxima_abertura(agora: datetime, horario: Horario = HORARIO_PADRAO) -> datetime:
    """The first opening strictly after `agora` on a served weekday (closed weekdays skipped)."""
    local = agora.astimezone(FUSO)
    for adiante in range(0, 9):
        dia = local.date() + timedelta(days=adiante)
        if dia.isoweekday() not in horario.dias:
            continue
        abre = datetime.combine(dia, horario.abertura, tzinfo=FUSO)
        if abre > local:
            return abre
    raise ValueError("horário sem nenhum dia de atendimento")


def segundos_ate_abertura(agora: datetime, horario: Horario = HORARIO_PADRAO) -> float:
    """Seconds until the next opening (today when still before it on a served day, else the next served day)."""
    return max(1.0, (proxima_abertura(agora, horario) - agora.astimezone(FUSO)).total_seconds())


def validar_horario(abertura: Any, fechamento: Any, dias: Any) -> Horario:
    """pt-BR 422 on a bad window: unreadable time, opening not before closing (no window across midnight), bad weekdays."""
    try:
        a, f = _hhmm(abertura), _hhmm(fechamento)
    except ValueError as exc:
        raise AppException("horario_invalido", "Informe os horários no formato HH:MM.", status_code=422) from exc
    if a >= f:
        raise AppException(
            "horario_invalido",
            "A abertura precisa ser antes do fechamento no mesmo dia (horário que passa da meia-noite não é suportado).",
            status_code=422,
        )
    if not isinstance(dias, (list, tuple, set, frozenset)) or not dias or not all(
        isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 7 for d in dias
    ):
        raise AppException("dias_invalidos", "Escolha ao menos um dia da semana (1 = segunda a 7 = domingo).", status_code=422)
    return Horario(a, f, frozenset(dias))


def validar_portal_texto(texto: Any) -> Optional[str]:
    """The portal opener text: blank = None (fall back to the org's `mensagem_inicial`). Else it must carry `{link}` (the LGPD
    disclosure is not optional), fit `PORTAL_TEXTO_MAX` and use only the known placeholders."""
    if texto is None or not str(texto).strip():
        return None
    t = str(texto).strip()
    if "{link}" not in t:
        raise AppException(
            "portal_texto_sem_link",
            "A mensagem do primeiro contato precisa conter {link}: é o link do aviso de privacidade (LGPD).", status_code=422,
        )
    if len(t) > PORTAL_TEXTO_MAX:
        raise AppException("portal_texto_longo", f"A mensagem pode ter no máximo {PORTAL_TEXTO_MAX} caracteres.", status_code=422)
    desconhecidos = sorted({m for m in re.findall(r"\{[^{}]*\}", t) if m not in PORTAL_TEXTO_TOKENS})
    if desconhecidos:
        raise AppException(
            "portal_texto_marcador_invalido",
            f"Marcador não reconhecido: {', '.join(desconhecidos)}. Use apenas {', '.join(PORTAL_TEXTO_TOKENS)}.", status_code=422,
        )
    return t


_UNIDADE_TIMEDELTA = {"minutos": "minutes", "horas": "hours", "dias": "days"}


def _delta(valor: int, unidade: str) -> timedelta:
    return timedelta(**{_UNIDADE_TIMEDELTA[unidade]: int(valor)})


# ── config ──────────────────────────────────────────────────────────────────
def _normalizar(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k, v) for k, v in CONFIG_PADRAO.items()}
    for k in ("horario_abertura", "horario_fechamento"):
        out[k] = _fmt(_hhmm(out[k]))
    out["dias_atendimento"] = sorted(int(d) for d in out["dias_atendimento"])
    return out


def obter_config(db: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = db.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    return _normalizar(rows[0] if rows else {})


def salvar_config(db: Any, org_id: UUID | str, valores: dict[str, Any], *, ator: Optional[str] = None) -> dict[str, Any]:
    """Merge `valores` over the org's config and save. Validates the window / opener text (pt-BR 422) and records ONE
    `configuracao_alterada` event naming the changed keys (never a value) -- EOA / measurement-by-design."""
    atual = obter_config(db, org_id)
    recebidos = {k: v for k, v in valores.items() if k in CONFIG_PADRAO}
    if "portal_primeiro_contato_texto" in recebidos:
        recebidos["portal_primeiro_contato_texto"] = validar_portal_texto(recebidos["portal_primeiro_contato_texto"])
    novo = {**atual, **recebidos}
    if any(k in recebidos for k in CHAVES_HORARIO):
        h = validar_horario(novo["horario_abertura"], novo["horario_fechamento"], novo["dias_atendimento"])
        novo["horario_abertura"], novo["horario_fechamento"], novo["dias_atendimento"] = _fmt(h.abertura), _fmt(h.fechamento), sorted(h.dias)
    novo = _normalizar(novo)
    db.table(T_CONFIG).upsert(
        {"org_id": str(org_id), **novo, "updated_at": _now().isoformat()}, on_conflict="org_id",
    ).execute()
    mudou = sorted(k for k in recebidos if novo[k] != atual[k])
    if mudou:
        julia_eventos_service.emitir(db, org_id, "configuracao_alterada", None, {
            "area": "reengajamento", "chaves": mudou, "ator": ator,
            "portal_texto_proprio": novo["portal_primeiro_contato_texto"] is not None,
        })
    return novo


# ── reguas ──────────────────────────────────────────────────────────────────
def _nao_encontrada() -> AppException:
    return AppException("regua_nao_encontrada", "Régua não encontrada.", status_code=404)


def _tentativas_da(db: Any, org_id: UUID | str, regua_id: UUID | str) -> list[dict[str, Any]]:
    rows = (
        db.table(T_TENTATIVAS).select("*").eq("org_id", str(org_id)).eq("regua_id", str(regua_id)).execute().data or []
    )
    return sorted(rows, key=lambda r: int(r.get("ordem") or 0))


def _regua_row(db: Any, org_id: UUID | str, regua_id: UUID | str) -> dict[str, Any]:
    rows = db.table(T_REGUAS).select("*").eq("org_id", str(org_id)).eq("id", str(regua_id)).limit(1).execute().data or []
    if not rows:
        raise _nao_encontrada()
    return rows[0]


def obter_regua(db: Any, org_id: UUID | str, regua_id: UUID | str) -> dict[str, Any]:
    return {**_regua_row(db, org_id, regua_id), "tentativas": _tentativas_da(db, org_id, regua_id)}


def listar_reguas(db: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    reguas = sorted(
        db.table(T_REGUAS).select("*").eq("org_id", str(org_id)).execute().data or [],
        key=lambda r: str(r.get("created_at") or ""),
    )
    tent = db.table(T_TENTATIVAS).select("*").eq("org_id", str(org_id)).execute().data or []
    por_regua: dict[str, list[dict[str, Any]]] = {}
    for t in sorted(tent, key=lambda r: int(r.get("ordem") or 0)):
        por_regua.setdefault(str(t["regua_id"]), []).append(t)
    return [{**r, "tentativas": por_regua.get(str(r["id"]), [])} for r in reguas]


def criar_regua(db: Any, org_id: UUID | str, *, nome: str, compra: bool, aluguel: bool) -> dict[str, Any]:
    """A new regua is always INACTIVE (it has no attempt yet; the guard refuses an active one)."""
    row = {
        "id": str(uuid4()), "org_id": str(org_id), "nome": nome.strip(), "ativa": False, "compra": bool(compra), "aluguel": bool(aluguel),
    }
    created = db.table(T_REGUAS).insert(row).execute().data or []
    if not created:
        raise RuntimeError("julia: regua insert returned no row")
    return {**created[0], "tentativas": []}


def atualizar_regua(db: Any, org_id: UUID | str, regua_id: UUID | str, patch: dict[str, Any]) -> dict[str, Any]:
    _regua_row(db, org_id, regua_id)
    campos = {k: v for k, v in patch.items() if k in ("nome", "compra", "aluguel")}
    if "nome" in campos:
        campos["nome"] = str(campos["nome"]).strip()
    if campos:
        db.table(T_REGUAS).update({**campos, "updated_at": _now().isoformat()}).eq("org_id", str(org_id)).eq(
            "id", str(regua_id)).execute()
    return obter_regua(db, org_id, regua_id)


def apagar_regua(db: Any, org_id: UUID | str, regua_id: UUID | str) -> None:
    _regua_row(db, org_id, regua_id)
    # children first, explicitly (the erasure must not depend on the FK cascade); the regua goes
    # inactive first so the "last active attempt" guard has nothing left to protect.
    db.table(T_REGUAS).update({"ativa": False}).eq("org_id", str(org_id)).eq("id", str(regua_id)).execute()
    db.table(T_TENTATIVAS).delete().eq("org_id", str(org_id)).eq("regua_id", str(regua_id)).execute()
    db.table(T_REGUAS).delete().eq("org_id", str(org_id)).eq("id", str(regua_id)).execute()


def ativar_regua(db: Any, org_id: UUID | str, regua_id: UUID | str) -> dict[str, Any]:
    _regua_row(db, org_id, regua_id)
    if not any(t.get("ativa") for t in _tentativas_da(db, org_id, regua_id)):
        raise AppException(
            "regua_sem_tentativa", "Adicione ao menos uma tentativa ativa antes de ativar a régua.", status_code=409,
        )
    db.table(T_REGUAS).update({"ativa": True, "updated_at": _now().isoformat()}).eq("org_id", str(org_id)).eq(
        "id", str(regua_id)).execute()
    return obter_regua(db, org_id, regua_id)


def desativar_regua(db: Any, org_id: UUID | str, regua_id: UUID | str) -> dict[str, Any]:
    _regua_row(db, org_id, regua_id)
    db.table(T_REGUAS).update({"ativa": False, "updated_at": _now().isoformat()}).eq("org_id", str(org_id)).eq(
        "id", str(regua_id)).execute()
    return obter_regua(db, org_id, regua_id)


# ── tentativas ──────────────────────────────────────────────────────────────
def _tentativa_row(tentativas: list[dict[str, Any]], tid: UUID | str) -> dict[str, Any]:
    for t in tentativas:
        if str(t["id"]) == str(tid):
            return t
    raise AppException("tentativa_nao_encontrada", "Tentativa não encontrada.", status_code=404)


def _ultima_ativa_de_regua_ativa(regua: dict[str, Any], tentativas: list[dict[str, Any]], alvo: dict[str, Any]) -> bool:
    outras_ativas = [t for t in tentativas if t.get("ativa") and str(t["id"]) != str(alvo["id"])]
    return bool(regua.get("ativa")) and bool(alvo.get("ativa")) and not outras_ativas


def _erro_ultima() -> AppException:
    return AppException(
        "ultima_tentativa_ativa",
        "A régua ativa precisa de ao menos uma tentativa ativa. Desative a régua primeiro.",
        status_code=409,
    )


def criar_tentativa(db: Any, org_id: UUID | str, regua_id: UUID | str, dados: dict[str, Any]) -> dict[str, Any]:
    _regua_row(db, org_id, regua_id)
    atuais = _tentativas_da(db, org_id, regua_id)
    if len(atuais) >= MAX_TENTATIVAS:
        raise AppException("limite_tentativas", f"Uma régua tem no máximo {MAX_TENTATIVAS} tentativas.", status_code=409)
    usadas = {int(t["ordem"]) for t in atuais}
    ordem = dados.get("ordem") or next(o for o in range(1, MAX_TENTATIVAS + 1) if o not in usadas)
    if ordem in usadas:
        raise AppException("ordem_ocupada", "Já existe uma tentativa com essa ordem.", status_code=409)
    row = {
        "id": str(uuid4()), "org_id": str(org_id), "regua_id": str(regua_id), "ordem": int(ordem),
        "espera_valor": int(dados["espera_valor"]), "espera_unidade": dados.get("espera_unidade") or "dias",
        "texto": dados.get("texto"), "template_id": str(dados["template_id"]) if dados.get("template_id") else None,
        "ativa": bool(dados.get("ativa", True)),
    }
    created = db.table(T_TENTATIVAS).insert(row).execute().data or []
    if not created:
        raise RuntimeError("julia: tentativa insert returned no row")
    return created[0]


def atualizar_tentativa(
    db: Any, org_id: UUID | str, regua_id: UUID | str, tid: UUID | str, patch: dict[str, Any],
) -> dict[str, Any]:
    regua = _regua_row(db, org_id, regua_id)
    tentativas = _tentativas_da(db, org_id, regua_id)
    alvo = _tentativa_row(tentativas, tid)
    campos = {k: v for k, v in patch.items() if k in ("espera_valor", "espera_unidade", "ativa", "ordem")}
    # texto XOR template: setting one clears the other (the DB CHECK is the backstop).
    if patch.get("texto") is not None:
        campos["texto"], campos["template_id"] = patch["texto"], None
    elif patch.get("template_id") is not None:
        campos["template_id"], campos["texto"] = str(patch["template_id"]), None
    if campos.get("ativa") is False and _ultima_ativa_de_regua_ativa(regua, tentativas, alvo):
        raise _erro_ultima()
    if "ordem" in campos and any(int(t["ordem"]) == int(campos["ordem"]) and str(t["id"]) != str(tid) for t in tentativas):
        raise AppException("ordem_ocupada", "Já existe uma tentativa com essa ordem.", status_code=409)
    if campos:
        db.table(T_TENTATIVAS).update(campos).eq("org_id", str(org_id)).eq("id", str(tid)).execute()
    return _tentativa_row(_tentativas_da(db, org_id, regua_id), tid)


def apagar_tentativa(db: Any, org_id: UUID | str, regua_id: UUID | str, tid: UUID | str) -> None:
    regua = _regua_row(db, org_id, regua_id)
    tentativas = _tentativas_da(db, org_id, regua_id)
    alvo = _tentativa_row(tentativas, tid)
    if _ultima_ativa_de_regua_ativa(regua, tentativas, alvo):
        raise _erro_ultima()
    db.table(T_TENTATIVAS).delete().eq("org_id", str(org_id)).eq("id", str(tid)).execute()


# ── cold-lead hook (wave 3 replaces it) ─────────────────────────────────────
def lead_frio_padrao(client: Any, org_id: UUID | str, contato: dict[str, Any]) -> None:
    """Default cold-lead hook: a no-op. Wave 3 (envio ao SW) replaces it via `registrar_lead_frio`."""
    logger.debug("julia: lead frio org=%s contato=%s -- no cold-lead policy registered yet", org_id, contato.get("id"))


_lead_frio: Callable[[Any, UUID | str, dict[str, Any]], Any] = lead_frio_padrao


def registrar_lead_frio(fn: Callable[[Any, UUID | str, dict[str, Any]], Any]) -> None:
    global _lead_frio
    _lead_frio = fn


async def _chamar_lead_frio(client: Any, org_id: UUID | str, contato: dict[str, Any]) -> None:
    """Run the cold-lead hook (sync or async: wave 3's enqueues a timer). Never raises."""
    try:
        out = _lead_frio(client, org_id, contato)
        if inspect.isawaitable(out):
            await out
    except Exception as exc:
        logger.error("julia: cold-lead hook failed org=%s contato=%s (%s)", org_id, contato.get("id"), type(exc).__name__)


# ── scheduling ──────────────────────────────────────────────────────────────
def chave_do_chat(connection_id: UUID | str, chat_id: str) -> str:
    return f"lead:{connection_id}:{chat_id}"


def _payload(contato: dict[str, Any]) -> dict[str, Any]:
    return {
        **julia_contatos_service.payload_job(contato, chave_do_chat(contato["connection_id"], contato["chat_id"])),
        "contato_id": str(contato["id"]), "connection_id": str(contato["connection_id"]), "chat_id": contato["chat_id"],
    }


def escolher_regua(db: Any, org_id: UUID | str, contato: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The oldest ACTIVE regua that serves the contato's operacao (compra / aluguel); a contato whose
    operacao is not known yet (or is administracao) takes the oldest active regua of any kind."""
    ativas = [r for r in listar_reguas(db, org_id) if r.get("ativa") and any(t.get("ativa") for t in r["tentativas"])]
    op = contato.get("operacao")
    if op in ("compra", "aluguel"):
        ativas = [r for r in ativas if r.get(op)]
    return ativas[0] if ativas else None


def _proxima_tentativa(regua: dict[str, Any], depois_de: int) -> Optional[dict[str, Any]]:
    return next(
        (t for t in regua["tentativas"] if t.get("ativa") and int(t["ordem"]) > depois_de), None,
    )


async def _enfileirar_tentativa(
    repo: Any, db: Any, org_id: UUID | str, contato: dict[str, Any], regua: dict[str, Any],
    tentativa: dict[str, Any], *, base: datetime,
) -> Job:
    quando = base + _delta(tentativa["espera_valor"], tentativa["espera_unidade"])
    gen = int(contato.get("gen") or 0)
    return await repo.enqueue(
        type=JOB_REGUA,
        payload={**_payload(contato), "regua_id": str(regua["id"]), "ordem": int(tentativa["ordem"])},
        max_retries=JOB_MAX_RETRIES, scheduled_for=quando,
        dedupe_key=f"julia:regua:{contato['id']}:{gen}:{regua['id']}:{tentativa['ordem']}",
    )


async def _iniciar_regua_ou_esfriar(
    repo: Any, db: Any, org_id: UUID | str, contato: dict[str, Any], *, base: datetime,
) -> str:
    """The end of the default tiers: start the regua, or -- no regua serves this lead -- the lead is cold."""
    regua = escolher_regua(db, org_id, contato)
    primeira = _proxima_tentativa(regua, 0) if regua else None
    if regua is None or primeira is None:
        await _chamar_lead_frio(db, org_id, contato)
        return "frio"
    await _enfileirar_tentativa(repo, db, org_id, contato, regua, primeira, base=base)
    return "regua"


async def agendar_apos_outbound(
    db: Any, repo: Any, org_id: UUID | str, contato: dict[str, Any], *, agora: Optional[datetime] = None,
) -> list[str]:
    """Arm the re-engagement timers after a Julia outbound. `contato` is the FRESH row (its `gen` is what
    every job below will be compared against). Returns the job types enqueued. Never for an encerrado
    contato."""
    if contato.get("encerrado_at"):
        return []
    agora = _now(agora)
    cfg = obter_config(db, org_id)
    gen = int(contato.get("gen") or 0)
    enfileirados: list[str] = []
    if cfg["minutos_ativo"]:
        await repo.enqueue(
            type=JOB_MINUTOS, payload={**_payload(contato), "tier": "minutos"}, max_retries=JOB_MAX_RETRIES,
            scheduled_for=agora + timedelta(minutes=int(cfg["minutos_intervalo"])),
            dedupe_key=f"julia:reeng:minutos:{contato['id']}:{gen}",
        )
        enfileirados.append(JOB_MINUTOS)
    if cfg["horas_ativo"]:
        await repo.enqueue(
            type=JOB_HORAS, payload={**_payload(contato), "tier": "horas"}, max_retries=JOB_MAX_RETRIES,
            scheduled_for=agora + timedelta(hours=int(cfg["horas_intervalo"])),
            dedupe_key=f"julia:reeng:horas:{contato['id']}:{gen}",
        )
        enfileirados.append(JOB_HORAS)
    if not enfileirados:
        regua = escolher_regua(db, org_id, contato)
        primeira = _proxima_tentativa(regua, 0) if regua else None
        if regua and primeira:
            await _enfileirar_tentativa(repo, db, org_id, contato, regua, primeira, base=agora)
            enfileirados.append(JOB_REGUA)
    return enfileirados


# ── job handlers ────────────────────────────────────────────────────────────
#: `(deps, connection, chat_id, contato, estado_extra, marker_id) -> bool` (True = a message went out).
#: Bound to `julia_lead_turn_service.run_reengajamento_turn` by the worker module; tests inject a recorder.
TurnRunner = Callable[..., Any]
#: What a turn runner returns (instead of a bool) when agents refused the follow-up because the lead already got the
#: maximum in a row with no reply (`limite_retomadas`, the owner's cap, decided by agents): the contact's sequence ENDS.
RESULTADO_LIMITE_RETOMADAS = "limite_retomadas"


def _ultimo_default(cfg: dict[str, Any]) -> Optional[str]:
    if cfg["horas_ativo"]:
        return JOB_HORAS
    if cfg["minutos_ativo"]:
        return JOB_MINUTOS
    return None


async def _contexto_do_job(deps: Any, job: Job) -> tuple[str, Optional[dict[str, Any]], Optional[Any]]:
    """`(estado, contato, connection)`; `estado` != "ok" means the job ends here with that outcome."""
    p = job.payload or {}
    db = deps.scoped
    org_id = p.get("org_id")
    if not (org_id and p.get("contato_id") and p.get("connection_id") and p.get("chat_id")):
        return "payload_invalido", None, None
    if julia_contatos_service.job_obsoleto(db, org_id, p["contato_id"], int(p.get("gen") or 0)):
        return "obsoleto", None, None
    rows = db.table("julia_contatos").select("*").eq("org_id", str(org_id)).eq("id", str(p["contato_id"])).limit(1).execute().data or []
    contato = rows[0] if rows else None
    if contato is None:
        return "obsoleto", None, None
    if contato.get("encerrado_at"):
        return "encerrado", contato, None
    connection = deps.connection_lookup(UUID(str(p["connection_id"])))
    if connection is None or not connection.agente_leads_ativo:
        return "sem_conexao", contato, None
    # julia-v2: no local pause gate -- agents answers `reengajamento_ignorado` when the agent is off / paused / not the
    # active participant, and the turn sends nothing (the mirror `agente_pausado` is display only).
    return "ok", contato, connection


async def _encerrar_sequencia(deps: Any, org_id: Any, contato: dict[str, Any]) -> None:
    """agents' follow-up cap was hit: this contact is followed up NO MORE. `gen + 1` + `encerrado_at` make every other queued
    job of the contato stale (the sibling tier / the regua), then the cold-lead hook runs once. A reply from the lead reopens
    the contact (`registrar_inbound` clears `encerrado_at`). The `agente_nao_atendeu {status}` timeline event is written by
    the turn runner's not-served handling."""
    julia_contatos_service.bump_gen(deps.scoped, contato["id"], encerrado_at=datetime.now(timezone.utc).isoformat())
    await _chamar_lead_frio(deps.scoped, org_id, contato)


def _evento_timeline(db: Any, org_id: UUID | str, contato: dict[str, Any], **extra: Any) -> None:
    julia_eventos_service.emitir(db, org_id, "reengajamento", contato["id"], {"texto": MSG_TIMELINE, **extra})


async def _bloqueio_opt_out(
    deps: Any, org_id: Any, connection: Any, contato: dict[str, Any], fluxo: julia_envio_gate.Fluxo,
) -> Optional[str]:
    """The opt-out leg of the outbound gate for a re-engagement / regua send. Returns the `bloqueado:<motivo>` outcome
    (the refusal is logged + an `envio_bloqueado` event) or None when the lead may be contacted. A lead who opted out
    also gets `gen + 1` + `encerrado_at`, so every queued job of the contato is stale: the follow-up chain STOPS."""
    factory = getattr(deps, "agents_client_factory", None)
    agents = factory(UUID(str(org_id))) if factory is not None else None
    try:
        await julia_envio_gate.exigir_sem_opt_out(
            deps.scoped, org_id, connection.id, fluxo, contato_id=contato["id"], agents=agents,
        )
    except julia_envio_gate.EnvioBloqueado as exc:
        if exc.motivo == julia_envio_gate.MOTIVO_OPT_OUT:
            julia_contatos_service.bump_gen(deps.scoped, contato["id"], encerrado_at=datetime.now(timezone.utc).isoformat())
        return f"bloqueado:{exc.motivo}"
    return None


async def executar_default(
    job: Job, *, deps: Any, repo: Any, run_turn: TurnRunner, agora: Optional[datetime] = None,
) -> str:
    """`julia_reengajar_minutos` / `julia_reengajar_horas`. Returns the outcome label."""
    agora = _now(agora)
    tier = "horas" if job.type == JOB_HORAS else "minutos"
    estado, contato, connection = await _contexto_do_job(deps, job)
    if estado != "ok":
        return estado
    assert contato is not None and connection is not None
    horario = horario_da_org(deps.scoped, job.payload["org_id"])
    if tier == "horas" and not dentro_do_horario(agora, horario):
        raise RescheduleLater(segundos_ate_abertura(agora, horario), "fora do horário de atendimento da organização (São Paulo)")
    if tier == "minutos" and not contato.get("ultimo_inbound_at"):
        return "sem_interacao"  # the hours tier owns the lead who never replied
    org_id = job.payload["org_id"]
    fluxo = julia_envio_gate.FLUXO_DO_TIER[tier]
    try:  # the outbound gate, before the agents call (the turn's own send re-checks it)
        julia_envio_gate.exigir(deps.scoped, org_id, connection.id, fluxo, contato_id=contato["id"])
    except julia_envio_gate.EnvioBloqueado as exc:
        return f"bloqueado:{exc.motivo}"
    bloqueio = await _bloqueio_opt_out(deps, org_id, connection, contato, fluxo)
    if bloqueio is not None:
        return bloqueio
    enviou = await run_turn(deps, connection, contato["chat_id"], contato, {"reengajamento": tier}, f"reeng:{job.id}")
    if enviou == RESULTADO_LIMITE_RETOMADAS:
        await _encerrar_sequencia(deps, org_id, contato)
        return RESULTADO_LIMITE_RETOMADAS
    if enviou:
        _evento_timeline(deps.scoped, org_id, contato, tier=tier)
    if _ultimo_default(obter_config(deps.scoped, org_id)) == job.type:
        await _iniciar_regua_ou_esfriar(repo, deps.scoped, org_id, contato, base=agora)
    return "enviado" if enviou else "silencio"


async def executar_tentativa(
    job: Job, *, deps: Any, repo: Any, run_turn: TurnRunner, agora: Optional[datetime] = None,
) -> str:
    """`julia_regua_tentativa`: one attempt of a regua, then arm the next (or the cold-lead hook)."""
    agora = _now(agora)
    estado, contato, connection = await _contexto_do_job(deps, job)
    if estado != "ok":
        return estado
    assert contato is not None and connection is not None
    p = job.payload
    org_id, db = p["org_id"], deps.scoped
    try:
        regua = obter_regua(db, org_id, p["regua_id"])
    except AppException:
        return "regua_removida"
    tentativa = next((t for t in regua["tentativas"] if int(t["ordem"]) == int(p["ordem"])), None)
    if not regua.get("ativa") or tentativa is None or not tentativa.get("ativa"):
        return "regua_inativa"
    if not contato.get("ultimo_inbound_at"):
        return "sem_interacao"  # a regua only follows a lead who interacted and then stopped
    horario = horario_da_org(db, org_id)
    if not dentro_do_horario(agora, horario):
        # Lais' regua card ("Periodo de execucao: Das 8h as 20h") is the DEFAULT window; the org may change it -- same window as the hours tier.
        raise RescheduleLater(segundos_ate_abertura(agora, horario), "regua fora do horario de atendimento (Sao Paulo)")
    try:  # the outbound gate (Julia on + this regua active), before any send or agents call
        liberacao = julia_envio_gate.exigir(db, org_id, connection.id, julia_envio_gate.Fluxo.REGUA,
                                           contato_id=contato["id"], regua_id=regua["id"])
    except julia_envio_gate.EnvioBloqueado as exc:
        return f"bloqueado:{exc.motivo}"
    bloqueio = await _bloqueio_opt_out(deps, org_id, connection, contato, julia_envio_gate.Fluxo.REGUA)
    if bloqueio is not None:
        return bloqueio
    enviou = False
    sem_transporte = False
    if tentativa.get("template_id"):
        enviou = await _enviar_template(deps, org_id, connection, contato, tentativa, liberacao)
        if enviou:
            _evento_timeline(db, org_id, contato, regua_id=str(regua["id"]), ordem=int(tentativa["ordem"]))
        else:
            sem_transporte = True
            julia_eventos_service.emitir(
                db, org_id, "regua_sem_transporte", contato["id"],
                {"regua_id": str(regua["id"]), "ordem": int(tentativa["ordem"]), "template_id": str(tentativa["template_id"])},
            )
    else:
        enviou = await run_turn(
            deps, connection, contato["chat_id"], contato,
            {"reengajamento": "regua", "reescrever": True, "texto_base": tentativa.get("texto") or "",
             "tentativa": int(tentativa["ordem"]), "regua_id": str(regua["id"])},
            f"regua:{job.id}",
        )
        if enviou == RESULTADO_LIMITE_RETOMADAS:
            await _encerrar_sequencia(deps, org_id, contato)
            return RESULTADO_LIMITE_RETOMADAS
        if enviou:
            _evento_timeline(db, org_id, contato, regua_id=str(regua["id"]), ordem=int(tentativa["ordem"]))
    proxima = _proxima_tentativa(regua, int(tentativa["ordem"]))
    if proxima is not None:
        await _enfileirar_tentativa(repo, db, org_id, contato, regua, proxima, base=agora)
    else:
        await _chamar_lead_frio(db, org_id, contato)
    if sem_transporte:
        return "regua_sem_transporte"
    return "enviado" if enviou else "silencio"


async def _enviar_template(
    deps: Any, org_id: Any, connection: Any, contato: dict[str, Any], tentativa: dict[str, Any],
    liberacao: julia_envio_gate.Liberacao,
) -> bool:
    """A regua attempt carrying a Cloud template (wave 12). True = sent. False = it could not go out: the
    connection is not a configured Cloud one (WAHA free text is never a template stand-in), the modelo is not
    approved / gone, or the send failed -- the caller records `regua_sem_transporte` and the regua moves on."""
    from app.services import julia_modelos_service, julia_transporte

    if not julia_transporte.cloud_configurada(connection):
        return False
    try:
        modelo = julia_modelos_service.obter(deps.scoped, org_id, tentativa["template_id"])
    except AppException:
        return False
    tel = "".join(ch for ch in str(contato.get("telefone_e164") or "") if ch.isdigit())
    if modelo["status"] != "aprovado" or not tel:
        return False
    nome_julia = None
    if deps.agents_client_factory is not None:
        from app.services import julia_agente_service

        nome_julia = await julia_agente_service.nome_do_agente(deps.agents_client_factory(UUID(str(org_id))))
    valores = {"nome_pessoa": (contato.get("nome") or "").strip() or "tudo bem", "nome_julia": nome_julia or "Julia"}
    chaves = julia_modelos_service.corpo_posicional(modelo["corpo"])[1]
    transporte = julia_transporte.transporte_da_conexao(
        connection, waha_factory=deps.waha_factory, cloud_client_factory=getattr(deps, "cloud_client_factory", None),
    )
    julia_envio_gate.conferir(liberacao, connection.id)
    try:
        await transporte.enviar_template(
            tel, julia_modelos_service.nome_meta(modelo), [valores.get(c) or "-" for c in chaves],
            modelo.get("idioma") or julia_transporte.IDIOMA_PADRAO,
        )
    except Exception as exc:  # one failed attempt must not stop the regua
        logger.error("julia regua: template send failed org=%s (%s)", org_id, type(exc).__name__)
        return False
    julia_contatos_service.registrar_outbound(deps.scoped, contato["id"])
    return True


def handlers(*, deps_factory: Callable[[], Any], repo: Any, run_turn: TurnRunner) -> dict[str, Callable[[Job], Any]]:
    """`{job type: handler}` for the seed `Worker`. `deps_factory` builds the lead deps at fire time (the
    conversation module may not exist yet at import)."""

    async def _default(job: Job) -> None:
        deps = deps_factory()
        if deps is None:
            raise RescheduleLater(60.0, "lead deps not ready")
        outcome = await executar_default(job, deps=deps, repo=repo, run_turn=run_turn)
        logger.info("julia reengajamento %s job=%s -> %s", job.type, job.id, outcome)

    async def _tentativa(job: Job) -> None:
        deps = deps_factory()
        if deps is None:
            raise RescheduleLater(60.0, "lead deps not ready")
        outcome = await executar_tentativa(job, deps=deps, repo=repo, run_turn=run_turn)
        logger.info("julia reengajamento %s job=%s -> %s", job.type, job.id, outcome)

    return {JOB_MINUTOS: _default, JOB_HORAS: _default, JOB_REGUA: _tentativa}


__all__ = [
    "CONFIG_PADRAO", "HORARIO_PADRAO", "Horario", "PORTAL_TEXTO_MAX", "JOB_HORAS", "JOB_MINUTOS", "JOB_REGUA", "JOB_TYPES", "MAX_TENTATIVAS", "MSG_TIMELINE",
    "agendar_apos_outbound", "apagar_regua", "apagar_tentativa", "ativar_regua", "atualizar_regua",
    "atualizar_tentativa", "criar_regua", "criar_tentativa", "dentro_do_horario", "horario_da_config", "horario_da_org", "proxima_abertura", "validar_horario", "validar_portal_texto", "desativar_regua",
    "escolher_regua", "executar_default", "executar_tentativa", "handlers", "lead_frio_padrao", "listar_reguas",
    "obter_config", "obter_regua", "registrar_lead_frio", "salvar_config", "segundos_ate_abertura",
]
