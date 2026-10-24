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

WRITE SEMANTICS FOR THE EXTRACTED FIELDS (D1, migration 154)
-------------------------------------------------------------
`numero_matricula`, `numero_registro_imoveis`, `prefeitura_cadastro_
imobiliario` and `situacao_onus` each carry a provenance quintet
(`_origem/_documento_id/_em/_confirmado_por/_confirmado_em`), mirroring
`clientes.data_nascimento` (068). A human write through `atualizar` stamps
`origem='manual'`; a machine reading goes ONLY through
`campos_extraidos_service.aplicar`, which fills an empty column and turns a
disagreement into a conflict a human decides — never an overwrite. A machine
read never overwrites a machine read either: a matrícula number has no
plausibility gate (see `noctusai_lib.integrations.documents.
matricula_extractor`), so trading a value for another nobody can check is
exactly what the conflict exists to stop.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import (
    AppException,
    NotFoundError,
    ValidationError_,
)

from app.services import identificadores as idf
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
    # Migration 158 — the development/condomínio name for a manually
    # registered imóvel (migration 149), which has no Vista mirror row and
    # therefore no `imoveis.empreendimento` at all. Confirmed like
    # `endereco_manual_*` (149) — a single stamp, not the 154 quintet: there
    # is no document extraction for this field to reconcile against.
    "empreendimento_manual",
    # Migration 300 — the imóvel's condomínio (FK to the master list, 265)
    # OR the explicit "casa de rua" answer; mutually exclusive (see
    # `_condominio_patch`). Supersedes 202's free `em_condominio` flag, which
    # the app no longer writes (kept read-only for one release).
    "condominio_id",
    "casa_de_rua",
    # Migration 264 — valuation characteristics (see CAMPOS_AVALIACAO).
    "padrao_construtivo",
    "estado_conservacao",
    "area_terreno_m2",
    "area_construida_m2",
    "testada_m",
    "profundidade_m",
    "topografia",
    "posicao_lote",
)

