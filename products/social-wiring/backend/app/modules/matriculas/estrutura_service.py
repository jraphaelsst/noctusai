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
- every text this module returns is `texto_extraido[inicio:fim]`, and nothing
  else. There is no strip, no join separator, no normalisation on the way out.
  `normalize` is used ONLY to MATCH suggestion terms, never to produce output.

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
    MatriculaAto,
    ato_hint_span,
    normalize,
    segment_matricula_atos,
)
from noctusai_lib.primitives.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub import documentos_service as docs_svc
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

EXTRACOES_TABLE = "matricula_extracoes"
ATOS_TABLE = "matricula_atos"
SELECAO_TABLE = "atendimento_contrato_matricula_atos"
CONTRATOS_TABLE = "atendimento_contratos"

STATUS_CONCLUIDA = "concluida"

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
    return len(linhas)


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


def listar_atos(client: Any, org_id: UUID, extracao_id: UUID) -> dict:
    extracao = exigir_extracao(client, org_id, extracao_id)
    texto = extracao.get("texto_extraido") or ""
    atos = [_ato_saida(r, texto) for r in _linhas_de_atos(client, org_id, extracao)]
    return {
        "extracao_id": extracao["id"],
        "status": extracao.get("status"),
        "codigo": extracao.get("codigo"),
        "total": len(atos),
        "atos": atos,
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


def obter_selecao(client: Any, org_id: UUID, contrato_id: UUID) -> dict:
    """The contract's quoted acts, in contract order, as literal slices.

    `texto` is the plain concatenation of the slices — no separator is added,
    because the segmenter's spans already carry their own line breaks.
    Selecting every act in matrícula order therefore yields `texto_extraido`
    byte for byte.
    """
    _exigir_contrato(client, org_id, contrato_id)
    selecao = sorted(
        table_reads.paged_rows(
            client, SELECAO_TABLE, org_id, eq_filters={"contrato_id": str(contrato_id)}
        ),
        key=lambda r: r["ordem"],
    )
    if not selecao:
        return {
            "contrato_id": str(contrato_id),
            "extracao_id": None,
            "codigo": None,
            "atos": [],
            "texto": "",
            "selecionado_por": None,
            "selecionado_em": None,
        }

    extracao = exigir_extracao(client, org_id, selecao[0]["extracao_id"])
    texto = extracao.get("texto_extraido") or ""
    por_id = {str(r["id"]): r for r in _linhas_de_atos(client, org_id, extracao)}

    atos = []
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
        atos.append(
            {
                "ato_id": str(row["id"]),
                "ordem": sel["ordem"],
                "kind": row["kind"],
                "numero": row.get("numero"),
                "char_inicio": inicio,
                "char_fim": fim,
                "texto": _fatia(texto, inicio, fim),
            }
        )

    resolved = table_reads.resolve_actors(
        {selecao[0].get("selecionado_por")} - {None}
    )
    return {
        "contrato_id": str(contrato_id),
        "extracao_id": str(extracao["id"]),
        "codigo": extracao.get("codigo"),
        "atos": atos,
        "texto": "".join(a["texto"] for a in atos),
        "selecionado_por": table_reads.actor(resolved, selecao[0].get("selecionado_por")),
        "selecionado_em": selecao[0].get("created_at"),
    }


def definir_selecao(
    client: Any,
    org_id: UUID,
    contrato_id: UUID,
    *,
    extracao_id: Optional[UUID],
    ato_ids: list[UUID],
    usuario_id: Optional[Any],
) -> dict:
    """Replace the contract's quoted acts. `ato_ids` order = contract order."""
    _exigir_contrato(client, org_id, contrato_id)
    ids = [str(i) for i in ato_ids]
    if len(set(ids)) != len(ids):
        raise ValidationError_("Ato repetido na seleção.", field="ato_ids")

    linhas: list[dict] = []
    if ids:
        if extracao_id is None:
            raise ValidationError_(
                "extracao_id é obrigatório ao selecionar atos.", field="extracao_id"
            )
        extracao = exigir_extracao(client, org_id, extracao_id)
        _exigir_concluida(extracao)
        por_id = {str(r["id"]): r for r in _linhas_de_atos(client, org_id, extracao)}
        faltando = [i for i in ids if i not in por_id]
        if faltando:
            raise ValidationError_(
                f"Atos não pertencem a esta matrícula: {', '.join(faltando)}",
                field="ato_ids",
            )
        agora = now_iso()
        linhas = [
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "contrato_id": str(contrato_id),
                "extracao_id": str(extracao["id"]),
                "ato_id": ato_id,
                "ordem": ordem,
                "selecionado_por": str(usuario_id) if usuario_id else None,
                "created_at": agora,
            }
            for ordem, ato_id in enumerate(ids, start=1)
        ]

    # Delete-then-insert: the UNIQUE (contrato_id, ordem) index makes an
    # in-place reorder impossible row by row. A failure between the two calls
    # surfaces as an error on this request, and the operator re-submits the
    # same body — it is a replace, so a retry is exact.
    _t(client, SELECAO_TABLE).delete().eq("org_id", str(org_id)).eq(
        "contrato_id", str(contrato_id)
    ).execute()
    if linhas:
        _t(client, SELECAO_TABLE).insert(linhas).execute()
    return obter_selecao(client, org_id, contrato_id)


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
    "ATOS_TABLE",
    "CONTRATOS_TABLE",
    "EXTRACOES_TABLE",
    "SELECAO_TABLE",
    "criar_extracao_de_documento",
    "definir_fontes",
    "definir_selecao",
    "exigir_extracao",
    "garantir_removivel",
    "linhas_de_atos",
    "listar_atos",
    "obter_fontes",
    "obter_selecao",
    "persistir_atos",
    "sugerir",
]
