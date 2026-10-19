"""Julia wave 5 -- Visitas (pre-scheduling), contract section 7.

Pieces (one module, three layers):

  config      `julia_visitas_config`: separar_operacao + per-profile rules (geral | compra | aluguel):
              ativo, cpf_obrigatorio, min_dias/min_horas, max_dias, weekday grade. Validated by
              `ConfigVisitas` (StrictHttpModel): HH:MM on the 30-min grid, inicio < fim, no overlap.
  slots       `slots_livres` feeds the seed `SchedulingEngine` (via `app.modules.scheduling.engine`)
              one rules object per weekday: working windows = that day's grade, 30-min grid and
              duration, zero travel buffer; the already-booked visits are the engine's blocked
              intervals, so a taken slot never reappears. Min/max window cut the horizon.
  lifecycle   `pedido_visita` handler (action registry) -> `solicitada` + event
              `pre_agendamento_visita` + hook; `confirmar | remarcar | cancelar` state machine
              (409 `transicao_invalida`), the `atendimento_agendamentos` row on Confirmar, and the
              WAHA text to the lead.

CPF (LGPD, contract 17): the clear number lives only inside the handler call; the DB gets sha256 of
the digits + the last 3 digits. Nothing here logs it.

WAVE-3 HOOKS (no-op defaults; wave 3 binds the real ones with `registrar_hook`):
  `on_visita_solicitada(org_id, contato, visita)`      trigger envio if a rule asks
  `forcar_envio_sw(org_id, contato, visita)`           force send-to-SW on Confirmar when not sent yet
"""
from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain.scheduling import BlockedInterval, WorkingWindow
from noctusai_lib.primitives.exceptions import AppException

from app.modules.scheduling.engine import SchedulingRuleDefaults, build_engine, build_rules
from app.services import julia_eventos_service as eventos

logger = logging.getLogger(__name__)

T_CONFIG = "julia_visitas_config"
T_VISITAS = "julia_visitas"
T_CONTATOS = "julia_contatos"
T_AGENDAMENTOS = "atendimento_agendamentos"
T_ATENDIMENTOS = "atendimentos"

TZ_NOME = "America/Sao_Paulo"
TZ = ZoneInfo(TZ_NOME)
SLOT_MIN = 30
DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")  # index == date.weekday()
PERFIS = ("geral", "compra", "aluguel")
VIVAS = ("solicitada", "confirmada", "remarcada")
STATUS = (*VIVAS, "cancelada")
#: from-status allowed per transition
TRANSICOES: dict[str, tuple[str, ...]] = {
    "confirmar": ("solicitada", "remarcada"),
    "remarcar": ("solicitada", "confirmada", "remarcada"),
    "cancelar": ("solicitada", "confirmada", "remarcada"),
}
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_LOCAL_LOCATION = "visita"


# ── config models ───────────────────────────────────────────────────────────
class Faixa(StrictHttpModel):
    inicio: str
    fim: str

    @model_validator(mode="after")
    def _faixa(self) -> "Faixa":
        for v in (self.inicio, self.fim):
            if not _HHMM.match(v):
                raise ValueError("horario_invalido")
        a, b = _hhmm(self.inicio), _hhmm(self.fim)
        if a >= b:
            raise ValueError("faixa_invertida")
        if (a.minute % SLOT_MIN) or (b.minute % SLOT_MIN):
            raise ValueError("fora_da_grade_de_30_min")
        return self


class PerfilVisitas(StrictHttpModel):
    ativo: bool = False
    cpf_obrigatorio: bool = False
    min_dias: int = Field(default=0, ge=0, le=365)
    min_horas: int = Field(default=0, ge=0, le=23)
    max_dias: int = Field(default=30, ge=1, le=365)
    grade: dict[str, list[Faixa]] = Field(default_factory=dict)

    @field_validator("grade")
    @classmethod
    def _grade(cls, grade: dict[str, list[Faixa]]) -> dict[str, list[Faixa]]:
        for dia, faixas in grade.items():
            if dia not in DIAS:
                raise ValueError("dia_invalido")
            ordenadas = sorted(faixas, key=lambda f: f.inicio)
            for a, b in zip(ordenadas, ordenadas[1:]):
                if b.inicio < a.fim:
                    raise ValueError("faixas_sobrepostas")
        return grade

    @model_validator(mode="after")
    def _janela(self) -> "PerfilVisitas":
        if self.max_dias * 24 <= self.min_dias * 24 + self.min_horas:
            raise ValueError("janela_invalida")
        return self


