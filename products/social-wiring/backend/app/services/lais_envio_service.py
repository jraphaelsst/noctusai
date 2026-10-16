"""Lais wave 3 -- "Envio ao SW": rules, policies, the idempotent send and its triggers (contract 5).

`enviar(client, org_id, contato, gatilho)` turns a `lais_contato` into a normal SW lead + funil card:

  1. IDEMPOTENT per normalised phone per org: a contato already linked to a lead is a no-op; otherwise the
     org's existing SW lead with that phone is ATTACHED and topped up (never duplicated); only when there is
     none is `leads_service.create_lead` called (source slug `julia`, row created per org on first send)
     -- its DB trigger `spawn_funil_card` creates the card -- and `attach_lead_now` resolves the cliente.
  2. The interacao resumo + the collected slots become the card's first note (and the lead's `observacoes`).
  3. `status_envio` on the contato, one `lais_envio_entregas` ledger row, event `novo_lead`.

Triggers (every one goes through `enviar`, so two of them for one phone are one lead and one card):
  qualificado  action `qualificar_lead`, only when the org's rule matches (else the contato stays "Nao pronto")
  visita       the `on_visita_solicitada` hook (when a rule has the visit criterion) and `forcar_envio_sw`
  frio         timer job `lais_envio_frio`, armed by the cold-lead hook after the last re-engagement attempt;
               stale-guarded by `gen` (contract 0.2)
  captacao     action `captacao` + the org policy (enviar | notificar)
  invalido     `encerrar(invalido)` + the WhatsApp-invalido policy
  manual       the Lais > Leads row action / bulk send

Everything binds through the foundation registries at `registrar()` (called once by the router import);
nobody edits the foundation modules' internals.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.jobs import Job
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.primitives.phone import normalize_phone

from app.modules.leads.services import dimensions_service, leads_service
from app.services import (
    clientes_service,
    lais_acoes_service,
    lais_contatos_service as contatos,
    lais_contexto_service,
    lais_envio_criterios as criterios,
    lais_eventos_service as eventos,
    lais_perguntas_service,
    lais_reengajamento_service,
    lais_slots_sensiveis as sensiveis,
    lais_visitas_service,
)

logger = logging.getLogger(__name__)

T_REGRAS = "lais_envio_regras"
T_POLITICAS = "lais_envio_politicas"
T_ENTREGAS = "lais_envio_entregas"
T_LEADS = "leads"
T_NOTAS = "cliente_notas"

JOB_FRIO = "lais_envio_frio"
JOB_MAX_RETRIES = 2
FUSO = lais_reengajamento_service.FUSO
ORIGEM_SLUG = "julia"
ORIGEM_LABEL = "Julia (Lais)"

GATILHOS = ("qualificado", "visita", "frio", "captacao", "invalido", "manual")
#: `lais_contatos.status_envio`: "enviado" = sent on Julia's qualification or by a person, "enviado_auto" = any other
#: automatic trigger (the Lais > Leads list shows "Enviado pela Julia" / "Enviado automaticamente").
STATUS_POR_GATILHO = {"qualificado": "enviado", "manual": "enviado"}
STATUS_ENVIADOS = ("enviado", "enviado_auto")
GATILHO_LABEL = {
    "qualificado": "qualificado pela Julia", "visita": "visita pré-agendada", "frio": "lead frio",
    "captacao": "potencial captação", "invalido": "WhatsApp inválido", "manual": "envio manual",
}
INTERVALO_FRIO = tuple(range(30, 601, 30))
MODOS_FRIO = ("intervalo", "manha_seguinte")
CAPTACOES = ("enviar", "notificar")
FRIOS_PADRAO: dict[str, Any] = {"ativo": False, "modo": "intervalo", "minutos": 60}
POLITICAS_PADRAO: dict[str, Any] = {
    "frios": dict(FRIOS_PADRAO), "captacoes": "notificar", "whatsapp_invalido": False, "pesquisa": False,
}
NOTA_VALOR_MAX = 200
ERRO_MAX = 300

# DI seam: the schema-scoped service client for code that runs outside a request (visit hooks, the cold job).
_client_provider: Optional[Callable[[], Any]] = None
# The job repository of the running Lais worker (set by `lais_reengajamento_worker.build_worker`).
_repo: Any = None


def registrar_client_provider(fn: Optional[Callable[[], Any]]) -> None:
    global _client_provider
    _client_provider = fn


def registrar_repo(repo: Any) -> None:
    global _repo
    _repo = repo


def _client() -> Any:
    if _client_provider is not None:
        return _client_provider()
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client("social_wiring")


def _now(agora: Optional[datetime]) -> datetime:
    return agora or datetime.now(timezone.utc)


# ── rules ───────────────────────────────────────────────────────────────────
def listar_regras(client: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    rows = client.table(T_REGRAS).select("*").eq("org_id", str(org_id)).execute().data or []
    return sorted(rows, key=lambda r: r.get("operacao") or "")


def montar_regras(client: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = listar_regras(client, org_id)
    return {
        "diferenciar": any(r["operacao"] in ("compra", "aluguel") for r in rows),
        "regras": [{"operacao": r["operacao"], "grupos": r.get("grupos") or [], "versao": int(r.get("versao") or 1)} for r in rows],
    }


def org_tem_regra(client: Any, org_id: UUID | str) -> bool:
    return any(r.get("grupos") for r in listar_regras(client, org_id))


def regra_do_contato(rows: list[dict[str, Any]], operacao: Optional[str]) -> Optional[dict[str, Any]]:
    """The org's rule for the contato's operacao: its own row, else the shared `ambas` row."""
    por_op = {r["operacao"]: r for r in rows}
    return por_op.get(operacao or "") or por_op.get("ambas")


def _chaves_slot(client: Any) -> set[str]:
    return {q["chave"] for q in lais_perguntas_service.listar_catalogo(client)}


def substituir_regras(client: Any, org_id: UUID | str, diferenciar: Optional[bool], regras: list[dict[str, Any]]) -> dict[str, Any]:
    """Full replace of the org's rule set (the wizard's Salvar). Typed 422s: `operacoes_invalidas`, plus every
    `criterios.validar_grupos` code."""
    ops = [r["operacao"] for r in regras]
    if diferenciar is None:  # the wizard sends only the rules: two rows = "different for compra and aluguel"
        diferenciar = "ambas" not in ops
    esperado = {"compra", "aluguel"} if diferenciar else {"ambas"}
    if set(ops) != esperado or len(ops) != len(esperado):
        raise AppException(
            "operacoes_invalidas",
            "Informe uma regra para compra e outra para aluguel." if diferenciar else "Informe uma única regra para todas as operações.",
            status_code=422, details={"esperado": sorted(esperado)},
        )
    chaves = _chaves_slot(client)
    novas = {r["operacao"]: criterios.validar_grupos(r["grupos"], chaves) for r in regras}
    org = str(org_id)
    atuais = {r["operacao"]: r for r in listar_regras(client, org_id)}
    for op in [o for o in atuais if o not in novas]:
        client.table(T_REGRAS).delete().eq("org_id", org).eq("operacao", op).execute()
    agora = datetime.now(timezone.utc).isoformat()
    for op, grupos in novas.items():
        atual = atuais.get(op)
        if atual is None:
            client.table(T_REGRAS).insert({"org_id": org, "operacao": op, "grupos": grupos, "versao": 1}).execute()
        elif (atual.get("grupos") or []) != grupos:
            client.table(T_REGRAS).update(
                {"grupos": grupos, "versao": int(atual.get("versao") or 1) + 1, "updated_at": agora}
            ).eq("org_id", org).eq("operacao", op).execute()
    return montar_regras(client, org_id)


def criterios_que_usam(client: Any, org_id: UUID | str) -> dict[str, list[str]]:
    """`{slot key: [criterion names]}` -- bound to Perguntas (`registrar_criterios`) for its 409 `usada_em_criterio`."""
    nomes = {"compra": "Compra", "aluguel": "Aluguel", "ambas": "Compra e aluguel"}
    out: dict[str, list[str]] = {}
    for r in listar_regras(client, org_id):
        for gi, g in enumerate(r.get("grupos") or [], start=1):
            for chave in criterios.chaves_usadas([g]):
                out.setdefault(chave, []).append(f"{nomes.get(r['operacao'], r['operacao'])} · grupo {gi}")
    return out


# ── policies ────────────────────────────────────────────────────────────────
def ler_politicas(client: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_POLITICAS).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        return {**POLITICAS_PADRAO, "frios": dict(FRIOS_PADRAO)}
    r = rows[0]
    return {
        "frios": {**FRIOS_PADRAO, **(r.get("frios") or {})},
        "captacoes": r.get("captacoes") or POLITICAS_PADRAO["captacoes"],
        "whatsapp_invalido": bool(r.get("whatsapp_invalido")),
        "pesquisa": bool(r.get("pesquisa")),
    }


def _validar_frios(frios: dict[str, Any], atual: dict[str, Any]) -> dict[str, Any]:
    novo = {**atual, **{k: v for k, v in frios.items() if v is not None}}
    if not isinstance(novo.get("ativo"), bool):
        raise AppException("politica_invalida", "O campo 'ativo' dos leads frios é verdadeiro ou falso.", status_code=422)
    if novo.get("modo") not in MODOS_FRIO:
        raise AppException("politica_invalida", "Modo de lead frio inválido.", status_code=422, details={"modos": list(MODOS_FRIO)})
    minutos = novo.get("minutos")
    if isinstance(minutos, bool) or minutos not in INTERVALO_FRIO:
        raise AppException("politica_invalida", "O intervalo vai de 30 minutos a 10 horas, de 30 em 30 minutos.",
                           status_code=422, details={"min": INTERVALO_FRIO[0], "max": INTERVALO_FRIO[-1]})
    return {"ativo": novo["ativo"], "modo": novo["modo"], "minutos": int(minutos)}


def salvar_politicas(client: Any, org_id: UUID | str, patch: dict[str, Any]) -> dict[str, Any]:
    """Partial update (only keys present): the rest of the row stays."""
    atual = ler_politicas(client, org_id)
    novo = dict(atual)
    if "frios" in patch and patch["frios"] is not None:
        novo["frios"] = _validar_frios(patch["frios"], atual["frios"])
    if patch.get("captacoes") is not None:
        if patch["captacoes"] not in CAPTACOES:
            raise AppException("politica_invalida", "Captação: 'enviar' ou 'notificar'.", status_code=422, details={"opcoes": list(CAPTACOES)})
        novo["captacoes"] = patch["captacoes"]
    for k in ("whatsapp_invalido", "pesquisa"):
        if patch.get(k) is not None:
            novo[k] = bool(patch[k])
    org = str(org_id)
    existe = client.table(T_POLITICAS).select("org_id").eq("org_id", org).limit(1).execute().data or []
    if existe:
        client.table(T_POLITICAS).update({**novo, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("org_id", org).execute()
    else:
        client.table(T_POLITICAS).insert({"org_id": org, **novo}).execute()
    return ler_politicas(client, org_id)


# ── the send ────────────────────────────────────────────────────────────────
def telefone_do_contato(contato: dict[str, Any]) -> Optional[str]:
    """The contato's canonical E.164 phone: the stored one, else the digits of a `@c.us` chat id."""
    cand = contato.get("telefone_e164")
    if not cand:
        chat = str(contato.get("chat_id") or "")
        cand = chat[: -len("@c.us")] if chat.endswith("@c.us") else None
    return normalize_phone(cand) if cand else None


