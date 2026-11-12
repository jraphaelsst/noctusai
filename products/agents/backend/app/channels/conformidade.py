"""Post-turn conformance for channel turns (Julia v2 CONTRACT §3.5 E3, owner round 2: IP protection).

Pure detectors over the facts of one turn, a prompt-leak fingerprint, and the policy application. Nothing
here owns a human-readable string: the correction a ``bloquear`` rule re-runs the model with is the row
``conformidade.correcao.<regra>`` (registry key in ``textos_registry``), the hand-off note is
``conformidade.handoff_resumo``. A violation row stores CODES and COUNTS only -- never the reply, the
lead's words or a prompt fragment (the leak detector is the last thing that may copy the prompt around).

Detectors (each is a function ``(...) -> detalhe | None``; ``None`` = clean):

* ``imovel_sem_ferramenta`` -- the reply carries a property code (rule parameter ``padrao_codigo``, a
  regex that is DATA) or a link that no tool returned in this thread;
* ``termina_sem_pergunta`` -- the reply does not end in a question although the participant stays active
  and nothing handed off / concluded / ended;
* ``transferencia_sem_handoff`` -- the reply PROMISES a transfer to a person ("vou te transferir", "um especialista vai
  falar com você") although no ``handoff`` call happened in the turn (blocks by default: one corrective re-run);
* ``insatisfacao_sem_alerta`` -- the LEAD's message complains about the service ("já te falei", "você não presta atenção")
  and no ``sinalizar_alerta`` call succeeded in the turn (blocks by default; never on a stop request / hand-off / ``encerrar``);
* ``perfil_citado_sem_registro`` -- the lead answered the criterion being asked (matched ONLY through the
  option synonyms the standard's rows list) and no ``registrar_perfil`` for it happened;
* ``fallback_enviado`` -- the tool loop was exhausted (the reply is the fallback or nothing);
* ``pergunta_repetida`` -- the reply asks about a criterion whose value the dossier already holds;
* ``vazamento_prompt`` -- the per-org/per-version canary, or >= :data:`SHINGLE_TOKENS` consecutive
  normalised tokens shared with the compiled prompt / texts (hashed shingles precomputed at publish).
  Default policy ``bloquear``;
* ``tentativa_extracao`` -- INPUT side, signal only: the lead's message tries to extract instructions;
* ``link_nao_permitido`` / ``contato_nao_permitido`` / ``pii_na_resposta`` / ``formato_suspeito`` /
  ``padroes_proibidos`` -- the public-line output filters (``bloquear`` by default): a link, a contact, an
  identity number, an encoded/structured payload or a policy pattern (rule DATA) that no tool, the org or
  the lead itself put in the thread;
* ``alegacao_identidade`` -- INPUT side, signal only (patterns are rule data): "sou o dono", "sou da polícia".
  A claim never grants anything: no detector result may ADD a capability
  (``tests/channels/test_julia_guardrails.py`` keeps that as an invariant).

The deterministic escalations (``escala_*``) live here too: their match patterns are rule parameters
(data); ``escala_qualificacao_completa`` needs none.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from noctusai_lib.integrations.llm.guardrails import (
    SHINGLE_TOKENS,
    SHINGLE_TOKENS_DERIVADO,
    GuardContext,
    RealOutputGuard,
    canario,
    contar_padroes,
    contato_nao_permitido,
    detectar_vazamento,
    esqueleto,
    formato_suspeito,
    link_nao_permitido,
    lista_de_spec,
    mascarar_dados_da_org,
    padroes_proibidos,
    pii_na_resposta,
    sem_falas_de_exemplo,
    shingles_de,
    tem_caractere_oculto,
    worst_of,
)
from noctusai_lib.integrations.llm.guardrails.fingerprint import tokens_of as _tokens
from noctusai_lib.integrations.llm.guardrails.text import (
    skeleton_targets as _alvos,
    strip_trailing_decoration as _fim_sem_enfeite,
    termina_com_pergunta,
)

from app.qualificacao.matcher import normalizar
from app.stores.conformidade import (
    PALAVRAS_PARAR_PISO,
    PISO_DE_PADROES,
    POLITICA_PADRAO,
    ConformidadeStore,
    Impressao,
    RegraConfig,
    Violacao,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SHINGLE_TOKENS",
    "shingle_tokens_da_regra",
    "EntradaConformidade",
    "GuardaVazamento",
    "canario",
    "avaliar_resposta",
    "CAMPOS_PROTEGIDOS",
    "SPEC_CNPJ",
    "SPEC_CONTATOS",
    "SPEC_DOMINIOS",
    "contato_nao_permitido",
    "contar_padroes",
    "formato_suspeito",
    "lista_de_spec",
    "link_nao_permitido",
    "nivel_seguranca",
    "padroes_proibidos",
    "padroes_efetivos",
    "palavra_de_parar",
    "pii_na_resposta",
    "valor_sem_ferramenta",
    "transferencia_sem_handoff",
    "insatisfacao_sem_alerta",
    "sinal_alegacao",
    "casar_padroes",
    "detectar_vazamento",
    "impressao_derivada",
    "mascarar_dados_da_org",
    "garantir_impressao",
    "impressao_de",
    "sinal_extracao",
    "termina_com_pergunta",
    "texto_fonte_do_prompt",
    "violacoes_bloqueantes",
]

#: Org-spec keys (``{{org.<chave>}}`` values, the agency's own data) the output filters read.
SPEC_DOMINIOS = "dominios_permitidos"  # hosts the agency owns (its site); one per line / comma separated
SPEC_CONTATOS = "contatos_oficiais"  # official phones / e-mails of the agency
SPEC_CNPJ = "cnpj_oficial"  # the agency's own CNPJ (the only company id a reply may carry)
#: Lead-influenced tool arguments that reach humans (spec B3.6): tool -> argument names.
CAMPOS_PROTEGIDOS: dict[str, tuple[str, ...]] = {
    "handoff": ("motivo",),
    "captacao": ("descricao", "endereco"),
    "encerrar": ("motivo_texto",),
    "registrar_reacao_imovel": ("motivo",),
    "registrar_reacao_opcao": ("motivo",),
    "registrar_intencao_visita": ("preferencia_horario",),
    "sinalizar_alerta": ("descricao", "trecho"),
}




def impressao_de(version_id: UUID, texto: str, k: int = SHINGLE_TOKENS) -> Impressao:
    """The fingerprint of ``texto`` (hashes only: it detects a leak, it cannot rebuild the prompt)."""
    return Impressao(version_id, k, shingles_de(texto, k))



#: Key prefix of the corrective system message (``conformidade.correcao.<regra>``). It is injected ONLY into a corrective
#: re-run and tells the model what to say, so it is model-facing speech, not prompt a lead could extract: left out of the
#: fingerprint. (Measured 2026-11-07: it was NOT the cause of the re-run false positives -- see :data:`_FALA_ENTRE_ASPAS` -- but
#: it was the same latent exposure, so it is closed with the same stroke.)
PREFIXO_CORRECAO = "conformidade.correcao."


def _e_correcao(texto_row: Any) -> bool:
    return str(getattr(texto_row, "chave", "") or "").startswith(PREFIXO_CORRECAO)




def texto_fonte_do_prompt(
    compiled: Any, skills: Iterable[str] = (), skill_files: Iterable[str] = (), *, so_skills: bool = False,
) -> str:
    """Everything the model is told that must not be repeated: the compiled prompt plus the content rows
    that ride outside it (texts, tool descriptions, decision rules) and the SKILL texts it reads as tool results
    (``skills`` = the bodies, ``skill_files`` = the reference files, rendered for the org). ``so_skills`` returns only the
    skill part: it is fingerprinted with a longer window than the prompt (:data:`SHINGLE_TOKENS_DERIVADO`), because a skill
    teaches example sentences the agent legitimately says."""
    partes = [] if so_skills else [compiled.texto]
    cont = getattr(compiled, "conteudo", None)
    if cont is not None and not so_skills:
        partes += [t.conteudo for t in cont.textos if t.conteudo and not _e_correcao(t)]
        partes += [f.descricao for f in cont.ferramentas if f.ativo and f.descricao]
        partes += [d.regra for d in cont.decisoes if d.regra]
    partes += list(skills) + list(skill_files)
    return "\n".join(sem_falas_de_exemplo(p) for p in partes if p)


SHINGLE_MIN, SHINGLE_MAX = 4, 64  # the ``conformidade_impressoes.shingle_tokens`` CHECK (037)


def shingle_tokens_da_regra(regra: RegraConfig | None) -> int:
    """The shingle length of the ``vazamento_prompt`` rule: ``parametros.shingle_tokens`` (data, per agent)
    when it is an integer in the stored range, else :data:`SHINGLE_TOKENS`. A mandatory disclosure sentence
    of N tokens that the prompt and the replies must both carry would self-trigger a shorter window; the
    platform admin raises the length for that agent instead of switching the rule off."""
    bruto = (regra.parametros or {}).get("shingle_tokens") if regra is not None else None
    if isinstance(bruto, bool) or not isinstance(bruto, int) or not (SHINGLE_MIN <= bruto <= SHINGLE_MAX):
        if bruto is not None:
            logger.warning("agents.conformidade.shingle_tokens_invalido valor=%r", bruto)
        return SHINGLE_TOKENS
    return bruto


def garantir_impressao(
    store: ConformidadeStore, org_id: UUID, version_id: UUID, compiled: Any, k: int = SHINGLE_TOKENS,
) -> Impressao:
    """The stored fingerprint of the version, computing + storing it when publish has not (an older
    version), when the stored one was cut at another shingle length than the rule's ``k`` now asks, or when it no longer
    equals what the source yields now (the source definition changed after publish). Publish calls this too."""
    atual = store.obter_impressao(org_id, version_id)
    nova = impressao_de(version_id, texto_fonte_do_prompt(compiled), k)
    if atual is not None and atual.shingle_tokens == k and atual.shingles == nova.shingles:
        return atual
    # a fingerprint stored before the source changed (the scripted-speech exemption below) is rebuilt, not trusted
    store.salvar_impressao(org_id, nova)
    return nova




def impressao_derivada(textos: Iterable[str], k: int = SHINGLE_TOKENS_DERIVADO) -> Impressao | None:
    """The fingerprint of the prompt-derived text a tool returned to the model THIS turn (skill bodies / files rendered for the
    org). A reply can only reproduce what the model read, and skills reach it as tool results, outside the compiled text the
    stored fingerprint covers. ``None`` when nothing was handed over."""
    todos: set[int] = set()
    for t in textos:
        todos |= shingles_de(t, k)
    return Impressao(UUID(int=0), k, frozenset(todos)) if todos else None



# ── the detectors ───────────────────────────────────────────────────────────



def imovel_sem_ferramenta(
    resposta: str, codigos_permitidos: Iterable[str], padrao_codigo: str | None,
) -> dict[str, Any] | None:
    """A property code (rule parameter ``padrao_codigo``, DATA) no tool returned in this thread. Links are
    ``link_nao_permitido``'s business."""
    permitidos = {c.casefold() for c in codigos_permitidos}
    achado: dict[str, Any] = {}
    if padrao_codigo:
        try:
            rx = re.compile(padrao_codigo, re.IGNORECASE)
        except re.error:
            logger.error("agents.conformidade.padrao_codigo_invalido")  # a bad rule parameter must be seen
            rx = None
        if rx is not None:
            fora = {m.group(0).casefold() for m in rx.finditer(resposta)} - permitidos
            if fora:
                achado["codigos"] = len(fora)
    return achado or None


