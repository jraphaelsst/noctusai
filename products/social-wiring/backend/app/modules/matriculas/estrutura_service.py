"""The structured half of a matrícula: its acts, what a contract quotes, and
where the título aquisitivo and the ônus come from (migration 109).

🔴 THE USER DECISION THIS FILE EXISTS TO KEEP
---------------------------------------------
The promessa de compra e venda describes the property with the LITERAL text
of its matrícula — typos, odd spacing and OCR artefacts included — because a
cartório compares the quote against its own book. So:

- the split comes from the SEED (`segment_matricula_atos`), never re-done here;
- acts are persisted as OFFSETS into `matricula_extracoes.texto_extraido` —
  no table in this flow carries a copy of an act's text;
- every text `listar_atos` returns is `texto_extraido[inicio:fim]`, and
  nothing else — no strip, no join separator, no normalisation on the way
  out. `normalize` is used ONLY to MATCH suggestion terms, never to produce
  output.
  🔴 UPDATED BY MIGRATION 136 — the one exception is the CONTRACT QUOTE
  (`_citacao`/`obter_selecao`): each act's slice is first `subtrair_ruido`'d
  against the extraction's `ruido` (page furniture detected at transcription
  time), so a header/footer that landed inside an act is never quoted into a
  deed. The quote is therefore `texto_extraido[inicio:fim]` MINUS its noise
  spans, joined back together with no separator — still no strip, no
  normalisation, just fewer bytes. `ruido = []` (nothing detected, or a row
  from before migration 136) is the one case where the quote is still the
  untouched slice, unchanged from before.

IMMUTABILITY IS WHAT MAKES OFFSETS SAFE
---------------------------------------
An extraction's text is written once (`service.processar_extracao`), and its
acts are inserted once: `persistir_atos` refuses to re-segment an extraction
that already has acts. A contract selection or an imovel_dados pointer can
therefore hold offsets forever, and migration 109's RESTRICT foreign keys turn
"delete an extraction something quotes" into a loud failure —
`garantir_removivel` turns it into a 409 before the database has to.

THE SUGGESTER NEVER WRITES
--------------------------
`sugerir` is a heuristic over act text (latest transfer act → título
aquisitivo; acts citing hipoteca / alienação fiduciária / penhora /
indisponibilidade / usufruto → ônus candidates). Its output is returned for the
operator to confirm. Only `definir_fontes` — a human request — writes a
pointer, stamping `origem='sugerido'` when the human picked what the heuristic
picked and `'manual'` otherwise. 099's manual `situacao_onus` is never touched.

🔴 EVERY QUERY CARRIES AN EXPLICIT `org_id` PREDICATE
------------------------------------------------------
The clients here are service-role (the request path uses
`deps.get_matriculas_client`, the background task `deps.get_background_client`),
and service-role bypasses RLS.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import (
    BlocoAbertura,
    MatriculaAto,
    RuidoSpan,
    ato_hint_span,
    normalize,
    segment_matricula_atos,
    segmentar_abertura,
    subtrair_ruido,
)
from noctusai_lib.integrations.documents.abnt import clip_ranges
from noctusai_lib.integrations.documents.formatting import (
    FormatRange,
    ranges_from_json,
    ranges_to_json,
)
from noctusai_lib.primitives.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import negociacao_service
from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub import documentos_service as docs_svc
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import arquivos_service as arquivos_svc
from app.modules.matriculas import qualificacao_service as qualificacao_svc
from app.services import table_reads
from app.services.documento_store import log_acesso_extracao, now_iso, today

logger = logging.getLogger(__name__)

EXTRACOES_TABLE = "matricula_extracoes"
ATOS_TABLE = "matricula_atos"
#: Migration 136 — the abertura's typed sub-spans (`descricao_imovel`,
#: `cadastro_municipal`, `proprietarios`, `registro_anterior`).
ABERTURA_BLOCOS_TABLE = "matricula_abertura_blocos"
SELECAO_TABLE = "atendimento_contrato_matricula_atos"
CONTRATOS_TABLE = "atendimento_contratos"
NEGOCIACAO_TABLE = "atendimento_negociacao"
PERMUTA_ATIVOS_TABLE = "permuta_ativos"

#: `atendimento_contrato_matricula_atos.papel` (migration 115).
PAPEL_OBJETO = "objeto"
PAPEL_PERMUTA = "permuta"

STATUS_CONCLUIDA = "concluida"

#: A read of the raw transcription (migration 111) — the CPF-bearing text
#: `imovel_documento_acessos` (109) never logged. See `log_leitura_texto`.
ACAO_TEXT_VIEW = "text_view"

#: [2026-09-22] `vincular_imovel` linking an unlinked extraction to a
#: código — the one write-side `acao` this table carries. `log_acesso_
#: extracao`'s shape (`extracao_id` + `usuario_id` + `acao` + `created_at`)
#: is agnostic to read-vs-write; reused here rather than a new migration
#: adding a `codigo_vinculado_por`/`_em` provenance pair to `matricula_
#: extracoes`, since this table has no other provenance columns for
#: `codigo` to begin with.
ACAO_IMOVEL_VINCULADO = "imovel_vinculado"

#: Only a PDF goes through the transcriber (`service.processar_extracao`
#: hands it `mimetype="application/pdf"`); an imóvel's photographed matrícula
#: is still stored, just not transcribed.
MIME_TRANSCREVIVEL = "application/pdf"

_ESTADOS_EM_ANDAMENTO = ("pendente", "processando")


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _exigir_org(org_id: Any) -> str:
    if not org_id:
        raise ValueError(
            "matricula estrutura requires an org_id — a service-role query "
            "without one is not scoped to any tenant"
        )
    return str(org_id)


def _fatia(texto: str, inicio: int, fim: int) -> str:
    """`texto[inicio:fim]` — refusing, loudly, offsets that do not fit.

    An out-of-range offset means an act and its text diverged, which the
    immutability contract says cannot happen. Python would silently clamp the
    slice and return a SHORTER quote; for a legal quote that is the worst
    possible failure, so it raises instead.
    """
    if not (0 <= inicio <= fim <= len(texto)):
        raise ValueError(
            f"offsets [{inicio}:{fim}] fora do texto (len={len(texto)}) — "
            "atos e texto_extraido divergiram"
        )
    return texto[inicio:fim]


# ─── persistence ──────────────────────────────────────────────────────────


def linhas_de_atos(
    extracao_id: str, org_id: str, atos: list[MatriculaAto]
) -> list[dict]:
    """Seed segmenter output → `matricula_atos` rows. Offsets only."""
    return [
        {
            "id": str(uuid4()),
            "org_id": org_id,
            "extracao_id": extracao_id,
            "ordem": ordem,
            "kind": ato.kind,
            "numero": ato.numero,
            "char_inicio": ato.start,
            "char_fim": ato.end,
            "header_inicio": ato.header_start,
            "header_fim": ato.header_end,
            "created_at": now_iso(),
        }
        for ordem, ato in enumerate(atos)
    ]


def linhas_de_abertura_blocos(
    extracao_id: str, org_id: str, blocos: tuple[BlocoAbertura, ...]
) -> list[dict]:
    """Seed segmenter output (`matricula_abertura.segmentar_abertura`) ->
    `matricula_abertura_blocos` rows. Offsets only — same discipline as
    `linhas_de_atos`."""
    return [
        {
            "id": str(uuid4()),
            "org_id": org_id,
            "extracao_id": extracao_id,
            "campo": bloco.campo,
            "char_inicio": bloco.start,
            "char_fim": bloco.end,
            "rotulo_inicio": bloco.rotulo_start,
            "rotulo_fim": bloco.rotulo_end,
            "created_at": now_iso(),
        }
        for bloco in blocos
    ]


def persistir_atos(db: Any, extracao_id: str, org_id: Any, texto: str) -> int:
    """Segment `texto` and insert its acts. Returns how many were written.

    🔴 Never re-segments: if the extraction already has acts, nothing is
    written (returns 0). Re-segmenting would mint new act ids and orphan every
    contract selection / imovel_dados pointer that quotes the old ones.
    """
    org = _exigir_org(org_id)
    existentes = (
        _t(db, ATOS_TABLE)
        .select("id")
        .eq("org_id", org)
        .eq("extracao_id", str(extracao_id))
        .limit(1)
        .execute()
    ).data or []
    if existentes:
        return 0
    linhas = linhas_de_atos(str(extracao_id), org, segment_matricula_atos(texto or ""))
    if linhas:
        _t(db, ATOS_TABLE).insert(linhas).execute()
        # Migration 115 — each act's typed reading, as a SUGGESTION. Its own
        # try: the acts are the product and are already written; a failed
        # detail insert is logged at ERROR and self-heals on the next read
        # (`ato_detalhes_service.detalhes_por_ato` mints missing suggestions).
        try:
            detalhes_svc.persistir_sugestoes(db, org, str(extracao_id), texto or "", linhas)
        except Exception as falha:  # noqa: BLE001 - acts landed; details heal on read
            logger.error(
                "matricula %s: acts persisted but their detail suggestions were not "
                "(%s) — they are re-read on the next GET .../atos",
                extracao_id,
                falha,
                exc_info=True,
            )

        # Migration 136 — the abertura's typed sub-spans (`IMÓVEL:`,
        # `CADASTRO MUNICIPAL:`, ...). Same posture as the details above: the
        # acts are already written and are the product; a failed block insert
        # is logged at ERROR and does not roll anything back. Also self-heals
        # on read like the details above — `_blocos_abertura` mints missing
        # blocks the first time anything asks for them, covering BOTH a
        # failure right here and a row whose acts already existed before
        # migration 136 shipped and therefore never took this branch at all.
        abertura = next((l for l in linhas if l["kind"] == "abertura"), None)
        if abertura is not None:
            try:
                blocos = segmentar_abertura(
                    texto or "", abertura["char_inicio"], abertura["char_fim"]
                )
                if blocos:
                    _t(db, ABERTURA_BLOCOS_TABLE).insert(
                        linhas_de_abertura_blocos(str(extracao_id), org, blocos)
                    ).execute()
            except Exception as falha_abertura:  # noqa: BLE001 - acts landed; blocks heal on read
                logger.error(
                    "matricula %s: acts persisted but its abertura blocks were not "
                    "(%s) — they are re-segmented on the next GET .../atos",
                    extracao_id,
                    falha_abertura,
                    exc_info=True,
                )

        # Migration 137 — each party's qualificação, consolidated across acts
        # and matched against this org's clientes, as a SUGGESTION. Same
        # posture as the two blocks above: the acts are already written and
        # are the product; a failed qualification insert is logged at ERROR
        # and self-heals on the next read
        # (`qualificacao_svc.qualificacoes_da_extracao` mints missing rows).
        try:
            qualificacao_svc.persistir_sugestoes(db, org, str(extracao_id), texto or "", linhas)
        except Exception as falha_qualificacao:  # noqa: BLE001 - acts landed; qualificações heal on read
            logger.error(
                "matricula %s: acts persisted but their party qualifications were "
                "not (%s) — they are re-read on the next GET .../atos",
                extracao_id,
                falha_qualificacao,
                exc_info=True,
            )
    return len(linhas)


def purgar_texto_expirado(client: Any, org_id: UUID) -> int:
    """NULL `texto_extraido` for every extraction whose `retencao_ate` has
    passed (migration 111). Returns how many rows were purged.

    A PURGE, not a soft delete: `matricula_atos` offsets and every RESTRICT
    citation (`atendimento_contrato_matricula_atos`, `imovel_dados`'s
    título/ônus pointers) keep referencing this row by id, so the row itself
    must survive — only the CPF-bearing text it points into is gone. The
    row's `codigo` / `status` / act count stay readable as a record that a
    transcription existed and was purged, same posture `documento_store.
    DocumentoStore.varrer_expirados` takes with a soft-deleted document.

    NOC-REMEDIATE[retention-sweep-scheduler]: not wired to a scheduled job —
    same as `documento_store.DocumentoStore.varrer_expirados` (imovel) and
    `card_hub.financiamento_service.varrer_retencao` (atendimento) today. All
    three read the same policy table; wiring one is wiring the pattern, not a
    one-surface fix. — 2026-09-14
    """
    # Filtered on `texto_extraido` in PYTHON, not via `.not_.is_()` — the same
    # caution `certidoes.service._get_tjsp_last_request_at` documents:
    # supabase-py's `.not_.is_()` filter can silently behave differently
    # across client versions, and this query already has to fetch the id
    # either way.
    candidatos = (
        _t(client, EXTRACOES_TABLE)
        .select("id,texto_extraido")
        .eq("org_id", str(org_id))
        .lte("retencao_ate", today().isoformat())
        .execute()
    ).data or []
    rows = [r for r in candidatos if r.get("texto_extraido")]
    for row in rows:
        _t(client, EXTRACOES_TABLE).update({"texto_extraido": None}).eq(
            "id", row["id"]
        ).execute()
        # Migration 115 — party names / CPFs READ OUT of this text are the
        # same personal data; they must not outlive the text they came from.
        detalhes_svc.purgar_da_extracao(client, org_id, row["id"])
        # Migration 137 — a qualificação row carries the SAME class of data
        # (name, CPF/CNPJ, RG, endereço, profissão) and often MORE of it per
        # person than a detalhes row does. Same purge, same reason.
        qualificacao_svc.purgar_da_extracao(client, org_id, row["id"])
    return len(rows)


# ─── reads ────────────────────────────────────────────────────────────────


def exigir_extracao(client: Any, org_id: UUID, extracao_id: UUID) -> dict:
    rows = (
        _t(client, EXTRACOES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(extracao_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(EXTRACOES_TABLE, str(extracao_id))
    return rows[0]


def vincular_imovel(
    client: Any,
    org_id: UUID,
    extracao_id: UUID,
    *,
    codigo: str,
    substituir: bool,
    usuario_id: Optional[Any],
) -> dict:
    """Link an EXISTING transcription (`codigo IS NULL`) to a property —
    the matrícula picker's escape hatch for an extraction that was
    transcribed without ever naming a código (an upload-without-codigo, or
    a manual paste), so it never needs a second, PAID re-upload just to
    become selectable for a contract.

    🔴 WRITE-ONCE, THE SAME AS THE DATABASE (migrations 111/135/136). A
    trigger on `matricula_extracoes` unconditionally refuses changing
    `codigo` once it is already set — "codigo não pode ser alterado após
    vinculado a um imóvel" — with NO escape hatch, `substituir` included:
    the trigger cannot see an application-level flag at all. This function
    enforces that SAME rule before ever attempting the write, so a caller
    gets a clean, named 409 instead of a raw Postgres exception surfacing
    as a 500 — but `substituir=True` still cannot make an already-linked
    extraction relink to a DIFFERENT código; it only changes which of two
    409 messages comes back (unconfirmed vs. permanently immutable), so a
    caller — and a human reading the response — can tell the two apart.
    Actually loosening the guard is a production schema decision, not an
    application one; see this function's delivery note.

    The código itself is NOT re-validated as "registered" here — the
    router already refused an unregistered one with a 422 before this
    runs (`dados_service.registro_status`); re-checking would just be a
    second query for the same answer.
    """
    extracao = exigir_extracao(client, org_id, extracao_id)
    canonico = (codigo or "").strip().upper()
    if not canonico:
        raise ValidationError_("Código do imóvel é obrigatório.", field="codigo")

    atual = extracao.get("codigo")
    if atual == canonico:
        return _extracao_saida_resumida(extracao)

    if atual:
        if not substituir:
            raise ConflictError(
                f"Esta transcrição já está vinculada ao imóvel {atual}. "
                "Envie substituir=true para confirmar a troca.",
                resource=EXTRACOES_TABLE,
            )
        # `substituir=True` still cannot land: the DB's write-once trigger
        # (migrations 111/135/136) refuses ANY change to an already-set
        # `codigo`, unconditionally — see the docstring above.
        raise ConflictError(
            f"O vínculo desta transcrição com o imóvel {atual} é permanente "
            "e não pode ser trocado — crie uma nova transcrição para "
            f"vincular ao imóvel {canonico}.",
            resource=EXTRACOES_TABLE,
        )

    dados_service.ensure_imovel(client, org_id, canonico)
    (
        _t(client, EXTRACOES_TABLE)
        .update({"codigo": canonico})
        .eq("org_id", str(org_id))
        .eq("id", str(extracao_id))
        .execute()
    )
    log_acesso_extracao(
        client,
        docs_svc.STORE.acessos_table,
        org_id,
        extracao_id,
        usuario_id,
        ACAO_IMOVEL_VINCULADO,
    )
    return _extracao_saida_resumida({**extracao, "codigo": canonico})


def _extracao_saida_resumida(extracao: dict) -> dict:
    """The SAME summary shape `GET /extracoes` (the list) returns — never
    the full row `GET /extracoes/{id}` does, which carries the CPF-bearing
    `texto_extraido` and (LGPD, migration 111) logs a `text_view` access
    every time it is read. A link operation is not a read of that text, so
    this response should not silently cost one."""
    colunas = (
        "id", "nome_arquivo", "tamanho_bytes", "num_paginas", "status",
        "erro_mensagem", "codigo", "imovel_documento_id", "arquivo_origem_id",
        "substituida_por", "possui_marcacao_bruta", "created_at",
    )
    return {c: extracao.get(c) for c in colunas}


def log_leitura_texto(
    client: Any, org_id: UUID, extracao_id: Any, usuario_id: Optional[Any]
) -> None:
    """Append a `text_view` row (migration 111) — written BEFORE the caller
    returns the text it names. A failed write fails the request, same
    contract as `DocumentoStore.url`.

    Keyed to `imovel_documento_acessos` via `docs_svc.STORE.acessos_table`
    rather than the literal name, so a future change to which table backs
    the imóvel surface's access log cannot silently drift the two apart.
    """
    log_acesso_extracao(
        client,
        docs_svc.STORE.acessos_table,
        org_id,
        extracao_id,
        usuario_id,
        ACAO_TEXT_VIEW,
    )


def _linhas_de_atos(client: Any, org_id: UUID, extracao: dict) -> list[dict]:
    """The extraction's act rows, ordered — healing a concluded extraction
    that has none.

    The heal covers two real cases: an extraction concluded before migration
    109 existed, and one whose act insert failed after its text landed
    (`service.processar_extracao` logs that failure and relies on this).
    """
    if extracao.get("status") != STATUS_CONCLUIDA or not extracao.get("texto_extraido"):
        return []

    def _ler() -> list[dict]:
        rows = table_reads.paged_rows(
            client,
            ATOS_TABLE,
            org_id,
            eq_filters={"extracao_id": str(extracao["id"])},
        )
        return sorted(rows, key=lambda r: r["ordem"])

    rows = _ler()
    if not rows:
        escritos = persistir_atos(
            client, str(extracao["id"]), org_id, extracao["texto_extraido"]
        )
        logger.info(
            "matricula %s: healed %d acts on first read", extracao["id"], escritos
        )
        rows = _ler()
    return rows


def _ato_saida(row: dict, texto: str) -> dict:
    inicio, fim = int(row["char_inicio"]), int(row["char_fim"])
    corpo = _fatia(texto, inicio, fim)
    rotulo_ini, rotulo_fim = ato_hint_span(
        texto,
        MatriculaAto(
            kind=row["kind"],
            numero=row.get("numero"),
            start=inicio,
            end=fim,
            header_start=row.get("header_inicio"),
            header_end=row.get("header_fim"),
        ),
    )
    return {
        "id": row["id"],
        "ordem": row["ordem"],
        "kind": row["kind"],
        "numero": row.get("numero"),
        "char_inicio": inicio,
        "char_fim": fim,
        "header_inicio": row.get("header_inicio"),
        "header_fim": row.get("header_fim"),
        "rotulo": texto[rotulo_ini:rotulo_fim],
        "texto": corpo,
    }


def atos_da_extracao(client: Any, org_id: UUID, extracao: dict) -> list[dict]:
    """The extraction's act rows in matrícula order (healing missing acts)."""
    return _linhas_de_atos(client, org_id, extracao)