#: Migration 264 — PHYSICAL attributes the price evaluator reads. Not legal
#: data: they are read/written on the imóvel's OWN row and do NOT follow the
#: manual<->Vista `legal_efetivo` link. A change stamps who/when.
CAMPOS_AVALIACAO: tuple[str, ...] = (
    "padrao_construtivo",
    "estado_conservacao",
    "area_terreno_m2",
    "area_construida_m2",
    "testada_m",
    "profundidade_m",
    "topografia",
    "posicao_lote",
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

#: The scalar fields whose full provenance quintet a human write stamps
#: `manual` (and a clear empties) — migration 068's shape for
#: `numero_matricula`, extended by 154 to the other three contract-feeding
#: cartório fields. `campos_extraidos_service` re-exports this.
CAMPOS_QUINTETO_MANUAL: tuple[str, ...] = (
    "numero_matricula",
    "numero_registro_imoveis",
    "prefeitura_cadastro_imobiliario",
    "situacao_onus",
)

_SUFIXOS_QUINTETO: tuple[str, ...] = (
    "_origem", "_documento_id", "_em", "_confirmado_por", "_confirmado_em",
)

#: Migration 158 — fields with a bare `_confirmado_por`/`_confirmado_em`
#: stamp (mirrors `endereco_manual_*`, 149) rather than the full 154 quintet
#: above: nothing extracts these from a document, so `_origem`/
#: `_documento_id`/`_em` would be columns that could never be written.
CAMPOS_CONFIRMADO_SIMPLES: tuple[str, ...] = (
    "empreendimento_manual",
)

#: Provenance columns — stamped, never accepted from a body. Listed so the
#: refusal below names them rather than silently dropping them, which is the
#: silent-error shape this codebase forbids.
CAMPOS_PROVENIENCIA: tuple[str, ...] = tuple(
    f"{campo}{sufixo}" for campo in CAMPOS_QUINTETO_MANUAL for sufixo in _SUFIXOS_QUINTETO
)


#: Migration 109 — where the título aquisitivo came from: an act of a
#: transcribed matrícula, as offsets. Written ONLY by
#: `matriculas.estrutura_service.definir_fontes` — a human's own PUT, OR
#: (2026-09-30) `matriculas.autopiloto_service`'s automatic confirmation of
#: that SAME writer when the derivation is unambiguous (still `definir_
#: fontes`, still `origem` restricted to `sugerido`/`manual` by the 109
#: CHECK — the autopilot's confirmation is a `confirmado_por IS NULL`
#: `sugerido` row). Never by the PATCH route and never by the heuristic
#: suggester writing directly.
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
#: phrase and the ônus creditor. Written by `matriculas.titulo_service`'s
#: `confirmar_titulo`/`confirmar_onus_credor` (an operator's PUT, stamped
#: `origem='manual'`), by `imovel_hub.campos_extraidos_service.aplicar`'s
#: machine-pending fill (`origem='matricula'`, D1), or (2026-09-30) by
#: `matriculas.autopiloto_service` re-stamping that SAME machine-pending row
#: `origem='ia'` + confirmed, once the reading is unambiguous — never by the
#: PATCH route, and the SUGGESTION itself is still recomputed from the acts
#: on every read, not stored.
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

#: Migration 306 — the operator-typed IMÓVEL: description (the matrícula
#: abertura's `descricao_imovel` block). Same single-stamp shape and trust
#: model as `CAMPOS_ENDERECO_CONTRATO`: typed by a human, never a machine
#: read; when set it wins over the derived block in the contract's OBJETO
#: clause (`contrato_gerador.carregador`).
CAMPOS_DESCRICAO_IMOVEL_CONTRATO: tuple[str, ...] = (
    "descricao_imovel_texto",
    "descricao_imovel_confirmado_por",
    "descricao_imovel_confirmado_em",
)

CAMPOS_TEXTO_CONTRATO: tuple[str, ...] = (
    "titulo_aquisitivo_texto",
    # Migration 154 — `manual` when an operator's PUT wrote it (vs. `matricula`
    # when `campos_extraidos_service` filled it from the acts).
    "titulo_aquisitivo_texto_origem",
    "titulo_aquisitivo_texto_confirmado_por",
    "titulo_aquisitivo_texto_confirmado_em",
    "onus_credor",
    "onus_credor_origem",
    "onus_credor_confirmado_por",
    "onus_credor_confirmado_em",
) + CAMPOS_ENDERECO_CONTRATO + CAMPOS_DESCRICAO_IMOVEL_CONTRATO

#: Migration 149, widened by 159 — the manual override for all 7 address
#: fields the `Endereco` dataclass carries. 149 shipped only the 4
#: `contrato_gerador.derivacao._imovel` gates the contract on (logradouro/
#: número/cidade/UF); 159 adds complemento/bairro/CEP so the override can
#: also carry a condo UNIT's full address when the Vista mirror only holds
#: the building's GATE address (owner rule 2026-09-23: the property table,
#: not the matrícula, is the address of record). This product has no
#: write-back to the Vista mirror those fields normally come from
#: (`busca_service.enriquecer`) — see `carregador._endereco_manual` for
#: where the override wins per-field over the mirror. Written ONLY by
#: `gravar_endereco_manual`, which also logs every change to
#: `imovel_endereco_historico` — a human overriding synced/external data
#: needs no approval, but does need a trail. Applies to ANY registered
#: código (`ensure_imovel` only checks `imovel_registry`, never
#: `origem_descoberta`) — Vista-synced or hand-registered alike.
CAMPOS_ENDERECO_MANUAL: tuple[str, ...] = (
    "endereco_manual_logradouro",
    "endereco_manual_numero",
    "endereco_manual_complemento",
    "endereco_manual_bairro",
    "endereco_manual_cidade",
    "endereco_manual_uf",
    "endereco_manual_cep",
)

#: The mirror-facing field name for each override column — what
#: `imovel_endereco_historico.campo` and the `Endereco` dataclass both use.
_CAMPO_MIRROR = {
    "endereco_manual_logradouro": "logradouro",
    "endereco_manual_numero": "numero",
    "endereco_manual_complemento": "complemento",
    "endereco_manual_bairro": "bairro",
    "endereco_manual_cidade": "cidade",
    "endereco_manual_uf": "uf",
    "endereco_manual_cep": "cep",
}

#: Migration 159 — the fields `RegistrarImovelBody` requires at manual
#: registration time (owner rule 2026-09-23). `complemento` is deliberately
#: absent: it names a unit inside a building and has no meaning for a house
#: or a lot, so the FE offers it but the backend never refuses its absence.
CAMPOS_ENDERECO_MANUAL_OBRIGATORIOS: tuple[str, ...] = (
    "endereco_manual_logradouro",
    "endereco_manual_numero",
    "endereco_manual_bairro",
    "endereco_manual_cidade",
    "endereco_manual_uf",
    "endereco_manual_cep",
)

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
    # Migration 306 — who sold, typed (names only).
    "ultima_transferencia_manual_transmitentes",
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

    inserir_registry(client, org_id, canonico, display=(codigo or "").strip(), origem=origem)
    return canonico


def inserir_registry(
    client: Any, org_id: UUID, canonico: str, *, display: str, origem: str
) -> None:
    """The ONE `imovel_registry` insert shape (a plain INSERT — a conflict on
    `uq_imovel_registry_org_codigo` propagates, it is never swallowed).

    `registrar_imovel` calls it after its read-then-insert existence check;
    `captacao_service.registrar_manual` calls it directly because it must
    know it WON the código (a generated `SW-NNNN` two requests raced for),
    which the idempotent read-first path would hide.
    """
    _t(client, REGISTRY_TABLE).insert(
        {
            "org_id": str(org_id),
            "codigo_canonical": canonico,
            # The spelling we actually received, kept for tracing. 063 keeps
            # it for display and never matches on it.
            "codigo_display": display,
            "ativo_no_vista": False,
            "origem_descoberta": origem,
            "primeiro_visto_em": _now(),
            "created_at": _now(),
            "updated_at": _now(),
        }
    ).execute()


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


def _saida(
    codigo: str,
    row: Optional[dict],
    resolved: dict,
    propria: Optional[dict] = None,
    condominio: Optional[dict] = None,
) -> dict:
    """The response shape. An imóvel with no row yet is NOT an error and NOT
    an empty object — it is every field, null. A caller that had to tell
    "no row" apart from "row with nothing in it" would branch on it at every
    call site, and the two mean the same thing to a user."""
    row = row or {}
    propria = propria if propria is not None else row
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
        # Migration 300 — the typed answer, and the DERIVED three-state the
        # 202 flag used to carry: linked -> True, casa de rua -> False,
        # neither -> None. `em_condominio_legado` is the raw 202 column
        # (read-only, dropped next release) — the contract's fallback for an
        # unlinked imóvel an operator once marked "em condomínio".
        "condominio_id": row.get("condominio_id"),
        "casa_de_rua": bool(row.get("casa_de_rua")),
        "em_condominio": em_condominio_derivado(row),
        "em_condominio_legado": row.get("em_condominio"),
        "condominio": condominio,
        # Migration 264 — valuation characteristics, from the imóvel's OWN row.
        **{campo: propria.get(campo) for campo in CAMPOS_AVALIACAO},
        "avaliacao_campos_atualizado_em": propria.get("avaliacao_campos_atualizado_em"),
        "avaliacao_campos_atualizado_por": table_reads.actor(
            resolved, propria.get("avaliacao_campos_atualizado_por")
        ),
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
        # Migration 306 — the typed IMÓVEL: description override (see
        # `CAMPOS_DESCRICAO_IMOVEL_CONTRATO`).
        "descricao_imovel_texto": row.get("descricao_imovel_texto"),
        "descricao_imovel_confirmado_por": table_reads.actor(
            resolved, row.get("descricao_imovel_confirmado_por")
        ),
        "descricao_imovel_confirmado_em": row.get("descricao_imovel_confirmado_em"),
        # Migration 149, widened by 159 — the manual override for all 7
        # address fields. `None` on every field means "use the mirror".
        "endereco_manual_logradouro": row.get("endereco_manual_logradouro"),
        "endereco_manual_numero": row.get("endereco_manual_numero"),
        "endereco_manual_complemento": row.get("endereco_manual_complemento"),
        "endereco_manual_bairro": row.get("endereco_manual_bairro"),
        "endereco_manual_cidade": row.get("endereco_manual_cidade"),
        "endereco_manual_uf": row.get("endereco_manual_uf"),
        "endereco_manual_cep": row.get("endereco_manual_cep"),
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
        "ultima_transferencia_manual_transmitentes": list(
            row.get("ultima_transferencia_manual_transmitentes") or []
        ),
        "ultima_transferencia_manual_confirmado_por": table_reads.actor(
            resolved, row.get("ultima_transferencia_manual_confirmado_por")
        ),
        "ultima_transferencia_manual_confirmado_em": row.get(
            "ultima_transferencia_manual_confirmado_em"
        ),
        # Migration 158 — the authored development/condomínio name, read by
        # `carregador._empreendimento` ahead of the Vista mirror's own
        # `imoveis.empreendimento`. `None` means "use the mirror".
        "empreendimento_manual": row.get("empreendimento_manual"),
        "empreendimento_manual_confirmado_por": table_reads.actor(
            resolved, row.get("empreendimento_manual_confirmado_por")
        ),
        "empreendimento_manual_confirmado_em": row.get(
            "empreendimento_manual_confirmado_em"
        ),
        # Migration 154 — where each extracted contract field came from, and
        # whether it still awaits a human (the D2 gate's "machine-pending").
        "proveniencia": _proveniencia(row, resolved),
        "updated_at": row.get("updated_at"),
    }


