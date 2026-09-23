"""Contrato from an accepted orçamento — roadmap R10/R12, wave-2 slice A.

    gerar           aceito orçamento → `contrato` (valor_mensal = total_mensal,
                    posts_por_mes = Σ criação quantidade_mensal, valor_excedente
                    from the scope limits) + its PDF in the private bucket
    marcar_assinado física only: the printed contract came back signed (optional
                    scan) → contrato ativo, cliente ativo

THE MODALIDADE IS THE GATE (R12). `digital` goes down the existing signature
path (`contrato_documento.enviar_para_assinatura` — a flagged DRY-RUN until a
provider is homologated, `NOC-REMEDIATE[igig-assinatura]`), and its activation
arrives through the HMAC-signed webhook. `fisica` never touches e-signature: the
PDF carries hand-signature lines + the "N vias" closing, and a human marks it
signed. Marking a DIGITAL contract signed by hand is refused — that would be a
second, unsigned activation path around the webhook.

Refusals (:class:`RegraViolada`):
  409 `orcamento_nao_aceito`  contrato from an orçamento that is not aceito
  409 `contrato_existente`    this orçamento already has a live contrato
  409 `contrato_digital`      marcar-assinado on a digital contrato
  409 `contrato_ja_assinado`  marcar-assinado twice
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.integrations.storage import StorageBackend

from app.services import orcamentos as orc_svc
from app.services import quadro_comum as qc
from app.services.contrato_documento import enviar_para_assinatura
from app.services.documentos_pdf import renderizar_contrato_pdf
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = ["gerar", "marcar_assinado", "listar", "chave_documento", "URL_TTL_SEGUNDOS"]

#: Signed download links are short-lived: the bucket is private and a link in a
#: chat log should not stay a door into a client's contract for hours.
URL_TTL_SEGUNDOS = 600


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def chave_documento(org_id: str, contrato_id: str) -> str:
    return f"{org_id}/contratos/{contrato_id}/contrato.pdf"


async def gerar(
    db: Any,
    org_id: str,
    orcamento_id: str,
    *,
    modalidade: str,
    dia_vencimento: int | None,
    vias: int,
    signatario_email: str | None,
    agencia: str,
    storage: StorageBackend,
    bucket: str,
    hoje: date,
) -> dict:
    orcamento = orc_svc.obter(db, org_id, orcamento_id, hoje=hoje)
    if orcamento["status"] != "aceito":
        raise RegraViolada(
            409, "orcamento_nao_aceito",
            "Só um orçamento aceito gera contrato. Aceite o orçamento primeiro.",
        )
    existentes = [
        c for c in paged_rows(db, "contrato", org_id, eq_filters={"orcamento_id": orcamento_id},
                              select="id, status")
        if c.get("status") != "encerrado"
    ]
    if existentes:
        raise RegraViolada(409, "contrato_existente", "Este orçamento já tem um contrato gerado.")
    cliente_id = orcamento.get("cliente_id") or (orcamento.get("negocio") or {}).get("cliente_id")
    if not cliente_id:
        negocio = qc.carregar(db, "negocio", org_id, str(orcamento["negocio_id"]),
                              select="id, cliente_id", rotulo="negócio")
        cliente_id = negocio.get("cliente_id")
    if not cliente_id:
        raise RuntimeError(f"orcamento aceito {orcamento_id} sem cliente — o fechamento não criou o Cliente")
    cliente = qc.carregar(db, "cliente", org_id, str(cliente_id),
                          select="id, nome, email, telefone", rotulo="cliente")

    limites = orcamento.get("limites_escopo") or {}
    posts = sum(i["quantidade_mensal"] for i in orcamento["itens"] if i["secao"] == "criacao_conteudo")
    criado = db.table("contrato").insert({
        "org_id": org_id,
        "cliente_id": cliente["id"],
        "orcamento_id": orcamento_id,
        "valor_mensal": orcamento["total_mensal"],
        "posts_por_mes": posts,
        "valor_excedente": float(limites.get("valor_excedente") or 0),
        "dia_vencimento": dia_vencimento,
        "data_inicio": hoje.isoformat(),
        "status": "aguardando_assinatura",
        "modalidade_assinatura": modalidade,
    }).execute().data or []
    if not criado:
        raise RuntimeError("insert de contrato não retornou a linha criada")
    contrato = criado[0]
    contrato_id = str(contrato["id"])

    pdf = await anyio.to_thread.run_sync(
        lambda: renderizar_contrato_pdf(
            agencia=agencia, cliente=cliente, orcamento=orcamento, contrato=contrato,
            modalidade=modalidade, vias=vias, emitido_em=hoje,
        )
    )
    chave = chave_documento(org_id, contrato_id)
    await storage.put(bucket=bucket, key=chave, data=pdf, content_type="application/pdf")

    updates: dict[str, Any] = {"documento_key": chave}
    assinatura = None
    if modalidade == "digital":
        lead_email = (orcamento.get("lead") or {}).get("email")
        solicitacao = enviar_para_assinatura(
            org_id=org_id,
            provedor="interno",
            documento_nome=f"Contrato — {cliente.get('nome')}",
            signatario_email=signatario_email or lead_email or cliente.get("email"),
        )
        updates.update({
            "provedor_assinatura": solicitacao.provedor,
            "assinatura_external_id": solicitacao.external_id,
            "link_assinatura": solicitacao.link_assinatura,
        })
        assinatura = {
            "provedor": solicitacao.provedor,
            "link_assinatura": solicitacao.link_assinatura,
            "external_id": solicitacao.external_id,
            "dry_run": solicitacao.dry_run,
        }
    linhas = db.table("contrato").update(updates).eq("id", contrato_id).eq(
        "org_id", org_id
    ).execute().data or []
    if not linhas:
        raise RuntimeError("update de contrato não retornou a linha")
    url = await storage.signed_url(bucket=bucket, key=chave, expires_in_seconds=URL_TTL_SEGUNDOS)
    logger.info("contrato gerado org=%s contrato=%s orcamento=%s modalidade=%s",
                org_id, contrato_id, orcamento_id, modalidade)
    return {"contrato": {**contrato, **linhas[0]}, "url": url, "assinatura": assinatura}


async def marcar_assinado(
    db: Any,
    org_id: str,
    contrato_id: str,
    *,
    arquivo: tuple[bytes, str, str] | None,
    storage: StorageBackend,
    bucket: str,
) -> dict:
    """`arquivo` = (bytes, filename, content_type) of the scanned signed copy."""
    contrato = qc.carregar(db, "contrato", org_id, contrato_id, rotulo="contrato")
    if (contrato.get("modalidade_assinatura") or "digital") != "fisica":
        raise RegraViolada(
            409, "contrato_digital",
            "Este contrato é de assinatura digital — ele é ativado pela confirmação da assinatura.",
        )
    if contrato.get("status") == "ativo":
        raise RegraViolada(409, "contrato_ja_assinado", "Este contrato já está assinado.")
    agora = _agora()
    updates: dict[str, Any] = {"status": "ativo", "assinado_em": agora, "assinado_manual_em": agora}
    if arquivo is not None:
        dados, nome, tipo = arquivo
        seguro = Path(nome or "assinado.pdf").name
        chave = f"{org_id}/contratos/{contrato_id}/assinado-{seguro}"
        await storage.put(bucket=bucket, key=chave, data=dados, content_type=tipo)
        updates["documento_assinado_key"] = chave
    linhas = db.table("contrato").update(updates).eq("id", contrato_id).eq(
        "org_id", org_id
    ).execute().data or []
    if not linhas:
        raise RuntimeError("update de contrato não retornou a linha")
    # Same Módulo 1 automation the signature webhook runs for a digital one.
    db.table("cliente").update({"status": "ativo"}).eq("id", contrato["cliente_id"]).eq(
        "org_id", org_id
    ).execute()
    logger.info("contrato fisico assinado org=%s contrato=%s scan=%s",
                org_id, contrato_id, arquivo is not None)
    return {**contrato, **linhas[0]}


def listar(db: Any, org_id: str, *, cliente_id: str | None = None) -> list[dict]:
    linhas = paged_rows(db, "contrato", org_id,
                        eq_filters={"cliente_id": cliente_id} if cliente_id else None)
    linhas.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return linhas