class ConfigVisitas(StrictHttpModel):
    separar_operacao: bool = False
    config: dict[str, PerfilVisitas]

    @model_validator(mode="after")
    def _perfis(self) -> "ConfigVisitas":
        if any(k not in PERFIS for k in self.config):
            raise ValueError("perfil_invalido")
        exigidos = ("compra", "aluguel") if self.separar_operacao else ("geral",)
        faltam = [p for p in exigidos if p not in self.config]
        if faltam:
            raise ValueError(f"perfil_ausente:{','.join(faltam)}")
        return self


def _hhmm(v: str) -> time:
    h, m = v.split(":")
    return time(int(h), int(m))


def _grade_padrao() -> dict[str, list[dict[str, str]]]:
    """The live Julia default: 09-17 weekdays, 09-18 weekend."""
    return {d: [{"inicio": "09:00", "fim": "17:00" if i < 5 else "18:00"}] for i, d in enumerate(DIAS)}


def config_padrao() -> dict[str, Any]:
    return {
        "separar_operacao": False,
        "config": {"geral": {"ativo": False, "cpf_obrigatorio": False, "min_dias": 0, "min_horas": 2,
                             "max_dias": 30, "grade": _grade_padrao()}},
    }


# ── config storage ──────────────────────────────────────────────────────────
def ler_config(client: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        return config_padrao()
    r = rows[0]
    return {"separar_operacao": bool(r.get("separar_operacao")), "config": r.get("config") or {}}


def salvar_config(client: Any, org_id: UUID | str, nova: ConfigVisitas) -> dict[str, Any]:
    corpo = {
        "org_id": str(org_id),
        "separar_operacao": nova.separar_operacao,
        "config": {k: v.model_dump(mode="json") for k, v in nova.config.items()},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table(T_CONFIG).upsert(corpo, on_conflict="org_id").execute()
    return {"separar_operacao": corpo["separar_operacao"], "config": corpo["config"]}


def perfil_para(cfg: dict[str, Any], operacao: Optional[str]) -> Optional[dict[str, Any]]:
    """The profile that applies to `operacao` (compra/aluguel when separated, else geral)."""
    if cfg.get("separar_operacao"):
        chave = operacao if operacao in ("compra", "aluguel") else None
        return (cfg.get("config") or {}).get(chave) if chave else None
    return (cfg.get("config") or {}).get("geral")


# ── slots ───────────────────────────────────────────────────────────────────
def _dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _bloqueios(client: Any, org_id: UUID | str, ignorar_id: Optional[str] = None) -> list[BlockedInterval]:
    rows = (client.table(T_VISITAS).select("id, inicio, fim, status").eq("org_id", str(org_id))
            .in_("status", list(VIVAS)).execute().data or [])
    out: list[BlockedInterval] = []
    for r in rows:
        if ignorar_id and str(r.get("id")) == str(ignorar_id):
            continue
        a, b = _dt(r.get("inicio")), _dt(r.get("fim"))
        if a and b:
            out.append(BlockedInterval(start=a.astimezone(TZ), end=b.astimezone(TZ), location_id=_LOCAL_LOCATION))
    return out


def _engine_do_dia(perfil: dict[str, Any], dia: date):
    faixas = (perfil.get("grade") or {}).get(DIAS[dia.weekday()]) or []
    if not faixas:
        return None
    rules = build_rules(SchedulingRuleDefaults(
        timezone=TZ_NOME, travel_buffer_minutes=0, standard_duration_minutes=SLOT_MIN,
        same_location_duration_minutes=SLOT_MIN, slot_grid_minutes=SLOT_MIN,
    ))
    rules = dataclasses.replace(rules, working_windows=[
        WorkingWindow(name=f"f{i}", start=_hhmm(f["inicio"]), end=_hhmm(f["fim"])) for i, f in enumerate(faixas)
    ])
    return build_engine(rules)


def slots_livres(
    client: Any, org_id: UUID | str, perfil: dict[str, Any], *, agora: Optional[datetime] = None,
    dias: Optional[int] = None, ignorar_visita_id: Optional[str] = None,
) -> list[dict[str, str]]:
    """Free 30-min slots in [agora + min, agora + max], per-weekday grade, minus booked visits."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(TZ)
    minimo = agora + timedelta(days=int(perfil.get("min_dias") or 0), hours=int(perfil.get("min_horas") or 0))
    maximo = agora + timedelta(days=int(perfil.get("max_dias") or 0))
    if dias is not None:
        maximo = min(maximo, agora + timedelta(days=dias))
    bloqueios = _bloqueios(client, org_id, ignorar_visita_id)
    out: list[dict[str, str]] = []
    dia = minimo.date()
    while dia <= maximo.date():
        engine = _engine_do_dia(perfil, dia)
        if engine is not None:
            for s in engine.candidate_slots(dia, _LOCAL_LOCATION, bloqueios):
                if minimo <= s.start_at and s.end_at <= maximo:
                    out.append({"inicio": s.start_at.isoformat(), "fim": s.end_at.isoformat()})
        dia += timedelta(days=1)
    out.sort(key=lambda x: x["inicio"])
    return out


def horario_valido(
    client: Any, org_id: UUID | str, perfil: dict[str, Any], inicio: datetime, *, agora: Optional[datetime] = None,
    ignorar_visita_id: Optional[str] = None,
) -> bool:
    alvo = inicio.astimezone(TZ)
    livres = slots_livres(client, org_id, perfil, agora=agora, ignorar_visita_id=ignorar_visita_id)
    return any(_dt(s["inicio"]) == alvo for s in livres)


# ── CPF (hash + last 3 only) ────────────────────────────────────────────────
def hash_cpf(cpf: Any) -> Optional[tuple[str, str]]:
    digitos = re.sub(r"\D", "", str(cpf or ""))
    if len(digitos) != 11:
        return None
    return hashlib.sha256(digitos.encode("utf-8")).hexdigest(), digitos[-3:]


# ── wave-3 hooks ────────────────────────────────────────────────────────────
def _hook_noop(org_id: Any, contato: dict[str, Any], visita: dict[str, Any]) -> None:
    return None


HOOKS: dict[str, Callable[[Any, dict[str, Any], dict[str, Any]], Any]] = {
    "on_visita_solicitada": _hook_noop,
    "forcar_envio_sw": _hook_noop,
}


def registrar_hook(nome: str, fn: Callable[[Any, dict[str, Any], dict[str, Any]], Any]) -> None:
    if nome not in HOOKS:
        raise KeyError(nome)
    HOOKS[nome] = fn


def on_visita_solicitada(org_id: Any, contato: dict[str, Any], visita: dict[str, Any]) -> Any:
    return HOOKS["on_visita_solicitada"](org_id, contato, visita)


def forcar_envio_sw(org_id: Any, contato: dict[str, Any], visita: dict[str, Any]) -> Any:
    return HOOKS["forcar_envio_sw"](org_id, contato, visita)


def _chamar_hook(fn: Callable[..., Any], org_id: Any, contato: dict[str, Any], visita: dict[str, Any]) -> None:
    try:
        fn(org_id, contato, visita)
    except Exception:
        # a wave-3 hook must never undo a visit that is already stored
        logger.exception("julia visitas: hook %s failed (org=%s visita=%s)", getattr(fn, "__name__", "?"), org_id, visita.get("id"))


# ── action handler: pedido_visita ───────────────────────────────────────────
def _h_pedido_visita(ctx: Any, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    cfg = ler_config(ctx.client, ctx.org_id)
    perfil = perfil_para(cfg, ctx.contato.get("operacao"))
    if not perfil or not perfil.get("ativo"):
        return {"erro": "visitas_desativadas"}
    inicio = _dt(payload.get("inicio"))
    if inicio is None:
        return {"erro": "inicio_invalido"}
    cpf = hash_cpf(payload.get("cpf"))
    if perfil.get("cpf_obrigatorio") and cpf is None:
        return {"erro": "cpf_obrigatorio"}
    if not horario_valido(ctx.client, ctx.org_id, perfil, inicio):
        return {"erro": "horario_indisponivel"}
    inicio_l = inicio.astimezone(TZ)
    fim_l = inicio_l + timedelta(minutes=SLOT_MIN)
    codigo = payload.get("codigo")
    linha = {
        "id": str(uuid4()), "org_id": str(ctx.org_id), "contato_id": str(ctx.contato["id"]),
        "codigo_imovel": str(codigo)[:40] if codigo else None, "operacao": ctx.contato.get("operacao"),
        "inicio": inicio_l.isoformat(), "fim": fim_l.isoformat(), "status": "solicitada",
        "cpf_hash": cpf[0] if cpf else None, "cpf_final": cpf[1] if cpf else None,
        "responsavel_user_id": ctx.contato.get("responsavel_user_id"),
    }
    rows = ctx.client.table(T_VISITAS).insert(linha).execute().data or [linha]
    visita = rows[0]
    eventos.emitir(ctx.client, ctx.org_id, "pre_agendamento_visita", ctx.contato["id"],
                   {"visita_id": str(visita.get("id")), "inicio": linha["inicio"], "codigo": linha["codigo_imovel"]})
    _chamar_hook(on_visita_solicitada, ctx.org_id, ctx.contato, visita)
    return {"visita_id": str(visita.get("id")), "status": "solicitada"}


def registrar() -> None:
    """Bind the handler + the tool (idempotent); called once at import of the router."""
    from app.services import julia_acoes_service

    julia_acoes_service.registrar_handler("pedido_visita", _h_pedido_visita)


# ── tool: horarios_visita ───────────────────────────────────────────────────
def horarios_para_ferramenta(client: Any, org_id: UUID | str, dias: int, operacao: Optional[str] = None,
                             *, agora: Optional[datetime] = None) -> list[dict[str, str]]:
    cfg = ler_config(client, org_id)
    if cfg.get("separar_operacao") and operacao not in ("compra", "aluguel"):
        # per-operation grades: without knowing the operation, only slots valid for BOTH are safe
        pa, pb = (cfg["config"].get("compra"), cfg["config"].get("aluguel"))
        if not (pa and pb and pa.get("ativo") and pb.get("ativo")):
            return []
        a = {s["inicio"]: s for s in slots_livres(client, org_id, pa, dias=dias, agora=agora)}
        b = {s["inicio"] for s in slots_livres(client, org_id, pb, dias=dias, agora=agora)}
        return [s for k, s in a.items() if k in b]
    perfil = perfil_para(cfg, operacao)
    if not perfil or not perfil.get("ativo"):
        return []
    return slots_livres(client, org_id, perfil, dias=dias, agora=agora)


# ── listing ─────────────────────────────────────────────────────────────────
def _intervalo(view: str, data: date) -> tuple[datetime, datetime]:
    if view == "dia":
        ini = datetime.combine(data, time(0, 0), tzinfo=TZ)
        return ini, ini + timedelta(days=1)
    ini = datetime.combine(data - timedelta(days=data.weekday()), time(0, 0), tzinfo=TZ)
    return ini, ini + timedelta(days=7)


def listar(client: Any, org_id: UUID | str, *, view: str, data: date, operacao: Optional[str] = None,
           status: Optional[str] = None, responsavel_user_id: Optional[str] = None) -> list[dict[str, Any]]:
    ini, fim = _intervalo(view, data)
    q = (client.table(T_VISITAS).select("*").eq("org_id", str(org_id))
         .gte("inicio", ini.isoformat()).lt("inicio", fim.isoformat()))
    if operacao:
        q = q.eq("operacao", operacao)
    if status:
        q = q.eq("status", status)
    if responsavel_user_id:
        q = q.eq("responsavel_user_id", responsavel_user_id)
    rows = q.order("inicio").execute().data or []
    return [saida(r) for r in rows]


def saida(r: dict[str, Any]) -> dict[str, Any]:
    """The API shape: never the hash, only `cpf_final` (last 3)."""
    return {k: r.get(k) for k in (
        "id", "contato_id", "codigo_imovel", "operacao", "inicio", "fim", "status", "motivo_cancelamento",
        "agendamento_id", "responsavel_user_id", "cpf_final", "created_at", "updated_at")}


# ── lifecycle ───────────────────────────────────────────────────────────────
def _erro_transicao(atual: str, acao: str) -> AppException:
    return AppException("transicao_invalida", f"Não é possível {acao} uma visita {atual}.", status_code=409)


def obter(client: Any, org_id: UUID | str, visita_id: UUID | str) -> dict[str, Any]:
    rows = (client.table(T_VISITAS).select("*").eq("org_id", str(org_id)).eq("id", str(visita_id)).limit(1)
            .execute().data or [])
    if not rows:
        raise AppException("visita_nao_encontrada", "Visita não encontrada.", status_code=404)
    return rows[0]


def _contato(client: Any, org_id: UUID | str, contato_id: Any) -> dict[str, Any]:
    rows = (client.table(T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(contato_id)).limit(1)
            .execute().data or [])
    return rows[0] if rows else {}


def _atendimento_do_lead(client: Any, org_id: UUID | str, lead_id: Any) -> Optional[str]:
    rows = (client.table(T_ATENDIMENTOS).select("id").eq("org_id", str(org_id)).eq("lead_id", str(lead_id))
            .order("created_at", desc=True).limit(1).execute().data or [])
    return str(rows[0]["id"]) if rows else None


def _atualizar(client: Any, org_id: UUID | str, visita_id: Any, patch: dict[str, Any]) -> dict[str, Any]:
    patch = {**patch, "updated_at": datetime.now(timezone.utc).isoformat()}
    rows = (client.table(T_VISITAS).update(patch).eq("org_id", str(org_id)).eq("id", str(visita_id))
            .execute().data or [])
    return rows[0] if rows else patch


def confirmar(client: Any, org_id: UUID | str, visita_id: UUID | str) -> dict[str, Any]:
    v = obter(client, org_id, visita_id)
    if v["status"] not in TRANSICOES["confirmar"]:
        raise _erro_transicao(v["status"], "confirmar")
    contato = _contato(client, org_id, v["contato_id"])
    if contato.get("lead_id") and contato.get("status_envio") not in ("enviado", "enviado_auto"):
        _chamar_hook(forcar_envio_sw, org_id, contato, v)
        contato = _contato(client, org_id, v["contato_id"]) or contato
    patch: dict[str, Any] = {"status": "confirmada"}
    aviso = None
    if v.get("agendamento_id"):
        client.table(T_AGENDAMENTOS).update({"quando": v["inicio"], "deleted_at": None}).eq("id", str(v["agendamento_id"])).execute()
    else:
        atendimento = _atendimento_do_lead(client, org_id, contato["lead_id"]) if contato.get("lead_id") else None
        if atendimento is None:
            aviso = "sem_card: agendamento não criado (o contato ainda não tem lead/card)"
        else:
            ag = client.table(T_AGENDAMENTOS).insert({
                "org_id": str(org_id), "atendimento_id": atendimento, "quando": v["inicio"], "tipo": "visita",
                "nota": f"Visita pré-agendada pela Julia{' · imóvel ' + v['codigo_imovel'] if v.get('codigo_imovel') else ''}",
            }).execute().data or []
            if ag:
                patch["agendamento_id"] = str(ag[0]["id"])
    novo = _atualizar(client, org_id, visita_id, patch)
    return {**saida({**v, **novo}), "aviso": aviso}


def remarcar(client: Any, org_id: UUID | str, visita_id: UUID | str, inicio: datetime, fim: datetime,
             *, agora: Optional[datetime] = None) -> dict[str, Any]:
    v = obter(client, org_id, visita_id)
    if v["status"] not in TRANSICOES["remarcar"]:
        raise _erro_transicao(v["status"], "remarcar")
    cfg = ler_config(client, org_id)
    perfil = perfil_para(cfg, v.get("operacao")) or perfil_para(cfg, "geral")
    if not perfil or not perfil.get("ativo"):
        raise AppException("visitas_desativadas", "Pré-agendamento de visita desativado.", status_code=422)
    if (fim - inicio) != timedelta(minutes=SLOT_MIN) or not horario_valido(
            client, org_id, perfil, inicio, agora=agora, ignorar_visita_id=str(visita_id)):
        raise AppException("horario_indisponivel", "Horário fora da grade ou já ocupado.", status_code=422)
    i, f = inicio.astimezone(TZ), fim.astimezone(TZ)
    if v.get("agendamento_id"):
        client.table(T_AGENDAMENTOS).update({"quando": i.isoformat()}).eq("id", str(v["agendamento_id"])).execute()
    novo = _atualizar(client, org_id, visita_id, {"status": "remarcada", "inicio": i.isoformat(), "fim": f.isoformat()})
    return saida({**v, **novo})


def cancelar(client: Any, org_id: UUID | str, visita_id: UUID | str, motivo: Optional[str]) -> dict[str, Any]:
    v = obter(client, org_id, visita_id)
    if v["status"] not in TRANSICOES["cancelar"]:
        raise _erro_transicao(v["status"], "cancelar")
    if v.get("agendamento_id"):  # soft delete (D3)
        client.table(T_AGENDAMENTOS).update({"deleted_at": datetime.now(timezone.utc).isoformat()}).eq(
            "id", str(v["agendamento_id"])).execute()
    novo = _atualizar(client, org_id, visita_id, {"status": "cancelada", "motivo_cancelamento": motivo})
    return saida({**v, **novo})


# ── message to the lead ─────────────────────────────────────────────────────
def mensagem_lead(acao: str, visita: dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        d = _dt(v)
        return d.astimezone(TZ).strftime("%d/%m às %H:%M") if d else ""

    if acao == "confirmar":
        return f"Visita confirmada para {fmt(visita.get('inicio'))}. Te esperamos!"
    if acao == "remarcar":
        return f"Sua visita foi remarcada para {fmt(visita.get('inicio'))}. Qualquer dúvida, é só avisar."
    return "Sua visita foi cancelada. Se quiser agendar outro horário, é só me avisar."


async def avisar_lead(client: Any, org_id: UUID | str, visita: dict[str, Any], texto: str, *, store: Any,
                      waha_factory: Callable[..., Any]) -> bool:
    """Send `texto` over the contato's own WAHA line. False (logged) when it could not go out --
    the state change stands, the response says the message did not leave."""
    contato = _contato(client, org_id, visita["contato_id"])
    if not contato.get("connection_id") or not contato.get("chat_id"):
        logger.warning("julia visitas: contato %s has no chat to message", visita.get("contato_id"))
        return False
    try:
        record = store.get_connection(connection_id=UUID(str(contato["connection_id"])), org_id=UUID(str(org_id)), decrypt=True)
        if record is None:
            logger.warning("julia visitas: connection %s not found", contato["connection_id"])
            return False
        waha = waha_factory(base_url=record.base_url or None, api_key=record.api_key, session=record.session_name)
        await waha.send_text(contato["chat_id"], texto)
    except Exception:
        logger.exception("julia visitas: could not message the lead (visita=%s)", visita.get("id"))
        return False
    return True


__all__ = [
    "ConfigVisitas", "HOOKS", "TRANSICOES", "avisar_lead", "cancelar", "config_padrao", "confirmar", "forcar_envio_sw",
    "hash_cpf", "horarios_para_ferramenta", "ler_config", "listar", "mensagem_lead", "obter",
    "on_visita_solicitada", "registrar", "registrar_hook", "remarcar", "salvar_config", "slots_livres",
]