def _proveniencia(row: dict, resolved: dict) -> dict:
    from app.modules.imovel_hub.campos_extraidos_service import CAMPOS, pendente

    saida: dict = {}
    for chave, campo in CAMPOS.items():
        saida[chave] = {
            "origem": row.get(campo.origem),
            "documento_id": row.get(campo.documento_id) if campo.documento_id else None,
            "em": row.get(campo.em) if campo.em else None,
            "confirmado_por": table_reads.actor(resolved, row.get(campo.confirmado_por)),
            "confirmado_em": row.get(campo.confirmado_em),
            "pendente": pendente(row, campo),
        }
    return saida


def obter(client: Any, org_id: UUID, codigo: str) -> dict:
    ensure_imovel(client, org_id, codigo)
    # READ through the manual<->Vista link (Vista -> manual fallback per field
    # group, conflicts flagged — see `vinculo_legal`). Writers use `linha`.
    from app.modules.imovel_hub import vinculo_legal

    efetivo = vinculo_legal.legal_efetivo(client, org_id, codigo)
    row = efetivo.linha
    propria = linha(client, org_id, codigo) or {}
    ids = {
        propria.get("avaliacao_campos_atualizado_por"),
        (row or {}).get("captador_user_id"),
        (row or {}).get("numero_matricula_confirmado_por"),
        (row or {}).get("onus_registrado_por"),
        (row or {}).get("titulo_aquisitivo_confirmado_por"),
        (row or {}).get("onus_fonte_confirmado_por"),
        (row or {}).get("titulo_aquisitivo_texto_confirmado_por"),
        (row or {}).get("onus_credor_confirmado_por"),
        (row or {}).get("endereco_registro_confirmado_por"),
        (row or {}).get("descricao_imovel_confirmado_por"),
        (row or {}).get("endereco_manual_confirmado_por"),
        (row or {}).get("ultima_transferencia_manual_confirmado_por"),
        (row or {}).get("empreendimento_manual_confirmado_por"),
        (row or {}).get("numero_registro_imoveis_confirmado_por"),
        (row or {}).get("prefeitura_cadastro_imobiliario_confirmado_por"),
        (row or {}).get("situacao_onus_confirmado_por"),
    }
    saida = _saida(
        codigo, row, table_reads.resolve_actors(ids), propria,
        condominio_resumo(client, org_id, (row or {}).get("condominio_id")),
    )
    # None when unlinked / read from the manual side.
    saida["vinculo_legal"] = efetivo.como_dict()
    return saida


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
    patch = canonizar_valores(
        client, org_id, codigo, {k: v for k, v in valores.items() if k in CAMPOS_EDITAVEIS}
    )
    patch.update(_condominio_patch(client, org_id, patch))

    # A human typing the value IS the provenance. Stamped here rather than
    # left null so a later extraction can tell the column is already spoken
    # for — that check is what turns a disagreeing reading into a conflict
    # instead of an overwrite (D1, `campos_extraidos_service.aplicar`).
    for campo in CAMPOS_QUINTETO_MANUAL:
        if campo not in patch:
            continue
        if patch[campo] == (atual or {}).get(campo):
            # Unchanged — a form re-saving the block it belongs to (the ônus
            # block always sends `situacao_onus`) is not a human deciding
            # this value. Its provenance stays as it was: a machine-pending
            # value is validated through the D2 gate, never as a side effect
            # of saving a neighbouring field.
            continue
        if patch[campo]:
            patch[f"{campo}_origem"] = "manual"
            patch[f"{campo}_documento_id"] = None
            patch[f"{campo}_em"] = _now()
            patch[f"{campo}_confirmado_por"] = str(usuario_id) if usuario_id else None
            patch[f"{campo}_confirmado_em"] = _now()
        else:
            # Cleared. Its provenance must go with it — a stale origin
            # pointing at a value that is no longer there is worse than none.
            for sufixo in _SUFIXOS_QUINTETO:
                patch[f"{campo}{sufixo}"] = None

    # Migration 158 — single-stamp confirmation (mirrors `endereco_manual_*`,
    # 149), not the quintet above: this field has no document/origem to
    # reconcile against, only a confirmed value and when it was set.
    for campo in CAMPOS_CONFIRMADO_SIMPLES:
        if campo not in patch:
            continue
        if patch[campo] == (atual or {}).get(campo):
            continue
        if patch[campo]:
            patch[f"{campo}_confirmado_por"] = str(usuario_id) if usuario_id else None
            patch[f"{campo}_confirmado_em"] = _now()
        else:
            patch[f"{campo}_confirmado_por"] = None
            patch[f"{campo}_confirmado_em"] = None

    # Migration 264 — stamp who/when on a real change to a valuation field.
    if any(
        campo in patch and patch[campo] != (atual or {}).get(campo)
        for campo in CAMPOS_AVALIACAO
    ):
        patch["avaliacao_campos_atualizado_em"] = _now()
        patch["avaliacao_campos_atualizado_por"] = (
            str(usuario_id) if usuario_id else None
        )

    if "captador_user_id" in patch and patch["captador_user_id"] is not None:
        patch["captador_user_id"] = str(patch["captador_user_id"])

    _gravar(client, org_id, codigo, atual, patch)
    return obter(client, org_id, codigo)