def termina_sem_pergunta(resposta: str, *, participante_segue_ativo: bool, encerrou_ou_transferiu: bool) -> dict[str, Any] | None:
    if not resposta.strip() or not participante_segue_ativo or encerrou_ou_transferiu:
        return None
    return None if termina_com_pergunta(resposta) else {"termina_com_pergunta": False}


def perfil_citado_sem_registro(
    criterio: Any | None, mensagens_lead: Sequence[str], registrou_criterio: bool,
) -> dict[str, Any] | None:
    """``criterio`` is the standard's :class:`CriterioDef` of the ``proximo_criterio`` at turn start. Matches
    only through the option ``sinonimos`` rows."""
    if criterio is None or registrou_criterio:
        return None
    alvo = " ".join(normalizar(m) for m in mensagens_lead)
    if not alvo:
        return None
    for op in criterio.opcoes:
        for sin in op.sinonimos:
            n = normalizar(sin)
            if n and f" {n} " in f" {alvo} ":
                return {"criterio": criterio.chave, "opcao": op.valor}
    return None


def fallback_enviado(esgotou_loop: bool) -> dict[str, Any] | None:
    return {"esgotou_loop": True} if esgotou_loop else None


def pergunta_repetida(
    resposta: str, criterios_preenchidos: Mapping[str, str], registrados_no_turno: Iterable[str],
) -> dict[str, Any] | None:
    """``criterios_preenchidos`` maps chave -> rotulo of every criterion the dossier already holds. The
    reply's LAST question is checked against those labels (normalised containment, labels >= 4 chars)."""
    if not termina_com_pergunta(resposta):
        return None
    corpo = _fim_sem_enfeite(resposta)
    ultima = re.split(r"(?<=[.!?\n])\s+", corpo)[-1]
    alvo = f" {normalizar(ultima)} "
    ja = set(registrados_no_turno)
    repetidos = [
        k for k, rotulo in criterios_preenchidos.items()
        if k not in ja and len(normalizar(rotulo)) >= 4 and f" {normalizar(rotulo)} " in alvo
    ]
    return {"criterios": sorted(repetidos)} if repetidos else None


