"""Certidão -> party profile feed (CONTRACT §1.7).

An automated Receita/PGFN certidão answers "who is this CPF/CNPJ" with the
registry's own data (`nome` / `razao_social`, the document number). Until now
that data fed only the certidão row; the party's profile never saw it. After a
`cnd_federal` resultado lands, this writes what it read onto the party it is
linked to, through the SAME fill-empty / conflict-on-disagree mechanics every
other source uses:

- **PF -> `clientes`**: `nome_oficial`, `cpf`, `data_nascimento` (the last
  only when the response carries it — Receita's does not today), through
  `identidade_extracao_service.aplicar_campos_ao_cliente` with its quinteto
  provenance (`<campo>_origem/_documento_id/_em/_confirmado_*`) and
  `cliente_campo_conflitos`. Not forked: that function IS the one write
  chokepoint (CPF mod-11 refusal, another-party guard, automatic divergence
  resolution) every source funnels through.
- **PJ -> `empresas`**: `razao_social` (from the response) and
  `situacao_cadastral` / `data_situacao_cadastral` (from the consulta's own
  registration-status columns, migration 116, when somebody recorded them),
  through the `dados_*` group provenance and `empresa_campo_conflitos`.

Origem written: `certidao` (`proveniencia.fontes.FONTES["certidao"]`).

Conservative by design — the certidão is a lower-trust source than the
party's own documents:

- It never touches a group that already has provenance: an empresa whose
  `dados_*` quintet is stamped (a Cartão CNPJ, a manual edit, a prior
  certidão) is only COMPARED — a disagreement opens a conflict, an empty
  field is left for its owner. Re-stamping the group would silently demote a
  confirmed Cartão CNPJ to a machine-pending certidão read.
- A response whose document number disagrees with the consulta's is not
  evidence about this party: nothing is written (logged).
- Never raises: the certidão itself already succeeded; a feed failure is
  logged and returned, never propagated into the certidão pipeline.

Conflicts it opens are committed (`pendente`) and listed by the existing
conflict readers; this module has no notifier, so they are logged by campo
rather than announced — same posture `notificar_conflitos` documents for a
caller without a `notification_service`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.cpf import only_digits

from app.services import campo_conflitos, table_reads

logger = logging.getLogger(__name__)

ORIGEM = "certidao"

#: Only the Receita/PGFN certidão is identity-authoritative (it is keyed on the
#: CPF/CNPJ and answers with the registry's own name). Every other tipo is a
#: court/registry search ABOUT the person, not a statement of who they are.
TIPOS_FONTE = frozenset({"cnd_federal"})

#: `clientes` fields this feed may write (`identidade_extracao_service.CAMPOS`
#: item keys).
CAMPOS_PF = ("nome_oficial", "cpf", "data_nascimento")
#: `empresas` cadastral fields this feed may write.
CAMPOS_PJ = ("razao_social", "situacao_cadastral", "data_situacao_cadastral")

_CONFIANCA = "alta"
_ROTULO = "Certidão Receita/PGFN"
_EMPRESAS = "empresas"


def _texto(valor: Any) -> Optional[str]:
    if isinstance(valor, str) and valor.strip():
        return " ".join(valor.split())
    return None


def _data_iso(valor: Any) -> Optional[str]:
    """`dd/mm/aaaa` or `aaaa-mm-dd` -> ISO, else None (never guessed)."""
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto[:10], formato).date().isoformat()
        except ValueError:
            continue
    return None


def _item(raw_response: Optional[dict]) -> dict:
    data = (raw_response or {}).get("data") or []
    return data[0] if data and isinstance(data[0], dict) else {}


def _documento_da_resposta(item: dict, tipo_documento: str) -> Optional[str]:
    chaves = ("normalizado_cpf", "cpf") if tipo_documento == "cpf" else ("normalizado_cnpj", "cnpj")
    for chave in chaves:
        digitos = only_digits(str(item.get(chave) or ""))
        if digitos:
            return digitos
    return None


def lidos_pf(item: dict, consulta: dict) -> dict[str, tuple[Any, str, Optional[str], bool]]:
    """`{item_key: (valor, confianca, rotulo, pode_persistir)}` for the PF
    fields the response actually carries — the shape `aplicar_campos_ao_cliente`
    takes. A field the response does not carry is simply absent."""
    nascimento = _data_iso(
        item.get("data_nascimento") or item.get("nascimento") or item.get("birthdate")
    )
    candidatos = {
        "nome_oficial": _texto(item.get("nome")),
        "cpf": _documento_da_resposta(item, "cpf"),
        "data_nascimento": nascimento,
    }
    return {
        campo: (valor, _CONFIANCA, _ROTULO, True)
        for campo, valor in candidatos.items()
        if valor
    }


def alvos_pj(item: dict, consulta: dict) -> dict[str, Any]:
    """The PJ cadastral values to offer: `razao_social` off the response,
    situação/data off the consulta's own registration-status columns."""
    candidatos = {
        "razao_social": _texto(item.get("razao_social")),
        "situacao_cadastral": _texto(consulta.get("situacao_cadastral")),
        "data_situacao_cadastral": _data_iso(consulta.get("data_situacao")),
    }
    return {campo: valor for campo, valor in candidatos.items() if valor}


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ""


def _mesmo(atual: Any, proposto: Any) -> bool:
    return " ".join(str(atual).split()).casefold() == " ".join(str(proposto).split()).casefold()