def _bloco_abertura_saida(row: dict, texto: str) -> dict:
    inicio, fim = int(row["char_inicio"]), int(row["char_fim"])
    return {
        "id": row["id"],
        "campo": row["campo"],
        "char_inicio": inicio,
        "char_fim": fim,
        "rotulo_inicio": row.get("rotulo_inicio"),
        "rotulo_fim": row.get("rotulo_fim"),
        "texto": _fatia(texto, inicio, fim),
    }


def _blocos_abertura(client: Any, org_id: UUID, extracao: dict) -> list[dict]:
    """`matricula_abertura_blocos` rows for one extraction, in document
    order — healing a concluded extraction that has an abertura act but no
    blocks yet.

    That gap is real: `persistir_atos` only ever writes blocks on the SAME
    call that first segments an extraction's acts, so a row whose acts were
    already there before migration 136 shipped (which is every row that
    existed on 2026-09-18) never enters that branch and is stuck at zero
    blocks forever — unlike `matricula_atos` itself, which `_linhas_de_atos`
    below already self-heals on read. Both are derived ENTIRELY from
    `texto_extraido` (`segmentar_abertura` over the abertura act's own
    frozen offsets), so nothing is actually missing here, only unwritten.

    🔴 Never re-segments a row that already has blocks: the heal below only
    ever runs when this extraction has ZERO rows in
    `matricula_abertura_blocos` — the same discipline `persistir_atos`
    holds for acts, and for the same reason (re-deriving would mint new ids
    under offsets a future caller may come to address by id).

    `[]` for an extraction with no abertura act at all, one whose abertura
    text has no label `segmentar_abertura` recognises (see that function's
    module docstring), or one whose `texto_extraido` was purged (migration
    111) — there is nothing left to derive from, and that must come back
    empty, never raise. The purged case is checked BEFORE reading the table
    at all, same posture `_linhas_de_atos` takes for acts: a block's offsets
    are meaningless once the text they point into is gone, so even a block
    persisted before the purge must not be handed back as if it still
    quoted something.
    """
    extracao_id = str(extracao["id"])
    texto = extracao.get("texto_extraido")
    if not texto:
        return []
    rows = table_reads.paged_rows(
        client, ABERTURA_BLOCOS_TABLE, org_id, eq_filters={"extracao_id": extracao_id}
    )
    if not rows:
        abertura = next(
            (r for r in _linhas_de_atos(client, org_id, extracao) if r["kind"] == "abertura"),
            None,
        )
        if abertura is not None:
            try:
                blocos = segmentar_abertura(
                    texto, int(abertura["char_inicio"]), int(abertura["char_fim"])
                )
                if blocos:
                    _t(client, ABERTURA_BLOCOS_TABLE).insert(
                        linhas_de_abertura_blocos(extracao_id, _exigir_org(org_id), blocos)
                    ).execute()
            except Exception as falha:  # noqa: BLE001 - heal is best-effort; the re-read
                # below is the source of truth regardless — a lost race against a
                # concurrent healer looks identical to a genuine insert failure from
                # here, and both are answered the same way: read what is actually there.
                logger.error(
                    "matricula %s: abertura blocks did not heal cleanly on read (%s)",
                    extracao_id,
                    falha,
                    exc_info=True,
                )
            rows = table_reads.paged_rows(
                client,
                ABERTURA_BLOCOS_TABLE,
                org_id,
                eq_filters={"extracao_id": extracao_id},
            )
    return sorted(rows, key=lambda r: r["char_inicio"])