# ── public-line output filters (spec B3) ───────────────────────────────────




_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")


def padroes_efetivos(regra: str, parametros: Mapping[str, Any] | None) -> list[str]:
    """The patterns a pattern rule runs: the code-side FLOOR first, then the stored ones (the DB adds, never removes)."""
    piso = PISO_DE_PADROES.get(regra, ())
    guardados = [p for p in ((parametros or {}).get("padroes") or []) if isinstance(p, str) and p not in piso]
    return [*piso, *guardados]



# ── an amount the tools never returned (P1-2) ──────────────────────────────

_ESCALAS = {"mil": Decimal(1000), "k": Decimal(1000), "mi": Decimal(10) ** 6, "milhao": Decimal(10) ** 6,
            "milhoes": Decimal(10) ** 6, "bi": Decimal(10) ** 9, "bilhao": Decimal(10) ** 9, "bilhoes": Decimal(10) ** 9}
_NUMERO = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"
_ESCALA_RX = r"(?:\s*(mil(?:h(?:ao|oes|\u00e3o|\u00f5es))?|mi|bi(?:lh(?:ao|oes))?|k)\b)?"  # noc-allow: prompt-text-in-code -- a regex of scale words, detection structure never read by a model
_DINHEIRO = re.compile(rf"(?:r\$|reais?\s*:?)\s*({_NUMERO}){_ESCALA_RX}|({_NUMERO}){_ESCALA_RX}\s*(?:reais|real)\b", re.IGNORECASE)
_PORCENTO = re.compile(rf"({_NUMERO})\s*(?:%|por\s*cento|percent)", re.IGNORECASE)
_QUALQUER_NUMERO = re.compile(rf"(?<![\w.,])({_NUMERO}){_ESCALA_RX}", re.IGNORECASE)
_CENTAVOS = Decimal("0.01")


def _candidatos(tok: str) -> set[Decimal]:
    """The values a numeric token can mean (pt-BR ``1.234,50`` / ``450.000``, JSON ``450000.5``): ambiguity yields
    every reading, so a legitimately backed amount is never refused for its spelling."""
    out: set[Decimal] = set()
    try:
        if "," in tok and "." in tok:
            out.add(Decimal(tok.replace(".", "").replace(",", ".")))
        elif "," in tok:
            out.add(Decimal(tok.replace(",", ".")))
            if re.fullmatch(r"\d{1,3}(,\d{3})+", tok):
                out.add(Decimal(tok.replace(",", "")))
        elif "." in tok:
            out.add(Decimal(tok))
            if re.fullmatch(r"\d{1,3}(\.\d{3})+", tok):
                out.add(Decimal(tok.replace(".", "")))
        else:
            out.add(Decimal(tok))
    except InvalidOperation:
        return set()
    return {v.quantize(_CENTAVOS) for v in out}