# ── Migration 300 — condomínio link ─────────────────────────────────────────

CONDOMINIOS_TABLE = "condominios"


def em_condominio_derivado(row: Optional[dict]) -> Optional[bool]:
    """The three-state answer the 202 flag carried, derived from the typed
    link: attached -> True, casa de rua -> False, neither -> None."""
    row = row or {}
    if row.get("condominio_id"):
        return True
    if row.get("casa_de_rua"):
        return False
    return None


def condominio_resumo(client: Any, org_id: UUID, condominio_id: Any) -> Optional[dict]:
    """`{id, nome, cidade, bairro, status_validacao}` of the linked
    condomínio, or None when unlinked. Org-scoped (the trigger guarantees it
    on write; the read re-checks rather than trusting it)."""
    if not condominio_id:
        return None
    rows = (
        _t(client, CONDOMINIOS_TABLE)
        .select("id,nome,cidade,bairro,status_validacao,fundido_em_id")
        .eq("org_id", str(org_id))
        .eq("id", str(condominio_id))
        .execute()
    ).data or []
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r["id"],
        "nome": r.get("nome"),
        "cidade": r.get("cidade"),
        "bairro": r.get("bairro"),
        "status_validacao": r.get("status_validacao"),
    }


def _condominio_patch(client: Any, org_id: UUID, patch: dict) -> dict:
    """Validate + complete the condomínio pair of a write.

    Exclusive by construction: attaching a condomínio clears `casa_de_rua`;
    marking `casa_de_rua` detaches the condomínio — the CHECK can never be
    reached through the app. Both set at once is a 422 (the schema refuses it
    first; this is the service-level backstop for non-HTTP callers). The
    condomínio must exist IN THIS ORG and not be merged/discarded."""
    extra: dict = {}
    tem_cond = "condominio_id" in patch
    tem_rua = "casa_de_rua" in patch
    if tem_rua and patch["casa_de_rua"] is None:
        raise ValidationError_("casa_de_rua não pode ser nulo.", field="casa_de_rua")
    if tem_cond and tem_rua and patch["casa_de_rua"] and patch["condominio_id"]:
        raise ValidationError_(
            "condominio_id e casa_de_rua são exclusivos: um imóvel de rua não "
            "pertence a um condomínio.",
            field="casa_de_rua",
        )
    if tem_cond and patch["condominio_id"]:
        cid = str(patch["condominio_id"])
        rows = (
            _t(client, CONDOMINIOS_TABLE)
            .select("id,status_validacao,fundido_em_id")
            .eq("org_id", str(org_id))
            .eq("id", cid)
            .execute()
        ).data or []
        if not rows:
            raise ValidationError_("Condomínio não encontrado.", field="condominio_id")
        if rows[0].get("fundido_em_id"):
            raise ValidationError_(
                "Este condomínio foi fundido em outro; escolha o condomínio de destino.",
                field="condominio_id",
            )
        if rows[0].get("status_validacao") == "descartado":
            raise ValidationError_(
                "Este condomínio foi descartado; reabra-o em Condomínios ou escolha outro.",
                field="condominio_id",
            )
        extra["condominio_id"] = cid
        if not tem_rua:
            extra["casa_de_rua"] = False
    if tem_rua and patch["casa_de_rua"] and not tem_cond:
        extra["condominio_id"] = None
    return extra


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