def blocos_abertura_da_extracao(client: Any, org_id: UUID, extracao: dict) -> list[dict]:
    """The abertura's typed blocks (migration 136) — healing on first read,
    see `_blocos_abertura`. Public for `preenchimento_service` (the
    `CADASTRO MUNICIPAL` block feeds the inscrição) and the backfill."""
    return _blocos_abertura(client, org_id, extracao)


def listar_atos(
    client: Any, org_id: UUID, extracao_id: UUID, *, usuario_id: Optional[Any] = None
) -> dict:
    """The acts as literal slices, each with its typed `detalhes` (migration
    115; `None` for the abertura). One `text_view` log covers the details
    too: they are readings OF the text this response already hands back.

    Migration 136 — also carries `ruido` (the extraction's detected page
    furniture, `[]` when none) and `abertura_blocos` (the abertura's typed
    sub-spans, `[]` when there is no abertura or none was recognised) — both
    as literal slices of the SAME `texto`, so the FE can highlight furniture
    and typed blocks in place. Unlike `atos`, these are NOT noise-subtracted:
    this endpoint shows the raw transcription; only the contract quote
    (`obter_selecao`) subtracts.
    """
    extracao = exigir_extracao(client, org_id, extracao_id)
    log_leitura_texto(client, org_id, extracao_id, usuario_id)
    texto = extracao.get("texto_extraido") or ""
    rows = _linhas_de_atos(client, org_id, extracao)
    atos = [_ato_saida(r, texto) for r in rows]
    detalhes = detalhes_svc.detalhes_por_ato(client, org_id, extracao, rows) if rows else {}
    qualificacoes = (
        qualificacao_svc.qualificacoes_da_extracao(client, org_id, extracao, rows)
        if rows
        else []
    )
    resolved = table_reads.resolve_actors(
        (
            {d.get("confirmado_por") for d in detalhes.values()}
            | {q.get("confirmado_por") for q in qualificacoes}
            | {q.get("descartado_por") for q in qualificacoes}
        )
        - {None}
    )
    for ato in atos:
        ato["detalhes"] = detalhes_svc.detalhes_saida(detalhes.get(str(ato["id"])), resolved)
    blocos = _blocos_abertura(client, org_id, extracao) if rows else []
    return {
        "extracao_id": extracao["id"],
        "status": extracao.get("status"),
        "codigo": extracao.get("codigo"),
        "total": len(atos),
        "atos": atos,
        "ruido": extracao.get("ruido") or [],
        "abertura_blocos": [_bloco_abertura_saida(r, texto) for r in blocos],
        # Migration 137 — the matrícula's parties, consolidated across acts
        # and matched against this org's clientes. `[]` for an extraction
        # with no R/AV acts, or whose text carries no checksum-valid
        # CPF/CNPJ anywhere.
        "qualificacoes": [
            qualificacao_svc.qualificacao_saida(row, resolved) for row in qualificacoes
        ],
    }


