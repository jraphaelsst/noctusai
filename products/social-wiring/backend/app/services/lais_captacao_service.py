"""Lais wave 8 -- Captacao (potential property captures), contract section 10.

  action `captacao`  the agent says the contato owns a property that could be captured. The handler
                     (a) inserts the `lais_captacoes` row (status `nova`), then (b) runs the wave-3
                     policy (`lais_envio_service.aplicar_politica_captacao`: records the `captacao`
                     event -- wave 6 fans it out as a notification -- and sends to the SW when the org
                     policy says `enviar`). It COMPOSES wave 3; it never forks the policy.
  registrar          creates the manual imovel through the existing `imovel_captacao` flow (migration
                     226, `captacao_service.registrar_manual`) prefilled from the row, stores its
                     codigo in `imovel_id`, status `registrada`.
  descartar          status `descartada`.

Visibility (A7) is applied by the router via `lais_acesso`: a captacao hangs off a contato.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.modules.imovel_hub import captacao_service as imovel_captacao
from app.services import lais_acesso, lais_acoes_service, lais_envio_service, lais_leads_service as leads

logger = logging.getLogger(__name__)

T_CAPTACOES = "lais_captacoes"
T_CONTATOS = "lais_contatos"
STATUS = ("nova", "registrada", "descartada")
OPERACOES = ("venda", "aluguel")
PAGE_SIZES = (5, 10, 15, 20)
#: the agent may speak in the contato vocabulary (compra) -- the table speaks venda|aluguel
_OPERACAO_DE = {"compra": "venda", "venda": "venda", "aluguel": "aluguel", "locacao": "aluguel"}
_CAMPOS_CONTATO = "id, nome, telefone_e164, canal, responsavel_user_id, connection_id, org_id"


def _texto(valor: Any, limite: int) -> Optional[str]:
    if not isinstance(valor, str):
        return None
    valor = " ".join(valor.split())
    return valor[:limite] or None


def normalizar_operacao(valor: Any) -> Optional[str]:
    return _OPERACAO_DE.get(valor.strip().lower()) if isinstance(valor, str) else None


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- the action handler ---------------------------------------------------------------
def criar(client: Any, org_id: UUID | str, contato_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    row = {
        "org_id": str(org_id), "contato_id": str(contato_id),
        "descricao": _texto(payload.get("descricao"), 2000), "endereco": _texto(payload.get("endereco"), 300),
        "operacao": normalizar_operacao(payload.get("operacao")), "status": "nova",
    }
    return client.table(T_CAPTACOES).insert(row).execute().data[0]


def _h_captacao(ctx: lais_acoes_service.AcaoCtx, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Row first (the feed must show it even if the policy leg fails), then the wave-3 policy."""
    captacao = criar(ctx.client, ctx.org_id, ctx.contato["id"], payload or {})
    politica = lais_envio_service.aplicar_politica_captacao(ctx.client, ctx.org_id, ctx.contato)
    return {"captacao_id": captacao["id"], **(politica or {})}


def registrar() -> None:
    """Bind the real `captacao` handler (replaces wave 3's policy-only one by composing it)."""
    lais_acoes_service.registrar_handler("captacao", _h_captacao)


# -- reads ----------------------------------------------------------------------------
def _contatos_de(client: Any, org_id: UUID | str, ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 200):
        for c in client.table(T_CONTATOS).select(_CAMPOS_CONTATO).eq("org_id", str(org_id)).in_("id", ids[i:i + 200]).execute().data or []:
            out[str(c["id"])] = c
    return out


def serializar(captacao: dict[str, Any], contato: Optional[dict[str, Any]]) -> dict[str, Any]:
    c = contato or {}
    return {
        "id": captacao["id"], "status": captacao["status"], "descricao": captacao.get("descricao"),
        "endereco": captacao.get("endereco"), "operacao": captacao.get("operacao"),
        "imovel_id": captacao.get("imovel_id"), "imovel_codigo": captacao.get("imovel_codigo"), "created_at": captacao["created_at"], "contato_id": captacao["contato_id"],
        "contato": {"id": c.get("id"), "nome": c.get("nome"), "telefone_e164": c.get("telefone_e164"), "canal": c.get("canal")},
    }