def _escalado(base: set[Decimal], escala: str | None) -> set[Decimal]:
    if not escala:
        return base
    fator = _ESCALAS.get(normalizar(escala).replace(" ", ""), Decimal(1))
    return {(v * fator).quantize(_CENTAVOS) for v in base}


def _valores_do_texto(texto: str) -> set[Decimal]:
    out: set[Decimal] = set()
    for m in _QUALQUER_NUMERO.finditer(texto):
        base = _candidatos(m.group(1))
        out |= base | _escalado(base, m.group(2))
    return out


def valor_sem_ferramenta(resposta: str, textos_com_valor: Iterable[str]) -> dict[str, Any] | None:
    """Every ``R$`` amount and every percentage of the reply must be a number that appears in ``textos_com_valor`` (this
    thread's tool results, the lead's own words, the agent's earlier replies, the dossier). A price or a discount
    nobody returned is invented. ``detalhe`` holds the count of unbacked figures, never the figures."""
    if not resposta or not resposta.strip():
        return None
    permitidos: set[Decimal] = set()
    for t in textos_com_valor:
        if isinstance(t, str) and t:
            permitidos |= _valores_do_texto(unicodedata.normalize("NFKC", t))
    sem: set[tuple[str, Decimal]] = set()
    for alvo in _alvos([resposta]):
        for m in _DINHEIRO.finditer(alvo):
            tok, escala = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            cand = _escalado(_candidatos(tok), escala)
            if cand and not (cand & permitidos):
                sem.add(("valor", min(cand)))
        for m in _PORCENTO.finditer(alvo):
            cand = _candidatos(m.group(1))
            if cand and not (cand & permitidos):
                sem.add(("percentual", min(cand)))
    return {"valores": len(sem)} if sem else None


# ── a promised transfer nobody made ─────────────────────────────────────────

#: The people a promise may name (accents folded; matched on the de-obfuscated skeleton).
_PESSOAS: tuple[str, ...] = (
    "corretor\\w*", "atendente\\w*", "humano\\w*", "pessoa\\w*", "especialista\\w*", "consultor\\w*", "gerente\\w*",
    "equipe", "time", "alguem", "colega\\w*", "responsavel", "setor",
)
_PESSOA = "(?:" + "|".join(_PESSOAS) + ")"
#: A COMMITMENT to move the lead to a person (a first-person future / progressive / perfect form). Modal offers ("posso
#: te transferir", "quer que eu te transfira") carry none of these anchors, so they never match.
_PROMESSA_TRANSFERENCIA: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    r"\b(?:vou|irei|vamos|iremos)\s+(?:ja\s+)?(?:te\s+|lhe\s+)?(?:transferir|encaminhar)\b",
    r"\b(?:estou|to|estarei|ja\s+estou)\s+(?:te\s+|lhe\s+)?(?:transferindo|encaminhando|passando|direcionando|conectando)\b",
    r"\b(?:ja\s+|acabei\s+de\s+)?(?:te\s+|lhe\s+)?(?:transferi|encaminhei)\b",
))
#: A softer promise of CONTACT: "vou passar para o responsavel" / "um corretor vai entrar em contato". It is true (not a lie)
#: whenever the turn handed the lead over (``handoff`` / ``concluir_qualificacao``) OR registered a visit intention
#: (``registrar_intencao_visita``: the skill ``intencao-de-visita`` tells the agent to say exactly this). It is a violation only
#: when nothing in the turn backs it. The explicit transfer verbs above stay handoff-only.
_PROMESSA_CONTATO: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    r"\b(?:vou|irei|vamos|iremos)\s+(?:ja\s+)?(?:te\s+|lhe\s+)?(?:passar|direcionar|colocar|conectar|chamar|apresentar|"
    r"pedir|solicitar|acionar)\b[^.!?\n]{0,60}\b" + _PESSOA + r"\b",
    r"\b(?:um|uma|o|a|nosso|nossa|algum|alguem\s+d[aeo]\s+\w+)\s+" + _PESSOA + r"\b[^.!?\n]{0,40}\b(?:vai|ira|vao|irao)\s+"
    r"(?:\w+\s+){0,2}?(?:falar\s+(?:com\s+)?(?:voce|vc|o\s+senhor|a\s+senhora)|te\s+(?:atender|chamar|ligar|responder|procurar)|"
    r"entrar\s+em\s+contato|assumir|continuar|dar\s+(?:continuidade|sequencia|seguimento)|seguir\s+(?:com|o))",
))
#: A sentence that only OFFERS or negates is not a promise ("se quiser, vou te transferir"; "não vou te transferir").
_NAO_E_PROMESSA = re.compile(
    r"\b(?:se\s+(?:voce\s+|vc\s+)?(?:quiser|preferir|desejar|precisar|gostar|topar)|caso\s+(?:voce\s+)?(?:queira|prefira|deseje|precise)|"
    r"nao\s+(?:vou|irei|vamos|posso|consigo|estou)|sem\s+que)\b")