def _hoje_sp(agora: Optional[datetime]) -> date:
    return _now(agora).astimezone(FUSO).date()


def montar_nota(client: Any, contato: dict[str, Any], gatilho: str) -> str:
    """The card's first note: the latest interacao resumo + the collected (non-sensitive) slots."""
    inter = (
        client.table(contatos.T_INTERACOES).select("*").eq("contato_id", str(contato["id"]))
        .order("iniciada_at", desc=True).limit(1).execute().data or []
    )
    partes = [f"Lead enviado pela Julia ({GATILHO_LABEL.get(gatilho, gatilho)})."]
    resumo = (inter[0].get("resumo") if inter else None) or ""
    if resumo.strip():
        partes.append(f"Resumo da conversa:\n{resumo.strip()}")
    linhas: list[str] = []
    if contato.get("operacao"):
        linhas.append(f"- operação: {contato['operacao']}")
    for k, v in sorted((contato.get("slots") or {}).items()):
        if k in sensiveis.SENSIVEIS or v in (None, ""):
            continue
        linhas.append(f"- {k}: {str(v)[:NOTA_VALOR_MAX]}")
    if linhas:
        partes.append("Informações coletadas:\n" + "\n".join(linhas))
    return "\n\n".join(partes)


def garantir_origem(client: Any, org_id: UUID | str) -> str:
    """The org's `julia` lead source (created on the first send)."""
    rows = client.table("lead_sources").select("id").eq("org_id", str(org_id)).eq("slug", ORIGEM_SLUG).limit(1).execute().data or []
    if rows:
        return str(rows[0]["id"])
    row = dimensions_service.create_source(client, UUID(str(org_id)), slug=ORIGEM_SLUG, label=ORIGEM_LABEL, categoria="direto")
    return str(row["id"])