def listar(
    client: Any, org_id: UUID | str, ctx: lais_acesso.AcessoCtx, *, status: Optional[str], de: Optional[date], ate: Optional[date],
    page: int, page_size: int,
) -> dict[str, Any]:
    """`{items, total}`: newest first, A7-filtered (a member sees the captacoes of their contatos only)."""
    def pagina(a: int, b: int) -> Any:
        q = client.table(T_CAPTACOES).select("*").eq("org_id", str(org_id))
        if status:
            q = q.eq("status", status)
        if de:
            q = q.gte("created_at", leads._dia_ini(de))
        if ate:
            q = q.lt("created_at", leads._dia_fim(ate))
        return q.order("id").range(a, b).execute().data

    todas = sorted(iter_paged_rows(pagina, label="lais captacoes"), key=lambda r: r["created_at"], reverse=True)  # paged by id, shown newest first
    linhas = lais_acesso.filtrar_por_contato(client, ctx, todas)
    fatia = linhas[(page - 1) * page_size: page * page_size]
    contatos = _contatos_de(client, org_id, sorted({str(r["contato_id"]) for r in fatia}))
    return {"items": [serializar(r, contatos.get(str(r["contato_id"]))) for r in fatia], "total": len(linhas)}


def obter(client: Any, org_id: UUID | str, captacao_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_CAPTACOES).select("*").eq("org_id", str(org_id)).eq("id", str(captacao_id)).limit(1).execute().data or []
    if not rows:
        raise AppException("captacao_nao_encontrada", "Captação não encontrada.", status_code=404)
    return rows[0]


# -- actions --------------------------------------------------------------------------
def _exigir_nova(captacao: dict[str, Any]) -> None:
    if captacao["status"] != "nova":
        raise AppException("captacao_ja_tratada", "Esta captação já foi tratada.", status_code=409,
                           details={"status": captacao["status"], "imovel_id": captacao.get("imovel_id"), "imovel_codigo": captacao.get("imovel_codigo")})


def valores_do_imovel(captacao: dict[str, Any], corpo: dict[str, Any]) -> dict[str, Any]:
    """The prefill: titulo/endereco/finalidade/observacoes from the row; the operator's body wins."""
    texto_endereco = captacao.get("endereco")
    valores: dict[str, Any] = {"titulo": _texto(texto_endereco or captacao.get("descricao") or "Captação da Lais", 200)}
    if captacao.get("operacao"):
        valores["finalidades"] = [captacao["operacao"]]
        valores["status"] = "Venda" if captacao["operacao"] == "venda" else "Aluguel"
    if captacao.get("descricao"):
        valores["observacoes"] = captacao["descricao"][:10000]
    if texto_endereco:
        valores["endereco"] = {"logradouro": texto_endereco[:200]}
    valores.update({k: v for k, v in corpo.items() if v is not None})
    return valores


def registrar_captacao(
    client: Any, org_id: UUID, captacao_id: UUID | str, corpo: dict[str, Any], *, usuario_id: Optional[UUID],
) -> dict[str, Any]:
    captacao = obter(client, org_id, captacao_id)
    _exigir_nova(captacao)
    imovel = imovel_captacao.registrar_manual(client, org_id, valores_do_imovel(captacao, corpo), usuario_id=usuario_id)
    codigo = imovel.get("codigo_norm") or imovel["codigo"]
    exibicao = imovel.get("codigo") or codigo
    client.table(T_CAPTACOES).update({"status": "registrada", "imovel_id": codigo, "imovel_codigo": exibicao, "updated_at": _agora()}) \
        .eq("org_id", str(org_id)).eq("id", str(captacao_id)).execute()
    return {"imovel_id": codigo, "imovel_codigo": exibicao}


def descartar(client: Any, org_id: UUID, captacao_id: UUID | str) -> None:
    captacao = obter(client, org_id, captacao_id)
    if captacao["status"] == "descartada":
        return
    _exigir_nova(captacao)
    client.table(T_CAPTACOES).update({"status": "descartada", "updated_at": _agora()}) \
        .eq("org_id", str(org_id)).eq("id", str(captacao_id)).execute()


__all__ = ["OPERACOES", "PAGE_SIZES", "STATUS", "criar", "descartar", "listar", "normalizar_operacao",
           "obter", "registrar", "registrar_captacao", "serializar", "valores_do_imovel"]