# ─── linking an imóvel's stored PDF ────────────────────────────────────────


def criar_extracao_de_documento(
    client: Any,
    org_id: UUID,
    *,
    codigo: str,
    imovel_documento_id: UUID,
    usuario_id: Optional[Any],
) -> dict:
    """Create a `pendente` extraction for a matrícula PDF the imóvel already
    holds. The caller schedules the transcription.

    409 when the document already has an extraction that is in flight or
    concluded — a second transcription of the same bytes would mint a second
    set of act ids for the same matrícula, and contracts would quote either at
    random. An `erro` extraction does not block a retry.
    """
    codigo = codigo.strip().upper()
    dados_service.ensure_imovel(client, org_id, codigo)
    documento = docs_svc.STORE.exigir(client, org_id, codigo, imovel_documento_id)
    if documento.get("tipo_documento") != "matricula":
        raise ValidationError_(
            "O documento não é uma matrícula.", field="imovel_documento_id"
        )
    if documento.get("mime_type") != MIME_TRANSCREVIVEL:
        raise ValidationError_(
            "Apenas matrículas em PDF podem ser transcritas.",
            field="imovel_documento_id",
        )

    anteriores = (
        _t(client, EXTRACOES_TABLE)
        .select("id,status")
        .eq("org_id", str(org_id))
        .eq("imovel_documento_id", str(imovel_documento_id))
        .neq("status", "erro")
        .limit(1)
        .execute()
    ).data or []
    if anteriores:
        raise ConflictError(
            f"Este documento já tem uma transcrição ({anteriores[0]['id']}, "
            f"{anteriores[0]['status']}).",
            resource=EXTRACOES_TABLE,
        )

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "user_id": str(usuario_id) if usuario_id else None,
        "nome_arquivo": documento.get("nome_original") or "matricula.pdf",
        "tamanho_bytes": documento.get("tamanho_bytes"),
        "status": "pendente",
        "codigo": codigo,
        "imovel_documento_id": str(imovel_documento_id),
        "created_at": now_iso(),
    }
    _t(client, EXTRACOES_TABLE).insert(row).execute()
    return {**row, "storage_path": documento["storage_path"]}


def criar_extracao_manual(
    client: Any,
    org_id: UUID,
    *,
    codigo: str,
    texto: str,
    usuario_id: Optional[Any],
) -> dict:
    """Create a CONCLUDED extraction straight from typed/pasted matrícula
    text (migration 149) — the manual path for testing the contract
    generator without an AI transcription. The row is `origem='manual'` and
    otherwise indistinguishable to every downstream reader from an uploaded
    one: `service.registrar_transcricao_manual` (called by the router right
    after this) runs the SAME `persistir_atos` segmenter an AI
    transcription's text goes through, so acts/título/ônus selection work
    identically.

    No collision check against an existing extraction for this código —
    same posture the plain PDF-upload route (`POST /extrair` with a
    `codigo`) already takes; only the imóvel-linked re-transcription
    (`criar_extracao_de_documento`) refuses a duplicate, because THAT one is
    scoped to one specific stored document.
    """
    codigo = codigo.strip().upper()
    texto = (texto or "").strip()
    if not texto:
        raise ValidationError_("O texto da matrícula é obrigatório.", field="texto")
    dados_service.ensure_imovel(client, org_id, codigo)

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "user_id": str(usuario_id) if usuario_id else None,
        "nome_arquivo": f"Transcrição manual — {codigo}",
        "status": "pendente",
        "origem": "manual",
        "codigo": codigo,
        "created_at": now_iso(),
    }
    _t(client, EXTRACOES_TABLE).insert(row).execute()
    return row


def caminho_da_fonte(client: Any, org_id: UUID, extracao: dict) -> Optional[str]:
    """The storage path of the PDF this extraction was (or will be)
    transcribed from — the imóvel's document, or the standalone retained
    file (migration 135). `None` when nothing was kept (a pre-135 row) or
    the kept file was since removed: there is nothing to re-read, and the
    caller must say so rather than retry forever."""
    try:
        if extracao.get("imovel_documento_id"):
            return docs_svc.STORE.exigir(
                client, org_id, extracao["codigo"], UUID(str(extracao["imovel_documento_id"]))
            )["storage_path"]
        if extracao.get("arquivo_origem_id"):
            return arquivos_svc.exigir(
                client, org_id, UUID(str(extracao["arquivo_origem_id"]))
            )["storage_path"]
    except NotFoundError:
        logger.warning(
            "matricula %s: its retained source is gone — nothing to re-read",
            extracao.get("id"),
        )
    return None


def criar_retranscricao(
    client: Any, org_id: UUID, extracao_id: str, *, usuario_id: Optional[Any]
) -> dict:
    """Re-run transcription of a CONCLUDED extraction's retained source
    (migration 135). SUPERSEDES: inserts a new `pendente` row carrying the
    same `codigo` / `imovel_documento_id` / `arquivo_origem_id`, then marks
    `anterior.substituida_por` — never touches `anterior.texto_extraido`, so
    the write-once trigger (111) is never in tension with this.

    409 when there is nothing to re-run from: the extraction is not yet
    concluded, it was already superseded once, or (the pre-135 rows this
    slice cannot repair — see `NOC-REMEDIATE`-turned-closed note in
    `service.py`) it kept no retained source at all.
    """
    anterior = exigir_extracao(client, org_id, UUID(extracao_id))
    if anterior.get("status") != STATUS_CONCLUIDA:
        raise ConflictError(
            "Só é possível retranscrever uma extração concluída.",
            resource=EXTRACOES_TABLE,
        )
    if anterior.get("substituida_por"):
        raise ConflictError(
            "Esta extração já foi substituída por uma retranscrição mais "
            "recente.",
            resource=EXTRACOES_TABLE,
        )

    imovel_documento_id = anterior.get("imovel_documento_id")
    arquivo_origem_id = anterior.get("arquivo_origem_id")
    if imovel_documento_id:
        documento = docs_svc.STORE.exigir(
            client, org_id, anterior["codigo"], UUID(imovel_documento_id)
        )
        storage_path = documento["storage_path"]
        nome_arquivo = documento.get("nome_original") or anterior["nome_arquivo"]
    elif arquivo_origem_id:
        arquivo = arquivos_svc.exigir(client, org_id, UUID(arquivo_origem_id))
        storage_path = arquivo["storage_path"]
        nome_arquivo = arquivo.get("nome_original") or anterior["nome_arquivo"]
    else:
        raise ConflictError(
            "Esta extração não guardou o PDF de origem — envie o arquivo "
            "novamente para transcrever.",
            resource=EXTRACOES_TABLE,
        )

    nova_id = uuid4()
    row = {
        "id": str(nova_id),
        "org_id": str(org_id),
        "user_id": str(usuario_id) if usuario_id else None,
        "nome_arquivo": nome_arquivo,
        "tamanho_bytes": anterior.get("tamanho_bytes"),
        "status": "pendente",
        "codigo": anterior.get("codigo"),
        "imovel_documento_id": imovel_documento_id,
        "arquivo_origem_id": arquivo_origem_id,
        "created_at": now_iso(),
    }
    _t(client, EXTRACOES_TABLE).insert(row).execute()
    # 🔴 Marked AFTER the new row exists, never before: a failure between the
    # insert above and this update would leave `anterior` un-superseded
    # rather than pointing at a row that was never created.
    _t(client, EXTRACOES_TABLE).update({"substituida_por": str(nova_id)}).eq(
        "id", str(extracao_id)
    ).eq("org_id", str(org_id)).execute()
    return {**row, "storage_path": storage_path}