def _lead_por_telefone(client: Any, org_id: UUID | str, telefone: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(T_LEADS).select("*").eq("org_id", str(org_id)).eq("contato_norm", telefone)
        .order("created_at").limit(1).execute().data or []
    )
    return rows[0] if rows else None


def _anexar(client: Any, org_id: UUID | str, contato: dict[str, Any], lead: dict[str, Any], nota: str) -> Optional[str]:
    """Attach the contato to an EXISTING lead: fill what the lead lacks, never overwrite."""
    patch: dict[str, Any] = {}
    if not (lead.get("cliente_nome") or "").strip() and contato.get("nome"):
        patch["cliente_nome"] = contato["nome"]
    codigo = (contato.get("slots") or {}).get("codigo_imovel")
    if not lead.get("codigo_imovel") and codigo:
        patch["codigo_imovel"] = str(codigo)[:40]
    obs = lead.get("observacoes") or ""
    if nota not in obs:
        patch["observacoes"] = f"{obs}\n\n{nota}".strip()
    if patch:
        leads_service.update_lead(client, UUID(str(org_id)), UUID(str(lead["id"])), patch)
    return leads_service.clientes_dos_leads(client, UUID(str(org_id)), [str(lead["id"])]).get(str(lead["id"]))


def _criar(client: Any, org_id: UUID | str, contato: dict[str, Any], telefone: str, nota: str, agora: Optional[datetime]) -> tuple[dict[str, Any], Optional[str]]:
    codigo = (contato.get("slots") or {}).get("codigo_imovel")
    payload = {
        "data_entrada": _hoje_sp(agora).isoformat(),
        "cliente_nome": contato.get("nome"),
        "contato": telefone,
        "origem_id": garantir_origem(client, org_id),
        "origem_raw": ORIGEM_LABEL,
        "tipo_lead": "novo",
        "codigo_raw": str(codigo)[:40] if codigo else None,
        "codigo_imovel": str(codigo)[:40] if codigo else None,
        "observacoes": nota,
    }
    lead = leads_service.create_lead(client, UUID(str(org_id)), payload)
    # the DB trigger `spawn_funil_card` created the card on that INSERT; this resolves the pessoa synchronously
    return lead, clientes_service.attach_lead_now(client, UUID(str(org_id)), lead)