def municipio_do_imovel(client: Any, org_id: UUID, codigo: str) -> Optional[str]:
    """The município an imóvel sits in — the context the inscrição municipal
    needs to be read at all (each prefeitura has its own mask,
    `canonical-identifiers`). The live Vista mirror first, then the
    registry's delist-time snapshot; None when neither knows."""
    for tabela, chave_codigo, coluna in (
        ("imoveis", "codigo", "cidade"),
        (REGISTRY_TABLE, "codigo_canonical", "snap_cidade"),
    ):
        rows = (
            _t(client, tabela)
            .select(coluna)
            .eq("org_id", str(org_id))
            .eq(chave_codigo, codigo)
            .limit(1)
            .execute()
        ).data or []
        if rows and rows[0].get(coluna):
            return str(rows[0][coluna])
    return None


def canonizar_valores(
    client: Any, org_id: UUID, codigo: str, valores: dict
) -> dict:
    """CANONICAL ON WRITE for the identifier columns of `imovel_dados`
    (owner rule 2026-10-01, `canonical-identifiers`): `numero_matricula` is
    stored `79.826`, `prefeitura_cadastro_imobiliario` in its município's
    punctuated mask. A value that does not fit its type is kept AS READ
    (never rewritten, stays visible); one that is a valid identifier of
    ANOTHER type (a CPF typed into the matrícula field) is refused —
    `ValidationError_` naming the field, the hand-in a human sees."""
    saida = dict(valores)
    municipio: Optional[str] = None
    municipio_lido = False
    for campo, tipo in idf.TIPO_POR_CAMPO_ESCRITA_IMOVEL.items():
        bruto = saida.get(campo)
        if bruto is None or not str(bruto).strip():
            continue
        ctx: dict = {}
        if tipo == "inscricao_municipal":
            if not municipio_lido:
                municipio, municipio_lido = municipio_do_imovel(client, org_id, codigo), True
            ctx["municipio"] = municipio
        g = idf.para_gravar(tipo, bruto, **ctx)
        if g.rejeitado_por_tipo:
            raise ValidationError_(
                f"O valor informado é um {str(g.tipo_detectado).upper()} válido, "
                f"não um(a) {campo.replace('_', ' ')}.",
                field=campo,
            )
        saida[campo] = g.valor
    return saida


