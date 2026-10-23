"""Complete a CNH-sourced RG from the matrícula's averbação — by itself.

A CNH prints the RG WITHOUT its check digit; the checklist then carries the
`rg_so_da_cnh` ressalva ("confirme o número ou envie o RG/CPF") until a human
steps in. A matrícula averbação very often states the owner's FULL numbers
("o RG de FULANO é 29.790.659-8 e o CPF 219.671.678-26"). When ONE averbação
pair carries this cliente's CPF and an RG whose prefix is the CNH number, the
full RG is written (`rg_origem = 'matricula_averbacao'`) and the ressalva
drops on its own — no click. Never a guess: a CPF mismatch, a different
prefix, two competing completions, or a printed DV that fails its own check
completes nothing (the ressalva stays and asks the human).

Heal-on-read: `completar` is called where the row is read for the checklist
and for the contract loader; it is a no-op (no query) unless the row rests on
an unconfirmed CNH reading.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.rg import formatar_rg_como_impresso
from noctusai_lib.integrations.documents.rg_averbacao import (
    completar_rg_cnh,
    find_rg_cpf_averbacao,
)

from app.services import table_reads

logger = logging.getLogger(__name__)

CLIENTES_TABLE = "clientes"
ORIGEM_AVERBACAO = "matricula_averbacao"


def apoia_se_so_na_cnh(cliente: Optional[dict]) -> bool:
    """Does the RG on this row rest only on an unconfirmed CNH reading?"""
    c = cliente or {}
    return bool(c.get("rg") and c.get("cpf") and c.get("rg_origem") == "cnh" and not c.get("rg_confirmado_em"))


def _codigos_do_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> list[str]:
    """Imóveis this cliente is tied to: registered owner rows + the imóvel of
    every negociação they are titular or parte of."""
    codigos: dict[str, None] = {}
    for r in table_reads.paged_rows(
        client, "imovel_proprietarios", org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
        select="id,codigo",
    ):
        if r.get("codigo"):
            codigos[str(r["codigo"])] = None
    atendimentos = {
        str(r["id"])
        for r in table_reads.paged_rows(
            client, "atendimentos", org_id,
            eq_filters={"cliente_id": str(cliente_id)}, select="id",
        )
    } | {
        str(r["atendimento_id"])
        for r in table_reads.paged_rows(
            client, "atendimento_partes", org_id,
            eq_filters={"cliente_id": str(cliente_id)}, select="id,atendimento_id",
        )
        if r.get("atendimento_id")
    }
    if atendimentos:
        for r in table_reads.in_batched_rows(
            client, "atendimento_negociacao", org_id, "atendimento_id", sorted(atendimentos),
            select="atendimento_id,imovel_codigo", order_col="atendimento_id",
        ):
            if r.get("imovel_codigo"):
                codigos[str(r["imovel_codigo"])] = None
    return list(codigos)


def completar(client: Any, org_id: UUID, cliente_id: UUID, cliente: Optional[dict]) -> Optional[dict]:
    """Return `cliente` with the RG completed from a matrícula averbação when
    it can be (the row is also updated in the database); otherwise unchanged."""
    if not apoia_se_so_na_cnh(cliente):
        return cliente
    # Lazy: the matrícula service imports card_hub (cycle at import time).
    from app.modules.matriculas import titulo_service

    pares = []
    for codigo in _codigos_do_cliente(client, org_id, cliente_id):
        try:
            texto = titulo_service.texto_da_matricula(client, org_id, codigo)
        except Exception as exc:  # noqa: BLE001 — a heal must never break the read it rides on
            logger.warning("rg da matrícula: leitura de %s falhou para %s: %s", codigo, cliente_id, exc)
            continue
        pares.extend(find_rg_cpf_averbacao(texto or ""))
    completo = completar_rg_cnh(cliente["rg"], cliente["cpf"], pares)
    rg = formatar_rg_como_impresso(completo) if completo else None
    if not rg:
        return cliente
    from app.modules.card_hub.services import _now, _t

    agora = _now()
    _t(client, CLIENTES_TABLE).update(
        {"rg": rg, "rg_origem": ORIGEM_AVERBACAO, "rg_em": agora, "updated_at": agora}
    ).eq("org_id", str(org_id)).eq("id", str(cliente_id)).execute()
    logger.info("rg do cliente %s completado pela averbação da matrícula", cliente_id)
    return {**cliente, "rg": rg, "rg_origem": ORIGEM_AVERBACAO, "rg_em": agora}
