"""Repair the existing matrícula corpus WITHOUT re-transcribing it (migration
154). Idempotent: a second run changes nothing.

THE DEFECTS
-----------
- (prod, 2026-09-22) 5 of 8 `matricula_extracoes` carry literal `**` / `<u>`
  in `texto_extraido` (`possui_marcacao_bruta = true`) — pre-113 vision
  output. The contract generator BLOCKS on them, and they hide every
  line-start label (`**IMÓVEL:**`) from the abertura segmenter.
- (prod, 2026-09-22) 5 lack `matricula_abertura_blocos` — the same
  markers, or a row whose acts predate migration 136.
- (prod, 2026-09-23) `texto_extraido` opens with a registry provenance
  stamp (`Valide aqui\\neste documento`, an ONR "ri digital" footer, ...)
  ahead of the matrícula's real content — see `matricula_marcacao.
  remover_boilerplate` and `media.pdf_text._PROVENANCE_STAMP_PATTERNS`.
  Fresh transcriptions strip these at extraction time (`transcription.py`,
  both rungs); this repairs rows transcribed before that shipped.

WHAT `normalizar_extracao` DOES
-------------------------------
1. Strip the markers with the seed's `remover_marcacao` — the SAME
   `parse_markup` a fresh transcription runs, so the result (clean text +
   bold/underline ranges) is what a re-transcription would have produced
   from this text, at zero LLM cost. The markers ARE the formatting;
   nothing is lost. Then strip registry provenance stamps with
   `remover_boilerplate`, on whatever step 1 left behind — same offset
   shape, applied second and independently.
2. Move every offset that points into the text through EACH pass's own
   map (`MarcacaoRemovida.mapear`, composed by running `_aplicar_remocao`
   once per pass): acts, abertura blocks, page-noise spans, qualification
   name spans, the imóvel's título/ônus pointers. Each pass's text, `ruido`
   and `formatacao` land in ONE update — the only shape migration 154's
   trigger exception accepts.
3. Re-derive what was READ from the pre-clean text, after EACH pass: act-
   detail and qualification SUGGESTIONS (confirmed ones are a human's, and
   are kept); and, when the clean text segments into DIFFERENT acts than
   before (a `**R-3/...**` header the segmenter could not see, or a
   provenance stamp that happened to straddle an act boundary) and nothing
   quotes this extraction yet, the acts themselves.
4. Heal the abertura blocks (`estrutura_service.blocos_abertura_da_extracao`).
5. Feed `imovel_dados` (`preenchimento_service`, D1).

🔴 WHAT IT REFUSES TO DO
------------------------
Re-segment the acts of an extraction something QUOTES (a contract
selection, an imóvel's título/ônus pointer, a confirmed act detail or
qualification) — new act ids would orphan those. Such a row keeps its
remapped acts and is reported `atos_divergentes` for a human to look at.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import has_raw_markup, segment_matricula_atos
from noctusai_lib.integrations.documents.formatting import (
    FormatRange,
    ranges_from_json,
    ranges_to_json,
)
from noctusai_lib.integrations.documents.matricula_marcacao import (
    MarcacaoRemovida,
    remover_boilerplate,
    remover_marcacao,
)

from app.modules.imovel_hub import dados_service
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.modules.matriculas import preenchimento_service
from app.modules.matriculas import qualificacao_service as qualificacao_svc
from app.services import table_reads

logger = logging.getLogger(__name__)


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _linhas(client: Any, org_id: Any, tabela: str, extracao_id: str) -> list[dict]:
    return table_reads.paged_rows(client, tabela, org_id, eq_filters={"extracao_id": extracao_id})


def _remapear_formatacao(
    r: MarcacaoRemovida, existente: tuple[FormatRange, ...]
) -> tuple[FormatRange, ...]:
    """The stored ranges (usually `[]` on a legacy row) moved onto the clean
    text, plus the ranges the markers themselves encoded."""
    movidos = [
        FormatRange(
            start=r.mapear(f.start), end=r.mapear(f.end), bold=f.bold, underline=f.underline
        )
        for f in existente
        if r.mapear(f.end) > r.mapear(f.start)
    ]
    return tuple(sorted([*movidos, *r.formatacao], key=lambda f: (f.start, f.end)))


def _referenciada(client: Any, org_id: Any, extracao_id: str) -> bool:
    if dados_service.extracao_referenciada(client, org_id, extracao_id):
        return True
    selecao = (
        _t(client, estrutura_svc.SELECAO_TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("extracao_id", extracao_id)
        .limit(1)
        .execute()
    ).data or []
    if selecao:
        return True
    if any(
        d.get("origem") == detalhes_svc.ORIGEM_CONFIRMADO
        for d in _linhas(client, org_id, detalhes_svc.DETALHES_TABLE, extracao_id)
    ):
        return True
    return any(
        q.get("confirmado_em") or q.get("descartado_em")
        for q in _linhas(client, org_id, qualificacao_svc.TABLE, extracao_id)
    )


def _mesmos_atos(atos: list[dict], texto: str) -> bool:
    frescos = segment_matricula_atos(texto)
    atuais = sorted(atos, key=lambda a: a["ordem"])
    return [(a.kind, a.numero, a.start, a.end) for a in frescos] == [
        (a["kind"], a.get("numero"), int(a["char_inicio"]), int(a["char_fim"]))
        for a in atuais
    ]


def _remover_derivados(client: Any, org_id: Any, extracao_id: str, *, atos_tambem: bool) -> None:
    """Delete what was READ from the markered text so it re-derives from the
    clean one. Suggestions only, unless `atos_tambem` (the caller has proven
    nothing quotes this extraction)."""
    org = str(org_id)
    if atos_tambem:
        # Detalhes cascade from their act (115's FK); blocks and
        # qualificações hang off the extraction and go explicitly.
        _t(client, detalhes_svc.DETALHES_TABLE).delete().eq("org_id", org).eq(
            "extracao_id", extracao_id
        ).execute()
        _t(client, qualificacao_svc.TABLE).delete().eq("org_id", org).eq(
            "extracao_id", extracao_id
        ).execute()
        _t(client, estrutura_svc.ABERTURA_BLOCOS_TABLE).delete().eq("org_id", org).eq(
            "extracao_id", extracao_id
        ).execute()
        _t(client, estrutura_svc.ATOS_TABLE).delete().eq("org_id", org).eq(
            "extracao_id", extracao_id
        ).execute()
        return
    _t(client, detalhes_svc.DETALHES_TABLE).delete().eq("org_id", org).eq(
        "extracao_id", extracao_id
    ).eq("origem", detalhes_svc.ORIGEM_SUGESTAO).execute()
    qualificacoes = _linhas(client, org_id, qualificacao_svc.TABLE, extracao_id)
    if not any(q.get("confirmado_em") or q.get("descartado_em") for q in qualificacoes):
        # Healed on read only when NONE exist (`qualificacoes_da_extracao`),
        # so it is all-or-nothing: re-derive only when no human touched one.
        _t(client, qualificacao_svc.TABLE).delete().eq("org_id", org).eq(
            "extracao_id", extracao_id
        ).execute()


def _remapear_offsets(client: Any, org_id: Any, extracao: dict, r: MarcacaoRemovida) -> None:
    org = str(org_id)
    eid = str(extracao["id"])
    m = r.mapear
    for ato in _linhas(client, org_id, estrutura_svc.ATOS_TABLE, eid):
        patch = {"char_inicio": m(int(ato["char_inicio"])), "char_fim": m(int(ato["char_fim"]))}
        for col in ("header_inicio", "header_fim"):
            if ato.get(col) is not None:
                patch[col] = m(int(ato[col]))
        _t(client, estrutura_svc.ATOS_TABLE).update(patch).eq("org_id", org).eq(
            "id", str(ato["id"])
        ).execute()
    for bloco in _linhas(client, org_id, estrutura_svc.ABERTURA_BLOCOS_TABLE, eid):
        _t(client, estrutura_svc.ABERTURA_BLOCOS_TABLE).update(
            {
                col: m(int(bloco[col]))
                for col in ("char_inicio", "char_fim", "rotulo_inicio", "rotulo_fim")
            }
        ).eq("org_id", org).eq("id", str(bloco["id"])).execute()
    for q in _linhas(client, org_id, qualificacao_svc.TABLE, eid):
        if q.get("nome_inicio") is None or q.get("nome_fim") is None:
            continue
        _t(client, qualificacao_svc.TABLE).update(
            {"nome_inicio": m(int(q["nome_inicio"])), "nome_fim": m(int(q["nome_fim"]))}
        ).eq("org_id", org).eq("id", str(q["id"])).execute()

    codigo = extracao.get("codigo")
    linha = dados_service.linha(client, org_id, codigo) if codigo else None
    if linha:
        patch: dict = {}
        if str(linha.get("titulo_aquisitivo_extracao_id") or "") == eid:
            for col in ("titulo_aquisitivo_char_inicio", "titulo_aquisitivo_char_fim"):
                if linha.get(col) is not None:
                    patch[col] = m(int(linha[col]))
        if str(linha.get("onus_fonte_extracao_id") or "") == eid:
            patch["onus_fonte_atos"] = [
                {**a, "char_inicio": m(int(a["char_inicio"])), "char_fim": m(int(a["char_fim"]))}
                for a in linha.get("onus_fonte_atos") or []
            ]
        if patch:
            dados_service.gravar_fontes_matricula(client, org_id, codigo, patch)


def _aplicar_remocao(
    client: Any,
    org_id: Any,
    extracao: dict,
    r: MarcacaoRemovida,
    *,
    relatorio: dict,
    flag_key: str,
    extra_update: Optional[dict] = None,
) -> dict:
    """Apply ONE offset-tracked removal pass (`remover_marcacao` OR
    `remover_boilerplate`) to `extracao`: write text + ruido + formatacao
    in ONE update (migration 154's trigger exception accepts exactly this
    shape), remap every offset-bearing table through `r.mapear`, and
    re-derive acts when the clean text segments differently.

    A no-op `r` (`not r.alterou`) changes nothing and returns `extracao`
    UNCHANGED — the caller can feed that same value straight into the next
    pass, which is what makes two calls to this function compose two
    `MarcacaoRemovida`s correctly: `_remapear_offsets` always reads the
    table's CURRENT row, so calling it once per pass (each against
    whatever the previous pass just wrote) is the same as chaining the two
    `mapear` functions by hand.
    """
    eid = str(extracao["id"])
    if not r.alterou:
        return extracao
    ruido = [
        {**span, "start": r.mapear(int(span["start"])), "end": r.mapear(int(span["end"]))}
        for span in extracao.get("ruido") or []
    ]
    formatacao = _remapear_formatacao(r, ranges_from_json(extracao.get("formatacao")))
    _t(client, estrutura_svc.EXTRACOES_TABLE).update(
        {
            "texto_extraido": r.texto,
            "ruido": ruido,
            "formatacao": ranges_to_json(formatacao),
            **(extra_update or {}),
        }
    ).eq("org_id", str(org_id)).eq("id", eid).execute()
    _remapear_offsets(client, org_id, extracao, r)
    relatorio[flag_key] = True
    extracao = estrutura_svc.exigir_extracao(client, org_id, UUID(eid))

    atos = _linhas(client, org_id, estrutura_svc.ATOS_TABLE, eid)
    if atos and not _mesmos_atos(atos, r.texto):
        if _referenciada(client, org_id, eid):
            relatorio["atos_divergentes"] = True
            logger.warning(
                "matricula %s: clean text segments into different acts, but the "
                "extraction is quoted — acts kept (remapped); needs a human",
                eid,
            )
            _remover_derivados(client, org_id, eid, atos_tambem=False)
        else:
            _remover_derivados(client, org_id, eid, atos_tambem=True)
            relatorio["atos_ressegmentados"] = estrutura_svc.persistir_atos(
                client, eid, org_id, r.texto
            )
    else:
        _remover_derivados(client, org_id, eid, atos_tambem=False)
    return extracao


def normalizar_extracao(client: Any, org_id: Any, extracao_id: Any) -> dict:
    """Steps 1–4 of the module docstring for ONE extraction. Synchronous;
    `backfill` adds step 5 (the async fill).

    Two independent removal passes, composed sequentially:
    `remover_marcacao` (the `**`/`<u>` markers) first, `remover_boilerplate`
    (registry provenance/validation stamps — 2026-09-23) second, on
    whatever `remover_marcacao` left behind. Each is verified against its
    own reconstruction independently; `_aplicar_remocao` is what makes
    running it twice equivalent to chaining the two offset maps.
    """
    extracao = estrutura_svc.exigir_extracao(client, org_id, UUID(str(extracao_id)))
    eid = str(extracao["id"])
    texto = extracao.get("texto_extraido")
    if extracao.get("status") != estrutura_svc.STATUS_CONCLUIDA or not texto:
        return {"extracao_id": eid, "status": "sem_texto"}

    relatorio: dict = {
        "extracao_id": eid,
        "status": "ok",
        "marcacao_removida": False,
        "boilerplate_removida": False,
    }

    r1 = remover_marcacao(texto)
    extracao = _aplicar_remocao(
        client,
        org_id,
        extracao,
        r1,
        relatorio=relatorio,
        flag_key="marcacao_removida",
        # Written on the SAME update as the marker pass, not the
        # boilerplate one — a stray unbalanced `**` is what this flag
        # means, and boilerplate removal can neither cause nor cure one.
        extra_update={"possui_marcacao_bruta": has_raw_markup(r1.texto)},
    )
    # Re-read above when the text changed, so this is the stored flag. Still
    # true only for an UNBALANCED marker `parse_markup` keeps literal — a
    # human's call, reported rather than guessed at.
    relatorio["possui_marcacao_bruta"] = bool(extracao.get("possui_marcacao_bruta"))

    r2 = remover_boilerplate(extracao.get("texto_extraido") or "")
    extracao = _aplicar_remocao(
        client, org_id, extracao, r2, relatorio=relatorio, flag_key="boilerplate_removida"
    )

    # Step 4 — heals acts, then blocks, then (on read) suggestions.
    atos = estrutura_svc.atos_da_extracao(client, org_id, extracao)
    detalhes_svc.detalhes_por_ato(client, org_id, extracao, atos)
    qualificacao_svc.qualificacoes_da_extracao(client, org_id, extracao, atos)
    relatorio["blocos_abertura"] = len(
        estrutura_svc.blocos_abertura_da_extracao(client, org_id, extracao)
    )
    return relatorio


async def backfill(
    client: Any,
    org_id: Any,
    *,
    extracao_id: Optional[Any] = None,
    notificador: Optional[Any] = None,
) -> dict:
    """Every concluded extraction of the org (or one): normalize, heal, fill.
    Per-extraction isolation — one failure is reported, never fatal."""
    if extracao_id is not None:
        alvos = [str(extracao_id)]
    else:
        alvos = [
            str(r["id"])
            for r in table_reads.paged_rows(
                client,
                estrutura_svc.EXTRACOES_TABLE,
                org_id,
                eq_filters={"status": estrutura_svc.STATUS_CONCLUIDA},
            )
            if not r.get("substituida_por")
        ]
    itens: list[dict] = []
    for eid in alvos:
        try:
            item = normalizar_extracao(client, org_id, eid)
        except Exception as exc:  # noqa: BLE001 - reported per row, never fatal
            logger.error("matricula backfill %s failed: %s", eid, exc, exc_info=True)
            itens.append({"extracao_id": eid, "status": "erro", "erro": str(exc)})
            continue
        item["imovel_dados"] = await preenchimento_service.preencher_imovel(
            client, org_id, eid, notificador=notificador
        )
        itens.append(item)
    return {
        "total": len(itens),
        "marcacao_removida": sum(1 for i in itens if i.get("marcacao_removida")),
        "boilerplate_removida": sum(1 for i in itens if i.get("boilerplate_removida")),
        "atos_divergentes": sum(1 for i in itens if i.get("atos_divergentes")),
        "erros": sum(1 for i in itens if i.get("status") == "erro"),
        "items": itens,
    }


__all__ = ["backfill", "normalizar_extracao"]
