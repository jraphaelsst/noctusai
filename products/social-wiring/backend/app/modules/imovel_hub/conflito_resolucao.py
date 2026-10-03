"""Automatic resolution of an `imovel_campo_conflitos` divergence — the
imóvel twin of `app.services.divergencia_resolucao` (which decides the
`clientes` fields). Owner directive (2026-09-29): "resolve divergencies
without the need of a human"; the 2026-10-03 P3/P4 test loop measured why
contracts still blocked: values written by readers that have since been FIXED
now conflict with the fixed reader's correct fresh read of the same matrícula.

WHAT THIS IS
------------
A deterministic policy over evidence the database already holds — no tier
table, no vote, no model call. `decidir` returns a `Decisao` (the same type
the cliente resolver returns, persisted through the same
`campo_conflitos.registrar_decisao_automatica` audit write); the WRITE back
onto `imovel_dados` stays with `campos_extraidos_service` (the ONE place the
D1 write policy lives).

THE RULES, IN ORDER
-------------------
1. **equivalencia** — the two readings are the same value
   (`campos_extraidos_service.iguais`, incl. the cartório's book header /
   CNS / formatting noise and the inscrição read in its município's mask):
   nothing to decide, the on-file value stays.
2. **cartorio_localidade** (`numero_registro_imoveis`) — one reading is the
   other plus its locality (`SERVENTIA DO REGISTRO DE IMÓVEIS` →
   `... de Cotia`): same serventia, the reading naming its city is kept
   (`identificadores.cartorio_refinamento`).
3. **autoridade_prefeitura** (`prefeitura_cadastro_imobiliario`) — the
   prefeitura's own document (`guia_iptu`/`cnd_iptu`) about ITS OWN cadastral
   number outranks the matrícula's transcription of it (owner rule
   2026-09-24, the same ranking `_substituivel_por_prefeitura` applies on
   the live write). Two prefeitura documents that disagree stay human.
4. **proposta_substituida** — the proposal came from a matrícula extraction
   that has itself been SUPERSEDED (`matricula_extracoes.substituida_por`):
   its document is no longer current, the proposal is retracted (the same
   positive-retraction posture as the cliente resolver's `retratado`). The
   live tip's own fill proposes again, if it disagrees.
5. **extracao_substituida** — the ON-FILE value came from a superseded
   extraction (an earlier pass of a reader that has since been re-run) and
   the proposal comes from a LIVE (not superseded) extraction of the same
   imóvel: the stale reading loses to the current one.

Across every rule: **a human-entered or human-confirmed value is never
overridden** (`origem='manual'`, or `confirmado_por` set). The autopilot's
own confirmation (`confirmado_por IS NULL AND confirmado_em IS NOT NULL`,
`matriculas.autopiloto_service`) is a MACHINE vouch for an old reader's
output, not a person's — it does not protect a value from a fixed reader.
A verdict that keeps the human's value still stands.

Everything else returns `requer_humano=True` — the caller opens (or leaves)
the conflict exactly as before.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from app.services import identificadores as idf
from app.services import table_reads
from app.services.divergencia_resolucao import Decisao

logger = logging.getLogger(__name__)

#: The prefeitura's own documents about its own cadastral number (owner rule
#: 2026-09-24). Canonical here; `campos_extraidos_service.FONTES_PREFEITURA`
#: is this same object.
FONTES_PREFEITURA = frozenset({"guia_iptu", "cnd_iptu"})

#: A transcription of the cadastral number on the matrícula — what the
#: prefeitura told the cartório once. `"ia"` is the autopilot's re-stamp of a
#: matrícula reading (it never touches this field today; listed so a future
#: re-stamp cannot silently promote the transcription).
ORIGENS_TRANSCRICAO = frozenset({"matricula", "ia"})

ORIGEM_MANUAL = "manual"
EXTRACOES_TABLE = "matricula_extracoes"

HUMANO = Decisao(
    vencedor=None, regra="requer_humano",
    motivo="Nenhuma regra determinística separa as duas leituras — decisão "
           "humana necessária.",
    requer_humano=True,
)


def _decisao(vencedor: str, regra: str, motivo: str) -> Decisao:
    return Decisao(vencedor=vencedor, regra=regra, motivo=motivo, requer_humano=False)


def valor_humano(row: Optional[dict], campo: Any) -> bool:
    """A person typed or vouched for this field's current value."""
    row = row or {}
    return row.get(campo.origem) == ORIGEM_MANUAL or bool(row.get(campo.confirmado_por))


def extracao_do_valor(campo: Any, valor: Any, row: Optional[dict]) -> Optional[str]:
    """The `matricula_extracoes.id` a value was read from, when knowable:
    the pointer group's own `<chave>_extracao_id`, or the scalar's
    `<campo>_documento_id` (the matrícula fill stores the extraction id
    there). None otherwise — and a non-extraction id simply finds no row."""
    if campo.grupo:
        if isinstance(valor, dict):
            eid = valor.get(f"{campo.chave}_extracao_id")
            return str(eid) if eid else None
        return None
    if campo.documento_id and row:
        did = row.get(campo.documento_id)
        return str(did) if did else None
    return None


