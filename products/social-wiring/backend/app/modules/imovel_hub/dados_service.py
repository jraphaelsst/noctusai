"""The cartório data we author for an imóvel (migration 075).

`imoveis` is a Vista sync MIRROR — `imoveis_service.sync()` upserts every
property from the CRM. This table is ours: número de matrícula, número do
registro de imóveis, prefeitura do cadastro imobiliário, and the captador
who brought the property in. See migration 075's header for why authored
data does not live inside a mirror of somebody else's system.

🔴 AND WHY IT KEYS TO `imovel_registry`, NOT TO THE MIRROR (migration 076).
075 made that argument and then FK'd to the mirror anyway. The mirror holds
only what Vista lists TODAY; the registry holds every código we have ever
seen and is append-only. A property leaves the Vista catalog when it is
SOLD — so keying to the mirror would have made this feature 404 exactly the
imóveis whose paperwork is being handled.

WRITE SEMANTICS FOR `numero_matricula`
--------------------------------------
The column has a provenance quintuple, mirroring `clientes.data_nascimento`
(migration 068), and the same rule: **first writer wins.** A number a human
typed is never overwritten by a machine read, and a machine read never
overwrites a machine read. The extraction path (`matricula_extracao_service`)
offers a value; only an empty column accepts it unattended.

That asymmetry is deliberate and is the opposite of `nome`'s (where the
official document is meant to win). A matrícula number has no plausibility
gate — see `noctusai_lib.integrations.documents.matricula_extractor` — so
letting a read overwrite a human's entry would trade a value somebody
verified for one nobody can check.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.services import table_reads

TABLE = "imovel_dados"

#: 🔴 The REGISTRY, never the `imoveis` mirror — see migration 076.
#:
#: `imoveis` holds what Vista says TODAY and shrinks when a property leaves
#: the catalog. `imovel_registry` is append-only: one row per código we have
#: ever seen. Measured on prod 2026-08-25, 1062 of 3017 registered imóveis
#: (35%) were already absent from the mirror — and an imóvel leaves the
#: catalog because it was SOLD, i.e. exactly when its matrícula is in play.
#: Checking the mirror would 404 the properties this feature exists for.
REGISTRY_TABLE = "imovel_registry"
REGISTRY_CODIGO = "codigo_canonical"

#: The fields a human may set through the API. `numero_matricula` is here —
#: a human typing it is the FIRST writer and the most trusted one — but its
#: provenance columns are not: those are stamped by whichever path wrote the
#: value, never accepted from a request body.
CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "numero_matricula",
    "numero_registro_imoveis",
    "prefeitura_cadastro_imobiliario",
    "captador_user_id",
    # Migration 099 — situação de ônus. The first clause of every promessa de
    # compra e venda asserts the property is sold "livre e desembaraçado de
    # quaisquer ônus reais"; until now nothing in the schema could back that
    # sentence. `atendimento_financiamento` records the BUYER's financing,
    # which is the opposite side of the transaction from the SELLER's debt.
    #
    # 🔴 NO RULES ATTACHED, on purpose. The vocabulary below is what the UI
    # offers; nothing refuses to emit a document on a stale certidão and
    # nothing ties these fields to each other. The user asked for the field
    # now and the rules later, and a gate written before its policy is decided
    # is a gate that gets worked around.
    "situacao_onus",
    "onus_observacoes",
    "onus_certidao_em",
    "onus_documento_id",
)

#: What the UI offers for `situacao_onus`. Here rather than as a schema CHECK
#: for the reason migration 099 gives: the vocabulary is a product decision and
#: freezing a guessed enum in the database makes each addition a migration.
#: NOT enforced as a whitelist — see `atualizar`.
SITUACOES_ONUS: tuple[str, ...] = (
    "livre",
    "hipoteca",
    "alienacao_fiduciaria",
    "penhora",
    "usufruto",
    "indisponibilidade",
    "outro",
)

#: Provenance columns — stamped, never accepted from a body. Listed so the
#: refusal below names them rather than silently dropping them, which is the
#: silent-error shape this codebase forbids.
CAMPOS_PROVENIENCIA: tuple[str, ...] = (
    "numero_matricula_origem",
    "numero_matricula_documento_id",
    "numero_matricula_em",
    "numero_matricula_confirmado_por",
    "numero_matricula_confirmado_em",
)


#: Migration 109 — where the título aquisitivo came from: an act of a
#: transcribed matrícula, as offsets. Written ONLY by
#: `matriculas.estrutura_service.definir_fontes` (a human's choice), never by
#: the PATCH route and never by the heuristic suggester.
CAMPOS_TITULO_AQUISITIVO: tuple[str, ...] = (
    "titulo_aquisitivo_extracao_id",
    "titulo_aquisitivo_ato_id",
    "titulo_aquisitivo_char_inicio",
    "titulo_aquisitivo_char_fim",
    "titulo_aquisitivo_origem",
    "titulo_aquisitivo_confirmado_por",
    "titulo_aquisitivo_confirmado_em",
)

#: Migration 109 — the acts the ônus reading is sourced from. Pointers only:
#: 099's manual `situacao_onus` / `onus_observacoes` stay the human's reading
#: and are never derived from these.
CAMPOS_ONUS_FONTE: tuple[str, ...] = (
    "onus_fonte_extracao_id",
    "onus_fonte_atos",
    "onus_fonte_origem",
    "onus_fonte_confirmado_por",
    "onus_fonte_confirmado_em",
)

#: Migration 115 — the CONFIRMED contract wording: the título aquisitivo
#: phrase and the ônus creditor. Written ONLY by `matriculas.titulo_service`
#: (an operator's PUT), never by the PATCH route and never by a suggester —
#: the suggestion is recomputed from the acts on every read, not stored.
#: Migration 139 — the CONFIRMED short address ("situado à ...") the posse
#: clauses print. Same shape/trust model as the pair above: an operator
#: reads the matrícula and types it; never a recomputed suggestion, never the
#: `imoveis` CRM mirror's público endereço (which some tenants deliberately
#: publish as the portaria/gatehouse address rather than the real one — see
#: `contrato_gerador/dados.py`'s `Imovel.endereco` docstring).
CAMPOS_ENDERECO_CONTRATO: tuple[str, ...] = (
    "endereco_registro_texto",
    "endereco_registro_confirmado_por",
    "endereco_registro_confirmado_em",
)

CAMPOS_TEXTO_CONTRATO: tuple[str, ...] = (
    "titulo_aquisitivo_texto",
    "titulo_aquisitivo_texto_confirmado_por",
    "titulo_aquisitivo_texto_confirmado_em",
    "onus_credor",
    "onus_credor_confirmado_por",
    "onus_credor_confirmado_em",
) + CAMPOS_ENDERECO_CONTRATO

#: Migration 149 — the manual override for the 4 address fields
#: `contrato_gerador.derivacao._imovel` reads (logradouro/número/cidade/UF).
#: This product has no write-back to the Vista mirror those fields normally
#: come from (`busca_service.enriquecer`) — see `carregador._endereco_imovel`
#: for where the override wins per-field over the mirror. Written ONLY by
#: `gravar_endereco_manual`, which also logs every change to
#: `imovel_endereco_historico` — a human overriding synced/external data
#: needs no approval, but does need a trail.
CAMPOS_ENDERECO_MANUAL: tuple[str, ...] = (
    "endereco_manual_logradouro",
    "endereco_manual_numero",
    "endereco_manual_cidade",
    "endereco_manual_uf",
)

#: The mirror-facing field name for each override column — what
#: `imovel_endereco_historico.campo` and the `Endereco` dataclass both use.
_CAMPO_MIRROR = {
    "endereco_manual_logradouro": "logradouro",
    "endereco_manual_numero": "numero",
    "endereco_manual_cidade": "cidade",
    "endereco_manual_uf": "uf",
}

HISTORICO_ENDERECO_TABLE = "imovel_endereco_historico"

#: Migration 152 — the manual override for [Q9]'s previous-owner rule (the
#: LAST resort when `matriculas.titulo_service.antigos_proprietarios` finds
#: no ownership-transferring act at all): a typed date + optional nature, or
#: an explicit "não consta transferência registrada" statement. Written ONLY
#: by `gravar_ultima_transferencia_manual`, which `matriculas.titulo_service.
#: confirmar_ultima_transferencia_manual` calls after validating the
#: date/sem_registro/natureza combination.
CAMPOS_ULTIMA_TRANSFERENCIA_MANUAL: tuple[str, ...] = (
    "ultima_transferencia_manual_data",
    "ultima_transferencia_manual_natureza",
    "ultima_transferencia_manual_sem_registro",
    "ultima_transferencia_manual_confirmado_por",
    "ultima_transferencia_manual_confirmado_em",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def ensure_imovel(client: Any, org_id: UUID, codigo: str) -> dict:
    """The imóvel must be KNOWN before we can author data for it.

    "Known" means present in `imovel_registry` — every código we have ever
    seen, from any source — NOT present in the Vista catalog today. See the
    `REGISTRY_TABLE` note above for why the distinction decides whether this
    feature works for a sold property.

    Checked explicitly rather than left to the FK: a foreign-key violation
    surfaces as a 500 from the driver, and "imóvel não encontrado" is a 404
    the caller can act on.
    """
    rows = (
        _t(client, REGISTRY_TABLE)
        .select(REGISTRY_CODIGO)
        .eq("org_id", str(org_id))
        .eq(REGISTRY_CODIGO, codigo)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(REGISTRY_TABLE, codigo)
    return rows[0]


def registrar_imovel(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    origem: str,
) -> Optional[str]:
    """Give a código we have never seen a registry identity. Idempotent.

    🔴 WHY ANYTHING NEEDS THIS AT ALL
    ---------------------------------
    Until now exactly two things created `imovel_registry` rows: the nightly
    Vista sync (`imoveis_service._upsert_registry`) and migration 063's
    one-off backfill. So a portal lead arriving for a listing the catalog has
    never shown us produced a `leads.codigo_imovel` that no FK in this schema
    would accept — the lead saved fine (that column is free text), and every
    downstream feature keyed to the registry then 404'd the imóvel the lead
    was literally about.

    That is not a rare shape. 063 measured 1019 distinct well-formed códigos
    on leads that resolve against nothing in the mirror; a portal lead names
    the listing it came from by definition.

    WHY `origem_descoberta='lead'` NEEDS NO MIGRATION
    -------------------------------------------------
    063's CHECK already spells the vocabulary
    `('vista_sync', 'lead', 'venda', 'intake', 'manual', 'desconhecida')`.
    The slot was reserved when the table was designed and never filled. This
    fills it.

    🔴 READ-THEN-INSERT, NOT `upsert()`
    -----------------------------------
    `MockRequestBuilder.upsert()` is a documented NO-OP (see
    `noctusai_lib/testing/mocks.py`: conflict-target tracking is deferred), so
    an upsert-based path tests green and duplicates live. This is the same
    reasoning `olx_ingest_service` records for its own dedup check, and the
    unique constraint `uq_imovel_registry_org_codigo` is the real backstop.

    `ativo_no_vista` stays FALSE and `ultimo_visto_no_vista_em` stays NULL:
    063's default is FALSE precisely because a row born from a LEAD has never
    been seen in the catalog, and claiming otherwise would make the delist
    sweep "delist" something it never listed. When the nightly sync later
    meets the same código its `ON CONFLICT DO NOTHING` leaves
    `origem_descoberta` alone — how we LEARNED a código exists does not change
    because the catalog caught up.

    Returns the canonical código, or `None` when there was nothing to record.
    """
    canonico = (codigo or "").strip().upper()
    if not canonico:
        return None

    existing = (
        _t(client, REGISTRY_TABLE)
        .select(REGISTRY_CODIGO)
        .eq("org_id", str(org_id))
        .eq(REGISTRY_CODIGO, canonico)
        .limit(1)
        .execute()
    ).data or []
    if existing:
        return canonico

    _t(client, REGISTRY_TABLE).insert(
        {
            "org_id": str(org_id),
            "codigo_canonical": canonico,
            # The spelling we actually received, kept for tracing. 063 keeps
            # it for display and never matches on it.
            "codigo_display": (codigo or "").strip(),
            "ativo_no_vista": False,
            "origem_descoberta": origem,
            "primeiro_visto_em": _now(),
            "created_at": _now(),
            "updated_at": _now(),
        }
    ).execute()
    return canonico


def registro_status(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    """Is this código known at all — through the Vista-synced mirror, or
    only through the registry (manually registered, a lead, an intake)?

    🔴 WHY ANYTHING NEEDS THIS AT ALL. `GET /api/imoveis/{codigo}`
    (`app.routers.imoveis_router.get_imovel`) reads ONLY `imoveis`, the
    Vista mirror, and 404s otherwise — correct for that route's job (it is
    a DISPLAY of the CRM listing) but wrong as the property page's "can
    this even be opened" check: a manually registered código
    (`registrar_imovel` above) has no listing to display and never will,
    yet it is a perfectly real property the cartório/endereço/inscrição
    fields (`imovel_dados`, this same module) can still be authored for.

    `origem` is a TWO-value surface ("manual"/"vista"), narrower than the
    registry's own five-value `origem_descoberta` vocabulary
    (migration 063) — this route only needs to answer "did Vista ever list
    it", not which of the non-Vista paths (lead/venda/intake/manual/
    desconhecida) found it first. Read off the REGISTRY row, not off
    whether the mirror still HAS the código today: a synced property that
    later sold and left `imoveis` keeps `origem_descoberta='vista_sync'`
    forever (the registry is append-only) and must keep reporting "vista",
    never flip to "manual" just because it left the catalog.

    The `imoveis` lookup below is a defensive fallback, not the primary
    path — every synced row's OWN upsert also writes a registry row
    (`imoveis_service._upsert_registry`), so a mirror-only, registry-less
    código should not occur; kept so one never false-404s regardless.

    Returns `None` when the código is unknown to both.
    """
    canonico = (codigo or "").strip().upper()
    if not canonico:
        return None

    registry_rows = (
        _t(client, REGISTRY_TABLE)
        .select(f"{REGISTRY_CODIGO},origem_descoberta,created_at")
        .eq("org_id", str(org_id))
        .eq(REGISTRY_CODIGO, canonico)
        .limit(1)
        .execute()
    ).data or []
    if registry_rows:
        origem = "vista" if registry_rows[0].get("origem_descoberta") == "vista_sync" else "manual"
        return {
            "codigo": canonico,
            "registrado": True,
            "origem": origem,
            "criado_em": registry_rows[0].get("created_at"),
        }

    mirror_rows = (
        _t(client, "imoveis")
        .select("codigo,data_cadastro")
        .eq("org_id", str(org_id))
        .eq("codigo_norm", canonico)
        .limit(1)
        .execute()
    ).data or []
    if mirror_rows:
        return {
            "codigo": canonico,
            "registrado": True,
            "origem": "vista",
            "criado_em": mirror_rows[0].get("data_cadastro"),
        }
    return None


def linha(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _fonte_titulo_aquisitivo(row: dict, resolved: dict) -> Optional[dict]:
    """The título aquisitivo source pointer (migration 109), or None.

    Offsets only — the literal text lives in the matrícula transcription and
    is served by `GET /api/matriculas/extracoes/{id}/fontes`.
    """
    if not row.get("titulo_aquisitivo_ato_id"):
        return None
    return {
        "extracao_id": row.get("titulo_aquisitivo_extracao_id"),
        "ato_id": row.get("titulo_aquisitivo_ato_id"),
        "char_inicio": row.get("titulo_aquisitivo_char_inicio"),
        "char_fim": row.get("titulo_aquisitivo_char_fim"),
        "origem": row.get("titulo_aquisitivo_origem"),
        "confirmado_por": table_reads.actor(
            resolved, row.get("titulo_aquisitivo_confirmado_por")
        ),
        "confirmado_em": row.get("titulo_aquisitivo_confirmado_em"),
    }


def _fonte_onus(row: dict, resolved: dict) -> Optional[dict]:
    """The ônus source pointer (migration 109), or None. Offsets only."""
    if not row.get("onus_fonte_extracao_id"):
        return None
    return {
        "extracao_id": row.get("onus_fonte_extracao_id"),
        "atos": row.get("onus_fonte_atos") or [],
        "origem": row.get("onus_fonte_origem"),
        "confirmado_por": table_reads.actor(
            resolved, row.get("onus_fonte_confirmado_por")
        ),
        "confirmado_em": row.get("onus_fonte_confirmado_em"),
    }


def _saida(codigo: str, row: Optional[dict], resolved: dict) -> dict:
    """The response shape. An imóvel with no row yet is NOT an error and NOT
    an empty object — it is every field, null. A caller that had to tell
    "no row" apart from "row with nothing in it" would branch on it at every
    call site, and the two mean the same thing to a user."""
    row = row or {}
    return {
        "codigo": codigo,
        "numero_matricula": row.get("numero_matricula"),
        "numero_matricula_origem": row.get("numero_matricula_origem"),
        "numero_matricula_documento_id": row.get("numero_matricula_documento_id"),
        "numero_matricula_em": row.get("numero_matricula_em"),
        "numero_matricula_confirmado_por": table_reads.actor(
            resolved, row.get("numero_matricula_confirmado_por")
        ),
        "numero_matricula_confirmado_em": row.get("numero_matricula_confirmado_em"),
        "numero_registro_imoveis": row.get("numero_registro_imoveis"),
        "prefeitura_cadastro_imobiliario": row.get("prefeitura_cadastro_imobiliario"),
        "captador": table_reads.actor(resolved, row.get("captador_user_id")),
        "situacao_onus": row.get("situacao_onus"),
        "onus_observacoes": row.get("onus_observacoes"),
        # The date printed ON the certidão, not when it was uploaded — a
        # certidão's validity runs from its own emission, so the upload
        # timestamp answers a different question.
        "onus_certidao_em": row.get("onus_certidao_em"),
        "onus_documento_id": row.get("onus_documento_id"),
        "onus_registrado_por": table_reads.actor(
            resolved, row.get("onus_registrado_por")
        ),
        "onus_registrado_em": row.get("onus_registrado_em"),
        "situacoes_onus": list(SITUACOES_ONUS),
        "titulo_aquisitivo_fonte": _fonte_titulo_aquisitivo(row, resolved),
        "onus_fonte": _fonte_onus(row, resolved),
        # Migration 115 — the confirmed contract wording.
        "titulo_aquisitivo_texto": row.get("titulo_aquisitivo_texto"),
        "titulo_aquisitivo_texto_confirmado_por": table_reads.actor(
            resolved, row.get("titulo_aquisitivo_texto_confirmado_por")
        ),
        "titulo_aquisitivo_texto_confirmado_em": row.get(
            "titulo_aquisitivo_texto_confirmado_em"
        ),
        "onus_credor": row.get("onus_credor"),
        "onus_credor_confirmado_por": table_reads.actor(
            resolved, row.get("onus_credor_confirmado_por")
        ),
        "onus_credor_confirmado_em": row.get("onus_credor_confirmado_em"),
        # Migration 139 — the confirmed short address override the posse
        # clauses print when set (see `CAMPOS_ENDERECO_CONTRATO`).
        "endereco_registro_texto": row.get("endereco_registro_texto"),
        "endereco_registro_confirmado_por": table_reads.actor(
            resolved, row.get("endereco_registro_confirmado_por")
        ),
        "endereco_registro_confirmado_em": row.get("endereco_registro_confirmado_em"),
        # Migration 149 — the manual override for the 4 address fields the
        # contract gate reads. `None` on every field means "use the mirror".
        "endereco_manual_logradouro": row.get("endereco_manual_logradouro"),
        "endereco_manual_numero": row.get("endereco_manual_numero"),
        "endereco_manual_cidade": row.get("endereco_manual_cidade"),
        "endereco_manual_uf": row.get("endereco_manual_uf"),
        "endereco_manual_confirmado_por": table_reads.actor(
            resolved, row.get("endereco_manual_confirmado_por")
        ),
        "endereco_manual_confirmado_em": row.get("endereco_manual_confirmado_em"),
        # Migration 152 — the manual override for [Q9]'s previous-owner rule.
        # `matriculas.titulo_service.antigos_proprietarios` is the read that
        # actually resolves the EFFECTIVE value (acts-derivation wins over
        # this); these are the raw stored fields, mirrored here like every
        # other imovel_dados-authored field.
        "ultima_transferencia_manual_data": row.get("ultima_transferencia_manual_data"),
        "ultima_transferencia_manual_natureza": row.get("ultima_transferencia_manual_natureza"),
        "ultima_transferencia_manual_sem_registro": bool(
            row.get("ultima_transferencia_manual_sem_registro")
        ),
        "ultima_transferencia_manual_confirmado_por": table_reads.actor(
            resolved, row.get("ultima_transferencia_manual_confirmado_por")
        ),
        "ultima_transferencia_manual_confirmado_em": row.get(
            "ultima_transferencia_manual_confirmado_em"
        ),
        "updated_at": row.get("updated_at"),
    }


def obter(client: Any, org_id: UUID, codigo: str) -> dict:
    ensure_imovel(client, org_id, codigo)
    row = linha(client, org_id, codigo)
    ids = {
        (row or {}).get("captador_user_id"),
        (row or {}).get("numero_matricula_confirmado_por"),
        (row or {}).get("onus_registrado_por"),
        (row or {}).get("titulo_aquisitivo_confirmado_por"),
        (row or {}).get("onus_fonte_confirmado_por"),
        (row or {}).get("titulo_aquisitivo_texto_confirmado_por"),
        (row or {}).get("onus_credor_confirmado_por"),
        (row or {}).get("endereco_registro_confirmado_por"),
        (row or {}).get("endereco_manual_confirmado_por"),
        (row or {}).get("ultima_transferencia_manual_confirmado_por"),
    }
    return _saida(codigo, row, table_reads.resolve_actors(ids))


def atualizar(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    """Upsert the authored fields. Only keys present in `valores` are touched.

    `None` is a real value here — clearing a wrongly-typed matrícula number
    has to be possible — so absence, not null, is what means "leave alone".
    """
    ensure_imovel(client, org_id, codigo)

    recusados = sorted(set(valores) - set(CAMPOS_EDITAVEIS))
    if recusados:
        # Named, not dropped. A body field that is silently ignored is
        # indistinguishable from one that was saved.
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}",
            field=recusados[0],
        )

    atual = linha(client, org_id, codigo)
    patch = {k: v for k, v in valores.items() if k in CAMPOS_EDITAVEIS}

    # A human typing the number IS the provenance. Stamped here rather than
    # left null so a later extraction can tell the column is already spoken
    # for — that check is what makes first-writer-wins work.
    if "numero_matricula" in patch and patch["numero_matricula"]:
        patch["numero_matricula_origem"] = "manual"
        patch["numero_matricula_documento_id"] = None
        patch["numero_matricula_em"] = _now()
        patch["numero_matricula_confirmado_por"] = (
            str(usuario_id) if usuario_id else None
        )
        patch["numero_matricula_confirmado_em"] = _now()
    elif "numero_matricula" in patch:
        # Cleared. Its provenance must go with it — a stale origin pointing
        # at a number that is no longer there is worse than none.
        for coluna in CAMPOS_PROVENIENCIA:
            patch[coluna] = None

    if "captador_user_id" in patch and patch["captador_user_id"] is not None:
        patch["captador_user_id"] = str(patch["captador_user_id"])

    _gravar(client, org_id, codigo, atual, patch)
    return obter(client, org_id, codigo)


def _json_seguro(patch: dict) -> dict:
    """Render `date`/`datetime` values as ISO strings before they reach PostgREST.

    🔴 THE BUG THIS FIXES (live, 2026-09-22): saving the ônus block with a
    `Data da certidão` filled returned `[500] Erro interno do servidor` —
    `TypeError: Object of type date is not JSON serializable`. The body model
    parses `onus_certidao_em` into a real `datetime.date`, and httpx's JSON
    encoder (which PostgREST's client hands the payload to) refuses it. Every
    author of this table funnels through `_gravar`, so the coercion belongs
    here and nowhere else — a per-caller `.isoformat()` is the shape that let
    this reach production in the first place (the date column has been
    unwritable since migration 099 shipped it).
    """
    return {
        chave: (valor.isoformat() if isinstance(valor, (date, datetime)) else valor)
        for chave, valor in patch.items()
    }


def _gravar(
    client: Any, org_id: UUID, codigo: str, atual: Optional[dict], patch: dict
) -> None:
    """Insert the imóvel's row, or update it — the ONE write shape every
    author of this table uses (`atualizar`, `aplicar_matricula_extraida`,
    `gravar_fontes_matricula`).

    `atual` is the row the caller just re-read. Read-then-write rather than
    `upsert()` for the reason `registrar_imovel` records: the mock's upsert is
    a no-op, so an upsert path tests green and breaks live.
    """
    if atual is None:
        _t(client, TABLE).insert(
            _json_seguro(
                {"org_id": str(org_id), "codigo": codigo, **patch, "created_at": _now()}
            )
        ).execute()
    else:
        _t(client, TABLE).update(_json_seguro({**patch, "updated_at": _now()})).eq(
            "org_id", str(org_id)
        ).eq("codigo", codigo).execute()


def aplicar_matricula_extraida(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    numero: str,
    documento_id: UUID,
) -> bool:
    """Write an extracted number into an EMPTY column. Returns whether it landed.

    🔴 FIRST WRITER WINS, CHECKED AGAINST THE ROW, NOT AGAINST A FLAG.
    Re-read immediately before the write rather than trusting anything the
    caller passed: the extraction runs detached, minutes may separate the
    upload from this call, and a human may well have typed the number in
    between. Returning `False` here is the normal, correct outcome in that
    race — not a failure.
    """
    ensure_imovel(client, org_id, codigo)
    atual = linha(client, org_id, codigo)
    if atual and atual.get("numero_matricula"):
        return False

    patch = {
        "numero_matricula": numero,
        "numero_matricula_origem": "matricula",
        "numero_matricula_documento_id": str(documento_id),
        "numero_matricula_em": _now(),
        # Deliberately NOT confirmed: a machine read is attributable to a
        # document, never to a person. `confirmado_por` stays null until a
        # human agrees with it.
        "numero_matricula_confirmado_por": None,
        "numero_matricula_confirmado_em": None,
    }
    _gravar(client, org_id, codigo, atual, patch)
    return True


def gravar_fontes_matricula(
    client: Any, org_id: UUID, codigo: str, patch: dict
) -> None:
    """Write título aquisitivo / ônus source pointers (migration 109).

    The caller (`matriculas.estrutura_service.definir_fontes`) has already
    validated the acts against the extraction and stamped origem +
    confirmation. This refuses any column outside the two pointer groups — it
    is not a back door to the authored fields, and in particular never
    touches 099's manual `situacao_onus`.
    """
    recusados = sorted(set(patch) - set(CAMPOS_TITULO_AQUISITIVO) - set(CAMPOS_ONUS_FONTE))
    if recusados:
        raise ValueError(
            f"gravar_fontes_matricula: colunas fora das fontes: {', '.join(recusados)}"
        )
    ensure_imovel(client, org_id, codigo)
    _gravar(client, org_id, codigo, linha(client, org_id, codigo), patch)


def gravar_texto_contrato(
    client: Any, org_id: UUID, codigo: str, patch: dict
) -> None:
    """Write the confirmed título phrase / ônus creditor (migration 115).

    The caller (`matriculas.titulo_service`) stamps the confirmation. Refuses
    any column outside `CAMPOS_TEXTO_CONTRATO` — not a back door to the
    authored fields or the 109 source pointers.
    """
    recusados = sorted(set(patch) - set(CAMPOS_TEXTO_CONTRATO))
    if recusados:
        raise ValueError(
            f"gravar_texto_contrato: colunas fora do texto do contrato: {', '.join(recusados)}"
        )
    ensure_imovel(client, org_id, codigo)
    _gravar(client, org_id, codigo, linha(client, org_id, codigo), patch)


def gravar_endereco_manual(
    client: Any,
    org_id: UUID,
    codigo: str,
    *,
    valores: dict,
    mirror: dict,
    usuario_id: Optional[Any],
) -> dict:
    """Manual override for the 4 address fields the contract gate reads
    (migration 149). Only keys present in `valores` are touched — same
    absence-means-leave-alone / `None`-clears contract `atualizar` uses.

    `mirror` is the imóvel's CURRENT read off the Vista/registry mirror
    (`busca_service.enriquecer`'s row for this código), supplied by the
    caller rather than fetched here — this module does not import
    `busca_service`, so the coupling stays one-directional. It is used ONLY
    to log what an override REPLACED the first time a field is set; once a
    field already carries an override, the previous OVERRIDE value is what
    gets logged, not the mirror again.

    Every touched field whose effective value actually changes appends one
    row to `imovel_endereco_historico` — the mirror is external/synced data,
    not an official document, so an override needs no admin approval, but
    IS logged: previous value + who + when.
    """
    ensure_imovel(client, org_id, codigo)
    recusados = sorted(set(valores) - set(CAMPOS_ENDERECO_MANUAL))
    if recusados:
        raise ValidationError_(
            f"Campos de endereço inválidos: {', '.join(recusados)}",
            field=recusados[0],
        )
    if not valores:
        return obter(client, org_id, codigo)

    # 🔴 `None`, not `{}`, when there is no row yet — `_gravar` (the ONE write
    # shape every author of this table uses) decides INSERT vs UPDATE off
    # this exact sentinel, same as `atualizar`/`gravar_fontes_matricula`.
    # Coercing it to `{}` here would make `_gravar` UPDATE a row that does
    # not exist, which the mock (and Postgres) silently no-ops.
    atual = linha(client, org_id, codigo)
    patch: dict = {}
    historico: list[dict] = []
    for coluna, bruto in valores.items():
        novo = (bruto or "").strip() or None if isinstance(bruto, str) else bruto
        campo = _CAMPO_MIRROR[coluna]
        anterior_override = (atual or {}).get(coluna)
        anterior_efetivo = (
            anterior_override if anterior_override is not None else mirror.get(campo)
        )
        if anterior_efetivo != novo:
            historico.append(
                {
                    "org_id": str(org_id),
                    "codigo": codigo,
                    "campo": campo,
                    "valor_anterior": anterior_efetivo,
                    "valor_novo": novo,
                    "alterado_por": str(usuario_id) if usuario_id else None,
                    "alterado_em": _now(),
                }
            )
        patch[coluna] = novo

    patch["endereco_manual_confirmado_por"] = str(usuario_id) if usuario_id else None
    patch["endereco_manual_confirmado_em"] = _now()
    _gravar(client, org_id, codigo, atual, patch)
    if historico:
        _t(client, HISTORICO_ENDERECO_TABLE).insert(historico).execute()
    return obter(client, org_id, codigo)


def historico_endereco(client: Any, org_id: UUID, codigo: str) -> list[dict]:
    """Every field-level address override for this imóvel, newest first."""
    ensure_imovel(client, org_id, codigo)
    rows = (
        _t(client, HISTORICO_ENDERECO_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .order("alterado_em", desc=True)
        .execute()
    ).data or []
    resolved = table_reads.resolve_actors({r.get("alterado_por") for r in rows} - {None})
    return [
        {
            "campo": r["campo"],
            "valor_anterior": r.get("valor_anterior"),
            "valor_novo": r.get("valor_novo"),
            "alterado_por": table_reads.actor(resolved, r.get("alterado_por")),
            "alterado_em": r.get("alterado_em"),
        }
        for r in rows
    ]


def gravar_ultima_transferencia_manual(client: Any, org_id: UUID, codigo: str, patch: dict) -> None:
    """Write the manual override for [Q9]'s previous-owner rule (migration
    152). Refuses any column outside `CAMPOS_ULTIMA_TRANSFERENCIA_MANUAL` —
    the caller (`matriculas.titulo_service.confirmar_ultima_transferencia_
    manual`) validates the date/sem_registro/natureza combination and stamps
    the confirmation; this is not a back door to the other authored fields.
    """
    recusados = sorted(set(patch) - set(CAMPOS_ULTIMA_TRANSFERENCIA_MANUAL))
    if recusados:
        raise ValueError(
            "gravar_ultima_transferencia_manual: colunas fora do escopo: "
            + ", ".join(recusados)
        )
    ensure_imovel(client, org_id, codigo)
    _gravar(client, org_id, codigo, linha(client, org_id, codigo), patch)


def extracao_referenciada(client: Any, org_id: UUID, extracao_id: Any) -> bool:
    """Does any imóvel's título/ônus pointer quote this matrícula extraction?"""
    for coluna in ("titulo_aquisitivo_extracao_id", "onus_fonte_extracao_id"):
        rows = (
            _t(client, TABLE)
            .select("codigo")
            .eq("org_id", str(org_id))
            .eq(coluna, str(extracao_id))
            .limit(1)
            .execute()
        ).data or []
        if rows:
            return True
    return False


__all__ = [
    "CAMPOS_EDITAVEIS",
    "CAMPOS_ENDERECO_CONTRATO",
    "CAMPOS_ENDERECO_MANUAL",
    "CAMPOS_ONUS_FONTE",
    "CAMPOS_PROVENIENCIA",
    "CAMPOS_TEXTO_CONTRATO",
    "CAMPOS_TITULO_AQUISITIVO",
    "HISTORICO_ENDERECO_TABLE",
    "TABLE",
    "aplicar_matricula_extraida",
    "atualizar",
    "ensure_imovel",
    "extracao_referenciada",
    "gravar_endereco_manual",
    "gravar_fontes_matricula",
    "gravar_texto_contrato",
    "historico_endereco",
    "linha",
    "obter",
]
