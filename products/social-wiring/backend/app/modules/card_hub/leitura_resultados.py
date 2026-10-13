"""The model-routing learning loop's product half: record every routed read's
per-field outcome, and the human resolution that later settles it
(migration 254, `extracao_leitura_resultados`).

The seed decides (`documents.roteamento` + `documents.confianca` +
`releitura.conciliar`) and describes the read in `IdentityFields.roteamento`
(model ids, verdicts, fingerprints, cost — never a value). This module only
persists that description and, when a human settles a field, stamps which
read was right — the ground truth `noctus.dev.roteamento_modelos_recalibrar`
learns precision per (model, doc type, field) from.

Recording never blocks an extraction: a failed insert/update is LOGGED with
its reason (`logger.warning`) and the extraction carries on — the learning
loop is evidence, not a gate.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.confianca import impressao
from noctusai_lib.integrations.documents.types import IdentityFields

from app.modules.card_hub.services import _now, _t

logger = logging.getLogger(__name__)

TABELA = "extracao_leitura_resultados"

#: `clientes` column -> the seed field names whose reads it settles.
CAMPOS_DA_COLUNA: dict[str, tuple[str, ...]] = {
    "nome_oficial": ("nome",),
    "cpf": ("cpf",),
    "rg": ("rg", "rne"),
    "data_nascimento": ("data_nascimento",),
    "estado_civil": ("estado_civil",),
    "regime_bens": ("regime_bens",),
    "data_casamento": ("data_casamento",),
}


def registrar_leitura(
    client: Any,
    org_id: UUID,
    cliente_id: Optional[UUID],
    documento_id: Optional[UUID],
    tipo_documento: Optional[str],
    fields: IdentityFields,
) -> int:
    """Insert one row per critical field of a routed read. Returns how many
    rows were written (0 when the read carries no routing record — a text
    layer, the Fake — or the insert failed, which is logged)."""
    resumo = fields.roteamento
    if resumo is None or not resumo.campos:
        return 0
    usd = round(resumo.usd_total, 6)
    tok_in = sum(c.tokens_entrada for c in resumo.custos)
    tok_out = sum(c.tokens_saida for c in resumo.custos)
    linhas = [
        {
            "org_id": str(org_id),
            "cliente_id": str(cliente_id) if cliente_id else None,
            "documento_id": str(documento_id) if documento_id else None,
            "tipo_documento": tipo_documento,
            "campo": d.campo,
            "modo": resumo.modo,
            "modelo_primario": resumo.modelo_primario,
            "modelo_fallback": resumo.modelo_fallback,
            "fallback_executado": resumo.fallback_executado,
            "veredito": d.veredito,
            "motivos": list(d.motivos),
            "resultado": d.resultado,
            "acordo": d.acordo,
            "impressao_primaria": d.impressao_primaria,
            "impressao_fallback": d.impressao_fallback,
            "usd_documento": usd,
            "tokens_entrada": tok_in,
            "tokens_saida": tok_out,
        }
        for d in resumo.campos
    ]
    try:
        _t(client, TABELA).insert(linhas).execute()
    except Exception as exc:  # noqa: BLE001 — evidence, never a gate (module docstring)
        logger.warning(
            "leitura_resultados: insert of %d row(s) for documento=%s failed: %s",
            len(linhas), documento_id, exc,
        )
        return 0
    return len(linhas)


def registrar_resolucao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    coluna: str,
    *,
    resolucao: str,
    valor_final: Any = None,
) -> int:
    """A human settled `clientes.<coluna>`: stamp every still-open read
    outcome of that field for this cliente (and the `conflito_rejeitado`
    ones still waiting for the typed value) with the resolution and — when
    the final value is known — whether each read was right.

    `valor_final=None` with `resolucao='conflito_rejeitado'`: the admin said
    the PROPOSED reading is wrong but has not typed the right one yet; the
    row waits for the `edicao_manual` that follows. Returns rows updated."""
    campos = CAMPOS_DA_COLUNA.get(coluna)
    if not campos:
        return 0
    try:
        # postgrest-unbounded-ok: one cliente's reads of ONE field — a handful
        # of rows per uploaded document of that person, never near 1000.
        abertos = (
            _t(client, TABELA)
            .select("id,campo,resolucao,impressao_primaria,impressao_fallback,fallback_executado")
            .eq("org_id", str(org_id))
            .eq("cliente_id", str(cliente_id))
            .in_("campo", list(campos))
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001 — evidence, never a gate
        logger.warning("leitura_resultados: select for cliente=%s %s failed: %s", cliente_id, coluna, exc)
        return 0
    n = 0
    for row in abertos:
        if row.get("resolucao") not in (None, "conflito_rejeitado"):
            continue
        patch: dict[str, Any] = {"resolucao": resolucao, "resolvido_em": _now()}
        final = impressao(row["campo"], valor_final) if valor_final not in (None, "") else None
        if final is not None:
            patch["impressao_final"] = final
            patch["primario_correto"] = row.get("impressao_primaria") == final
            if row.get("fallback_executado"):
                patch["fallback_correto"] = row.get("impressao_fallback") == final
        elif resolucao == "conflito_rejeitado":
            # The rejected value is the conflict's PROPOSED reading B — the
            # fallback's when it read the field: known wrong, right one pending.
            if row.get("fallback_executado") and row.get("impressao_fallback"):
                patch["fallback_correto"] = False
        try:
            _t(client, TABELA).update(patch).eq("id", row["id"]).execute()
            n += 1
        except Exception as exc:  # noqa: BLE001 — evidence, never a gate
            logger.warning("leitura_resultados: update of %s failed: %s", row.get("id"), exc)
    return n


__all__ = ["CAMPOS_DA_COLUNA", "TABELA", "registrar_leitura", "registrar_resolucao"]
