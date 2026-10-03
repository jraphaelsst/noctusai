"""Pacto antenupcial — one upload, the COUPLE's regime de bens (P4 deal 858,
2026-10-01: the signed contract cited the pacto's date / tabelião / livro /
página and the product had no type to file it under).

`identidade_extracao_service.extrair_identidade` routes `tipo_documento ==
'pacto_antenupcial'` here after the blob read + access log, the same
"differently-shaped reader" dispatch `ficha_cadastral_service` uses — the
seed's reading (`noctusai_lib.integrations.documents.pacto_antenupcial.
PactoAntenupcialLido`) names two people, not one titular.

`aplicar_leitura`, in order:

    (a) match each contracting party the pacto names to a party of the
        SAME atendimento(s) this upload's cliente sits on — reusing
        `ficha_cadastral_service`'s own resolution (exact CPF against a
        party who has one on file; else the uploading card by name; else a
        UNIQUE strict name match among the atendimento's parties). An
        unmatched spouse is recorded, never created;
    (b) per matched spouse, write `regime_bens` — and (migration 193) the
        escritura's citation the contract prints, `pacto_antenupcial_{data,
        tabelionato,livro,folha}` — through the SAME D1 path
        every identity source uses (`identidade_extracao_service.
        aplicar_campos_ao_cliente`): an empty field is filled machine-
        pending; an existing DIFFERENT value is never overwritten — it goes
        to `campo_conflitos` (automatic resolution or a pending conflict
        for a human). `PRECISAO` carries no `pacto_antenupcial` cell, so
        the pacto can never silently outrank a value already on file;
    (c) record the WHOLE reading on the document (`cliente_documentos.
        extracao_pacto_antenupcial`, migration 191) — the escritura's own
        facts (data, tabelionato, livro, folhas, registro) are document
        facts, not person fields, and the contract reads them from there.

🔴 PRIVACY: logs carry ids and counts only, never a read value.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.pacto_antenupcial import PactoAntenupcialLido

from app.modules.card_hub import ficha_cadastral_service as ficha_svc
from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.deps import BUCKET
from app.services import extracao_job

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = "cliente_documentos"
TIPO = "pacto_antenupcial"
ERRO_SIDE_EFFECTS_FAILED = "side_effects_failed"

#: The person fields a pacto writes: the couple's regime, and (migration 193)
#: the escritura's own citation the contract prints — data, tabelionato,
#: livro, folha(s) — onto BOTH spouses' `clientes.pacto_antenupcial_*`.
CAMPOS_PACTO: tuple = (
    identidade_svc.CAMPO_POR_CHAVE["regime_bens"],
    *identidade_svc.CAMPOS_PACTO_ESCRITURA,
)

#: The reader states a confidence for `regime_bens` only. The escritura's
#: citation (date / tabelião / livro / folhas) is read label-anchored off the
#: same text, so it is recorded at the reader's middle tier — a constant,
#: named here, never a per-field guess.
_CONFIANCA_ESCRITURA = "media"

_ROTULO = "PACTO ANTENUPCIAL"


def _lidos(lida: PactoAntenupcialLido) -> dict[str, tuple]:
    confianca = getattr(lida.regime_bens_confianca, "value", lida.regime_bens_confianca)
    escritura = {
        "pacto_antenupcial_data": _iso(lida.data_escritura),
        "pacto_antenupcial_tabelionato": lida.tabelionato,
        "pacto_antenupcial_livro": lida.livro,
        "pacto_antenupcial_folha": lida.folhas,
    }
    return {
        "regime_bens": (lida.regime_bens, confianca, _ROTULO, bool(lida.regime_bens)),
        **{
            chave: (valor, _CONFIANCA_ESCRITURA, _ROTULO, bool(valor))
            for chave, valor in escritura.items()
        },
    }


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def serializar(lida: PactoAntenupcialLido, destinos: list[Optional[str]]) -> dict:
    """The stored shape of `extracao_pacto_antenupcial` — the field names
    the contract generator reads (see migration 191's column comment)."""
    reg = lida.registro
    return {
        "regime_bens": lida.regime_bens,
        "regime_bens_confianca": getattr(
            lida.regime_bens_confianca, "value", lida.regime_bens_confianca
        ),
        "data_escritura": _iso(lida.data_escritura),
        "tabelionato": lida.tabelionato,
        "livro": lida.livro,
        "folhas": lida.folhas,
        "registro": (
            {
                "numero": reg.numero,
                "livro": reg.livro,
                "cartorio": reg.cartorio,
                "data": _iso(reg.data),
            }
            if reg is not None else None
        ),
        "data_casamento": _iso(lida.data_casamento),
        "conjuges": [
            # `cliente_id_aplicado` is a foreign key into THIS org's own
            # `clientes`, or `None` when unmatched (never created).
            {"nome": c.nome, "cpf": c.cpf, "cliente_id_aplicado": destino}
            for c, destino in zip(lida.conjuges, destinos)
        ],
        "source": getattr(lida.source, "value", lida.source),
    }


async def aplicar_leitura(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    doc: dict,
    blob_data: bytes,
    *,
    extractor: Any,
    notification_service: Optional[Any] = None,
) -> dict:
    """The whole sequence on the shared `extracao_job` runner — the reading
    is persisted and every D1 apply runs inside `_processar`'s own try; the
    TERMINAL `extracao_status` is written last. Never raises."""

    async def _ler(blob_bytes: bytes, doc_row: dict) -> PactoAntenupcialLido:
        return await extractor.extract(
            blob_bytes, mimetype=doc_row.get("mime_type"), filename=doc_row.get("nome_original"),
        )

    async def _processar(lida: PactoAntenupcialLido, doc_row: dict) -> dict:
        linhas = ficha_svc.linhas_do_atendimento(client, org_id, cliente_id)
        cpfs = ficha_svc.mapa_cpf(linhas)
        titular_row = next((r for r in linhas if str(r["id"]) == str(cliente_id)), None)
        conflitos: list[dict] = []
        destinos: list[Optional[str]] = []
        ja_atribuidos: set[str] = set()
        aplicados: list[dict] = []

        for conjuge in lida.conjuges:
            destino = ficha_svc.resolver_destino(
                conjuge, cliente_id=cliente_id, mapa_cpf=cpfs,
                titular_row=titular_row, ja_atribuidos=ja_atribuidos, linhas=linhas,
            )
            destinos.append(destino)
            if destino is None:
                continue
            ja_atribuidos.add(destino)
            lidos = _lidos(lida)
            if not any(pode for _v, _c, _r, pode in lidos.values()):
                continue
            feitos, novos = identidade_svc.aplicar_campos_ao_cliente(
                client, org_id, destino, TIPO, lidos,
                campos=CAMPOS_PACTO, documento_id=documento_id,
                fonte_tabela=DOCUMENTOS_TABLE, fonte_id=documento_id,
            )
            conflitos.extend(novos)
            aplicados.append({"cliente_id": destino, "aplicados": feitos})

        extracao_job.marcar(
            client, DOCUMENTOS_TABLE, documento_id,
            extracao_pacto_antenupcial=serializar(lida, destinos),
        )
        if conflitos:
            await identidade_svc.notificar_conflitos(client, org_id, conflitos, notification_service)

        logger.info(
            "pacto %s: %d cônjuge(s) lido(s), %d correspondido(s), %d conflito(s)",
            documento_id, len(lida.conjuges), sum(d is not None for d in destinos), len(conflitos),
        )
        return {
            "status": extracao_job.OK if lida.achou_algo else extracao_job.SEM_DADOS,
            "conjuges_encontrados": len(lida.conjuges),
            "conjuges_correspondidos": sum(1 for d in destinos if d is not None),
            "aplicados": aplicados,
            "conflitos": len(conflitos),
        }

    config = extracao_job.ExtractionJobConfig(
        table=DOCUMENTOS_TABLE,
        bucket=BUCKET,
        deve_extrair=identidade_svc.deve_extrair,
        ler=_ler,
        leitura_erro=lambda lida: lida.error,
        leitura_erro_mensagem=lambda lida: lida.error_message,
        leitura_fonte=lambda lida: getattr(lida.source, "value", lida.source),
        processar=_processar,
        erro_aplicar_codigo=ERRO_SIDE_EFFECTS_FAILED,
    )
    blob = SimpleNamespace(data=blob_data)
    return await extracao_job.executar_com_blob(client, config, documento_id, doc, blob, TIPO)
