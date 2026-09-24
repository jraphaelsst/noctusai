"""Machine-read values → `imovel_dados`, under the owner's D1 write policy
(migration 154; roadmap `sw-extraction-contract-gate-2026-09`).

THE POLICY, VERBATIM INTENT (owner, 2026-09-22)
-----------------------------------------------
- Field EMPTY → the machine fills it, provenance recorded (`<campo>_origem`
  = the document tipo, `_documento_id`, `_em`; `_confirmado_*` left NULL —
  that NULL is what makes it "machine-pending" for the D2 validation gate).
- Field already set — by a human (`origem='manual'`) OR by an earlier
  extraction — and the new reading DISAGREES → never overwritten. A
  `imovel_campo_conflitos` row is opened and a human is notified; they
  accept (the proposed value lands, confirmed by them) or reject.
- The same value again → nothing to do.

🔴 ONE NAMED EXCEPTION (owner, 2026-09-24): `prefeitura_cadastro_imobiliario`
only. The prefeitura's own document (`guia_iptu`/`cnd_iptu`) may REPLACE a
matrícula-sourced, still-UNCONFIRMED value with no conflict — the matrícula's
`CADASTRO MUNICIPAL:` block is itself only a transcription of what the
prefeitura told the cartório once; the prefeitura's own current document
outranks it. A HUMAN-touched value (`confirmado_por` or `confirmado_em` set)
is NEVER silently replaced — that still opens a conflict like any other
disagreement. See `_substituivel_por_prefeitura`.

This module is the ONE place that policy lives for `imovel_dados`. Every
extraction path (the número read off an uploaded matrícula, the full
transcription, a guia de IPTU / CND read) calls `aplicar`; none of them
writes an extracted value into `imovel_dados` any other way.

FIELD GROUPS
------------
Two contract inputs are pointers, not scalars: the título aquisitivo act
(`titulo_aquisitivo_extracao_id/_ato_id/_char_inicio/_char_fim`) and the
ônus source acts (`onus_fonte_extracao_id/_atos`). They fill and conflict as
ONE unit — half a pointer is not a value. Their provenance columns predate
154 (migration 109) and their CHECK allows only `sugerido`/`manual`, so the
machine writes `origem='sugerido'` with NULL confirmation, which the shared
field-state contract reads as machine-pending exactly like any other field.

NOTIFICATION
------------
`aplicar` never does async I/O: it returns the conflict rows it opened, and
the caller hands them to `notificar` with whatever notifier its DI chain
holds (`matriculas.deps.get_notification_service`). A missing notifier is
LOGGED — the conflict is still recorded and still listed by `listar` — never
silently dropped.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.imovel_hub import dados_service
from app.services import campo_conflitos, table_reads

logger = logging.getLogger(__name__)

CONFLITOS_TABLE = "imovel_campo_conflitos"

#: Written into `<campo>_origem` for a pointer GROUP (109's CHECK vocabulary).
ORIGEM_SUGERIDO = "sugerido"
ORIGEM_MANUAL = "manual"

#: `preenchimento_service.ORIGEM` — kept as a literal here (not imported)
#: because THAT module imports this one; a reverse import would cycle.
ORIGEM_MATRICULA = "matricula"

#: Owner rule (2026-09-24), `prefeitura_cadastro_imobiliario` only: the
#: prefeitura's own document about ITS OWN cadastral number outranks the
#: matrícula's `CADASTRO MUNICIPAL:` block, which is a transcription of
#: what the prefeitura told the cartório at some point in the past. See
#: `_substituivel_por_prefeitura`.
FONTES_PREFEITURA = frozenset({"guia_iptu", "cnd_iptu"})

FONTE_EXTRACOES = "matricula_extracoes"
FONTE_DOCUMENTOS = "imovel_documentos"


@dataclass(frozen=True)
class CampoImovel:
    """One contract-feeding `imovel_dados` field (or field group) and its
    provenance columns. `documento_id`/`em` are None where the schema has no
    such column (the 109/115 fields)."""

    chave: str
    colunas: tuple[str, ...]
    origem: str
    confirmado_por: str
    confirmado_em: str
    documento_id: Optional[str] = None
    em: Optional[str] = None
    #: The column whose value identifies a GROUP for equality (an act id),
    #: so re-deriving offsets never reads as a disagreement.
    identidade: Optional[str] = None

    @property
    def grupo(self) -> bool:
        return len(self.colunas) > 1

    def colunas_proveniencia(self) -> tuple[str, ...]:
        return tuple(
            c
            for c in (self.origem, self.documento_id, self.em, self.confirmado_por, self.confirmado_em)
            if c
        )


def _quinteto(campo: str) -> CampoImovel:
    return CampoImovel(
        chave=campo,
        colunas=(campo,),
        origem=f"{campo}_origem",
        documento_id=f"{campo}_documento_id",
        em=f"{campo}_em",
        confirmado_por=f"{campo}_confirmado_por",
        confirmado_em=f"{campo}_confirmado_em",
    )


CAMPOS: dict[str, CampoImovel] = {
    c.chave: c
    for c in (
        _quinteto("numero_matricula"),
        _quinteto("numero_registro_imoveis"),
        _quinteto("prefeitura_cadastro_imobiliario"),
        _quinteto("situacao_onus"),
        CampoImovel(
            chave="titulo_aquisitivo_texto",
            colunas=("titulo_aquisitivo_texto",),
            origem="titulo_aquisitivo_texto_origem",
            confirmado_por="titulo_aquisitivo_texto_confirmado_por",
            confirmado_em="titulo_aquisitivo_texto_confirmado_em",
        ),
        CampoImovel(
            chave="onus_credor",
            colunas=("onus_credor",),
            origem="onus_credor_origem",
            confirmado_por="onus_credor_confirmado_por",
            confirmado_em="onus_credor_confirmado_em",
        ),
        CampoImovel(
            chave="titulo_aquisitivo",
            colunas=(
                "titulo_aquisitivo_extracao_id",
                "titulo_aquisitivo_ato_id",
                "titulo_aquisitivo_char_inicio",
                "titulo_aquisitivo_char_fim",
            ),
            origem="titulo_aquisitivo_origem",
            confirmado_por="titulo_aquisitivo_confirmado_por",
            confirmado_em="titulo_aquisitivo_confirmado_em",
            identidade="titulo_aquisitivo_ato_id",
        ),
        CampoImovel(
            chave="onus_fonte",
            colunas=("onus_fonte_extracao_id", "onus_fonte_atos"),
            origem="onus_fonte_origem",
            confirmado_por="onus_fonte_confirmado_por",
            confirmado_em="onus_fonte_confirmado_em",
            identidade="onus_fonte_atos",
        ),
    )
}

#: The four scalar fields a human edits through `PATCH .../dados` and whose
#: full quintet `dados_service.atualizar` stamps `manual` / clears. Owned by
#: `dados_service` (it imports nothing from here — no cycle).
CAMPOS_QUINTETO_MANUAL = dados_service.CAMPOS_QUINTETO_MANUAL

#: `aplicar`'s outcomes.
PREENCHIDO = "preenchido"
IGUAL = "igual"
CONFLITO = "conflito"
CONFLITO_EXISTENTE = "conflito_existente"
REJEITADO_ANTES = "rejeitado_antes"
#: The precedence replace (`_substituivel_por_prefeitura`) — a prefeitura
#: document overwrote a matrícula-sourced, unconfirmed value with no
#: conflict opened. Distinct from `PREENCHIDO` (which was empty before)
#: because the field WAS already set; distinct from `CONFLITO` because no
#: human review is needed for THIS disagreement.
SUBSTITUIDO = "substituido"


@dataclass(frozen=True)
class Resultado:
    status: str
    conflito: Optional[dict] = None

    @property
    def preenchido(self) -> bool:
        return self.status in (PREENCHIDO, SUBSTITUIDO)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def pendente(row: Optional[dict], campo: CampoImovel) -> bool:
    """The shared field-state contract (roadmap §Shared field-state contract):
    machine-pending iff origem set, not manual, and not yet confirmed."""
    row = row or {}
    origem = row.get(campo.origem)
    return bool(origem) and origem != ORIGEM_MANUAL and not row.get(campo.confirmado_em)


# ─── equality ─────────────────────────────────────────────────────────────


_WS = re.compile(r"\s+")


def _norm_texto(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return _WS.sub(" ", texto).strip().casefold().rstrip(".")


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor) if c.isdigit())


#: A trailing `-<digits>` DV suffix — `23231.42.11.0377.00.000-1`'s "-1".
#: Owner rule (2026-09-24): the prefeitura's guia/CND print the inscrição
#: WITH its dígito verificador; the matrícula's `CADASTRO MUNICIPAL:` block
#: routinely does not — that alone is not a real disagreement.
_DV_SUFIXO = re.compile(r"-\d+\s*$")


def _digitos_sem_dv(valor: Any) -> str:
    return _digitos(_DV_SUFIXO.sub("", str(valor)))


def _vazio(valor: Any) -> bool:
    return valor is None or valor == "" or valor == [] or valor == {}


def _valor_atual(row: Optional[dict], campo: CampoImovel) -> Any:
    row = row or {}
    if not campo.grupo:
        return row.get(campo.colunas[0])
    valores = {c: row.get(c) for c in campo.colunas}
    return None if all(_vazio(v) for v in valores.values()) else valores


def _identidade(campo: CampoImovel, valor: Any) -> Any:
    if not isinstance(valor, dict) or campo.identidade is None:
        return valor
    ident = valor.get(campo.identidade)
    if isinstance(ident, list):
        return sorted(str(a.get("ato_id")) for a in ident if isinstance(a, dict))
    return str(ident) if ident is not None else None


def iguais(campo: CampoImovel, atual: Any, proposto: Any) -> bool:
    """Same value, modulo what a human would not call a difference:
    accents/case/whitespace/trailing period for text, punctuation for
    number-shaped fields (`45.678` == `45678`), act identity for groups."""
    if campo.grupo:
        return _identidade(campo, atual) == _identidade(campo, proposto)
    if _vazio(atual) or _vazio(proposto):
        return _vazio(atual) and _vazio(proposto)
    da, dp = _digitos(atual), _digitos(proposto)
    if campo.chave in ("numero_matricula", "prefeitura_cadastro_imobiliario") and da and dp:
        if da == dp:
            return True
        if campo.chave == "prefeitura_cadastro_imobiliario":
            return _digitos_sem_dv(atual) == _digitos_sem_dv(proposto)
        return False
    return _norm_texto(atual) == _norm_texto(proposto)


# ─── the write ────────────────────────────────────────────────────────────


def _conflitos(client: Any, org_id: UUID, codigo: str, chave: str, status: str) -> list[dict]:
    return (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("campo", chave)
        .eq("status", status)
        .limit(50)
        .execute()
    ).data or []


def _patch_valor(campo: CampoImovel, valor: Any) -> dict:
    if campo.grupo:
        return {c: valor.get(c) for c in campo.colunas}
    return {campo.colunas[0]: valor}


def _patch_preenchimento(
    campo: CampoImovel, valor: Any, *, origem: str, documento_id: Optional[Any]
) -> dict:
    """The write shape for a machine reading — a first fill AND a
    precedence replace use the exact same shape (D1's own rule: a machine
    read is attributable to a document, never to a person, so confirmation
    always starts NULL)."""
    patch = _patch_valor(campo, valor)
    patch[campo.origem] = origem
    if campo.documento_id:
        patch[campo.documento_id] = str(documento_id) if documento_id else None
    if campo.em:
        patch[campo.em] = _now()
    patch[campo.confirmado_por] = None
    patch[campo.confirmado_em] = None
    return patch


def _substituivel_por_prefeitura(
    chave: str, row: Optional[dict], campo: CampoImovel, origem_proposta: str
) -> bool:
    """Owner rule (2026-09-24), `prefeitura_cadastro_imobiliario` only: a
    reading off the prefeitura's OWN document (`FONTES_PREFEITURA`) may
    REPLACE a matrícula-sourced value with no conflict opened — the
    matrícula's `CADASTRO MUNICIPAL:` block is a transcription of what the
    prefeitura told the cartório at some point; the prefeitura's own
    current document outranks it.

    Never true once a HUMAN has touched the field — `confirmado_por` set
    (a human accepted a proposed value) or `confirmado_em` set (the D2
    confirmation timestamp) both mean a person already stands behind the
    current value, and D1's ordinary conflict rule applies exactly as it
    does for any other disagreement.
    """
    if chave != "prefeitura_cadastro_imobiliario" or origem_proposta not in FONTES_PREFEITURA:
        return False
    row = row or {}
    return (
        row.get(campo.origem) == ORIGEM_MATRICULA
        and not row.get(campo.confirmado_por)
        and not row.get(campo.confirmado_em)
    )


def aplicar(
    client: Any,
    org_id: UUID,
    codigo: str,
    chave: str,
    valor: Any,
    *,
    origem: str,
    documento_id: Optional[Any] = None,
    confianca: Optional[str] = None,
    fonte_tabela: Optional[str] = None,
    fonte_id: Optional[Any] = None,
) -> Resultado:
    """Apply ONE machine reading to ONE field, per D1. Never raises for a
    disagreement — that is a `CONFLITO`, a normal outcome. May instead
    return `SUBSTITUIDO` for `prefeitura_cadastro_imobiliario` when the
    prefeitura's own document outranks a matrícula-sourced, unconfirmed
    value — see the module docstring's precedence exception.

    Re-reads the row immediately before deciding: extractions run detached,
    and a human may have typed the value a second ago.

    `documento_id` lands in `<campo>_documento_id` (only fields that have
    one). For `numero_matricula` it must be an `imovel_documentos.id` or
    None (075's FK); the caller knows which.
    """
    campo = CAMPOS[chave]
    if _vazio(valor):
        raise ValueError(f"aplicar({chave}): refusing an empty reading")
    dados_service.ensure_imovel(client, org_id, codigo)
    row = dados_service.linha(client, org_id, codigo)
    atual = _valor_atual(row, campo)

    if _vazio(atual):
        patch = _patch_preenchimento(campo, valor, origem=origem, documento_id=documento_id)
        dados_service.gravar_extraido(client, org_id, codigo, row, patch)
        return Resultado(PREENCHIDO)

    if iguais(campo, atual, valor):
        return Resultado(IGUAL)

    if _substituivel_por_prefeitura(chave, row, campo, origem):
        patch = _patch_preenchimento(campo, valor, origem=origem, documento_id=documento_id)
        dados_service.gravar_extraido(client, org_id, codigo, row, patch)
        logger.info(
            "imovel %s: %s — %s replaced a matricula-sourced, unconfirmed "
            "value (owner precedence rule, 2026-09-24), no conflict opened",
            codigo, chave, origem,
        )
        return Resultado(SUBSTITUIDO)

    if _conflitos(client, org_id, codigo, chave, "pendente"):
        return Resultado(CONFLITO_EXISTENTE)
    # A human already said no to exactly this reading — re-running the same
    # extraction must not re-open (and re-notify) the same question.
    if any(
        iguais(campo, r.get("valor_proposto"), valor)
        for r in _conflitos(client, org_id, codigo, chave, "rejeitado")
    ):
        return Resultado(REJEITADO_ANTES)

    # The insert shape/dedupe is `app.services.campo_conflitos`' (P0c
    # contract §H6, the N=3 formalization shared with `identidade_extracao
    # _service` and `app.modules.empresas`) — the `pendente` check above
    # already proved there is nothing to dedupe against, so this always
    # inserts.
    origem_anterior = (row or {}).get(campo.origem)
    linha = campo_conflitos.registrar_conflito(
        client, campo_conflitos.IMOVEL, org_id, codigo, chave,
        valor_anterior=atual,
        origem_anterior=origem_anterior,
        valor_proposto=valor,
        origem_proposto=origem,
        confianca_proposta=confianca,
        fonte_tabela=fonte_tabela,
        fonte_id=fonte_id,
        documento_id_proposto=documento_id,
    )
    logger.info(
        "imovel %s: conflict opened on %s (atual origem=%s, proposto origem=%s)",
        codigo, chave, origem_anterior, origem,
    )
    return Resultado(CONFLITO, conflito=linha)


# ─── the human's side ─────────────────────────────────────────────────────


def listar(
    client: Any, org_id: UUID, codigo: str, *, apenas_pendentes: bool = True
) -> dict:
    """`GET /api/imoveis/{codigo}/conflitos` — newest first."""
    dados_service.ensure_imovel(client, org_id, codigo)
    query = (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
    )
    if apenas_pendentes:
        query = query.eq("status", "pendente")
    # postgrest-unbounded-ok: one imóvel's conflicts — bounded by the
    # one-open-per-field index (≤ 8 pending) and by how many times a human
    # has decided on this one property.
    rows = query.limit(500).execute().data or []
    rows = sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)
    return {"items": rows, "total": len(rows)}


def resolver(
    client: Any,
    org_id: UUID,
    codigo: str,
    conflito_id: UUID,
    *,
    aceitar: bool,
    decidido_por: Optional[Any],
) -> dict:
    """A human decides a pending conflict.

    ACCEPT: the proposed value lands with its own provenance, CONFIRMED by
    the decider (accepting IS the human validation D2 asks for).
    `valor_anterior` stays on the conflict row — the permanent way back.
    REJECT: `imovel_dados` is untouched.

    First decision wins: a decided conflict is refused (`ValidationError_`).
    """
    rows = (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("id", str(conflito_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(CONFLITOS_TABLE, str(conflito_id))
    conflito = rows[0]
    if conflito.get("status") != "pendente":
        raise ValidationError_("Este conflito já foi decidido.", field="status")

    agora = _now()
    patch = {
        "status": "aceito" if aceitar else "rejeitado",
        "decidido_por": str(decidido_por) if decidido_por else None,
        "decidido_em": agora,
    }
    _t(client, CONFLITOS_TABLE).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(conflito_id)
    ).execute()

    if aceitar:
        campo = CAMPOS[conflito["campo"]]
        valores = _patch_valor(campo, conflito["valor_proposto"])
        valores[campo.origem] = conflito["origem_proposto"]
        if campo.documento_id:
            valores[campo.documento_id] = conflito.get("documento_id_proposto")
        if campo.em:
            valores[campo.em] = agora
        valores[campo.confirmado_por] = str(decidido_por) if decidido_por else None
        valores[campo.confirmado_em] = agora
        row = dados_service.linha(client, org_id, codigo)
        dados_service.gravar_extraido(client, org_id, codigo, row, valores)

    return {**conflito, **patch}


async def notificar(
    client: Any,
    org_id: UUID,
    codigo: str,
    conflitos: list[dict],
    notificador: Optional[Any],
) -> None:
    """Announce each newly opened conflict. Best-effort by design: a down
    WAHA session or SMTP server must not fail the extraction that found the
    disagreement — the conflict row is already recorded and listed.

    The loop/try-except/`notificado_em` stamp is `app.services.
    campo_conflitos.notificar_conflitos`'s (P0c contract §H6) — this
    function keeps only this exact "no notifier" wording and the
    `notify_imovel_field_conflict` call shape.
    """
    if not conflitos:
        return
    if notificador is None:
        logger.warning(
            "imovel %s: %d conflict(s) opened with no notifier wired — recorded, "
            "not announced: %s",
            codigo, len(conflitos), [c["campo"] for c in conflitos],
        )
        return

    async def _notify_one(conflito: dict) -> None:
        await notificador.notify_imovel_field_conflict(
            org_id=org_id, conflito=conflito, codigo=codigo
        )

    await campo_conflitos.notificar_conflitos(
        client, campo_conflitos.IMOVEL, conflitos, _notify_one
    )


__all__ = [
    "CAMPOS",
    "CAMPOS_QUINTETO_MANUAL",
    "CONFLITOS_TABLE",
    "CampoImovel",
    "ORIGEM_MANUAL",
    "ORIGEM_SUGERIDO",
    "Resultado",
    "aplicar",
    "iguais",
    "listar",
    "notificar",
    "pendente",
    "resolver",
]