async def obter_url_arquivo_original(
    client: Any,
    storage: Any,
    org_id: UUID,
    extracao_id: str,
    *,
    usuario_id: Optional[Any],
    intent: str = "view",
) -> dict:
    """A short-TTL signed URL for the SOURCE PDF an extraction was
    transcribed from — linked (`imovel_documentos`) or standalone
    (`matricula_extracao_arquivos`, migration 135) — so a human can audit the
    transcription against the original. 409 when nothing was retained (the
    pre-135 unlinked rows).

    Logs the access against the EXTRACTION (`documento_store.
    log_acesso_extracao`) for the standalone case, since
    `arquivos_svc.STORE` has no `acessos_table` of its own to log through —
    see that module's docstring. The linked case already logs through
    `docs_svc.STORE.url`'s own `imovel_documento_acessos` write (as a plain
    `view`/`download`, not `extracao_id`-keyed — it has a real
    `imovel_documentos` row to log against).
    """
    extracao = exigir_extracao(client, org_id, UUID(extracao_id))
    imovel_documento_id = extracao.get("imovel_documento_id")
    arquivo_origem_id = extracao.get("arquivo_origem_id")
    if imovel_documento_id:
        return await docs_svc.url_do_documento(
            client,
            storage,
            org_id,
            extracao["codigo"],
            UUID(imovel_documento_id),
            usuario_id=usuario_id,
        )
    if arquivo_origem_id:
        signed = await arquivos_svc.url(
            client, storage, org_id, UUID(arquivo_origem_id)
        )
        log_acesso_extracao(
            client, docs_svc.STORE.acessos_table, org_id, extracao_id,
            usuario_id, intent,
        )
        return signed
    raise ConflictError(
        "Esta extração não guardou o PDF de origem.", resource=EXTRACOES_TABLE
    )


# ─── the suggester ────────────────────────────────────────────────────────

#: (normalised term, label, kinds it counts on). A transfer is REGISTERED
#: (R); the one averbação that transfers is the fiduciary consolidation
#: (Lei 9.514, art. 26 §7).
_TRANSFERENCIAS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("COMPRA E VENDA", "compra e venda", frozenset({"R"})),
    ("VENDA E COMPRA", "compra e venda", frozenset({"R"})),
    ("DOACAO", "doação", frozenset({"R"})),
    ("PARTILHA", "partilha", frozenset({"R"})),
    ("ADJUDICACAO", "adjudicação", frozenset({"R"})),
    ("ARREMATACAO", "arrematação", frozenset({"R"})),
    ("PERMUTA", "permuta", frozenset({"R"})),
    ("DACAO EM PAGAMENTO", "dação em pagamento", frozenset({"R"})),
    ("INTEGRALIZACAO", "integralização de capital", frozenset({"R"})),
    ("USUCAPIAO", "usucapião", frozenset({"R"})),
    ("CONSOLIDACAO DA PROPRIEDADE", "consolidação da propriedade", frozenset({"R", "AV"})),
)

#: (normalised term, `situacao_onus` vocabulary value from 099).
_ONUS: tuple[tuple[str, str], ...] = (
    ("HIPOTECA", "hipoteca"),
    ("ALIENACAO FIDUCIARIA", "alienacao_fiduciaria"),
    ("PENHORA", "penhora"),
    ("INDISPONIBILIDADE", "indisponibilidade"),
    ("USUFRUTO", "usufruto"),
)

_CANCELAMENTO = re.compile(
    r"\b(CANCELAMENTO|CANCELAD[OA]|CANCELA-SE|BAIXA|EXTINCAO|EXTINT[OA]|"
    r"LEVANTAMENTO|RENUNCIA)\b"
)


def _contem(norm: str, termo: str) -> bool:
    return re.search(rf"\b{re.escape(termo)}", norm) is not None


def _cita(norm: str, kind: str, numero: int) -> bool:
    """Does `norm` cite act `kind`-`numero` (`R-2`, `R.02`, `R 2/45.678`)?"""
    return (
        re.search(rf"(?<![A-Z]){kind}\s*[-.]?\s*0*{numero}(?!\d)", norm) is not None
    )


def _ref(row: dict, texto: str, termo: str) -> dict:
    saida = _ato_saida(row, texto)
    return {
        "ato_id": saida["id"],
        "ordem": saida["ordem"],
        "kind": saida["kind"],
        "numero": saida["numero"],
        "char_inicio": saida["char_inicio"],
        "char_fim": saida["char_fim"],
        "rotulo": saida["rotulo"],
        "termo": termo,
    }


def sugerir(texto: str, atos: list[dict]) -> dict:
    """Heuristic suggestions over an extraction's acts. Pure; never writes.

    - `titulo_aquisitivo`: the LATEST act carrying a transfer term, excluding
      acts that are themselves cancellations. `None` when there is none.
    - `onus`: every non-cancellation act citing an encumbrance term, with
      `cancelamento_citado_por` listing later cancellation acts that cite it
      by number, and `sugerido` = not cancelled. Cancelled candidates are
      still returned so the operator sees why they were left out.
    """
    ordenados = sorted(atos, key=lambda r: r["ordem"])
    normalizados = {
        r["id"]: normalize(_fatia(texto, int(r["char_inicio"]), int(r["char_fim"])))
        for r in ordenados
    }
    cancelamentos = {
        r["id"] for r in ordenados if _CANCELAMENTO.search(normalizados[r["id"]])
    }

    titulo: Optional[dict] = None
    onus: list[dict] = []
    for row in ordenados:
        if row["kind"] == "abertura" or row["id"] in cancelamentos:
            continue
        norm = normalizados[row["id"]]
        for termo, rotulo, kinds in _TRANSFERENCIAS:
            if row["kind"] in kinds and _contem(norm, termo):
                titulo = _ref(row, texto, rotulo)  # later acts overwrite: latest wins
                break
        for termo, tipo in _ONUS:
            if not _contem(norm, termo):
                continue
            canceladores = [
                outro["id"]
                for outro in ordenados
                if outro["ordem"] > row["ordem"]
                and outro["id"] in cancelamentos
                and row.get("numero") is not None
                and _cita(normalizados[outro["id"]], row["kind"], int(row["numero"]))
            ]
            onus.append(
                {
                    **_ref(row, texto, tipo),
                    "tipo": tipo,
                    "cancelamento_citado_por": canceladores,
                    "sugerido": not canceladores,
                }
            )
            break
    return {"titulo_aquisitivo": titulo, "onus": onus}


# ─── título aquisitivo / ônus pointers ─────────────────────────────────────


def _texto_da_extracao(
    client: Any, org_id: UUID, extracao_id: Any, cache: dict[str, str]
) -> str:
    chave = str(extracao_id)
    if chave not in cache:
        cache[chave] = exigir_extracao(client, org_id, chave).get("texto_extraido") or ""
    return cache[chave]


def _fontes_saida(
    client: Any, org_id: UUID, extracao: dict, linha: Optional[dict]
) -> tuple[Optional[dict], Optional[dict]]:
    linha = linha or {}
    textos = {str(extracao["id"]): extracao.get("texto_extraido") or ""}
    resolved = table_reads.resolve_actors(
        {
            linha.get("titulo_aquisitivo_confirmado_por"),
            linha.get("onus_fonte_confirmado_por"),
        }
        - {None}
    )

    titulo = None
    if linha.get("titulo_aquisitivo_ato_id"):
        texto = _texto_da_extracao(
            client, org_id, linha["titulo_aquisitivo_extracao_id"], textos
        )
        inicio = int(linha["titulo_aquisitivo_char_inicio"])
        fim = int(linha["titulo_aquisitivo_char_fim"])
        titulo = {
            "extracao_id": linha["titulo_aquisitivo_extracao_id"],
            "ato_id": linha["titulo_aquisitivo_ato_id"],
            "char_inicio": inicio,
            "char_fim": fim,
            "texto": _fatia(texto, inicio, fim),
            "origem": linha.get("titulo_aquisitivo_origem"),
            "confirmado_por": table_reads.actor(
                resolved, linha.get("titulo_aquisitivo_confirmado_por")
            ),
            "confirmado_em": linha.get("titulo_aquisitivo_confirmado_em"),
        }

    onus = None
    if linha.get("onus_fonte_extracao_id"):
        texto = _texto_da_extracao(client, org_id, linha["onus_fonte_extracao_id"], textos)
        onus = {
            "extracao_id": linha["onus_fonte_extracao_id"],
            "atos": [
                {
                    "ato_id": a["ato_id"],
                    "char_inicio": int(a["char_inicio"]),
                    "char_fim": int(a["char_fim"]),
                    "texto": _fatia(texto, int(a["char_inicio"]), int(a["char_fim"])),
                }
                for a in (linha.get("onus_fonte_atos") or [])
            ],
            "origem": linha.get("onus_fonte_origem"),
            "confirmado_por": table_reads.actor(
                resolved, linha.get("onus_fonte_confirmado_por")
            ),
            "confirmado_em": linha.get("onus_fonte_confirmado_em"),
        }
    return titulo, onus