def transferencia_sem_handoff(
    resposta: str, *, transferiu_no_turno: bool, contato_garantido_no_turno: bool = False,
) -> dict[str, Any] | None:
    """The reply promises that a person takes over (a first-person commitment, see :data:`_PROMESSA_TRANSFERENCIA`) while no
    ``handoff`` call happened in the turn: the promise is false and the lead waits for nobody. Never fires when the turn
    transferred. A promise of CONTACT (:data:`_PROMESSA_CONTATO`) is also backed by ``contato_garantido_no_turno`` (a visit intention
    was registered, or the qualification was concluded). An offer ("posso te transferir se quiser?") is no commitment and is
    left alone. ``detalhe`` is a count."""
    if transferiu_no_turno or not resposta or not resposta.strip():
        return None
    n = 0
    for frase in re.split(r"(?<=[.!?\n])\s+|\n", esqueleto(resposta)):
        if _NAO_E_PROMESSA.search(frase):
            continue
        regras = _PROMESSA_TRANSFERENCIA if contato_garantido_no_turno else (*_PROMESSA_TRANSFERENCIA, *_PROMESSA_CONTATO)
        if any(rx.search(frase) for rx in regras):
            n += 1
    return {"promessas": n} if n else None


# ── a complaint about the service nobody flagged ────────────────────────────

#: Phrasings (accents folded: they run on the de-obfuscated skeleton too) of a lead complaining about the SERVICE: being
#: made to repeat, not being heard, insults at the agent, "what a bad service". A change of mind ("na verdade quero casa") and
#: neutral talk carry none of these anchors. The rule's ``parametros.padroes`` (regexes, data) extend the list.
_INSATISFACAO_BASE: tuple[str, ...] = (
    r"\bja\s+(?:te|lhe)\s+(?:falei|disse|informei|respondi|expliquei)\b",
    r"\bja\s+(?:falei|disse|informei|respondi)\s+(?:isso|isto|que|acima|antes|tudo)\b",
    r"\bja\s+(?:me\s+)?perguntou\s+(?:isso|isto|essa|esta)\b",
    r"\bvoce\s+ja\s+me\s+(?:perguntou|pediu)\b",
    r"\bnao\s+(?:(?:esta|ta)\s+)?(?:presta|prestando)\s+atencao\b",
    r"\bnao\s+(?:(?:esta|ta)\s+)?me\s+(?:ouvindo|entendendo|escutando|ouve|escuta|entende|compreende)\b",
    r"\bnao\s+foi\s+(?:isso|isto)\s+que\s+(?:eu\s+)?(?:pedi|perguntei|falei|disse|quis)\b",
    r"\batendimento\s+(?:e\s+|ta\s+|esta\s+)?(?:muito\s+|bem\s+|tao\s+)?(?:ruim|pessimo|horrivel|terrivel|lixo)\b",
    r"\b(?:voce|vc)\s+(?:e|eh)\s+(?:muito\s+|tao\s+|bem\s+)?(?:burr[ao]|inutil|idiot[ao]|estupid[ao]|incompetente|ridicul[ao])\b",
    r"\bnao\s+entende\s+nada\b",
    r"\bpela\s+(?:terceira|quarta|quinta|enesima|milesima)\s+vez\b",
    r"\be\s+a\s+(?:terceira|quarta|quinta)\s+vez\b",
    r"\bde\s+novo\s+(?:isso|essa\s+pergunta|a\s+mesma)\b",
    r"\bcansad[oa]\s+de\s+repetir\b",
    r"\bquantas\s+vezes\s+(?:vou|preciso|tenho\s+que)\s+(?:falar|dizer|repetir)\b",
)
#: A stop request goes to ``encerrar(lead_pediu_parar)`` (no alert): a complaint inside one never fires the rule. The EXACT stop
#: words are :func:`palavra_de_parar`'s; these are the sentence forms.
_PEDIDO_DE_PARAR = re.compile(
    r"\bnao\s+quero\s+mais\s+(?:receber|mensagem|mensagens|contato|conversar|falar|atendimento)\b"
    r"|\b(?:para|pare|parem)\s+de\s+(?:me\s+)?(?:mandar|enviar|chamar|ligar|incomodar|procurar)\b"
    r"|\bnao\s+me\s+(?:mande|envie|chame|ligue|procure)\b"
    r"|\bme\s+(?:tira|tire|remove|remova|exclui|exclua)\b|\bchega\s+de\s+mensagens?\b|\bdescadastr\w*|\bsai\s+fora\b", re.IGNORECASE)


def insatisfacao_sem_alerta(
    mensagens_lead: Sequence[str], *, alertou_no_turno: bool, encerrou_ou_transferiu: bool = False,
    padroes: Iterable[str] = (), palavras_parar: RegraConfig | None = None,
) -> dict[str, Any] | None:
    """The lead's messages of this turn complain about the service (:data:`_INSATISFACAO_BASE` + ``padroes``) while no
    ``sinalizar_alerta`` call succeeded in the turn. Never fires when the turn alerted, handed off or ended (the transfer / the
    opt-out is the priority) or when the lead asks to stop (exact word or sentence form). ``detalhe`` is a message count."""
    if alertou_no_turno or encerrou_ou_transferiu:
        return None
    msgs = [m for m in mensagens_lead if isinstance(m, str) and m.strip()]
    if not msgs or palavra_de_parar(msgs, palavras_parar) is not None:
        return None
    if any(_PEDIDO_DE_PARAR.search(a) for a in _alvos(msgs)):
        return None
    n = casar_padroes(msgs, [*_INSATISFACAO_BASE, *padroes])
    return {"mensagens": n} if n else None