def _entrega(client: Any, org_id: UUID | str, contato_id: Any, gatilho: str, status: str,
             erro: Optional[str] = None, lead_id: Optional[str] = None) -> None:
    try:
        client.table(T_ENTREGAS).insert({
            "org_id": str(org_id), "contato_id": str(contato_id), "gatilho": gatilho, "status": status,
            "erro": erro[:ERRO_MAX] if erro else None, "lead_id": lead_id,
        }).execute()
    except Exception:
        logger.exception("lais envio: could not write the entrega ledger row (org=%s contato=%s)", org_id, contato_id)


def _falhar(client: Any, org_id: UUID | str, contato: dict[str, Any], gatilho: str, erro: str) -> None:
    contatos.atualizar_contato(client, contato["id"], {"status_envio": "erro"})
    _entrega(client, org_id, contato["id"], gatilho, "erro", erro)


def enviar(client: Any, org_id: UUID | str, contato: dict[str, Any], gatilho: str, *, agora: Optional[datetime] = None) -> dict[str, Any]:
    """Send `contato` to the SW. Returns `{status_envio, lead_id, ja_enviado, criado}`.

    Raises `AppException`: 422 `contato_sem_telefone`, 502 `envio_falhou` (both leave status `erro` + an
    `erro` ledger row, so the Leads list offers the retry)."""
    if gatilho not in GATILHOS:
        raise ValueError(f"gatilho desconhecido: {gatilho!r}")
    org = str(org_id)
    rows = client.table(contatos.T_CONTATOS).select("*").eq("org_id", org).eq("id", str(contato["id"])).limit(1).execute().data or []
    if not rows:
        raise AppException("contato_nao_encontrado", "Contato não encontrado.", status_code=404)
    contato = rows[0]
    if contato.get("lead_id") and contato.get("status_envio") in STATUS_ENVIADOS:
        return {"status_envio": contato["status_envio"], "lead_id": str(contato["lead_id"]), "ja_enviado": True, "criado": False}
    telefone = telefone_do_contato(contato)
    if telefone is None:
        _falhar(client, org_id, contato, gatilho, "contato_sem_telefone")
        raise AppException("contato_sem_telefone", "Este contato não tem telefone para enviar ao SW.", status_code=422)
    try:
        nota = montar_nota(client, contato, gatilho)
        if contato.get("lead_id"):
            # already linked to an SW lead (its card exists): keep THAT lead, only complete the send
            lead_id, criado = str(contato["lead_id"]), False
            linhas = client.table(T_LEADS).select("*").eq("org_id", org).eq("id", lead_id).limit(1).execute().data or []
            cliente_id = _anexar(client, org_id, contato, linhas[0], nota) if linhas else None
        elif (existente := _lead_por_telefone(client, org_id, telefone)) is not None:
            lead_id, criado = str(existente["id"]), False
            cliente_id = _anexar(client, org_id, contato, existente, nota)
        else:
            lead, cliente_id = _criar(client, org_id, contato, telefone, nota, agora)
            lead_id, criado = str(lead["id"]), True
        if cliente_id:
            client.table(T_NOTAS).insert({"org_id": org, "cliente_id": str(cliente_id), "autor_id": None, "tipo": "comentario", "corpo": nota}).execute()
        else:
            logger.warning("lais envio: no cliente resolved for lead %s (org=%s) -- the note lives on leads.observacoes only", lead_id, org)
        status = STATUS_POR_GATILHO.get(gatilho, "enviado_auto")
        contatos.atualizar_contato(client, contato["id"], {"lead_id": lead_id, "status_envio": status})
        _entrega(client, org_id, contato["id"], gatilho, "ok", lead_id=lead_id)
        eventos.emitir(client, org_id, "novo_lead", contato["id"], {"lead_id": lead_id, "gatilho": gatilho, "criado": criado})
    except AppException:
        raise
    except Exception as exc:
        logger.exception("lais envio: send failed (org=%s contato=%s gatilho=%s)", org_id, contato.get("id"), gatilho)
        _falhar(client, org_id, contato, gatilho, f"envio_falhou: {type(exc).__name__}")
        raise AppException("envio_falhou", "Não foi possível enviar ao SW. Tente novamente.", status_code=502) from exc
    return {"status_envio": status, "lead_id": lead_id, "ja_enviado": False, "criado": criado}