def _gravar(
    client: Any, org_id: UUID, codigo: str, atual: Optional[dict], patch: dict
) -> None:
    """Insert the imóvel's row, or update it — the ONE write shape every
    author of this table uses (`atualizar`, `gravar_extraido`,
    `gravar_fontes_matricula`).

    `atual` is the row the caller just re-read. Read-then-write rather than
    `upsert()` for the reason `registrar_imovel` records: the mock's upsert is
    a no-op, so an upsert path tests green and breaks live.

    Identifier columns are written CANONICAL here (`canonizar_valores`) — the
    one chokepoint, so no author of this table can forget it.
    """
    patch = canonizar_valores(client, org_id, codigo, patch)
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
        _encerrar_conflitos_de_campos_limpos(client, org_id, codigo, patch)


def _encerrar_conflitos_de_campos_limpos(
    client: Any, org_id: UUID, codigo: str, patch: dict
) -> None:
    """A write that EMPTIES an extracted field ("Limpar") leaves nothing for a
    pending proposal to replace: its conflicts are closed here, at the one
    write chokepoint every author of this table shares (F62, 2026-10-23 — a
    cleared `titulo_aquisitivo_texto` kept an obsolete "Documento/atual" row
    pendente forever). Reuses the conflict sweep, scoped to the cleared
    fields (`campo_limpo`). Lazy import — that module imports this one."""
    if not any(valor is None for valor in patch.values()):
        return
    from app.modules.imovel_hub import campos_extraidos_service as campos_svc

    limpos = frozenset(
        campo.chave
        for campo in campos_svc.CAMPOS.values()
        if all(c in patch and patch[c] is None for c in campo.colunas)
    )
    if limpos:
        campos_svc.backfill_resolver_conflitos_pendentes(
            client, org_id, codigo=codigo, campos=limpos
        )


