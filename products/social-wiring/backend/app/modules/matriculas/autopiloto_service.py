"""The matrícula autopilot (owner directive, 2026-09-30, live-test evidence:
5 historical deals re-run on prod) — turns every contract-feeding matrícula
value `preenchimento_service` (D1) already derived into a value the contract
generator can actually USE, without a human click, whenever nothing about
the derivation is in doubt.

WHY THIS EXISTS
----------------
"Human reviews are meant to be the exception, not the rule." Before this
module, `preenchimento_service` filled `imovel_dados` from the matrícula's
acts but left every field MACHINE-PENDING (D1, migration 154): `_origem` set,
`_confirmado_em` NULL. D2 (migration 156, `contrato_gerador.
validacao_extracao`) then refuses to generate while ANY such field is
pending — so even a matrícula the transcriber, the act segmenter and the act-
detail extractor all read cleanly still needed an operator to click "accept"
on the cartório, the título aquisitivo (twice: the act AND its wording), the
ônus acts, the ônus credor and the situação de ônus — one contract at a time.
Live evidence (2026-09-30) showed exactly these fields reported `faltando`
on every one of 5 historical deals.

THIS MODULE DOES NOT RELAX D2. It runs the SAME question D2 already asks
("did a human vouch for this?") one step earlier, and answers it itself
— ONLY — when the derivation cannot reasonably be read two ways. Anything
short of that is left EXACTLY as `preenchimento_service` left it: a
machine-pending suggestion, still gated by D2, still requiring a human. This
is the "exception, not the rule" — the system resolves what it safely can
and asks a human only for the rest.

UNAMBIGUOUS, PRECISELY (owner's own three criteria, reusing existing,
already-tested primitives rather than a new heuristic)
-----------------------------------------------------------------------
- **Cartório ("header matched")** — `noctusai_lib...matricula_cabecalho.
  find_cartorio` returns a value ONLY at its own `"alta"` confidence (exactly
  one registry named in the heading); there is no `"baixa"` tier for it at
  all (see that function's docstring). So whenever `preenchimento_service`
  wrote `numero_registro_imoveis`, the header was already unambiguous BY
  CONSTRUCTION — nothing further to check.
- **Título aquisitivo ("single candidate act")** — `estrutura_service.
  sugerir` already narrows to exactly one non-cancelled transfer act (the
  LATEST one) or none; there is no second candidate to arbitrate between.
  What is still open is whether the act's INSTRUMENT resolved to a wording
  a contract could print — `preenchimento_service` only ever fills
  `titulo_aquisitivo_texto` when `frase_titulo_aquisitivo` returned a
  phrase, so that stored value being present (and pointing at THIS
  extraction) is proof the derivation is complete, not just that a
  candidate exists. An act with a term but no readable instrument
  (`titulo_service.MOTIVO_SEM_INSTRUMENTO`) is exactly the case this
  refuses to auto-confirm — a human fills the instrument in
  `MatriculaAtoDetalhesEditor` first.
- **Ônus ("no cancellations ambiguity")** — `preenchimento_service.
  derivar_situacao_onus` already refuses to answer (`None`) the moment any
  act could not be classified as encumbering-or-released (its own
  `[situacao-onus-unclassified-act]` guard). A non-`None` result IS the
  unambiguous case, by the SAME rule that already protects `situacao_onus`
  from a false "livre" — reused here verbatim, not re-derived.

Nothing above is a new inference: every signal is a pre-existing, already
tested "we can vouch for this" boundary. The autopilot's only new behaviour
is writing the CONFIRMATION once that boundary is already satisfied.

PROVENANCE
----------
- The four scalar fields (`numero_registro_imoveis`, `situacao_onus`,
  `titulo_aquisitivo_texto`, `onus_credor`) — free-text `_origem` columns,
  migration 154 — are re-stamped `ORIGEM_AUTOPILOTO` ("ia") at the moment
  the autopilot confirms them, replacing `preenchimento_service`'s
  `"matricula"` (which only says WHICH DOCUMENT the reading came from): "ia"
  says WHO now stands behind it. `_confirmado_por` stays `NULL` — nobody
  clicked — `_confirmado_em` is stamped. This is the audit signature a
  later query reads: `origem = 'ia' AND confirmado_por IS NULL AND
  confirmado_em IS NOT NULL` is "the autopilot decided this one"; a human's
  own accept always carries their id.
- The two pointer GROUPS (`titulo_aquisitivo`, `onus_fonte`) cannot take
  "ia": migration 109's CHECK constraints
  (`imovel_dados_titulo_aquisitivo_origem_check` /
  `..._onus_fonte_origem_check`) only allow `'sugerido' | 'manual'` — and
  `'sugerido'` already accurately says "the heuristic's own pick", so it is
  kept. The SAME audit signature applies with `origem = 'sugerido'` instead:
  `confirmado_por IS NULL AND confirmado_em IS NOT NULL`.
- No new "confidence" column is added. The unambiguity gate above is
  already binary (confirmed vs. left pending) and reuses signals the seed
  already computes; a decision's reasoning is logged (`logger.info`, one
  line per field) and returned in `aplicar_autopiloto`'s own result dict —
  both are inspectable without a schema change. A future numeric/tiered
  confidence (mirroring `app.services.divergencia_resolucao.PRECISAO`) is a
  reasonable next step once real measurement exists; this session does not
  invent one from nothing.

NEVER OVERRIDES A HUMAN
------------------------
Every write below is gated by `campos_extraidos_service.pendente()` (the
scalar fields) or by re-reading `imovel_dados` immediately before deciding
(the pointer groups) — the SAME "machine-pending, not `manual`, not yet
confirmed" test D1/D2 already use. A field a human already confirmed
(themselves, or a PRIOR autopilot run) or typed by hand (`origem='manual'`)
is read, reported, and never touched again.

CONTRACT ACTS (`matricula.atos`)
---------------------------------
`estrutura_service.sugerir`/`definir_fontes` decide WHICH acts feed the
título/ônus of the IMÓVEL; a SEPARATE step (migration 115,
`atendimento_contrato_matricula_atos`) decides which acts a given CONTRACT
quotes verbatim. Once the imóvel's título/ônus are resolved (auto or by a
human), `aplicar_autopiloto` defaults every contract of the imóvel's
atendimento(s) that has NO selection yet to the abertura + the título act +
the active ônus acts, in matrícula order — the acts the promessa's OBJETO/
ônus clauses actually quote. A contract that already has a selection
(anyone's — a human's, or an earlier autopilot run) is never touched.

D2 POLICY SWITCH (one final review per contract)
-------------------------------------------------
See `REVISAO_FINAL_UNICA_POR_CONTRATO` below.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from app.modules.imovel_hub import dados_service
from app.modules.matriculas import ato_detalhes_service as detalhes_svc
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.modules.matriculas import preenchimento_service
from app.services import table_reads
from app.services.documento_store import now_iso

logger = logging.getLogger(__name__)

#: [Provenance] Stamped on the four scalar fields the autopilot itself
#: confirms — see the module docstring's PROVENANCE section. Distinct from
#: `preenchimento_service.ORIGEM` ("matricula", meaning "read off a
#: matrícula") and from `campos_extraidos_service.ORIGEM_MANUAL`
#: ("manual", a human's own write): "ia" means "the autopilot vouched for
#: this reading without a human click".
ORIGEM_AUTOPILOTO = "ia"

#: [D2 policy switch — DECIDED, owner 2026-09-30: "one final review of the
#: finished contract by the legal team" replaces the per-field clicks.] An
#: ALIAS of `contrato_gerador.politica.Politica.revisao_final_unica`'s
#: production value, never a second copy: whatever this autopilot could not
#: confirm for itself is no longer a per-field click before generation; it
#: is listed on the generated version and confirmed by the ONE contract-level
#: "Aprovar revisão jurídica" (`contrato_gerador.revisao_juridica`).
REVISAO_FINAL_UNICA_POR_CONTRATO = POLITICA_PADRAO.revisao_final_unica

#: `aplicar_autopiloto`'s per-field outcomes.
CONFIRMADO_AUTOMATICO = "confirmado_automatico"
SUGESTAO_PENDENTE = "sugestao_pendente"
JA_CONFIRMADO_HUMANO = "ja_confirmado_humano"
SEM_VALOR = "sem_valor"
INAPLICAVEL = "inaplicavel"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _extracao(client: Any, org_id: Any, extracao_id: Any) -> Optional[dict]:
    rows = (
        _t(client, estrutura_svc.EXTRACOES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(extracao_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


# ─── the scalar fields (numero_registro_imoveis, situacao_onus,
#     titulo_aquisitivo_texto, onus_credor) ────────────────────────────────


def _confirmar_quinteto(
    client: Any, org_id: UUID, codigo: str, chave: str, *, inequivoco: bool, motivo: str
) -> str:
    """Confirm one scalar field IN PLACE (value untouched) when `inequivoco`
    — re-reading `imovel_dados` fresh so a human who just acted (elsewhere,
    a moment ago) is never raced. Returns the outcome, one of this module's
    `CONFIRMADO_AUTOMATICO` / `SUGESTAO_PENDENTE` / `JA_CONFIRMADO_HUMANO` /
    `SEM_VALOR`.
    """
    campo = campos_svc.CAMPOS[chave]
    linha = dados_service.linha(client, org_id, codigo) or {}
    if not linha.get(chave):
        return SEM_VALOR
    if not campos_svc.pendente(linha, campo):
        # Not pending — either a human's own value (`origem='manual'`) or
        # already confirmed (by a human or a previous autopilot pass).
        # Either way: never touched again.
        return JA_CONFIRMADO_HUMANO
    if not inequivoco:
        logger.info(
            "matricula autopiloto: imovel %s campo %s segue como sugestao — %s",
            codigo, chave, motivo,
        )
        return SUGESTAO_PENDENTE
    patch = {
        campo.origem: ORIGEM_AUTOPILOTO,
        campo.confirmado_por: None,
        campo.confirmado_em: now_iso(),
    }
    dados_service.gravar_extraido(client, org_id, codigo, linha, patch)
    logger.info(
        "matricula autopiloto: imovel %s campo %s confirmado automaticamente — %s",
        codigo, chave, motivo,
    )
    return CONFIRMADO_AUTOMATICO


# ─── título aquisitivo / ônus fonte pointer groups ─────────────────────────


def _titulo_inequivoco(sugestao: Optional[dict], linha: dict, eid: str) -> tuple[bool, str]:
    """[owner: "single candidate act"] `estrutura_service.sugerir` already
    narrows to exactly one non-cancelled transfer act (the latest) or none
    at all — see the module docstring. What remains to check is that the
    CURRENT pointer (`preenchimento_service` just wrote it, moments ago) is
    still exactly this same candidate, of THIS extraction, and that its
    wording actually resolved (`titulo_aquisitivo_texto` present) — the
    proof that the instrument was complete enough to quote."""
    if not sugestao:
        return False, "nenhum ato de transferencia encontrado"
    if str(linha.get("titulo_aquisitivo_extracao_id") or "") != eid:
        return False, "titulo aponta para outra extracao"
    if str(linha.get("titulo_aquisitivo_ato_id") or "") != str(sugestao["ato_id"]):
        return False, "ponteiro de titulo diverge da sugestao atual (edicao manual)"
    if not (linha.get("titulo_aquisitivo_texto") or "").strip():
        return False, "instrumento do ato nao resolveu uma redacao (sem_instrumento)"
    return True, "ato unico, sem cancelamento, instrumento resolvido"


def _onus_inequivoco(situacao: Optional[str]) -> tuple[bool, str]:
    """[owner: "no cancellations ambiguity"] `preenchimento_service.
    derivar_situacao_onus` already returns `None` the moment any act could
    not be classified as encumbering-or-released — a non-`None` result IS
    the unambiguous case, reused verbatim."""
    if situacao is None:
        return False, "ao menos um ato nao foi classificado (onus indeterminado)"
    return True, f"situacao de onus resolvida ({situacao})"


def _confirmar_pointer(
    client: Any,
    org_id: UUID,
    codigo: str,
    extracao_id: str,
    chave: str,
    *,
    inequivoco: bool,
    motivo: str,
) -> str:
    """Confirm the título/ônus pointer GROUP in place — never re-derives it
    (that is `preenchimento_service`'s job, already run before this); only
    stamps the confirmation via `estrutura_service.definir_fontes`, the
    SAME writer a human's own PUT uses, so the write shape (validation,
    origem bookkeeping) is exactly the one already tested there.
    """
    campo = campos_svc.CAMPOS[chave]
    linha = dados_service.linha(client, org_id, codigo) or {}
    valor = linha.get(campo.identidade) if campo.identidade else None
    if not valor:
        return SEM_VALOR
    if str(linha.get(f"{chave}_extracao_id") or "") != str(extracao_id):
        return INAPLICAVEL
    if not campos_svc.pendente(linha, campo):
        return JA_CONFIRMADO_HUMANO
    if not inequivoco:
        logger.info(
            "matricula autopiloto: imovel %s ponteiro %s segue como sugestao — %s",
            codigo, chave, motivo,
        )
        return SUGESTAO_PENDENTE
    if chave == "titulo_aquisitivo":
        estrutura_svc.definir_fontes(
            client, org_id, UUID(str(extracao_id)),
            valores={"titulo_aquisitivo_ato_id": linha["titulo_aquisitivo_ato_id"]},
            usuario_id=None,
        )
    else:
        estrutura_svc.definir_fontes(
            client, org_id, UUID(str(extracao_id)),
            valores={
                "onus_ato_ids": [a["ato_id"] for a in (linha.get("onus_fonte_atos") or [])]
            },
            usuario_id=None,
        )
    logger.info(
        "matricula autopiloto: imovel %s ponteiro %s confirmado automaticamente — %s",
        codigo, chave, motivo,
    )
    return CONFIRMADO_AUTOMATICO


# ─── contract acts default selection (migration 115) ───────────────────────


def _contratos_do_imovel(client: Any, org_id: UUID, codigo: str) -> list[dict]:
    """Every non-deleted contract of every atendimento negotiating THIS
    imóvel. One imóvel has few atendimentos and each few contracts — looped
    rather than an `.in_()` batch, so this never rides the PostgREST row cap
    (`KB PATTERNS/backend/postgrest-row-cap.md`)."""
    negociacoes = (
        _t(client, estrutura_svc.NEGOCIACAO_TABLE)
        .select("atendimento_id")
        .eq("org_id", str(org_id))
        .eq("imovel_codigo", codigo)
        .execute()
    ).data or []
    atendimento_ids = sorted(
        {str(r["atendimento_id"]) for r in negociacoes if r.get("atendimento_id")}
    )
    contratos: list[dict] = []
    for atendimento_id in atendimento_ids:
        rows = (
            _t(client, estrutura_svc.CONTRATOS_TABLE)
            .select("id,atendimento_id,deleted_at")
            .eq("org_id", str(org_id))
            .eq("atendimento_id", atendimento_id)
            .execute()
        ).data or []
        contratos.extend(r for r in rows if not r.get("deleted_at"))
    return contratos


def _atos_padrao(
    atos: list[dict], titulo_ato_id: Optional[str], onus_ato_ids: list[str]
) -> list[str]:
    """The default quote: the abertura (property description/PROPRIETÁRIOS),
    the título act, and every active ônus act — in matrícula order. Exactly
    `MatriculaAtosSelector`'s own guidance for what a promessa's OBJETO/ônus
    clauses need (see the module docstring)."""
    por_id = {str(a["id"]): a for a in atos}
    ids: list[str] = []
    abertura = next((a for a in atos if a["kind"] == "abertura"), None)
    if abertura is not None:
        ids.append(str(abertura["id"]))
    if titulo_ato_id and titulo_ato_id in por_id and titulo_ato_id not in ids:
        ids.append(titulo_ato_id)
    for oid in onus_ato_ids:
        if oid in por_id and oid not in ids:
            ids.append(oid)
    return sorted(ids, key=lambda i: por_id[i]["ordem"])


def _selecionar_atos_padrao(
    client: Any, org_id: UUID, codigo: str, extracao: dict, atos: list[dict], linha: dict
) -> dict:
    eid = str(extracao["id"])
    if str(linha.get("titulo_aquisitivo_extracao_id") or "") != eid:
        # Nothing definitive to quote from THIS extraction yet (título still
        # unset, or set from a different extraction) — a human resolves the
        # título first; this stays a no-op rather than guessing a selection.
        return {"aplicavel": False}

    titulo_ato_id = linha.get("titulo_aquisitivo_ato_id")
    onus_ato_ids = (
        [str(a["ato_id"]) for a in (linha.get("onus_fonte_atos") or [])]
        if str(linha.get("onus_fonte_extracao_id") or "") == eid
        else []
    )
    ids = _atos_padrao(atos, str(titulo_ato_id) if titulo_ato_id else None, onus_ato_ids)
    if not ids:
        return {"aplicavel": False}

    criados: list[str] = []
    existentes: list[str] = []
    for contrato in _contratos_do_imovel(client, org_id, codigo):
        contrato_id = UUID(str(contrato["id"]))
        selecao = estrutura_svc.obter_selecao(client, org_id, contrato_id)
        if selecao.get("atos"):
            # A selection already exists — anyone's (a human's, or an
            # earlier autopilot pass): never overridden.
            existentes.append(str(contrato_id))
            continue
        estrutura_svc.definir_selecao(
            client, org_id, contrato_id,
            extracao_id=UUID(eid), ato_ids=[UUID(i) for i in ids],
            usuario_id=None,
        )
        criados.append(str(contrato_id))
    if criados:
        logger.info(
            "matricula autopiloto: imovel %s — selecao padrao aplicada a %d contrato(s) (%s)",
            codigo, len(criados), ", ".join(criados),
        )
    return {
        "aplicavel": True,
        "atos": ids,
        "contratos_criados": criados,
        "contratos_existentes": existentes,
    }


# ─── orchestration ──────────────────────────────────────────────────────


def aplicar_autopiloto(client: Any, org_id: UUID, extracao_id: Any) -> dict:
    """Run right after `preenchimento_service.preencher_sincrono`/
    `preencher_imovel` land their machine-pending fill for `extracao_id`.
    Confirms every field it can vouch for unambiguously (see module
    docstring); leaves everything else exactly as `preenchimento_service`
    left it. Never raises for a single field's failure — isolated per field,
    same posture `preenchimento_service._aplicar` takes, because this runs
    right after a paid transcription and must not turn a fill into a
    failure. Idempotent: a second run finds every already-decided field
    `JA_CONFIRMADO_HUMANO` and changes nothing.
    """
    extracao = _extracao(client, org_id, extracao_id)
    if extracao is None or extracao.get("status") != estrutura_svc.STATUS_CONCLUIDA:
        return {"status": "sem_texto"}
    codigo = extracao.get("codigo")
    if not codigo:
        return {"status": "sem_imovel"}
    # Same rule as `preenchimento_service`: only NEVER-parsed (legacy) text is
    # untrustworthy; a parsed text with one literal marker is read, and the
    # fill never applied a value carrying one.
    if extracao.get("substituida_por") or (
        extracao.get("possui_marcacao_bruta") and extracao.get("formatacao") is None
    ):
        return {"status": "extracao_nao_confiavel"}

    eid = str(extracao["id"])
    texto = extracao.get("texto_extraido") or ""
    atos = estrutura_svc.atos_da_extracao(client, org_id, extracao)
    detalhes = detalhes_svc.detalhes_por_ato(client, org_id, extracao, atos)
    sugestoes = estrutura_svc.sugerir(texto, atos, detalhes)
    linha = dados_service.linha(client, org_id, codigo) or {}

    campos: dict[str, str] = {}

    def _tentar(chave: str, *, inequivoco: bool, motivo: str) -> None:
        try:
            campos[chave] = _confirmar_quinteto(
                client, org_id, codigo, chave, inequivoco=inequivoco, motivo=motivo
            )
        except Exception as exc:  # noqa: BLE001 - per-field isolation; logged loudly
            logger.error(
                "matricula autopiloto: imovel %s campo %s falhou — %s",
                codigo, chave, exc, exc_info=True,
            )
            campos[chave] = "erro"

    def _tentar_pointer(chave: str, *, inequivoco: bool, motivo: str) -> None:
        try:
            campos[chave] = _confirmar_pointer(
                client, org_id, codigo, eid, chave, inequivoco=inequivoco, motivo=motivo
            )
        except Exception as exc:  # noqa: BLE001 - per-field isolation; logged loudly
            logger.error(
                "matricula autopiloto: imovel %s ponteiro %s falhou — %s",
                codigo, chave, exc, exc_info=True,
            )
            campos[chave] = "erro"

    # 1. Cartório — see module docstring: `find_cartorio` only ever fills
    #    the field at its own "alta" confidence, so this is unambiguous by
    #    construction whenever there is a value at all.
    _tentar("numero_registro_imoveis", inequivoco=True, motivo="cabecalho com um unico cartorio")

    # 2. Título aquisitivo — the act pointer, then its confirmed wording.
    titulo_ok, motivo_titulo = _titulo_inequivoco(sugestoes["titulo_aquisitivo"], linha, eid)
    _tentar_pointer("titulo_aquisitivo", inequivoco=titulo_ok, motivo=motivo_titulo)
    # Re-read: the pointer confirm above may have changed nothing on the
    # ROW (it never touches `titulo_aquisitivo_texto`), but staying off a
    # stale `linha` for the next field would risk reading a value the
    # pointer confirm's own re-read already superseded.
    linha = dados_service.linha(client, org_id, codigo) or {}
    _tentar("titulo_aquisitivo_texto", inequivoco=titulo_ok, motivo=motivo_titulo)

    # 3. Ônus — the act pointer(s), the situação, and the credor — all
    #    share the SAME "no cancellations ambiguity" bar.
    situacao = preenchimento_service.derivar_situacao_onus(atos, detalhes, sugestoes["onus"])
    onus_ok, motivo_onus = _onus_inequivoco(situacao)
    _tentar_pointer("onus_fonte", inequivoco=onus_ok, motivo=motivo_onus)
    linha = dados_service.linha(client, org_id, codigo) or {}
    _tentar("situacao_onus", inequivoco=onus_ok, motivo=motivo_onus)
    _tentar("onus_credor", inequivoco=onus_ok, motivo=motivo_onus)

    # 4. The contract's default quote — only once the título is resolved
    #    (auto or human) against THIS extraction.
    linha = dados_service.linha(client, org_id, codigo) or {}
    atos_contrato = _selecionar_atos_padrao(client, org_id, codigo, extracao, atos, linha)

    return {"status": "ok", "codigo": codigo, "campos": campos, "atos_contrato": atos_contrato}


__all__ = [
    "CONFIRMADO_AUTOMATICO",
    "INAPLICAVEL",
    "JA_CONFIRMADO_HUMANO",
    "ORIGEM_AUTOPILOTO",
    "REVISAO_FINAL_UNICA_POR_CONTRATO",
    "SEM_VALOR",
    "SUGESTAO_PENDENTE",
    "aplicar_autopiloto",
]