def obter_fontes(client: Any, org_id: UUID, extracao_id: UUID) -> dict:
    extracao = exigir_extracao(client, org_id, extracao_id)
    texto = extracao.get("texto_extraido") or ""
    atos = _linhas_de_atos(client, org_id, extracao)
    codigo = extracao.get("codigo")
    linha = dados_service.linha(client, org_id, codigo) if codigo else None
    titulo, onus = _fontes_saida(client, org_id, extracao, linha)
    return {
        "extracao_id": extracao["id"],
        "codigo": codigo,
        "sugestoes": sugerir(texto, atos),
        "titulo_aquisitivo": titulo,
        "onus": onus,
    }


def _exigir_concluida(extracao: dict) -> None:
    if extracao.get("status") != STATUS_CONCLUIDA:
        raise ValidationError_(
            "A transcrição desta matrícula ainda não foi concluída.",
            field="extracao_id",
        )


def definir_fontes(
    client: Any,
    org_id: UUID,
    extracao_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[Any],
) -> dict:
    """Record the operator's título aquisitivo / ônus source acts.

    Only keys present in `valores` are touched. The request IS the
    confirmation: `confirmado_por/em` is stamped on every write, and `origem`
    records whether the human agreed with the heuristic (`sugerido`) or chose
    otherwise (`manual`).
    """
    extracao = exigir_extracao(client, org_id, extracao_id)
    _exigir_concluida(extracao)
    codigo = extracao.get("codigo")
    if not codigo:
        raise ValidationError_(
            "Vincule a matrícula a um imóvel antes de registrar título ou ônus.",
            field="codigo",
        )
    dados_service.ensure_imovel(client, org_id, codigo)

    texto = extracao.get("texto_extraido") or ""
    atos = _linhas_de_atos(client, org_id, extracao)
    por_id = {str(r["id"]): r for r in atos}
    sugestoes = sugerir(texto, atos)
    confirmado_por = str(usuario_id) if usuario_id else None
    agora = now_iso()

    def _exigir_ato(ato_id: Any, campo: str) -> dict:
        row = por_id.get(str(ato_id))
        if row is None:
            raise ValidationError_(
                f"O ato {ato_id} não pertence a esta matrícula.", field=campo
            )
        return row

    patch: dict[str, Any] = {}
    if "titulo_aquisitivo_ato_id" in valores:
        escolhido = valores["titulo_aquisitivo_ato_id"]
        if escolhido is None:
            patch.update({col: None for col in dados_service.CAMPOS_TITULO_AQUISITIVO})
        else:
            row = _exigir_ato(escolhido, "titulo_aquisitivo_ato_id")
            sugerido = sugestoes["titulo_aquisitivo"]
            patch.update(
                {
                    "titulo_aquisitivo_extracao_id": str(extracao["id"]),
                    "titulo_aquisitivo_ato_id": str(row["id"]),
                    "titulo_aquisitivo_char_inicio": int(row["char_inicio"]),
                    "titulo_aquisitivo_char_fim": int(row["char_fim"]),
                    "titulo_aquisitivo_origem": (
                        "sugerido"
                        if sugerido and sugerido["ato_id"] == str(row["id"])
                        else "manual"
                    ),
                    "titulo_aquisitivo_confirmado_por": confirmado_por,
                    "titulo_aquisitivo_confirmado_em": agora,
                }
            )

    if "onus_ato_ids" in valores:
        escolhidos = [str(i) for i in (valores["onus_ato_ids"] or [])]
        if len(set(escolhidos)) != len(escolhidos):
            raise ValidationError_("Ato repetido na lista de ônus.", field="onus_ato_ids")
        if not escolhidos:
            patch.update({col: None for col in dados_service.CAMPOS_ONUS_FONTE})
        else:
            rows = [_exigir_ato(i, "onus_ato_ids") for i in escolhidos]
            sugeridos = {o["ato_id"] for o in sugestoes["onus"] if o["sugerido"]}
            patch.update(
                {
                    "onus_fonte_extracao_id": str(extracao["id"]),
                    "onus_fonte_atos": [
                        {
                            "ato_id": str(r["id"]),
                            "char_inicio": int(r["char_inicio"]),
                            "char_fim": int(r["char_fim"]),
                        }
                        for r in rows
                    ],
                    "onus_fonte_origem": (
                        "sugerido" if set(escolhidos) == sugeridos else "manual"
                    ),
                    "onus_fonte_confirmado_por": confirmado_por,
                    "onus_fonte_confirmado_em": agora,
                }
            )

    if patch:
        dados_service.gravar_fontes_matricula(client, org_id, codigo, patch)
    return obter_fontes(client, org_id, extracao_id)


# ─── contract selection ───────────────────────────────────────────────────