# ── stop words: a SIGNAL for Julia, never an override (owner decision 2026-11-08) ───────────────────────────────────────────────


def _forma_exata(texto: str) -> str:
    """A message reduced to its words: skeleton, no punctuation, single spaces (``"  Parar!! "`` -> ``"parar"``)."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", esqueleto(texto))).strip()


def palavra_de_parar(mensagens_lead: Iterable[str], regra: RegraConfig | None) -> str | None:
    """The stop word when a message of the lead's batch IS (exactly, normalised) one of ``PARAR|PARE|PARA|PAREM|SAIR|SAI|
    STOP|CANCELAR|CHEGA|NÃO QUERO MAIS`` or a word of the rule's ``parametros.palavras`` -- a sentence merely CONTAINING it is not a match
    (the model weighs those). ``None`` when none, or when the rule is switched off."""
    if regra is not None and not regra.ativo:
        return None
    extras = [p for p in ((regra.parametros if regra else None) or {}).get("palavras") or [] if isinstance(p, str)]
    palavras = {_forma_exata(p) for p in (*PALAVRAS_PARAR_PISO, *extras)} - {""}
    for m in mensagens_lead:
        forma = _forma_exata(m)
        if forma in palavras:
            return forma
    return None


# ── input side + deterministic escalation (patterns are data, with a code-side floor for extraction) ──

#: A security heuristic, not prompt content: phrasings of an attempt to read the instructions. The rule's
#: ``parametros.padroes`` (regexes, data) extend it.
_EXTRACAO_BASE = (
    r"\b(ignore|ignora|esque[cç]a|desconsidere|desconsidera)\b.{0,40}\b(instru|regras|prompt|anterior|acima)",
    r"\b(system|developer|sistema)\s*(prompt|message|mensagem)\b",
    r"\b(repita|mostre|revele|imprima|liste|copie|diga|print|show|reveal|repeat|escreva|me\s+passe|me\s+mostra)\b.{0,50}\b(suas|seu|your|the|tuas|tuas)\b.{0,20}\b(instru[cç][oõ]es|prompt|regras|configura[cç][aã]o|instructions|rules)\b",
    r"\bcomo voc[eê] foi (programad|configurad|instru[ií]d)",
    r"\b(jailbreak|DAN mode|modo desenvolvedor|developer mode|modo\s+de?\s+teste|test\s+mode|modo\s+debug|debug\s+mode)\b",
    # role-play / persona override, "I'm the developer"
    r"\b(finja|finge|fingir|aja\s+como|atue\s+como|voc[eê]\s+agora\s+[eé]|a\s+partir\s+de\s+agora\s+voc[eê]|pretend|act\s+as|you\s+are\s+now)\b.{0,60}\b(sem\s+(regras|restri|filtro|limite)|desenvolvedor|developer|admin|root|outro\s+(rob[oô]|agente|assistente)|dan\b)",
    r"\b(sou|eu\s+sou|i\s*'?m|i\s+am)\b.{0,25}\b(o\s+|a\s+|seu\s+|sua\s+|the\s+|your\s+)?(desenvolvedor|programador|criador|developer|programmer|engenheiro\s+do\s+sistema)\b",
    # translate / summarise / encode the instructions
    r"\b(traduz|traduza|traduzir|translate|resuma|resumir|summari[sz]e|codifique|codifica|encode|converta|converte)\b.{0,60}\b(instru[cç][oõ]es|prompt|regras|tudo\s+que\s+(te|lhe)\s+(disseram|falaram|passaram)|everything\s+(above|before)|what\s+you\s+were\s+told)",
    r"\b(base\s*64|hexadecimal|rot\s*13|bin[aá]rio|morse)\b.{0,60}\b(instru[cç][oõ]es|regras|prompt)|\b(instru[cç][oõ]es|regras|prompt)\b.{0,60}\b(base\s*64|hexadecimal|rot\s*13|bin[aá]rio|morse)\b",
    # what comes before my first message / print the text above
    r"\b(o\s+que|tudo\s+(o\s+)?que)\b.{0,40}\b(vem|veio|est[aá]|estava|aparece)\b.{0,30}\b(antes|acima)\b.{0,30}\b(da\s+)?(minha|primeira)",
    r"\b(antes|acima)\s+d[ae]\s+(minha|primeira)\s+(primeira\s+)?mensagem",
    r"\b(print|imprima|mostre|repita|repeat|show)\b.{0,30}\b(the\s+text\s+above|o\s+texto\s+acima|texto\s+acima|tudo\s+acima|mensagem\s+acima)",
    # acrostics / first letter of each rule
    r"\b(primeira|[uú]ltima|first|last)\s+(letra|letter)\b.{0,40}\b(cada|each|every)\b.{0,30}\b(regra|instru|linha|rule|line|instruction)",
    r"\b(cada|each)\s+(regra|instru[cç][aã]o|rule|instruction)\b.{0,40}\b(primeira|first)\s+(letra|letter)",
)


def casar_padroes(textos: Iterable[str], padroes: Iterable[str]) -> int:
    """How many of ``textos`` match any of the regexes ``padroes`` (case/accent-insensitive). A broken
    pattern is logged and skipped -- a bad data row must not take the turn down, nor go unseen."""
    rxs = []
    for p in padroes:
        try:
            rxs.append(re.compile(p, re.IGNORECASE))
        except re.error:
            logger.error("agents.conformidade.padrao_invalido")
    n = 0
    for t in textos:
        if any(rx.search(alvo) for alvo in _alvos([t]) for rx in rxs):
            n += 1
    return n


def sinal_extracao(mensagens_lead: Sequence[str], regra: RegraConfig | None) -> dict[str, Any] | None:
    if regra is not None and not regra.ativo:
        return None
    extra = list((regra.parametros if regra else {}).get("padroes") or [])
    n = casar_padroes(mensagens_lead, [*_EXTRACAO_BASE, *extra])
    return {"mensagens": n} if n else None


def sinal_alegacao(mensagens_lead: Sequence[str], regra: RegraConfig | None) -> dict[str, Any] | None:
    """INPUT side, signal only: the lead CLAIMS to be someone (owner, broker, support, police, lawyer). The
    patterns are the code-side floor (``stores.conformidade.PADROES_ALEGACAO_PISO``) plus the rule's ``parametros.padroes``. A claim is
    only ever counted (``escala_seguranca``); nothing in code branches on it to grant anything."""
    if regra is not None and not regra.ativo:
        return None
    n = casar_padroes(mensagens_lead, padroes_efetivos("alegacao_identidade", regra.parametros if regra else None))
    return {"mensagens": n} if n else None


#: The ``escala_seguranca`` defaults (the rule's ``parametros`` override them; the migration CHECKs the shape).
LIMIAR_SUSPEITO_PADRAO = 2
LIMIAR_HANDOFF_PADRAO = 3
#: Range a stored threshold may take (migration 044 CHECK `conformidade_regras_escala_limiares_check`).
LIMIAR_MIN = 1
LIMIAR_MAX = 20


def _inteiro(valor: Any, padrao: int) -> int:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 1 else padrao


def nivel_seguranca(regra: RegraConfig | None, sinais_24h: int) -> str:
    """``normal`` | ``restrito`` | ``handoff`` for ``sinais_24h`` extraction/identity signals on one thread in
    24 h. Monotone: more signals never lower the level. A switched-off rule is always ``normal``."""
    if regra is None or not regra.ativo:
        return "normal"
    p = regra.parametros or {}
    suspeito = _inteiro(p.get("limiar_suspeito"), LIMIAR_SUSPEITO_PADRAO)
    handoff = _inteiro(p.get("limiar_handoff"), LIMIAR_HANDOFF_PADRAO)
    if handoff <= suspeito:  # a malformed pair must not disable the escalation
        handoff = suspeito + 1
    if sinais_24h >= handoff:
        return "handoff"
    return "restrito" if sinais_24h >= suspeito else "normal"


# ── orchestration ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntradaConformidade:
    """The facts of one turn the detectors read."""

    resposta: str
    mensagens_lead: Sequence[str]
    regras: Mapping[str, RegraConfig]
    canario: str | None = None
    impressao: Impressao | None = None
    codigos_permitidos: Iterable[str] = ()
    links_permitidos: Iterable[str] = ()
    participante_segue_ativo: bool = True
    encerrou_ou_transferiu: bool = False
    #: a ``handoff`` call succeeded in THIS turn (``transferencia_sem_handoff`` never fires then)
    transferiu_no_turno: bool = False
    #: a visit intention was registered or the qualification concluded in THIS turn: a promise of CONTACT is then true
    contato_garantido_no_turno: bool = False
    #: ``insatisfacao_sem_alerta`` inputs: a ``sinalizar_alerta`` call succeeded / the turn ended the agent in THIS turn, and
    #: the tool is offered at all (a turn that cannot alert is never blocked for not alerting)
    alertou_no_turno: bool = False
    encerrou_no_turno: bool = False
    alerta_ofertado: bool = False
    criterio_perguntado: Any | None = None
    registrou_perfil: bool = False
    criterios_preenchidos: Mapping[str, str] = field(default_factory=dict)
    registrados_no_turno: Iterable[str] = ()
    esgotou_loop: bool = False
    #: Org data (specs): hosts / contacts / CNPJ the agency owns.
    dominios_permitidos: Iterable[str] = ()
    contatos_permitidos: Iterable[str] = ()
    cnpjs_proprios: Iterable[str] = ()
    #: The texts whose numbers a reply may repeat (``valor_sem_ferramenta``): this thread's tool results, the lead's own
    #: words, the agent's earlier replies, the dossier values.
    textos_com_valor: Iterable[str] = ()
    #: fingerprint of the skill text handed to the model this turn (:func:`impressao_derivada`)
    impressao_derivada: Impressao | None = None
    #: the org's spec values: quoting them is not a leak (:func:`mascarar_dados_da_org`)
    dados_da_org: Iterable[str] = ()


_GUARD = RealOutputGuard()  # stateless; the generic output rules live in the seed organ (guardrails)
_pior = worst_of


def avaliar_resposta(e: EntradaConformidade) -> list[Violacao]:
    """Run every active reply detector; the policy of each hit is its rule's. The caller decides what
    ``bloquear`` means (suppress + one corrective re-run, then silence + hand-off)."""
    achados: list[tuple[str, dict[str, Any] | None]] = []
    ctx = GuardContext(
        lead_messages=e.mensagens_lead, allowed_links=e.links_permitidos, allowed_domains=e.dominios_permitidos,
        allowed_contacts=e.contatos_permitidos, own_company_ids=e.cnpjs_proprios, canary=e.canario,
        fingerprint=e.impressao, derived_fingerprint=e.impressao_derivada, org_data=e.dados_da_org)

    def ativa(nome: str) -> RegraConfig | None:
        r = e.regras.get(nome)
        return r if r is not None and r.ativo else None

    if (r := ativa("vazamento_prompt")) is not None:
        achados.append(("vazamento_prompt", _GUARD.evaluate("vazamento_prompt", e.resposta, ctx)))
    if (r := ativa("imovel_sem_ferramenta")) is not None and e.resposta.strip():
        achados.append(("imovel_sem_ferramenta", imovel_sem_ferramenta(
            e.resposta, e.codigos_permitidos, (r.parametros or {}).get("padrao_codigo"))))
    if ativa("termina_sem_pergunta") is not None:
        achados.append(("termina_sem_pergunta", termina_sem_pergunta(
            e.resposta, participante_segue_ativo=e.participante_segue_ativo,
            encerrou_ou_transferiu=e.encerrou_ou_transferiu)))
    if ativa("perfil_citado_sem_registro") is not None:
        achados.append(("perfil_citado_sem_registro", perfil_citado_sem_registro(
            e.criterio_perguntado, e.mensagens_lead, e.registrou_perfil)))
    if ativa("fallback_enviado") is not None:
        achados.append(("fallback_enviado", fallback_enviado(e.esgotou_loop)))
    if ativa("pergunta_repetida") is not None:
        achados.append(("pergunta_repetida", pergunta_repetida(
            e.resposta, e.criterios_preenchidos, e.registrados_no_turno)))
    if (r := ativa("insatisfacao_sem_alerta")) is not None and e.alerta_ofertado:
        achados.append(("insatisfacao_sem_alerta", insatisfacao_sem_alerta(
            e.mensagens_lead, alertou_no_turno=e.alertou_no_turno,
            encerrou_ou_transferiu=e.transferiu_no_turno or e.encerrou_no_turno,
            padroes=padroes_efetivos("insatisfacao_sem_alerta", r.parametros), palavras_parar=e.regras.get("opt_out_palavras"))))
    if e.resposta.strip():
        if ativa("link_nao_permitido") is not None:
            achados.append(("link_nao_permitido", _GUARD.evaluate("link_nao_permitido", e.resposta, ctx)))
        if ativa("contato_nao_permitido") is not None:
            achados.append(("contato_nao_permitido", _GUARD.evaluate("contato_nao_permitido", e.resposta, ctx)))
        if ativa("pii_na_resposta") is not None:
            achados.append(("pii_na_resposta", _GUARD.evaluate("pii_na_resposta", e.resposta, ctx)))
        if (r := ativa("formato_suspeito")) is not None:
            p = r.parametros or {}
            achados.append(("formato_suspeito", _GUARD.evaluate("formato_suspeito", e.resposta, ctx, {
                "max_chars": _inteiro(p.get("max_chars"), 1200), "max_bullets": _inteiro(p.get("max_bullets"), 6)})))
        if (r := ativa("padroes_proibidos")) is not None:
            achados.append(("padroes_proibidos", _GUARD.evaluate(
                "padroes_proibidos", e.resposta, ctx, {"padroes": padroes_efetivos("padroes_proibidos", r.parametros)})))
        if ativa("valor_sem_ferramenta") is not None:
            achados.append(("valor_sem_ferramenta", valor_sem_ferramenta(e.resposta, e.textos_com_valor)))
        if ativa("transferencia_sem_handoff") is not None:
            achados.append((
                "transferencia_sem_handoff",
                transferencia_sem_handoff(
                    e.resposta, transferiu_no_turno=e.transferiu_no_turno,
                    contato_garantido_no_turno=e.contato_garantido_no_turno)))
    return [
        Violacao(nome, e.regras[nome].politica, detalhe)
        for nome, detalhe in achados if detalhe is not None
    ]


def violacoes_bloqueantes(violacoes: Iterable[Violacao]) -> list[Violacao]:
    return [v for v in violacoes if v.politica == "bloquear"]


def politica_efetiva(regras: Mapping[str, RegraConfig], nome: str) -> str:
    r = regras.get(nome)
    return r.politica if r is not None else POLITICA_PADRAO.get(nome, "registrar")


# ── the guard for surfaces that are not a lead channel (studio test chat, eval outputs) ──────────


class GuardaVazamento:
    """The prompt-leak detector over ONE prompt text, for the studio test chat and the eval outputs a caller who is
    not a platform admin can read. Built from the compiled prompt of the turn (hashes only are kept)."""

    _CACHE: dict[str, Impressao] = {}
    _CACHE_MAX = 64

    def __init__(self, texto_fonte: str, *, canario_do_prompt: str | None = None) -> None:
        chave = hashlib.sha256(texto_fonte.encode("utf-8")).hexdigest()
        imp = self._CACHE.get(chave)
        if imp is None:
            imp = impressao_de(UUID(int=0), texto_fonte)
            if len(self._CACHE) >= self._CACHE_MAX:
                self._CACHE.pop(next(iter(self._CACHE)))
            self._CACHE[chave] = imp
        self._impressao = imp
        self._canario = canario_do_prompt

    def verificar(self, resposta: str) -> dict[str, Any] | None:
        return detectar_vazamento(resposta, canario_do_prompt=self._canario, impressao=self._impressao)
