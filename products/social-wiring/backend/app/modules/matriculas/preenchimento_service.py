"""A concluded matrícula transcription → every contract-feeding `imovel_dados`
field it can supply (migration 154, owner decision D1).

WHAT IS READ, AND FROM WHERE
----------------------------
| imovel_dados field               | source in the transcription                              |
|----------------------------------|----------------------------------------------------------|
| numero_matricula                 | seed `find_matricula` (heading label)                    |
| numero_registro_imoveis          | seed `find_cartorio` (heading)                           |
| prefeitura_cadastro_imobiliario  | `CADASTRO MUNICIPAL:` abertura block → `find_inscricao_municipal` |
| titulo_aquisitivo (act pointer)  | `estrutura_service.sugerir` — latest transfer act        |
| titulo_aquisitivo_texto          | seed `frase_titulo_aquisitivo` over that act's instrumento |
| onus_fonte (act pointers)        | `sugerir` — encumbrance acts not cited by a cancelamento |
| onus_credor                      | the `credor` of those acts' typed details               |
| situacao_onus                    | the acts: an unreleased hipoteca / alienação fiduciária / penhora / usufruto / indisponibilidade, else `livre` |

Every value goes through `campos_extraidos_service.aplicar` — fill an empty
field (machine-pending until a human validates it, D2), or open a conflict,
never an overwrite. Nothing here writes `imovel_dados` directly.

WHEN IT RUNS
------------
- right after `service.processar_extracao` / `registrar_transcricao_manual`
  land the text (and its acts), when the extraction is linked to an imóvel;
- when an unlinked extraction gets linked later (`vincular_imovel`);
- after the legacy-markup backfill cleans a text (`backfill_service`).

It is idempotent: a second run over the same extraction finds every field
already equal (`igual`) and writes nothing.

🔴 TEXT WITH RAW MARKUP IS NOT READ. A `possui_marcacao_bruta` text would
leak `**` into a cartório name or a creditor. The backfill cleans it first,
then calls this.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import (
    Instrumento,
    find_matricula,
    frase_titulo_aquisitivo,
)
from noctusai_lib.integrations.documents.matricula_cabecalho import (
    find_cartorio,
    find_inscricao_municipal,
)

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from app.modules.imovel_hub import dados_service
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.services import table_reads

logger = logging.getLogger(__name__)

ORIGEM = "matricula"

#: `matricula_ato_detalhes.natureza` values that encumber the property —
#: each is also a `dados_service.SITUACOES_ONUS` value.
NATUREZAS_ONUS: tuple[str, ...] = (
    "hipoteca",
    "alienacao_fiduciaria",
    "penhora",
    "usufruto",
    "indisponibilidade",
)
NATUREZA_CANCELAMENTO = "cancelamento"
SITUACAO_LIVRE = "livre"
SITUACAO_MULTIPLA = "outro"


def _extracao(client: Any, org_id: Any, extracao_id: Any) -> Optional[dict]:
    rows = (
        table_reads.table(client, estrutura_svc.EXTRACOES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(extracao_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _ref(ato: dict) -> Optional[tuple[str, int]]:
    if ato.get("numero") is None:
        return None
    return (str(ato["kind"]), int(ato["numero"]))


def derivar_situacao_onus(
    atos: list[dict], detalhes: dict[str, dict], sugestoes_onus: list[dict]
) -> str:
    """The property's ônus status from its acts. Pure.

    An encumbrance counts unless a LATER act releases it: a `cancelamento`
    whose typed `atos_referidos` names it, or (the text heuristic
    `sugerir` already computes) a later cancellation act citing its number.
    None active → `livre`; one kind → that kind; several kinds → `outro`
    (the vocabulary has no plural; a human reads `onus_fonte` for detail).
    """
    ordenados = sorted(atos, key=lambda r: r["ordem"])
    liberados: set[tuple[str, int]] = set()
    for ato in ordenados:
        det = detalhes.get(str(ato["id"])) or {}
        if det.get("natureza") != NATUREZA_CANCELAMENTO:
            continue
        for ref in det.get("atos_referidos") or []:
            try:
                liberados.add((str(ref["kind"]), int(ref["numero"])))
            except (KeyError, TypeError, ValueError):
                logger.warning("situacao_onus: malformed atos_referidos entry %r", ref)

    # Either reading of a release counts: the typed one above, or the text
    # heuristic's (`cancelamento_citado_por`) — a typed reading that missed
    # the reference must not resurrect a released hipoteca.
    liberados_por_texto = {
        str(o["ato_id"]) for o in sugestoes_onus if o.get("cancelamento_citado_por")
    }

    def _liberado(ato: dict) -> bool:
        return _ref(ato) in liberados or str(ato["id"]) in liberados_por_texto

    ativos: list[str] = []
    tipados: set[str] = set()
    for ato in ordenados:
        natureza = (detalhes.get(str(ato["id"])) or {}).get("natureza")
        if natureza:
            tipados.add(str(ato["id"]))
        if natureza in NATUREZAS_ONUS and not _liberado(ato):
            ativos.append(natureza)
    # The text heuristic fills in only where there is no typed reading of
    # that act at all — a typed nature (even a non-ônus one) wins.
    por_id = {str(a["id"]): a for a in ordenados}
    for o in sugestoes_onus:
        ato = por_id.get(str(o["ato_id"]))
        if ato is None or str(ato["id"]) in tipados or _liberado(ato):
            continue
        ativos.append(o["tipo"])

    tipos = sorted(set(ativos))
    if not tipos:
        return SITUACAO_LIVRE
    if len(tipos) == 1:
        return tipos[0]
    return SITUACAO_MULTIPLA


def _aplicar(
    resumo: dict,
    conflitos: list[dict],
    client: Any,
    org_id: Any,
    codigo: str,
    chave: str,
    valor: Any,
    *,
    extracao_id: str,
    origem: str = ORIGEM,
    documento_id: Optional[Any] = None,
    confianca: Optional[str] = None,
) -> None:
    """One field, isolated: a failure on one never stops the others."""
    try:
        r = campos_svc.aplicar(
            client,
            org_id,
            codigo,
            chave,
            valor,
            origem=origem,
            documento_id=documento_id,
            confianca=confianca,
            fonte_tabela=campos_svc.FONTE_EXTRACOES,
            fonte_id=extracao_id,
        )
    except Exception as exc:  # noqa: BLE001 - per-field isolation; logged loudly
        logger.error(
            "matricula %s: could not apply %s to imovel %s: %s",
            extracao_id, chave, codigo, exc, exc_info=True,
        )
        resumo[chave] = "erro"
        return
    resumo[chave] = r.status
    if r.conflito is not None:
        conflitos.append(r.conflito)


def preencher_sincrono(
    client: Any, org_id: Any, extracao_id: Any
) -> tuple[dict, list[dict]]:
    """The fill, without the (async) notification. Returns `(resumo,
    conflitos_abertos)`; `resumo["status"]` says why nothing ran when that
    is the case."""
    extracao = _extracao(client, org_id, extracao_id)
    if extracao is None:
        return {"status": "nao_encontrada"}, []
    if extracao.get("status") != estrutura_svc.STATUS_CONCLUIDA or not extracao.get(
        "texto_extraido"
    ):
        return {"status": "sem_texto"}, []
    codigo = extracao.get("codigo")
    if not codigo:
        return {"status": "sem_imovel"}, []
    if extracao.get("substituida_por"):
        return {"status": "substituida"}, []
    if extracao.get("possui_marcacao_bruta"):
        return {"status": "marcacao_bruta"}, []

    eid = str(extracao["id"])
    texto = extracao["texto_extraido"]
    resumo: dict = {"status": "ok"}
    conflitos: list[dict] = []

    def aplicar(chave: str, valor: Any, **kw: Any) -> None:
        _aplicar(resumo, conflitos, client, org_id, codigo, chave, valor, extracao_id=eid, **kw)

    numero, conf_numero, _rotulo = find_matricula(texto)
    if numero and conf_numero != "nenhuma":
        # 075's FK: `numero_matricula_documento_id` points at
        # `imovel_documentos` — the PDF this transcription came from, when
        # it is the imóvel's own document; NULL otherwise.
        aplicar(
            "numero_matricula", numero,
            documento_id=extracao.get("imovel_documento_id"), confianca=conf_numero,
        )

    cartorio, conf_cartorio, _ = find_cartorio(texto)
    if cartorio:
        aplicar("numero_registro_imoveis", cartorio, documento_id=eid, confianca=conf_cartorio)

    for bloco in estrutura_svc.blocos_abertura_da_extracao(client, org_id, extracao):
        if bloco["campo"] != "cadastro_municipal":
            continue
        inscricao, conf_insc = find_inscricao_municipal(
            texto[int(bloco["char_inicio"]) : int(bloco["char_fim"])]
        )
        if inscricao:
            aplicar(
                "prefeitura_cadastro_imobiliario", inscricao,
                documento_id=eid, confianca=conf_insc,
            )
        break

    atos = estrutura_svc.atos_da_extracao(client, org_id, extracao)
    detalhes = detalhes_svc.detalhes_por_ato(client, org_id, extracao, atos)
    sugestoes = estrutura_svc.sugerir(texto, atos)
    por_id = {str(a["id"]): a for a in atos}

    titulo = sugestoes["titulo_aquisitivo"]
    if titulo:
        aplicar(
            "titulo_aquisitivo",
            {
                "titulo_aquisitivo_extracao_id": eid,
                "titulo_aquisitivo_ato_id": titulo["ato_id"],
                "titulo_aquisitivo_char_inicio": titulo["char_inicio"],
                "titulo_aquisitivo_char_fim": titulo["char_fim"],
            },
            origem=campos_svc.ORIGEM_SUGERIDO,
        )
    onus_sugeridos = [o for o in sugestoes["onus"] if o["sugerido"]]
    if onus_sugeridos:
        aplicar(
            "onus_fonte",
            {
                "onus_fonte_extracao_id": eid,
                "onus_fonte_atos": [
                    {
                        "ato_id": o["ato_id"],
                        "char_inicio": o["char_inicio"],
                        "char_fim": o["char_fim"],
                    }
                    for o in onus_sugeridos
                ],
            },
            origem=campos_svc.ORIGEM_SUGERIDO,
        )

    # The phrase and the creditor are derived from the EFFECTIVE pointers
    # (a human's choice wins over the heuristic's) — but only when those
    # pointers quote THIS extraction; another extraction's acts are that
    # extraction's to read.
    linha = dados_service.linha(client, org_id, codigo) or {}
    if str(linha.get("titulo_aquisitivo_extracao_id") or "") == eid:
        ato = por_id.get(str(linha.get("titulo_aquisitivo_ato_id")))
        det = detalhes.get(str(ato["id"])) if ato else None
        if ato and det and ato.get("numero") is not None:
            frase = frase_titulo_aquisitivo(
                Instrumento.from_json(det.get("instrumento")),
                kind=ato["kind"],
                numero=int(ato["numero"]),
            )
            if frase:
                aplicar("titulo_aquisitivo_texto", frase)
    if str(linha.get("onus_fonte_extracao_id") or "") == eid:
        credores: list[str] = []
        for ref in linha.get("onus_fonte_atos") or []:
            credor = (detalhes.get(str(ref.get("ato_id"))) or {}).get("credor")
            if credor and credor not in credores:
                credores.append(credor)
        if credores:
            aplicar("onus_credor", "; ".join(credores))

    aplicar(
        "situacao_onus",
        derivar_situacao_onus(atos, detalhes, sugestoes["onus"]),
        documento_id=eid,
    )
    return resumo, conflitos


async def preencher_imovel(
    client: Any, org_id: Any, extracao_id: Any, *, notificador: Optional[Any] = None
) -> dict:
    """`preencher_sincrono` + announce each conflict it opened. NEVER raises
    — it runs after a paid transcription already landed, and nothing here
    may turn that into a failure."""
    try:
        resumo, conflitos = preencher_sincrono(client, org_id, extracao_id)
    except Exception as exc:  # noqa: BLE001 - the transcription already landed
        logger.error(
            "matricula %s: imovel_dados fill failed: %s", extracao_id, exc, exc_info=True
        )
        return {"status": "erro", "erro": str(exc)}
    if conflitos:
        extracao = _extracao(client, org_id, extracao_id) or {}
        await campos_svc.notificar(
            client, UUID(str(org_id)), extracao.get("codigo") or "", conflitos, notificador
        )
    resumo["conflitos_abertos"] = [c["campo"] for c in conflitos]
    return resumo


__all__ = [
    "NATUREZAS_ONUS",
    "derivar_situacao_onus",
    "preencher_imovel",
    "preencher_sincrono",
]