def gravar_extraido(
    client: Any, org_id: UUID, codigo: str, atual: Optional[dict], patch: dict
) -> None:
    """The write `campos_extraidos_service` (D1, migration 154) makes — a
    machine reading filling an empty field, or a human accepting a conflict.

    Refuses any column outside that module's field registry: this is not a
    back door to the other authored fields. `atual` is the row the caller
    just re-read (the D1 decision was made against it).
    """
    from app.modules.imovel_hub.campos_extraidos_service import CAMPOS

    permitidas = {
        coluna
        for campo in CAMPOS.values()
        for coluna in (*campo.colunas, *campo.colunas_proveniencia())
    }
    recusados = sorted(set(patch) - permitidas)
    if recusados:
        raise ValueError(
            f"gravar_extraido: colunas fora dos campos extraídos: {', '.join(recusados)}"
        )
    _gravar(client, org_id, codigo, atual, patch)


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
    """Manual override for all 7 address fields (migration 149, widened by
    159 from the 4 the contract gate reads to also cover complemento/bairro/
    CEP — a condo UNIT address). Only keys present in `valores` are touched —
    same absence-means-leave-alone / `None`-clears contract `atualizar` uses.

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
        if coluna == "endereco_manual_cep" and novo:
            # canonical BEFORE the history comparison, so `01310100` re-saved
            # as the `01310-100` already on file is not a change
            novo = idf.canonico_ou_bruto("cep", novo)
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


# ─── Deal references (migration 226) ──────────────────────────────────────
#
# Valid for ANY imóvel, Vista or manual: authored data that belongs on
# `imovel_dados`, never on the Vista mirror. `processo_atual_numero` is a
# convenience pointer to TODAY's deal (an imóvel can be sold or rented more
# than once; deals live in `processos_venda`), not the deal's identity.

CAMPOS_REFERENCIAS: tuple[str, ...] = (
    "processo_atual_numero",
    "drive_folder_url",
    "drive_folder_id",
)

#: A Drive FOLDER link only: `…/drive/folders/<id>`, `…/drive/u/0/folders/<id>`
#: or `…/folders/<id>`, optionally followed by a query string. A file link, a
#: `open?id=` link or any other host is refused (never guessed at).
_DRIVE_PASTA_RE = re.compile(
    r"^https://drive\.google\.com/(?:drive/(?:u/\d+/)?)?folders/(?P<id>[A-Za-z0-9_-]+)(?:[/?#].*)?$"
)


def parse_drive_folder_url(url: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """`(url, folder_id)` for a Drive folder link; `(None, None)` clears.

    The id is DERIVED here, never typed (migration 226). A URL that is not a
    Drive folder is a 400 `drive_url_invalida`, never stored.
    """
    limpo = (url or "").strip()
    if not limpo:
        return None, None
    m = _DRIVE_PASTA_RE.match(limpo)
    if not m:
        raise AppException(
            code="drive_url_invalida",
            message="Informe o link de uma PASTA do Google Drive (https://drive.google.com/drive/folders/…).",
            status_code=400,
            details={"campo": "drive_folder_url"},
        )
    return limpo, m.group("id")


def referencias_da_linha(row: Optional[dict]) -> dict:
    """The three refs as the wire shape, nulls when nothing is stored."""
    row = row or {}
    return {campo: row.get(campo) for campo in CAMPOS_REFERENCIAS}


def gravar_referencias(
    client: Any, org_id: UUID, codigo: str, *, valores: dict
) -> dict:
    """Partial write of `processo_atual_numero` / `drive_folder_url`
    (+ derived `drive_folder_id`) for ANY registered imóvel. Absence leaves a
    field alone; `None`/empty clears it. Returns the wire shape."""
    ensure_imovel(client, org_id, codigo)
    recusados = sorted(set(valores) - {"processo_atual_numero", "drive_folder_url"})
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )
    patch: dict = {}
    if "processo_atual_numero" in valores:
        numero = (valores["processo_atual_numero"] or "").strip()
        patch["processo_atual_numero"] = numero or None
    if "drive_folder_url" in valores:
        # Validated BEFORE any write: a bad link must leave nothing behind.
        url, pasta = parse_drive_folder_url(valores["drive_folder_url"])
        patch["drive_folder_url"] = url
        patch["drive_folder_id"] = pasta
    atual = linha(client, org_id, codigo)
    if patch:
        _gravar(client, org_id, codigo, atual, patch)
        atual = linha(client, org_id, codigo)
    return referencias_da_linha(atual)


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
    "CAMPOS_DESCRICAO_IMOVEL_CONTRATO",
    "CAMPOS_ENDERECO_MANUAL",
    "CAMPOS_ONUS_FONTE",
    "CAMPOS_PROVENIENCIA",
    "CAMPOS_TEXTO_CONTRATO",
    "CAMPOS_TITULO_AQUISITIVO",
    "HISTORICO_ENDERECO_TABLE",
    "TABLE",
    "CAMPOS_QUINTETO_MANUAL",
    "atualizar",
    "ensure_imovel",
    "extracao_referenciada",
    "gravar_endereco_manual",
    "gravar_extraido",
    "gravar_fontes_matricula",
    "gravar_texto_contrato",
    "historico_endereco",
    "linha",
    "obter",
]