def _e_truncamento(atual: Any, proposto: Any) -> bool:
    """`atual` is a strict prefix of `proposto` (a 40-column Crednet print of
    the same name) — not a disagreement."""
    if not isinstance(atual, str) or not isinstance(proposto, str):
        return False
    a, p = " ".join(atual.split()).casefold(), " ".join(proposto.split()).casefold()
    return bool(a) and a != p and p.startswith(a)


def alimentar_empresa(
    db: Any, org_id: Any, empresa_id: str, propostos: dict[str, Any], *, resultado_id: Optional[str]
) -> dict:
    """Fill-empty / conflict-on-disagree onto `empresas`, group provenance
    only when the group has none yet (see the module docstring)."""
    rows = (
        table_reads.table(db, _EMPRESAS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return {"aplicados": [], "conflitos": [], "aviso": "empresa_inexistente"}
    empresa = rows[0]
    sem_proveniencia = not empresa.get("dados_origem")

    patch: dict[str, Any] = {}
    conflitos: list[dict] = []
    for campo in CAMPOS_PJ:
        proposto = propostos.get(campo)
        if _vazio(proposto):
            continue
        atual = empresa.get(campo)
        if _vazio(atual):
            if sem_proveniencia:
                patch[campo] = proposto
            continue
        if _mesmo(atual, proposto) or (campo == "razao_social" and _e_truncamento(atual, proposto)):
            continue
        novo = campo_conflitos.registrar_conflito(
            db, campo_conflitos.EMPRESA, org_id, empresa_id, campo,
            valor_anterior=atual,
            origem_anterior=empresa.get("dados_origem"),
            valor_proposto=proposto,
            origem_proposto=ORIGEM,
            confianca_proposta=_CONFIANCA,
            fonte_tabela="certidao_resultados",
            fonte_id=resultado_id,
        )
        if novo is not None:
            conflitos.append(novo)

    if patch:
        agora = datetime.now(timezone.utc).isoformat()
        patch.update({
            "dados_origem": ORIGEM,
            "dados_documento_id": None,
            "dados_em": agora,
            "dados_confirmado_por": None,
            "dados_confirmado_em": None,
            "updated_at": agora,
        })
        table_reads.table(db, _EMPRESAS).update(patch).eq("id", str(empresa_id)).execute()
    return {
        "aplicados": [c for c in CAMPOS_PJ if c in patch],
        "conflitos": conflitos,
        "aviso": None,
    }


def alimentar_cliente(db: Any, org_id: Any, cliente_id: str, lidos: dict) -> dict:
    """PF half — delegates to the one `clientes` write chokepoint."""
    from app.modules.card_hub import identidade_extracao_service as identidade_svc

    campos = tuple(c for c in identidade_svc.CAMPOS if c.item_key in lidos)
    if not campos:
        return {"aplicados": [], "conflitos": [], "aviso": None}
    aplicados, conflitos = identidade_svc.aplicar_campos_ao_cliente(
        db, UUID(str(org_id)), UUID(str(cliente_id)), ORIGEM, lidos,
        campos=campos, documento_id=None,
    )
    return {
        "aplicados": [k for k, ok in aplicados.items() if ok],
        "conflitos": conflitos,
        "aviso": None,
    }


def alimentar_parte(
    db: Any, org_id: Any, consulta: dict, tipo: str, raw_response: Optional[dict],
    *, resultado_id: Optional[str] = None,
) -> dict:
    """Feed the party a certidão resultado is linked to. Never raises.

    Returns `{"aplicados": [...], "conflitos": [...], "aviso": str|None}` —
    `aviso` names why nothing was written when that is not the plain "nothing
    to offer" case (document mismatch, unknown party, failure)."""
    vazio = {"aplicados": [], "conflitos": [], "aviso": None}
    if tipo not in TIPOS_FONTE:
        return vazio
    cliente_id, empresa_id = consulta.get("cliente_id"), consulta.get("empresa_id")
    if not cliente_id and not empresa_id:
        return vazio
    item = _item(raw_response)
    if not item:
        return vazio
    tipo_documento = consulta.get("tipo_documento")
    documento = only_digits(str(consulta.get("documento") or ""))
    doc_resposta = _documento_da_resposta(item, tipo_documento or "")
    if doc_resposta and documento and doc_resposta != documento:
        logger.warning(
            "certidão %s: documento da resposta diverge da consulta %s — "
            "perfil da parte não alimentado", tipo, consulta.get("id"),
        )
        return {**vazio, "aviso": "documento_divergente"}
    try:
        if empresa_id and tipo_documento == "cnpj":
            out = alimentar_empresa(
                db, org_id, str(empresa_id), alvos_pj(item, consulta), resultado_id=resultado_id,
            )
        elif cliente_id and tipo_documento == "cpf":
            out = alimentar_cliente(db, org_id, str(cliente_id), lidos_pf(item, consulta))
        else:
            return vazio
    except Exception as exc:  # noqa: BLE001 - the certidão already succeeded
        logger.error(
            "certidão %s (consulta %s): falha ao alimentar o perfil da parte: %s",
            tipo, consulta.get("id"), exc, exc_info=True,
        )
        return {**vazio, "aviso": "falha"}
    if out["conflitos"]:
        logger.warning(
            "certidão %s (consulta %s): %d conflito(s) aberto(s) no perfil da "
            "parte, registrados e não anunciados: %s",
            tipo, consulta.get("id"), len(out["conflitos"]),
            [c.get("campo") for c in out["conflitos"]],
        )
    return out


__all__ = [
    "CAMPOS_PF",
    "CAMPOS_PJ",
    "ORIGEM",
    "TIPOS_FONTE",
    "alimentar_cliente",
    "alimentar_empresa",
    "alimentar_parte",
    "alvos_pj",
    "lidos_pf",
]