def _exigir_contrato(client: Any, org_id: UUID, contrato_id: UUID) -> dict:
    rows = (
        _t(client, CONTRATOS_TABLE)
        .select("id,atendimento_id,deleted_at")
        .eq("org_id", str(org_id))
        .eq("id", str(contrato_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(CONTRATOS_TABLE, str(contrato_id))
    return rows[0]


def _ruido_da_extracao(extracao: dict) -> tuple[RuidoSpan, ...]:
    """`matricula_extracoes.ruido` (migration 136) -> `RuidoSpan`s
    `subtrair_ruido` consumes. `paginas` is not persisted — the shape guard
    (`matricula_ruido_valido`) only requires `start`/`end`/`kind` — and
    `subtrair_ruido` never reads it, so a placeholder `()` stands in for it
    here. `[]`/absent `ruido` (a pre-136 row, or nothing detected) yields
    `()`, under which `subtrair_ruido` is a no-op."""
    return tuple(
        RuidoSpan(start=int(item["start"]), end=int(item["end"]), kind=item["kind"], paginas=())
        for item in (extracao.get("ruido") or [])
    )


def _rebase_formatacao_da_selecao(
    spans: list[tuple[int, int]], formatacao_extracao: tuple[FormatRange, ...]
) -> tuple[FormatRange, ...]:
    """The extraction's DOCUMENT-level `formatacao` (offsets into the whole
    `texto_extraido`, migration 113) -> ranges local to the OUTPUT text
    `spans` concatenates (`"".join(texto[s:e] for s, e in spans)`), contract
    §5's "re-based onto the selected text".

    General over ANY ordered list of `[start, end)` spans into
    `texto_extraido` — not just one per act. Migration 136: a caller quoting
    an act ALSO subtracts its noise first (`subtrair_ruido`), so one act can
    contribute more than one span here; feeding the sub-spans through this
    same function (rather than the whole act range) is what keeps a
    formatting run that straddled a now-removed noise span correct. A range
    is clipped PER span (a range crossing a span boundary is split, same
    rule `abnt.paragraphs_from_text` applies at paragraph boundaries —
    reused via `clip_ranges`, not re-derived), then shifted from "0 inside
    this span" to its position in the OUTPUT text by the cumulative length
    of the spans already emitted. `spans` is walked in the caller's own
    (contract/quote) order, not extraction order, matching how the output
    text itself is built.
    """
    out: list[FormatRange] = []
    deslocamento = 0
    for inicio, fim in spans:
        for r in clip_ranges(formatacao_extracao, inicio, fim):
            out.append(
                FormatRange(
                    start=r.start + deslocamento,
                    end=r.end + deslocamento,
                    bold=r.bold,
                    underline=r.underline,
                )
            )
        deslocamento += fim - inicio
    return tuple(out)


def _papel(row: dict) -> str:
    return row.get("papel") or PAPEL_OBJETO


def texto_da_extracao(client: Any, org_id: UUID, extracao_id: Any) -> Optional[str]:
    """The extraction's raw transcription, or `None` when it doesn't exist /
    was never transcribed — a TOLERANT sibling of `exigir_extracao` (which
    404s) for callers reading the full text as a fact source
    (`contrato_gerador.carregador`'s `comarca_da_matricula` derivation)
    rather than requiring the row to exist."""
    rows = (
        _t(client, EXTRACOES_TABLE)
        .select("texto_extraido")
        .eq("org_id", str(org_id))
        .eq("id", str(extracao_id))
        .limit(1)
        .execute()
    ).data or []
    return (rows[0].get("texto_extraido") if rows else None) or None


def _extracao_padrao_do_imovel(client: Any, org_id: UUID, codigo: str) -> Optional[str]:
    """[Owner directive, 2026-09-23] `obter_selecao`'s fallback when the
    contract carries no explicit (operator-saved) selection yet: the
    extraction of the matrícula PDF uploaded on the imóvel page itself
    (`/imoveis/<codigo>` "Documentos do imóvel", tipo=matricula) — never a
    matrícula uploaded through some other surface. The most recently
    uploaded such document that actually finished transcribing wins; NEVER
    overrides an explicit `definir_selecao` (that path never reaches this
    helper — see the `if not todas` guard at its one call site)."""
    documentos = (
        _t(client, docs_svc.TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("tipo_documento", "matricula")
        .order("created_at", desc=True)
        .execute()
    ).data or []
    for documento in documentos:
        extracoes = (
            _t(client, EXTRACOES_TABLE)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("imovel_documento_id", str(documento["id"]))
            .eq("status", STATUS_CONCLUIDA)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if extracoes:
            return str(extracoes[0]["id"])
    return None


def obter_selecao(
    client: Any, org_id: UUID, contrato_id: UUID, *, usuario_id: Optional[Any] = None
) -> dict:
    """The contract's quoted acts, in contract order, as literal slices.

    `texto` is the plain concatenation of the slices — no separator is added,
    because the segmenter's spans already carry their own line breaks.
    🔴 UPDATED BY MIGRATION 136: each act's slice is FIRST `subtrair_ruido`'d
    against the extraction's `ruido` (detected page furniture), so selecting
    every act in matrícula order yields `texto_extraido` MINUS its noise
    spans, not `texto_extraido` byte for byte — a page header/footer landing
    inside an act must never be quoted into a deed. `ruido = []` (nothing
    detected, or a row from before migration 136) is the one case where the
    older invariant still holds exactly: byte for byte. `formatacao` is
    `texto`'s own bold/underline ranges, re-based from the extraction's
    document-level ranges (contract `projects/abnt-formatting-CONTRACT.md`
    §5) — `[]` for a selection made before the source carried formatting at
    all.

    `descricao_imovel` (migration 136): the `descricao_imovel` typed block
    (`matricula_abertura_blocos`, self-healed on read by `_blocos_abertura`
    when this extraction has an abertura but no blocks yet) for this
    extraction, as its own noise-subtracted `{texto, formatacao}`,
    independent of which acts are actually selected — `None` when the
    extraction has no such block (no `IMÓVEL:` label recognised, or no
    abertura at all). The contract's OBJETO clause needs this SPECIFICALLY
    rather than the whole selection: a de-furnitured abertura still ends in
    `PROPRIETÁRIOS: …`, which on a resold property names the PREVIOUS
    owners.

    The top-level quote is the OBJECT's (`papel='objeto'`), unchanged in
    shape. `permutas` (migration 115) lists one quote per property given in
    exchange, each in that same shape plus its `permuta_ativo_id`.
    """
    contrato = _exigir_contrato(client, org_id, contrato_id)
    todas = sorted(
        table_reads.paged_rows(
            client, SELECAO_TABLE, org_id, eq_filters={"contrato_id": str(contrato_id)}
        ),
        key=lambda r: (_papel(r) != PAPEL_OBJETO, str(r.get("permuta_ativo_id") or ""), r["ordem"]),
    )
    saida: dict[str, Any] = {
        "contrato_id": str(contrato_id),
        "extracao_id": None,
        "codigo": None,
        "atos": [],
        "texto": "",
        "formatacao": [],
        "descricao_imovel": None,
        "permutas": [],
        "selecionado_por": None,
        "selecionado_em": None,
    }
    if not todas:
        # [Owner directive, 2026-09-23] No explicit (operator-saved)
        # selection yet — default the EXTRACTION (never the atos/texto,
        # which stay a deliberate editorial pick) to the matrícula uploaded
        # on the imóvel page itself, so the FE picker opens on the RIGHT
        # document instead of nothing at all. `selecionado_por`/`_em` stay
        # unset — this is a computed default, not a recorded human choice.
        codigo = negociacao_service.imovel_do_atendimento(
            client, org_id, UUID(str(contrato["atendimento_id"]))
        )
        if codigo:
            saida["extracao_id"] = _extracao_padrao_do_imovel(client, org_id, codigo)
        return saida

    objeto = [r for r in todas if _papel(r) == PAPEL_OBJETO]
    if objeto:
        saida.update(_citacao(client, org_id, contrato_id, objeto, usuario_id))
    grupos: dict[str, list[dict]] = {}
    for row in todas:
        if _papel(row) == PAPEL_PERMUTA:
            grupos.setdefault(str(row["permuta_ativo_id"]), []).append(row)
    for permuta_ativo_id, rows in grupos.items():
        saida["permutas"].append(
            {
                "permuta_ativo_id": permuta_ativo_id,
                **_citacao(client, org_id, contrato_id, rows, usuario_id),
            }
        )

    resolved = table_reads.resolve_actors({todas[0].get("selecionado_por")} - {None})
    saida["selecionado_por"] = table_reads.actor(resolved, todas[0].get("selecionado_por"))
    saida["selecionado_em"] = todas[0].get("created_at")
    return saida


def _descricao_imovel_bloco(
    client: Any,
    org_id: UUID,
    extracao: dict,
    texto: str,
    ruido: tuple[RuidoSpan, ...],
) -> Optional[dict]:
    """The `descricao_imovel` typed block (migration 136) for this
    extraction, noise-subtracted and its own `formatacao` re-based —
    independent of which acts `selecao` actually picked, keyed only by the
    extraction (contract `carregador.py`'s OBJETO clause needs the property
    description SPECIFICALLY, never the whole abertura/selection). `None`
    when the extraction has no such block (no `IMÓVEL:` label recognised, or
    no abertura at all — `_blocos_abertura` heals a pre-136 row's missing
    blocks rather than answering `None` for it) — the caller falls back to
    the whole quote.
    """
    bloco = next(
        (b for b in _blocos_abertura(client, org_id, extracao) if b["campo"] == "descricao_imovel"),
        None,
    )
    if bloco is None:
        return None
    inicio, fim = int(bloco["char_inicio"]), int(bloco["char_fim"])
    spans = subtrair_ruido(inicio, fim, ruido)
    formatacao = _rebase_formatacao_da_selecao(spans, ranges_from_json(extracao.get("formatacao")))
    return {
        "texto": "".join(_fatia(texto, s, e) for s, e in spans),
        "formatacao": ranges_to_json(formatacao),
    }


def _citacao(
    client: Any,
    org_id: UUID,
    contrato_id: UUID,
    selecao: list[dict],
    usuario_id: Optional[Any],
) -> dict:
    """One group's quote — `selecao` is ordered and shares one extraction.

    🔴 Migration 136: each act's slice is subtracted against the
    extraction's `ruido` BEFORE it is quoted — see the module docstring's
    "UPDATED BY MIGRATION 136" note and `obter_selecao`'s docstring.
    """
    extracao = exigir_extracao(client, org_id, selecao[0]["extracao_id"])
    # 🔴 A quote (migration 111) — this returns the literal text of every
    # selected act, so a caller reading it is exactly as much a text access
    # as `listar_atos` or `GET /extracoes/{id}`.
    log_leitura_texto(client, org_id, extracao["id"], usuario_id)
    texto = extracao.get("texto_extraido") or ""
    ruido = _ruido_da_extracao(extracao)
    por_id = {str(r["id"]): r for r in _linhas_de_atos(client, org_id, extracao)}

    atos = []
    spans: list[tuple[int, int]] = []
    for sel in selecao:
        row = por_id.get(str(sel["ato_id"]))
        if row is None:
            # RESTRICT FKs make this unreachable in the database; reaching it
            # means the data is corrupt, and a quote with a hole in it must
            # not be served as if it were whole.
            raise ValueError(
                f"contrato {contrato_id}: ato {sel['ato_id']} selecionado não "
                f"existe na extração {extracao['id']}"
            )
        inicio, fim = int(row["char_inicio"]), int(row["char_fim"])
        # Migration 136 — the noise this act carries (a page header/footer
        # that landed inside its span) is never quoted: `subtrair_ruido`
        # returns the act's own ordered, disjoint sub-spans with every noise
        # span cut out. `ruido = ()` (nothing detected, or a pre-136 row) is
        # a no-op: `subtrair_ruido` returns `((inicio, fim),)` unchanged, so
        # this act's quote is exactly what it was before migration 136.
        subspans = subtrair_ruido(inicio, fim, ruido)
        spans.extend(subspans)
        atos.append(
            {
                "ato_id": str(row["id"]),
                "ordem": sel["ordem"],
                "kind": row["kind"],
                "numero": row.get("numero"),
                "char_inicio": inicio,
                "char_fim": fim,
                "texto": "".join(_fatia(texto, s, e) for s, e in subspans),
            }
        )

    formatacao = _rebase_formatacao_da_selecao(
        spans, ranges_from_json(extracao.get("formatacao"))
    )
    return {
        "extracao_id": str(extracao["id"]),
        "codigo": extracao.get("codigo"),
        "atos": atos,
        "texto": "".join(a["texto"] for a in atos),
        "formatacao": ranges_to_json(formatacao),
        "descricao_imovel": _descricao_imovel_bloco(client, org_id, extracao, texto, ruido),
    }


def _exigir_codigo_compativel(
    client: Any, org_id: UUID, contrato: dict, extracao: dict
) -> None:
    """Refuse a selection whose matrícula belongs to a different imóvel.

    `extracao.codigo` NULL means the extraction was never linked to any
    imóvel (the 092 unlinked-upload shape) — it cannot be trusted to be THIS
    deal's property either, so it is refused the same way a mismatch is.
    Without this check, F5's contract generation would read a completely
    unrelated property's matrícula as this deal's title source.
    """
    codigo_extracao = extracao.get("codigo")
    if not codigo_extracao:
        raise ValidationError_(
            "Esta extração não está vinculada a um imóvel — vincule-a a um "
            "imóvel antes de selecioná-la para o contrato.",
            field="extracao_id",
        )
    negociacao = (
        _t(client, NEGOCIACAO_TABLE)
        .select("imovel_codigo")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(contrato["atendimento_id"]))
        .maybe_single()
        .execute()
    ).data or {}
    codigo_negociacao = negociacao.get("imovel_codigo")
    if not codigo_negociacao or codigo_negociacao != codigo_extracao:
        raise ValidationError_(
            "A matrícula selecionada pertence a um imóvel diferente do "
            "negociado neste atendimento.",
            field="extracao_id",
        )


def _exigir_permuta_compativel(
    client: Any, org_id: UUID, permuta_ativo_id: Any, extracao: dict
) -> None:
    """Refuse a permuta quote whose matrícula is not the permuta ativo's
    property — the permuta twin of `_exigir_codigo_compativel` (migration 115).
    """
    codigo_extracao = extracao.get("codigo")
    if not codigo_extracao:
        raise ValidationError_(
            "Esta extração não está vinculada a um imóvel — vincule-a a um imóvel "
            "antes de selecioná-la como matrícula da permuta.",
            field="permutas",
        )
    rows = (
        _t(client, PERMUTA_ATIVOS_TABLE)
        .select("id,imovel_codigo")
        .eq("org_id", str(org_id))
        .eq("id", str(permuta_ativo_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(PERMUTA_ATIVOS_TABLE, str(permuta_ativo_id))
    codigo_ativo = (rows[0].get("imovel_codigo") or "").strip().upper()
    if not codigo_ativo or codigo_ativo != codigo_extracao:
        raise ValidationError_(
            "A matrícula selecionada para a permuta pertence a um imóvel diferente "
            "do ativo de permuta.",
            field="permutas",
        )


def _linhas_do_grupo(
    client: Any,
    org_id: UUID,
    contrato_id: UUID,
    extracao: dict,
    ids: list[str],
    *,
    papel: str,
    permuta_ativo_id: Optional[str],
    usuario_id: Optional[Any],
    campo: str,
    agora: str,
) -> list[dict]:
    por_id = {str(r["id"]): r for r in _linhas_de_atos(client, org_id, extracao)}
    faltando = [i for i in ids if i not in por_id]
    if faltando:
        raise ValidationError_(
            f"Atos não pertencem a esta matrícula: {', '.join(faltando)}",
            field=campo,
        )
    return [
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "contrato_id": str(contrato_id),
            "extracao_id": str(extracao["id"]),
            "ato_id": ato_id,
            "ordem": ordem,
            "papel": papel,
            "permuta_ativo_id": permuta_ativo_id,
            "selecionado_por": str(usuario_id) if usuario_id else None,
            "created_at": agora,
        }
        for ordem, ato_id in enumerate(ids, start=1)
    ]


def definir_selecao(
    client: Any,
    org_id: UUID,
    contrato_id: UUID,
    *,
    extracao_id: Optional[UUID],
    ato_ids: list[UUID],
    usuario_id: Optional[Any],
    permutas: Optional[list[dict]] = None,
) -> dict:
    """Replace the contract's quoted acts. `ato_ids` order = contract order.

    `permutas` (migration 115): `[{permuta_ativo_id, extracao_id, ato_ids}]` —
    the acts quoted from each exchanged property's matrícula. Replaced
    together with the object's quote.
    """
    contrato = _exigir_contrato(client, org_id, contrato_id)
    permutas = permutas or []
    ids = [str(i) for i in ato_ids]
    todos = ids + [str(a) for p in permutas for a in p["ato_ids"]]
    if len(set(todos)) != len(todos):
        raise ValidationError_("Ato repetido na seleção.", field="ato_ids")
    ativos = [str(p["permuta_ativo_id"]) for p in permutas]
    if len(set(ativos)) != len(ativos):
        raise ValidationError_("Permuta repetida na seleção.", field="permutas")

    agora = now_iso()
    linhas: list[dict] = []
    if ids:
        if extracao_id is None:
            raise ValidationError_(
                "extracao_id é obrigatório ao selecionar atos.", field="extracao_id"
            )
        extracao = exigir_extracao(client, org_id, extracao_id)
        _exigir_concluida(extracao)
        _exigir_codigo_compativel(client, org_id, contrato, extracao)
        linhas.extend(
            _linhas_do_grupo(
                client, org_id, contrato_id, extracao, ids,
                papel=PAPEL_OBJETO, permuta_ativo_id=None, usuario_id=usuario_id,
                campo="ato_ids", agora=agora,
            )
        )
    for permuta in permutas:
        extracao = exigir_extracao(client, org_id, permuta["extracao_id"])
        _exigir_concluida(extracao)
        _exigir_permuta_compativel(client, org_id, permuta["permuta_ativo_id"], extracao)
        linhas.extend(
            _linhas_do_grupo(
                client, org_id, contrato_id, extracao, [str(a) for a in permuta["ato_ids"]],
                papel=PAPEL_PERMUTA, permuta_ativo_id=str(permuta["permuta_ativo_id"]),
                usuario_id=usuario_id, campo="permutas", agora=agora,
            )
        )

    # Delete-then-insert: the UNIQUE (contrato_id, ordem) index makes an
    # in-place reorder impossible row by row. A failure between the two calls
    # surfaces as an error on this request, and the operator re-submits the
    # same body — it is a replace, so a retry is exact.
    _t(client, SELECAO_TABLE).delete().eq("org_id", str(org_id)).eq(
        "contrato_id", str(contrato_id)
    ).execute()
    if linhas:
        _t(client, SELECAO_TABLE).insert(linhas).execute()
    return obter_selecao(client, org_id, contrato_id, usuario_id=usuario_id)


# ─── delete guard ─────────────────────────────────────────────────────────


def garantir_removivel(client: Any, org_id: UUID, extracao_id: str) -> None:
    """409 when a contract or an imóvel's título/ônus quotes this extraction.

    The RESTRICT foreign keys in migration 109 are the backstop; this is what
    turns that backstop into a sentence the operator can act on.
    """
    citada = (
        _t(client, SELECAO_TABLE)
        .select("contrato_id")
        .eq("org_id", str(org_id))
        .eq("extracao_id", str(extracao_id))
        .limit(1)
        .execute()
    ).data or []
    if citada:
        raise ConflictError(
            "Esta matrícula é citada por um contrato — remova-a da seleção do "
            "contrato antes de excluir.",
            resource=EXTRACOES_TABLE,
        )
    if dados_service.extracao_referenciada(client, org_id, extracao_id):
        raise ConflictError(
            "Esta matrícula é a fonte do título aquisitivo ou dos ônus de um "
            "imóvel — altere essas fontes antes de excluir.",
            resource=EXTRACOES_TABLE,
        )


__all__ = [
    "ACAO_IMOVEL_VINCULADO",
    "ACAO_TEXT_VIEW",
    "ATOS_TABLE",
    "CONTRATOS_TABLE",
    "EXTRACOES_TABLE",
    "NEGOCIACAO_TABLE",
    "PAPEL_OBJETO",
    "PAPEL_PERMUTA",
    "PERMUTA_ATIVOS_TABLE",
    "SELECAO_TABLE",
    "atos_da_extracao",
    "blocos_abertura_da_extracao",
    "caminho_da_fonte",
    "criar_extracao_de_documento",
    "criar_retranscricao",
    "definir_fontes",
    "definir_selecao",
    "exigir_extracao",
    "garantir_removivel",
    "linhas_de_atos",
    "listar_atos",
    "log_leitura_texto",
    "obter_fontes",
    "obter_selecao",
    "obter_url_arquivo_original",
    "persistir_atos",
    "purgar_texto_expirado",
    "sugerir",
    "vincular_imovel",
]