def _enviar_automatico(client: Any, org_id: UUID | str, contato: dict[str, Any], gatilho: str) -> dict[str, Any]:
    """A trigger nobody is waiting on: a failure is already in the ledger + logs, never an exception."""
    try:
        res = enviar(client, org_id, contato, gatilho)
    except AppException as exc:
        return {"enviado": False, "erro": exc.code}
    return {"enviado": not res["ja_enviado"], "ja_enviado": res["ja_enviado"], "lead_id": res["lead_id"]}


def ja_qualificado(client: Any, org_id: UUID | str, contato_id: Any) -> bool:
    """Julia already ran `qualificar_lead` for this contato (ledger of applied actions)."""
    rows = (
        client.table(contatos.T_ACOES).select("id").eq("org_id", str(org_id)).eq("contato_id", str(contato_id))
        .eq("tipo", "qualificar_lead").limit(1).execute().data or []
    )
    return bool(rows)


def avaliar_e_enviar(client: Any, org_id: UUID | str, contato: dict[str, Any], gatilho: str, *, qualificado: bool, visita: bool) -> dict[str, Any]:
    regra = regra_do_contato(listar_regras(client, org_id), contato.get("operacao"))
    if regra is None or not criterios.avaliar(regra.get("grupos"), contato, qualificado=qualificado, visita=visita):
        return {"enviado": False, "motivo": "criterios_nao_atendidos"}
    return _enviar_automatico(client, org_id, contato, gatilho)


