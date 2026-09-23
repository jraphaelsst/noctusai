"""Matrícula party qualification -> the existing extraction pipeline
(migration 137).

WHAT THIS IS
------------
`noctusai_lib.integrations.documents.matricula_qualificacao` reads every
party a matrícula's act text qualifies by CPF/CNPJ — name, nacionalidade,
estado civil, profissão, RG + órgão, endereço, gênero. Nothing consumed it
before this module. This is that consumer, and it is deliberately built as a
new SOURCE for `identidade_extracao_service`'s existing suggest/confirm/apply
pipeline, not a second one — see migration 137's header for the full design
reasoning (why this is its own table, how a suggestion is keyed before a
cliente exists, why `endereco` is never auto-applied).

WHEN ROWS ARE WRITTEN
----------------------
At segmentation, same moment `estrutura_service.persistir_atos` mints
`matricula_ato_detalhes` rows: `persistir_sugestoes` runs
`extrair_qualificacoes` per R/AV act, `mesclar_qualificacoes` to consolidate
across acts, matches each consolidated person against this org's `clientes`
by normalised CPF/CNPJ, and inserts one row per person. Self-heals on read
the same way (`qualificacoes_da_extracao`) — an extraction with acts but zero
qualification rows (segmented before this module shipped, or whose insert
failed) gets them minted the first time anything asks.

🔴 NO SEPARATE ACCESS-LOG ACTION
---------------------------------
`estrutura_service.listar_atos` already logs `text_view` for the SAME
`texto_extraido` these rows are derived from — its own docstring already
states the reasoning 115 used for NOT giving `detalhes` a second log action:
"readings OF the text this response already hands back". Qualificações ride
the same response (`listar_atos`'s `qualificacoes` key), so they ride the
same log.

🔴 CONFIRMING DOES NOT MERGE INTO `identidade_extracao_service
.sugestoes_pendentes`
---------------------------------------------------------------------------
That function reads `cliente_documentos` rows scoped to `cliente_id` — a
shape this source structurally cannot produce (migration 137's header). A
matrícula-matched cliente's confirmed fields land on `clientes` through the
exact same `aplicar_campos_ao_cliente` mechanics `sugestoes_pendentes`'
sibling functions use, and are therefore visible wherever cliente data is
already read — but a PENDING (unconfirmed) matrícula suggestion is only
visible via THIS module's own surface (the matrícula extraction's
`listar_atos` response), not via a cliente card's identity-suggestions
panel. NOC-REMEDIATE[matricula-qualificacao-card-merge]: teaching
`sugestoes_pendentes` to also read `matricula_qualificacoes` is a real,
separate follow-up (mixing two suggestion-source shapes cleanly deserves its
own design pass, not a rushed bolt-on) — 2026-09-18.

🔴 FILL-EMPTY THE MOMENT A ROW IS `vinculado` — NOT ONLY ON `confirmar`
-------------------------------------------------------------------------
Migration 153's D1 (owner directive, 2026-09-22) already governs
`identidade_extracao_service.extrair_identidade`: a machine reading fills
whatever is EMPTY on `clientes`, with provenance, `confirmado_por=None`
(machine-pending, for the contract's validation gate) — no human has to
click anything first. `persistir_sugestoes` now applies that SAME policy the
instant `_linha` resolves a party to exactly one cliente
(`vinculo_status='vinculado'`) — see `_aplicar_automatico`, called for every
freshly-inserted `vinculado` row before this function returns. `confirmar`
still runs the identical mechanics with `confirmado_por=usuario_id` — a
human vouching for a value that was already applied machine-pending simply
re-stamps it confirmed (or opens/leaves the conflict `aplicar_campos_ao_cliente`
already returned `False` for). `backfill_aplicar_campos_vinculados` is the
one-time catch-up for rows written before this hook existed — idempotent by
construction, since a field already filled (by either path) is left alone.

NOC-REMEDIATE[matricula-qualificacao-auto-apply-notify]: a conflict this
auto-apply opens is logged (`logger.info`) but NOT fanned out through
`notification_service` — `persistir_sugestoes` runs synchronously from
`estrutura_service.persistir_atos` (itself called from a background-task
bridge, `router._run_extraction`), and threading an async notifier through
that whole chain is a real, separate follow-up; an admin still sees the
conflict via the general `conflitos_pendentes` queue. — 2026-09-23.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import (
    Qualificacao,
    QualificacaoConsolidada,
    extrair_qualificacoes,
    mesclar_qualificacoes,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from noctusai_lib.integrations.documents import canonical_gender

from app.modules.card_hub.identidade_extracao_service import (
    CampoExtraido,
    aplicar_campos_ao_cliente,
    notificar_conflitos,
)
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

TABLE = "matricula_qualificacoes"
CLIENTES_TABLE = "clientes"

#: Where a matrícula-sourced value's `<campo>_origem` reads on `clientes` —
#: distinct from a `tipo_documento` value (`'rg'`, `'cpf'`, ...) because this
#: source is not a `cliente_documentos` row at all. See migration 137.
ORIGEM_MATRICULA = "matricula"

VINCULADO = "vinculado"
SEM_CORRESPONDENCIA = "sem_correspondencia"
AMBIGUO = "ambiguo"

#: The fields `aplicar_campos_ao_cliente` may write onto `clientes` when an
#: operator confirms a matrícula qualification. Reuses
#: `identidade_extracao_service.CampoExtraido` — the dataclass IS the reusable
#: surface, not `identidade_extracao_service.CAMPOS` itself, because none of
#: these entries has a `cliente_documentos` reading to point `coluna_valor`
#: at (this source never writes that table) — see migration 137's header for
#: why nacionalidade/profissao are new `clientes` provenance quintets rather
#: than additions to the document-extraction `CAMPOS` tuple.
#:
#: `endereco` is deliberately ABSENT — see migration 137's header
#: (NOC-REMEDIATE[matricula-endereco-estruturado]).
CAMPOS_QUALIFICACAO: tuple[CampoExtraido, ...] = (
    # `sobrescreve` is not consulted on the write path any more — D1
    # (migration 153): `aplicar_campos_ao_cliente` never overwrites, a
    # differing value opens a conflict. Kept False everywhere for honesty.
    CampoExtraido(
        item_key="nome_oficial",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="genero",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="cpf",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="rg",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
    # Migration 153 — the issuer has its own provenance now instead of
    # riding along with `rg` via a keyword argument; `depende_de="rg"`
    # keeps it from landing beside somebody else's RG number.
    CampoExtraido(
        item_key="rg_orgao_expedidor",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
        depende_de="rg",
    ),
    CampoExtraido(
        item_key="estado_civil",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="nacionalidade",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
    CampoExtraido(
        item_key="profissao",
        coluna_valor="",
        coluna_confianca="",
        coluna_rotulo="",
        sobrescreve=False,
    ),
)


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _digitos(valor: Optional[str]) -> str:
    return re.sub(r"\D", "", valor or "")


def _clientes_por_cpf(client: Any, org_id: Any) -> dict[str, list[str]]:
    """`{cpf_normalizado: [cliente_id, ...]}` for every cliente in this org
    that has a CPF/CNPJ on file.

    CPF/CNPJ never carry a check-digit letter the way an RG can, so a plain
    digit strip on both sides is exact — the same comparison
    `normalizar_documento` makes SQL-side (097), done here in Python because
    PostgREST cannot filter on that expression directly.
    """
    rows = table_reads.paged_rows(
        client,
        CLIENTES_TABLE,
        org_id,
        select="id,cpf",
        refine=lambda q: q.not_.is_("cpf", "null"),
    )
    out: dict[str, list[str]] = {}
    for row in rows:
        chave = _digitos(row.get("cpf"))
        if not chave:
            continue
        out.setdefault(chave, []).append(row["id"])
    return out


def _vincular(
    normalizado: str, por_cpf: dict[str, list[str]]
) -> tuple[Optional[str], str]:
    """`(cliente_id, vinculo_status)` for one normalised CPF/CNPJ — the
    three-outcome contract migration 137's header names. Never picks one of
    several matches."""
    candidatos = por_cpf.get(normalizado) or []
    if len(candidatos) == 1:
        return candidatos[0], VINCULADO
    if len(candidatos) > 1:
        return None, AMBIGUO
    return None, SEM_CORRESPONDENCIA


def _linha(
    org_id: str,
    extracao_id: str,
    consolidada: QualificacaoConsolidada,
    por_cpf: dict[str, list[str]],
) -> Optional[dict]:
    q: Qualificacao = consolidada.qualificacao
    normalizado = _digitos(q.cpf_cnpj)
    if not normalizado:
        return None  # mesclar_qualificacoes never emits this; defensive only
    cliente_id, vinculo = _vincular(normalizado, por_cpf)
    return {
        "id": str(uuid4()),
        "org_id": org_id,
        "extracao_id": extracao_id,
        "cpf_cnpj": q.cpf_cnpj,
        "cpf_cnpj_normalizado": normalizado,
        "nome": q.nome,
        "nacionalidade": q.nacionalidade,
        "estado_civil": q.estado_civil,
        "profissao": q.profissao,
        "rg": q.rg,
        "rg_orgao_expedidor": q.rg_orgao_expedidor,
        "endereco": q.endereco,
        "genero": q.genero,
        "nome_inicio": q.nome_inicio,
        "nome_fim": q.nome_fim,
        "confianca": q.confianca,
        "origem": {k: str(v) for k, v in consolidada.origem.items()},
        "cliente_id": cliente_id,
        "vinculo_status": vinculo,
        "confirmado_por": None,
        "confirmado_em": None,
        "aplicado_campos": None,
        "descartado_por": None,
        "descartado_em": None,
    }


def persistir_sugestoes(
    db: Any, org_id: Any, extracao_id: str, texto: str, ato_rows: list[dict]
) -> int:
    """Insert one row per person `mesclar_qualificacoes` consolidates out of
    `ato_rows`. Returns how many were written.

    The caller guarantees this extraction has no qualificação rows yet
    (fresh acts at segmentation; the missing case in
    `qualificacoes_da_extracao`) — same discipline
    `ato_detalhes_service.persistir_sugestoes` documents. The
    `UNIQUE (extracao_id, cpf_cnpj_normalizado)` constraint is the backstop
    for a concurrent double-heal.

    Every freshly-inserted `vinculado` row is fed straight into
    `_aplicar_automatico` — see the module docstring's D1 paragraph. A
    per-row failure there is logged and skipped, never raised: the acts and
    the qualificação rows are already written and are the product (same
    posture `estrutura_service.persistir_atos` already documents for THIS
    function's own call); `backfill_aplicar_campos_vinculados` is the net
    for whatever a transient failure leaves unfilled.
    """
    atos = [r for r in ato_rows if r["kind"] != "abertura"]
    if not atos or not (texto or "").strip():
        return 0
    por_ato = [
        (str(row["id"]), extrair_qualificacoes(texto, int(row["char_inicio"]), int(row["char_fim"])))
        for row in sorted(atos, key=lambda r: r["ordem"])
    ]
    consolidadas = mesclar_qualificacoes(por_ato)
    if not consolidadas:
        return 0
    por_cpf = _clientes_por_cpf(db, org_id)
    org = str(org_id)
    linhas = [
        linha
        for linha in (_linha(org, str(extracao_id), c, por_cpf) for c in consolidadas)
        if linha is not None
    ]
    if linhas:
        _t(db, TABLE).insert(linhas).execute()
        for linha in linhas:
            try:
                _aplicados, conflitos = _aplicar_automatico(db, org_id, linha)
            except Exception:  # noqa: BLE001 - row landed; backfill is the net
                logger.error(
                    "matricula %s: qualificação %s inserted but its "
                    "auto-apply-to-cliente failed — see "
                    "backfill_aplicar_campos_vinculados",
                    extracao_id,
                    linha["id"],
                    exc_info=True,
                )
                continue
            if conflitos:
                logger.info(
                    "matricula %s: qualificação %s opened %d admin "
                    "conflict(s) instead of applying unattended: %s",
                    extracao_id,
                    linha["id"],
                    len(conflitos),
                    [c["campo"] for c in conflitos],
                )
    return len(linhas)


def linhas_da_extracao(client: Any, org_id: Any, extracao_id: Any) -> list[dict]:
    return table_reads.paged_rows(
        client, TABLE, org_id, eq_filters={"extracao_id": str(extracao_id)}
    )


def qualificacoes_da_extracao(
    client: Any, org_id: Any, extracao: dict, ato_rows: list[dict]
) -> list[dict]:
    """Every qualificação row for this extraction, minting the missing ones
    on read (the backfill — see module docstring). An extraction whose text
    was purged heals nothing: there is no text left to read."""
    existentes = linhas_da_extracao(client, org_id, extracao["id"])
    texto = extracao.get("texto_extraido")
    if not existentes and texto:
        escritas = persistir_sugestoes(client, org_id, extracao["id"], texto, ato_rows)
        if escritas:
            logger.info(
                "matricula %s: backfilled %d qualificacao suggestions on read",
                extracao["id"],
                escritas,
            )
            existentes = linhas_da_extracao(client, org_id, extracao["id"])
    return existentes


def qualificacao_saida(row: dict, resolved: dict) -> dict:
    """The API shape of one row."""
    return {
        "id": row["id"],
        "cpf_cnpj": row["cpf_cnpj"],
        "nome": row["nome"],
        "nacionalidade": row.get("nacionalidade"),
        "estado_civil": row.get("estado_civil"),
        "profissao": row.get("profissao"),
        "rg": row.get("rg"),
        "rg_orgao_expedidor": row.get("rg_orgao_expedidor"),
        "endereco": row.get("endereco"),
        "genero": row.get("genero"),
        "nome_inicio": row.get("nome_inicio"),
        "nome_fim": row.get("nome_fim"),
        "confianca": row["confianca"],
        "origem": row.get("origem") or {},
        "cliente_id": row.get("cliente_id"),
        "vinculo_status": row["vinculo_status"],
        "confirmado_por": table_reads.actor(resolved, row.get("confirmado_por")),
        "confirmado_em": row.get("confirmado_em"),
        "aplicado_campos": row.get("aplicado_campos"),
        "descartado_por": table_reads.actor(resolved, row.get("descartado_por")),
        "descartado_em": row.get("descartado_em"),
    }


def _linha_por_id(client: Any, org_id: Any, qualificacao_id: Any) -> dict:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(qualificacao_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE, str(qualificacao_id))
    return rows[0]


def _lidos(row: dict) -> dict[str, tuple[Any, str, Optional[str], bool]]:
    """`Qualificacao` fields -> the `lidos` shape `aplicar_campos_ao_cliente`
    expects, `pode_persistir=True` for every field — a human just confirmed
    this row, so nothing is held back the way an unattended BAIXA read would
    be. `nome` maps to the `nome_oficial` item_key, mirroring
    `identidade_extracao_service._valores_lidos`."""
    confianca = row["confianca"]
    valores = {
        "nome_oficial": row.get("nome"),
        # 🔴 The matrícula reader emits `m`/`f` codes; `clientes.genero` holds
        # the words `Masculino`/`Feminino` (the card dropdown, the identity
        # extractor). Writing the code made every later RG/CIN reading of the
        # SAME fact look like a disagreement. Canonicalised here, at the one
        # place a qualification becomes a client field (migration 153 also
        # repairs the rows already written).
        "genero": canonical_gender(row.get("genero")),
        "cpf": _formatar_cpf_para_cliente(row),
        "rg": row.get("rg"),
        "rg_orgao_expedidor": row.get("rg_orgao_expedidor"),
        "estado_civil": row.get("estado_civil"),
        "nacionalidade": row.get("nacionalidade"),
        "profissao": row.get("profissao"),
    }
    return {k: (v, confianca, None, True) for k, v in valores.items()}


def _aplicar_automatico(client: Any, org_id: Any, row: dict) -> tuple[dict[str, bool], list[dict]]:
    """Fill-empty, with provenance, the instant a qualificação is
    `vinculado` to a cliente — no human involved yet (D1, migration 153).
    Same mechanics `confirmar` uses, `confirmado_por=None` instead of the
    operator's id: a field already SET that disagrees opens a conflict
    (`aplicar_campos_ao_cliente`), never an overwrite; a field that already
    agrees, or is already machine-pending from the same source, is a no-op —
    which is what makes re-running this (`backfill_aplicar_campos_vinculados`,
    or a second `persistir_sugestoes` self-heal) safe.

    A no-op tuple for a row that is not (yet) `vinculado` — `_linha` already
    guarantees `cliente_id` is set whenever `vinculo_status == VINCULADO`,
    this is the defensive mirror for a caller handing back a stale/foreign
    dict (the backfill reads rows straight off the table).
    """
    if row.get("vinculo_status") != VINCULADO or not row.get("cliente_id"):
        return {c.item_key: False for c in CAMPOS_QUALIFICACAO}, []
    lidos = _lidos(row)
    return aplicar_campos_ao_cliente(
        client,
        org_id,
        row["cliente_id"],
        ORIGEM_MATRICULA,
        lidos,
        campos=CAMPOS_QUALIFICACAO,
        documento_id=None,
        fonte_tabela=TABLE,
        fonte_id=row["id"],
        # Machine-pending — see the module docstring's D1 paragraph. A human
        # who later clicks `confirmar` re-runs this with their own id and
        # stamps whatever is still unconfirmed.
        confirmado_por=None,
    )


def _formatar_cpf_para_cliente(row: dict) -> Optional[str]:
    """`cpf_cnpj` only promotes to `clientes.cpf` when it is CPF-shaped (11
    digits) — a matrícula party anchored on a CNPJ is a legal entity and has
    no `cpf` to write. Harmless either way under `sobrescreve=False`: the
    matched cliente was found BY this same value, so `clientes.cpf` is
    already set and this write is always a no-op in practice — kept for
    completeness/consistency with the other CAMPOS_QUALIFICACAO entries."""
    normalizado = _digitos(row.get("cpf_cnpj"))
    return row.get("cpf_cnpj") if len(normalizado) == 11 else None


async def confirmar(
    client: Any,
    org_id: Any,
    qualificacao_id: Any,
    *,
    usuario_id: Optional[Any] = None,
    notification_service: Optional[Any] = None,
) -> dict:
    """A human vouches for a matrícula reading: apply every field it carries
    onto the matched cliente, when there is one.

    Refuses a discarded suggestion. A row with `vinculo_status !=
    'vinculado'` still gets `confirmado_por/em` stamped — "yes, I looked at
    this" is a real, recordable act even when there is no cliente yet to
    write onto — but `aplicado_campos` stays empty, honestly.

    🔴 Migration 138: a field that DISAGREES with what is already on the
    matched cliente opens a `cliente_campo_conflitos` row instead of
    applying (see `aplicar_campos_ao_cliente`) — `aplicado_campos[campo]`
    reads `False` for it, same as any other declined field, and
    `conflitos_abertos` names it explicitly so the caller (and the return
    payload) never has to guess why. `notification_service`, when given
    (the router wires `matriculas.deps.get_notification_service`), fans out
    an admin alert per NEWLY opened conflict — best-effort: a notification
    failure is logged, never raised, so a down WAAH session/SMTP server
    cannot turn a real confirmation into a 500.
    """
    row = _linha_por_id(client, org_id, qualificacao_id)
    if row.get("descartado_em"):
        raise ValidationError_(
            "Esta sugestão já foi descartada.", field="descartado_em"
        )

    aplicados: dict[str, bool] = {}
    conflitos: list[dict] = []
    if row["vinculo_status"] == VINCULADO and row.get("cliente_id"):
        lidos = _lidos(row)
        aplicados, conflitos = aplicar_campos_ao_cliente(
            client,
            org_id,
            row["cliente_id"],
            ORIGEM_MATRICULA,
            lidos,
            campos=CAMPOS_QUALIFICACAO,
            documento_id=None,
            fonte_tabela=TABLE,
            fonte_id=qualificacao_id,
            # A human just confirmed this reading — the fields it fills are
            # validated, not machine-pending.
            confirmado_por=usuario_id,
        )

    agora = now_iso()
    patch = {
        "confirmado_por": str(usuario_id) if usuario_id else None,
        "confirmado_em": agora,
        "aplicado_campos": aplicados,
    }
    _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(qualificacao_id)
    ).execute()

    # The shared announcer (`identidade_extracao_service.notificar_
    # conflitos`) — this module used to carry its own copy of that loop.
    await notificar_conflitos(
        client, org_id, conflitos, notification_service, cliente_nome=row["nome"]
    )

    return {**row, **patch, "conflitos_abertos": [c["campo"] for c in conflitos]}


def descartar(
    client: Any, org_id: Any, qualificacao_id: Any, *, usuario_id: Optional[Any] = None
) -> dict:
    """Turn down a suggestion so it stops being offered. The reading is KEPT
    — same contract as `identidade_extracao_service.descartar_sugestao`."""
    row = _linha_por_id(client, org_id, qualificacao_id)
    agora = now_iso()
    patch = {
        "descartado_por": str(usuario_id) if usuario_id else None,
        "descartado_em": agora,
    }
    _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(qualificacao_id)
    ).execute()
    return {**row, **patch}


def backfill_aplicar_campos_vinculados(client: Any, org_id: Any) -> dict:
    """Catch-up for every `vinculado` qualificação written BEFORE
    `persistir_sugestoes` started calling `_aplicar_automatico` on insert
    (2026-09-23) — REGINA's `profissão`, e.g. Idempotent: `_aplicar_
    automatico` -> `aplicar_campos_ao_cliente` only ever fills a field that
    is still empty or opens/reuses a pending conflict for one that
    disagrees, so re-running this against the same org twice (or against a
    row `confirmar` already applied) touches nothing the second time.

    Never run against prod from this function alone — it takes whichever
    `client`/`org_id` the caller hands it, the same as every other function
    in this module; it is not itself an admin-only HTTP route, so a human
    invokes it deliberately, once, per org, e.g.:

        python -c "
    from app.dependencies import get_admin_client
    from app.modules.matriculas.qualificacao_service import (
        backfill_aplicar_campos_vinculados,
    )
    print(backfill_aplicar_campos_vinculados(get_admin_client(), '<ORG_ID>'))
    "

    Returns `{"linhas_vinculadas": N, "aplicados": M, "conflitos_abertos": K}`
    — `aplicados` counts individual (row, campo) fills across every row, not
    rows; `conflitos_abertos` the same for newly-opened conflicts.
    """
    rows = table_reads.paged_rows(
        client, TABLE, org_id, eq_filters={"vinculo_status": VINCULADO}
    )
    linhas_vinculadas = 0
    total_aplicados = 0
    total_conflitos = 0
    for row in rows:
        if not row.get("cliente_id"):
            continue
        linhas_vinculadas += 1
        aplicados, conflitos = _aplicar_automatico(client, org_id, row)
        total_aplicados += sum(1 for foi in aplicados.values() if foi)
        total_conflitos += len(conflitos)
    return {
        "linhas_vinculadas": linhas_vinculadas,
        "aplicados": total_aplicados,
        "conflitos_abertos": total_conflitos,
    }


def purgar_da_extracao(client: Any, org_id: Any, extracao_id: Any) -> None:
    """Delete every qualificação row read from `extracao_id` — called when
    its text is purged (`estrutura_service.purgar_texto_expirado`), so a
    name/CPF/RG/endereço lifted out of the text cannot outlive it. Mirrors
    `ato_detalhes_service.purgar_da_extracao`."""
    _t(client, TABLE).delete().eq("org_id", str(org_id)).eq(
        "extracao_id", str(extracao_id)
    ).execute()


__all__ = [
    "CAMPOS_QUALIFICACAO",
    "TABLE",
    "VINCULADO",
    "SEM_CORRESPONDENCIA",
    "AMBIGUO",
    "backfill_aplicar_campos_vinculados",
    "confirmar",
    "descartar",
    "persistir_sugestoes",
    "purgar_da_extracao",
    "qualificacao_saida",
    "qualificacoes_da_extracao",
]
