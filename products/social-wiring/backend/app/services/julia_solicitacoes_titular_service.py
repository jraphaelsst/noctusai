"""Data-subject requests (LGPD art. 18) a lead makes to Julia: RECORDED for a human, never executed (owner 2026-10-21).

Julia answers on a public number, so a lead's message must never delete anything: "leads cant ask for their data deletion nor
any other type of destructive actions". No keyword creates a request either. JULIA (the model) registers it through her tool
`registrar_solicitacao_titular` -> `POST /api/julia/ferramentas/solicitacao-titular` -> `registrar` here:

  * stores the request (`julia_solicitacoes_titular`, migration 293): org, lead (`contato_id` == agents' `lead_ref`), chat,
    the LGPD `tipo`, a <=500-char excerpt of what the lead said, `recebida_em`, `prazo_em = recebida_em + 15 days`, `aberta`;
  * notifies the org admins in-app (`write_in_app`, product `social-wiring`, link to the Opt-outs page). A failed notice is
    RECORDED on the row (`notificacao_status='falhou'` + the error) and logged -- never swallowed.

An org admin decides it in SW (`decidir`): `aberta -> em_analise -> atendida | negada | cancelada`, who/when/why recorded. An
erasure ("eliminacao") is done BY AN ADMIN through the operator "apagar-dados" flow -- never automatically, never from here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.primitives.exceptions import AppException

from app.services.julia_notificacoes_service import admins_da_org

logger = logging.getLogger(__name__)

T = "julia_solicitacoes_titular"
TIPOS = (
    "confirmacao", "acesso", "correcao", "eliminacao", "portabilidade", "revogacao_consentimento", "oposicao",
    "info_compartilhamento", "outro",
)
STATUS = ("aberta", "em_analise", "atendida", "negada", "cancelada")
STATUS_ABERTOS = ("aberta", "em_analise")
KIND = "julia_solicitacao_titular"
PRAZO_DIAS = 15
ALERTA_DIAS = 3  # the list highlights requests within this many days of the deadline
TRECHO_MAX = 500
MOTIVO_MAX = 1000
PAGE_SIZE_MAX = 100
ERRO_MAX = 500
LINK = "/julia/opt-outs?aba=solicitacoes&solicitacao={id}"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _parse(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def situacao_do_prazo(linha: dict[str, Any], agora: Optional[datetime] = None) -> str:
    """`vencida` (open past the deadline) | `vence_em_breve` (open, <= 3 days left) | `no_prazo` | `encerrada`."""
    if linha.get("status") not in STATUS_ABERTOS:
        return "encerrada"
    prazo = _parse(linha.get("prazo_em"))
    if prazo is None:
        return "no_prazo"
    restante = prazo - (agora or _agora())
    if restante < timedelta(0):
        return "vencida"
    return "vence_em_breve" if restante <= timedelta(days=ALERTA_DIAS) else "no_prazo"


def com_situacao(linha: dict[str, Any], agora: Optional[datetime] = None) -> dict[str, Any]:
    return {**linha, "prazo_situacao": situacao_do_prazo(linha, agora)}


def notificar_admins(client: Any, core: Any, org_id: UUID | str, linha: dict[str, Any]) -> dict[str, Any]:
    """Tell the org admins; the outcome (and the error, when it failed) is stored on the row. Never raises."""
    try:
        admins = admins_da_org(core, org_id)
        if not admins:
            raise RuntimeError("sem_destinatarios: a organização não tem admin para avisar")
        write_in_app(
            core, user_ids=admins, kind=KIND, org_id=org_id,
            title="Solicitação de dados pessoais de um lead",
            message="Um lead fez uma solicitação sobre seus dados pessoais. Nada foi apagado: ela aguarda a decisão de um admin.",
            metadata={"product": "social-wiring", "link": LINK.format(id=linha["id"]), "solicitacao_id": str(linha["id"])},
        )
        patch = {"notificacao_status": "enviada", "notificacao_erro": None, "notificado_em": _agora().isoformat()}
    except Exception as exc:  # recorded on the row + logged: a notice that did not land must be visible to an admin
        logger.exception("julia: data-subject request %s: admin notice failed", linha.get("id"))
        patch = {"notificacao_status": "falhou", "notificacao_erro": f"{type(exc).__name__}: {exc}"[:ERRO_MAX]}
    client.table(T).update({**patch, "updated_at": _agora().isoformat()}).eq("id", str(linha["id"])).execute()
    return {**linha, **patch}


def registrar(
    client: Any, core: Any, *, org_id: UUID | str, lead_ref: str, tipo: str, trecho: str, chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """Record one request of a lead of THIS org and notify the admins. Returns the stored row (`id`, `prazo_em`, ...)."""
    if tipo not in TIPOS:
        raise AppException("tipo_invalido", f"Tipo de solicitação inválido: {tipo}.", status_code=422)
    contato = (
        client.table("julia_contatos").select("id, connection_id, chat_id").eq("id", str(lead_ref)).eq("org_id", str(org_id))
        .limit(1).execute().data or []
    )
    if not contato:
        raise AppException("lead_desconhecido", "Lead não encontrado.", status_code=404)
    agora = _agora()
    linha = {
        "id": str(uuid4()), "org_id": str(org_id), "connection_id": contato[0].get("connection_id"), "contato_id": str(contato[0]["id"]),
        "chat_id": chat_id or contato[0].get("chat_id"), "tipo": tipo, "trecho_lead": (trecho or "").strip()[:TRECHO_MAX],
        "recebida_em": agora.isoformat(), "prazo_em": (agora + timedelta(days=PRAZO_DIAS)).isoformat(),
        "status": "aberta", "notificacao_status": "pendente",
    }
    res = client.table(T).insert(linha).execute().data or []
    if not res:
        raise RuntimeError(f"julia: data-subject request not stored (lead={lead_ref})")
    logger.info("julia: data-subject request %s recorded for a human org=%s tipo=%s", res[0].get("id"), org_id, tipo)
    return notificar_admins(client, core, org_id, res[0])


def listar(
    client: Any, org_id: UUID | str, *, status: Optional[str] = None, page: int = 1, page_size: int = 20,
) -> dict[str, Any]:
    if status is not None and status not in STATUS:
        raise AppException("status_invalido", f"Status inválido: {status}.", status_code=422)
    page_size = max(1, min(page_size, PAGE_SIZE_MAX))
    q = client.table(T).select("*", count="exact").eq("org_id", str(org_id))
    if status:
        q = q.eq("status", status)
    inicio = (max(page, 1) - 1) * page_size
    res = q.order("prazo_em").range(inicio, inicio + page_size - 1).execute()
    itens = [com_situacao(r) for r in (res.data or [])]
    total = getattr(res, "count", None)
    return {"items": itens, "total": total if isinstance(total, int) else len(itens)}


def decidir(
    client: Any, org_id: UUID | str, solicitacao_id: UUID | str, user_id: str, *, status: str, motivo: Optional[str] = None,
) -> dict[str, Any]:
    """An org admin moves the request. `negada` needs the reason; whoever decided and when is stored."""
    if status not in STATUS:
        raise AppException("status_invalido", f"Status inválido: {status}.", status_code=422)
    motivo = (motivo or "").strip() or None
    if motivo and len(motivo) > MOTIVO_MAX:
        raise AppException("motivo_longo", f"O motivo aceita até {MOTIVO_MAX} caracteres.", status_code=422)
    if status == "negada" and not motivo:
        raise AppException("motivo_obrigatorio", "Informe o motivo da negativa.", status_code=422)
    rows = client.table(T).select("*").eq("id", str(solicitacao_id)).eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        raise AppException("solicitacao_nao_encontrada", "Solicitação não encontrada.", status_code=404)
    agora = _agora().isoformat()
    patch: dict[str, Any] = {"status": status, "decidido_por": str(user_id), "decidido_em": agora, "updated_at": agora}
    if motivo is not None:
        patch["motivo_decisao"] = motivo
    client.table(T).update(patch).eq("id", str(solicitacao_id)).eq("org_id", str(org_id)).execute()
    return com_situacao({**rows[0], **patch})


__all__ = ["KIND", "STATUS", "TIPOS", "com_situacao", "decidir", "listar", "notificar_admins", "registrar", "situacao_do_prazo"]