# ── action handlers + hooks ─────────────────────────────────────────────────
def _h_qualificar_lead(ctx: lais_acoes_service.AcaoCtx, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    return avaliar_e_enviar(ctx.client, ctx.org_id, ctx.contato, "qualificado", qualificado=True, visita=False)


def aplicar_politica_captacao(client: Any, org_id: UUID | str, contato: dict[str, Any]) -> dict[str, Any]:
    """Public so wave 8's captacao handler reuses it: record the event, then send when the org policy says `enviar`."""
    politica = ler_politicas(client, org_id)["captacoes"]
    eventos.emitir(client, org_id, "captacao", contato["id"], {"politica": politica})
    if politica != "enviar":
        return {"politica": politica, "enviado": False}
    return {"politica": politica, **_enviar_automatico(client, org_id, contato, "captacao")}


def _h_captacao(ctx: lais_acoes_service.AcaoCtx, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    return aplicar_politica_captacao(ctx.client, ctx.org_id, ctx.contato)


def _pos_encerrar(ctx: lais_acoes_service.AcaoCtx, motivo: str) -> None:
    if motivo != "invalido":
        return
    if ler_politicas(ctx.client, ctx.org_id)["whatsapp_invalido"]:
        _enviar_automatico(ctx.client, ctx.org_id, ctx.contato, "invalido")


def _hook_on_visita(org_id: Any, contato: dict[str, Any], visita: dict[str, Any]) -> None:
    client = _client()
    regra = regra_do_contato(listar_regras(client, org_id), contato.get("operacao"))
    if regra is None or not criterios.usa_visita(regra.get("grupos")):
        return
    qual = ja_qualificado(client, org_id, contato["id"])
    avaliar_e_enviar(client, org_id, contato, "visita", qualificado=qual, visita=True)


def _hook_forcar_envio(org_id: Any, contato: dict[str, Any], visita: dict[str, Any]) -> None:
    _enviar_automatico(_client(), org_id, contato, "visita")


def _prov_acoes(ctx: lais_contexto_service.ContextoCtx) -> dict[str, Any]:
    """`contexto.acoes`: every action, minus `qualificar_lead` when the org has no send rule (nothing to qualify against)."""
    acoes = list(lais_contexto_service.ACOES_LAIS)
    if not org_tem_regra(ctx.client, ctx.org_id):
        acoes = [a for a in acoes if a != "qualificar_lead"]
    return {"acoes": acoes}


# ── cold lead timer ─────────────────────────────────────────────────────────
def instante_frio(frios: dict[str, Any], contato_id: Any, agora: datetime) -> datetime:
    """When the cold-lead send fires: `minutos` from now, or tomorrow morning 05:00-06:00 (São Paulo;
    the minute is derived from the contato id so a batch of cold leads does not land in the same second)."""
    if frios.get("modo") == "manha_seguinte":
        minuto = int(hashlib.sha256(str(contato_id).encode("utf-8")).hexdigest()[:8], 16) % 60
        amanha = agora.astimezone(FUSO).date() + timedelta(days=1)
        return datetime(amanha.year, amanha.month, amanha.day, 5, minuto, tzinfo=FUSO).astimezone(timezone.utc)
    return agora + timedelta(minutes=int(frios.get("minutos") or FRIOS_PADRAO["minutos"]))


async def lead_frio(client: Any, org_id: UUID | str, contato: dict[str, Any], *, agora: Optional[datetime] = None) -> Optional[str]:
    """The cold-lead hook (after the last re-engagement attempt): arm `lais_envio_frio` when the policy is on.
    Returns the job id, or None when nothing was armed."""
    frios = ler_politicas(client, org_id)["frios"]
    if not frios["ativo"] or contato.get("status_envio") in STATUS_ENVIADOS:
        return None
    if _repo is None:
        raise RuntimeError("lais envio: no job repository registered -- the cold-lead timer cannot be armed")
    agora = _now(agora)
    gen = int(contato.get("gen") or 0)
    job = await _repo.enqueue(
        type=JOB_FRIO,
        payload={
            **contatos.payload_job(contato, lais_reengajamento_service.chave_do_chat(contato["connection_id"], contato["chat_id"])),
            "contato_id": str(contato["id"]),
        },
        max_retries=JOB_MAX_RETRIES, scheduled_for=instante_frio(frios, contato["id"], agora),
        dedupe_key=f"lais:envio:frio:{contato['id']}:{gen}",
    )
    return str(getattr(job, "id", "")) or None


def executar_frio(job: Job, *, client: Any) -> str:
    """`lais_envio_frio` at fire time: stale-guarded by `gen`, policy re-read, then the send. Returns the outcome."""
    p = job.payload or {}
    org_id, contato_id = p.get("org_id"), p.get("contato_id")
    if not (org_id and contato_id):
        return "payload_invalido"
    if contatos.job_obsoleto(client, org_id, contato_id, int(p.get("gen") or 0)):
        return "obsoleto"
    rows = client.table(contatos.T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(contato_id)).limit(1).execute().data or []
    if not rows:
        return "obsoleto"
    contato = rows[0]
    if contato.get("encerrado_at"):
        return "encerrado"
    if contato.get("lead_id") and contato.get("status_envio") in STATUS_ENVIADOS:
        return "ja_enviado"
    if not ler_politicas(client, org_id)["frios"]["ativo"]:
        return "politica_desligada"
    res = _enviar_automatico(client, org_id, contato, "frio")
    return "enviado" if res.get("enviado") else f"erro:{res.get('erro', 'desconhecido')}"


def handlers(*, client_provider: Optional[Callable[[], Any]] = None) -> dict[str, Callable[[Job], Any]]:
    """`{job type: handler}` merged into the Lais worker. The client is built at FIRE time."""

    async def _frio(job: Job) -> None:
        outcome = executar_frio(job, client=(client_provider or _client)())
        logger.info("lais envio %s job=%s -> %s", job.type, job.id, outcome)

    return {JOB_FRIO: _frio}


# ── wiring ──────────────────────────────────────────────────────────────────
def registrar() -> None:
    """Bind every registry slot wave 3 owns (idempotent); called once at import of the router."""
    lais_acoes_service.registrar_handler("qualificar_lead", _h_qualificar_lead)
    if "captacao" not in lais_acoes_service.HANDLERS:  # wave 8 owns the real one and may already be bound
        lais_acoes_service.registrar_handler("captacao", _h_captacao)
    lais_acoes_service.registrar_pos_encerrar(_pos_encerrar)
    lais_contexto_service.registrar_provider("acoes", _prov_acoes)
    lais_perguntas_service.registrar_criterios(criterios_que_usam)
    lais_reengajamento_service.registrar_lead_frio(lead_frio)
    lais_visitas_service.registrar_hook("on_visita_solicitada", _hook_on_visita)
    lais_visitas_service.registrar_hook("forcar_envio_sw", _hook_forcar_envio)


__all__ = [
    "CAPTACOES", "FRIOS_PADRAO", "GATILHOS", "JOB_FRIO", "MODOS_FRIO", "POLITICAS_PADRAO", "STATUS_ENVIADOS",
    "aplicar_politica_captacao", "avaliar_e_enviar", "criterios_que_usam", "enviar", "executar_frio", "handlers",
    "instante_frio", "ja_qualificado", "ler_politicas", "lead_frio", "listar_regras", "montar_nota", "montar_regras",
    "org_tem_regra", "regra_do_contato", "registrar", "registrar_client_provider", "registrar_repo",
    "salvar_politicas", "substituir_regras", "telefone_do_contato",
]