def _extracao(client: Any, org_id: UUID, eid: Optional[str]) -> Optional[dict]:
    if not eid:
        return None
    rows = (
        table_reads.table(client, EXTRACOES_TABLE)
        .select("id,codigo,status,substituida_por")
        .eq("org_id", str(org_id))
        .eq("id", str(eid))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def decidir(
    client: Any,
    org_id: UUID,
    codigo: str,
    campo: Any,
    row: Optional[dict],
    *,
    valor_atual: Any,
    origem_atual: Optional[str],
    valor_proposto: Any,
    origem_proposto: Optional[str],
    fonte_tabela: Optional[str],
    fonte_id: Optional[Any],
    iguais: Callable[[Any, Any, Any], bool],
) -> tuple[Decisao, tuple[str, ...]]:
    """Decide one imóvel divergence. Returns `(decisao, evidencia_ids)` —
    the ids of the extractions/documents the deciding rule read, for the
    audit trail. `iguais(campo, a, b)` is `campos_extraidos_service.iguais`
    (injected: that module imports this one). `row` is the CURRENT
    `imovel_dados` row — re-read by the caller right before deciding."""
    decisao, evidencia = _decidir(
        client, org_id, codigo, campo, row,
        valor_atual=valor_atual, origem_atual=origem_atual,
        valor_proposto=valor_proposto, origem_proposto=origem_proposto,
        fonte_tabela=fonte_tabela, fonte_id=fonte_id, iguais=iguais,
    )
    if decisao.vencedor == "proposto" and valor_humano(row, campo):
        return Decisao(
            vencedor=None, regra="valor_humano",
            motivo=f"{campo.chave}: o valor em registro foi digitado ou "
                   f"confirmado por uma pessoa — nunca sobrescrito "
                   f"automaticamente; a regra {decisao.regra!r} preferiria o proposto.",
            requer_humano=True,
        ), evidencia
    return decisao, evidencia


def _decidir(
    client: Any,
    org_id: UUID,
    codigo: str,
    campo: Any,
    row: Optional[dict],
    *,
    valor_atual: Any,
    origem_atual: Optional[str],
    valor_proposto: Any,
    origem_proposto: Optional[str],
    fonte_tabela: Optional[str],
    fonte_id: Optional[Any],
    iguais: Callable[[Any, Any, Any], bool],
) -> tuple[Decisao, tuple[str, ...]]:
    chave = campo.chave

    # 1. Equivalence.
    if iguais(campo, valor_atual, valor_proposto):
        return _decisao(
            "atual", "equivalencia",
            f"{chave}: as duas leituras ({origem_atual} e {origem_proposto}) "
            f"são o mesmo valor, só muda a formatação — nada a decidir.",
        ), ()

    # 2. Cartório: one reading = the other + its locality.
    if chave == "numero_registro_imoveis":
        rel = idf.cartorio_refinamento(valor_atual, valor_proposto)
        if rel in (idf.MAIS_COMPLETO_A, idf.MAIS_COMPLETO_B):
            vencedor = "atual" if rel == idf.MAIS_COMPLETO_A else "proposto"
            return _decisao(
                vencedor, "cartorio_localidade",
                f"{chave}: a mesma serventia nas duas leituras; só a "
                f"{'em registro' if vencedor == 'atual' else 'proposta'} "
                f"nomeia a cidade — mantida a leitura completa.",
            ), ()

    # 3. The prefeitura's own document outranks the matrícula's transcription.
    if chave == "prefeitura_cadastro_imobiliario":
        if origem_atual in FONTES_PREFEITURA and origem_proposto in ORIGENS_TRANSCRICAO:
            return _decisao(
                "atual", "autoridade_prefeitura",
                f"{chave}: o documento da própria prefeitura ({origem_atual}) "
                f"prevalece sobre a transcrição da matrícula ({origem_proposto}).",
            ), ()
        if origem_proposto in FONTES_PREFEITURA and origem_atual in ORIGENS_TRANSCRICAO:
            return _decisao(
                "proposto", "autoridade_prefeitura",
                f"{chave}: o documento da própria prefeitura ({origem_proposto}) "
                f"prevalece sobre a transcrição da matrícula ({origem_atual}).",
            ), ()

    # 4/5. Superseded matrícula extractions.
    if fonte_tabela == EXTRACOES_TABLE and fonte_id:
        prop = _extracao(client, org_id, str(fonte_id))
        if prop is not None and prop.get("substituida_por"):
            return _decisao(
                "atual", "proposta_substituida",
                f"{chave}: a extração da matrícula que propôs este valor foi "
                f"substituída por uma nova extração — a proposta não vale mais.",
            ), (str(prop["id"]), str(prop["substituida_por"]))
        cur = _extracao(client, org_id, extracao_do_valor(campo, valor_atual, row))
        if (
            prop is not None
            and cur is not None
            and cur.get("substituida_por")
            and str(cur.get("codigo") or "") == str(codigo)
            and str(prop.get("codigo") or "") == str(codigo)
        ):
            return _decisao(
                "proposto", "extracao_substituida",
                f"{chave}: o valor em registro veio de uma extração da matrícula "
                f"já substituída; a proposta vem da extração vigente do mesmo imóvel.",
            ), (str(cur["id"]), str(prop["id"]))

    return HUMANO, ()


__all__ = [
    "EXTRACOES_TABLE",
    "FONTES_PREFEITURA",
    "HUMANO",
    "ORIGENS_TRANSCRICAO",
    "decidir",
    "extracao_do_valor",
    "valor_humano",
]
