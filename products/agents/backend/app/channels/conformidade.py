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
import hmac
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from noctusai_lib.primitives.identificador import cnpj_dv_valido, cpf_dv_valido

from app.qualificacao.matcher import normalizar
from app.stores.conformidade import (
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
    "pii_na_resposta",
    "sinal_alegacao",
    "casar_padroes",
    "detectar_vazamento",
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
    "registrar_intencao_visita": ("preferencia_horario",),
}

#: Consecutive normalised tokens that make a reply "the prompt".
SHINGLE_TOKENS = 12
_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_TRAILING_URL = ".,;:!?)]}\"'"

# ── fingerprint ─────────────────────────────────────────────────────────────


def _tokens(texto: str) -> list[str]:
    return normalizar(texto).split()


def _h(window: Sequence[str]) -> int:
    digest = hashlib.sha256(" ".join(window).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def shingles_de(texto: str, k: int = SHINGLE_TOKENS) -> frozenset[int]:
    toks = _tokens(texto)
    if len(toks) < k:
        return frozenset()
    return frozenset(_h(toks[i:i + k]) for i in range(len(toks) - k + 1))


def impressao_de(version_id: UUID, texto: str, k: int = SHINGLE_TOKENS) -> Impressao:
    """The fingerprint of ``texto`` (hashes only: it detects a leak, it cannot rebuild the prompt)."""
    return Impressao(version_id, k, shingles_de(texto, k))


def canario(org_id: UUID, version_id: UUID, *, segredo: str = "") -> str:
    """The per-org / per-version canary appended to the system prompt. Deterministic (HMAC over the two
    ids with the platform secret), so nothing is stored; it appears in a reply only if the prompt was
    reproduced. 20 hex chars: not a word, never produced by chance."""
    chave = (segredo or "noctus-canary").encode("utf-8")
    return hmac.new(chave, f"{org_id}:{version_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:20]


def texto_fonte_do_prompt(compiled: Any) -> str:
    """Everything the model is told that must not be repeated: the compiled prompt plus the content rows
    that ride outside it (texts, tool descriptions, decision rules)."""
    partes = [compiled.texto]
    cont = getattr(compiled, "conteudo", None)
    if cont is not None:
        partes += [t.conteudo for t in cont.textos if t.conteudo]
        partes += [f.descricao for f in cont.ferramentas if f.ativo and f.descricao]
        partes += [d.regra for d in cont.decisoes if d.regra]
    return "\n".join(p for p in partes if p)


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
    version) or when the stored one was cut at another shingle length than the rule's ``k`` now asks.
    Publish calls this too, so a turn normally only reads."""
    atual = store.obter_impressao(org_id, version_id)
    if atual is not None and atual.shingle_tokens == k:
        return atual
    nova = impressao_de(version_id, texto_fonte_do_prompt(compiled), k)
    store.salvar_impressao(org_id, nova)
    return nova


def detectar_vazamento(
    resposta: str, *, canario_do_prompt: str | None, impressao: Impressao | None,
) -> dict[str, Any] | None:
    """The reply reproduces the prompt: the canary appears, or >= ``impressao.shingle_tokens`` consecutive
    tokens match the fingerprint. ``detalhe`` carries the matched-window count only."""
    if not resposta or not resposta.strip():
        return None
    achado: dict[str, Any] = {}
    if canario_do_prompt and canario_do_prompt in resposta:
        achado["canario"] = True
    if impressao is not None and impressao.shingles:
        casados = shingles_de(resposta, impressao.shingle_tokens) & impressao.shingles
        if casados:
            achado["janelas"] = len(casados)
    return achado or None


# ── the detectors ───────────────────────────────────────────────────────────


def _fim_sem_enfeite(texto: str) -> str:
    """The text without trailing whitespace, emoji, symbols and closing quotes/brackets."""
    t = texto.rstrip()
    while t:
        c = t[-1]
        cat = unicodedata.category(c)
        if c.isspace() or cat.startswith(("S", "M", "C")) or c in "\"')]}»”’*_~":
            t = t[:-1]
            continue
        break
    return t


def termina_com_pergunta(texto: str) -> bool:
    return _fim_sem_enfeite(texto).endswith("?")


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

_TLDS = "|".join(("com", "br", "net", "org", "io", "me", "ly", "app", "site", "info", "xyz", "link", "online",
                      "co", "gov", "edu", "dev", "store", "shop", "top", "click", "cc", "tv"))
#: A URL, a ``www.`` host, a shortener / messenger host, or a bare domain on a common TLD. A bare domain glued to
#: an ``@`` is an e-mail address (``contato_nao_permitido``'s), not a link.
_LINK = re.compile(
    r"(?<![@\w.-])(?:https?://[^\s<>\"')\]]+|(?:www\.)[^\s<>\"')\]]+|(?:wa\.me|t\.me|bit\.ly|tinyurl\.com)/?[^\s<>\"')\]]*"
    r"|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:" + _TLDS + r")(?![a-z0-9-])(?:/[^\s<>\"')\]]*)?)",
    re.IGNORECASE,
)
_PREFIXO_URL = re.compile(r"^(?:https?://)?(?:www\.)?", re.IGNORECASE)


def _host(url: str) -> str:
    sem = _PREFIXO_URL.sub("", url.strip().rstrip(_TRAILING_URL))
    return re.split(r"[/?#:]", sem, maxsplit=1)[0].casefold()


def lista_de_spec(valor: str | None) -> list[str]:
    """An org-spec value holding a list (one item per line, ``,`` or ``;``) as clean items."""
    return [p.strip() for p in re.split(r"[\n,;]+", valor or "") if p.strip()]


def link_nao_permitido(
    resposta: str, links_permitidos: Iterable[str], dominios_permitidos: Iterable[str],
) -> dict[str, Any] | None:
    """Every URL **or bare domain** of the reply whose host is neither the host of a link a tool returned /
    Julia already sent, nor the agency's own domain (``dominios_permitidos``, an org spec; a subdomain of an
    own domain is own). ``detalhe`` holds the count of foreign hosts."""
    ok_hosts = {_host(l) for l in links_permitidos} | {_host(d) for d in dominios_permitidos}
    ok_hosts.discard("")
    fora: set[str] = set()
    for m in _LINK.finditer(unicodedata.normalize("NFKC", resposta)):
        h = _host(m.group(0))
        if not h or "." not in h:
            continue
        if any(h == ok or h.endswith("." + ok) for ok in ok_hosts):
            continue
        fora.add(h)
    return {"links": len(fora)} if fora else None


_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)
# Word-bounded on both sides: a digit run INSIDE an alphanumeric token (a hex canary, a hash, a listing code
# like ONE12345678901) is not a phone number.
_TELEFONE = re.compile(r"(?<![\w.])(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\w|[.,]\d)")
_PIX = re.compile(
    r"\bchave\s+pix\b|\bpix\s*(?:copia\s+e\s+cola|:)|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_CONTA = re.compile(
    r"\b(?:ag[eê]ncia|ag\.|c/c|conta\s+corrente|conta\s+poupan[cç]a|conta)\s*(?:n[ºo°.]\s*)?:?\s*\d[\d.\-]{2,}",
    re.IGNORECASE,
)
_BOLETO = re.compile(r"(?<!\d)(?:\d[\s.\-]?){46,47}\d(?!\d)")


def _digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _mesmo_telefone(a: str, b: str) -> bool:
    """Two phone numbers are the same when one's digits are the other's suffix (+55 / DDD optional), >= 8 digits."""
    da, db = _digitos(a), _digitos(b)
    return len(da) >= 8 and len(db) >= 8 and (da.endswith(db) or db.endswith(da))


def contato_nao_permitido(
    resposta: str, contatos_permitidos: Iterable[str], mensagens_lead: Iterable[str] = (),
) -> dict[str, Any] | None:
    """Phones, e-mails, PIX keys, bank account/agency and boleto lines in the reply. Allowed only when equal to an
    org-official contact (``contatos_oficiais`` spec) or a value the LEAD typed itself in this thread."""
    oficiais = [c for c in contatos_permitidos if c and c.strip()]
    do_lead = " \n ".join(mensagens_lead)
    emails_ok = {e.casefold() for c in oficiais for e in _EMAIL.findall(c)} | {e.casefold() for e in _EMAIL.findall(do_lead)}
    fones_ok = [m.group(0) for c in oficiais for m in _TELEFONE.finditer(c)] + [m.group(0) for m in _TELEFONE.finditer(do_lead)]
    texto = unicodedata.normalize("NFKC", resposta)
    achado: dict[str, int] = {}
    emails = {e.casefold() for e in _EMAIL.findall(texto)} - emails_ok
    if emails:
        achado["emails"] = len(emails)
    fones = {m.group(0) for m in _TELEFONE.finditer(texto) if not _BOLETO.fullmatch(m.group(0))}
    fones = {f for f in fones if not any(_mesmo_telefone(f, ok) for ok in fones_ok)}
    if fones:
        achado["telefones"] = len(fones)
    if _PIX.search(texto):
        achado["pix"] = len(_PIX.findall(texto))
    if _CONTA.search(texto):
        achado["conta"] = len(_CONTA.findall(texto))
    if _BOLETO.search(texto):
        achado["boleto"] = len(_BOLETO.findall(texto))
    return achado or None


_CPF = re.compile(r"(?<![\d.])\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?![\d])")
_CNPJ = re.compile(r"(?<![\d.])\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}(?![\d])")
_RG = re.compile(r"\brg\b\s*(?:n[ºo°.]\s*)?:?\s*\d[\d.\-xX]{5,}|(?<![\d.])\d{1,2}\.\d{3}\.\d{3}-[\dxX](?![\d])", re.IGNORECASE)


def pii_na_resposta(resposta: str, cnpjs_proprios: Iterable[str] = ()) -> dict[str, Any] | None:
    """A CPF with valid check digits (never echoed, not even the lead's own), an RG-shaped value, or a CNPJ that
    is not the agency's own."""
    texto = unicodedata.normalize("NFKC", resposta)
    proprios = {_digitos(c) for c in cnpjs_proprios if c}
    achado: dict[str, int] = {}
    cpfs = [m for m in _CPF.finditer(texto) if cpf_dv_valido(_digitos(m.group(0)))]
    if cpfs:
        achado["cpf"] = len(cpfs)
    cnpjs = [m for m in _CNPJ.finditer(texto)
             if cnpj_dv_valido(_digitos(m.group(0))) and _digitos(m.group(0)) not in proprios]
    if cnpjs:
        achado["cnpj"] = len(cnpjs)
    rgs = _RG.findall(texto)
    if rgs:
        achado["rg"] = len(rgs)
    return achado or None


_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")
_HEX = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{40,}(?![0-9A-Fa-f])")
_TITULO_MD = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_JSON = re.compile(r"[{\[]\s*\"[^\"\n]{1,60}\"\s*:|^\s*\[\s*[{\[\"]", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+\S", re.MULTILINE)
#: Function words that tell the languages apart (a heuristic floor, not content): words shared with Portuguese
#: are left out of the foreign sets.
_STOP_PT = frozenset("de da do das dos em no na nos nas um uma uns para por com que não nao se os as o a e é ou mais mas como você voce está esta já ja também tambem muito quando onde ele ela eu meu minha seu sua nós".split())
_STOP_EN = frozenset("the and is are you your of to in that this it for with on as be at have not or but what was were will would can could which their there from by about".split())
_STOP_ES = frozenset("el los las y es son usted tu tus del al lo con una unos para por pero qué como está están tiene tienen muy también cuando donde yo mi sus nosotros hay".split())


def formato_suspeito(resposta: str, max_chars: int = 1200, max_bullets: int = 6) -> dict[str, Any] | None:
    """Encoded or structured output that carries data out past the shingle check: base64 / hex runs of 40+,
    code fences, markdown headings, JSON, more than ``max_bullets`` bullet lines, a reply over ``max_chars``
    or one mostly in another language. ``detalhe`` holds the shape codes, never a fragment."""
    if not resposta or not resposta.strip():
        return None
    achado: dict[str, Any] = {}
    if _B64.search(resposta) or _HEX.search(resposta):
        achado["codificado"] = True
    if "```" in resposta or "~~~" in resposta:
        achado["bloco_codigo"] = True
    if _TITULO_MD.search(resposta):
        achado["titulo"] = True
    if _JSON.search(resposta):
        achado["json"] = True
    if len(_BULLET.findall(resposta)) > max_bullets:
        achado["lista_longa"] = True
    if len(resposta) > max_chars:
        achado["longo"] = True
    palavras = re.findall(r"[a-zà-ú']+", resposta.casefold())
    if len(palavras) >= 12:
        pt = sum(1 for w in palavras if w in _STOP_PT)
        fora = max(sum(1 for w in palavras if w in _STOP_EN), sum(1 for w in palavras if w in _STOP_ES))
        if fora >= 4 and fora > pt:
            achado["outro_idioma"] = True
    return achado or None


def contar_padroes(textos: Iterable[str], padroes: Iterable[str]) -> int:
    """How many DISTINCT regexes of ``padroes`` match any of ``textos`` (broken patterns logged + skipped)."""
    alvos = [unicodedata.normalize("NFKC", t) for t in textos]
    n = 0
    for p in padroes:
        try:
            rx = re.compile(p, re.IGNORECASE)
        except re.error:
            logger.error("agents.conformidade.padrao_invalido")
            continue
        if any(rx.search(a) for a in alvos):
            n += 1
    return n


def padroes_proibidos(resposta: str, padroes: Iterable[str]) -> dict[str, Any] | None:
    """The generic matcher: the rule's ``parametros.padroes`` (DATA -- financing promises, guarantees,
    verification codes, payment requests, protected traits) found in the reply. Counts only."""
    n = contar_padroes([resposta], padroes)
    return {"padroes": n} if n else None


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
        alvo = unicodedata.normalize("NFKC", t)
        if any(rx.search(alvo) for rx in rxs):
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
    patterns are rule data (``parametros.padroes``) -- no code floor, a rule with none never fires. A claim is
    only ever counted (``escala_seguranca``); nothing in code branches on it to grant anything."""
    if regra is None or not regra.ativo:
        return None
    n = casar_padroes(mensagens_lead, list((regra.parametros or {}).get("padroes") or []))
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
    criterio_perguntado: Any | None = None
    registrou_perfil: bool = False
    criterios_preenchidos: Mapping[str, str] = field(default_factory=dict)
    registrados_no_turno: Iterable[str] = ()
    esgotou_loop: bool = False
    #: Org data (specs): hosts / contacts / CNPJ the agency owns.
    dominios_permitidos: Iterable[str] = ()
    contatos_permitidos: Iterable[str] = ()
    cnpjs_proprios: Iterable[str] = ()


def avaliar_resposta(e: EntradaConformidade) -> list[Violacao]:
    """Run every active reply detector; the policy of each hit is its rule's. The caller decides what
    ``bloquear`` means (suppress + one corrective re-run, then silence + hand-off)."""
    achados: list[tuple[str, dict[str, Any] | None]] = []

    def ativa(nome: str) -> RegraConfig | None:
        r = e.regras.get(nome)
        return r if r is not None and r.ativo else None

    if (r := ativa("vazamento_prompt")) is not None:
        achados.append(("vazamento_prompt", detectar_vazamento(
            e.resposta, canario_do_prompt=e.canario, impressao=e.impressao)))
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
    if e.resposta.strip():
        if ativa("link_nao_permitido") is not None:
            achados.append(("link_nao_permitido", link_nao_permitido(
                e.resposta, e.links_permitidos, e.dominios_permitidos)))
        if ativa("contato_nao_permitido") is not None:
            achados.append(("contato_nao_permitido", contato_nao_permitido(
                e.resposta, e.contatos_permitidos, e.mensagens_lead)))
        if ativa("pii_na_resposta") is not None:
            achados.append(("pii_na_resposta", pii_na_resposta(e.resposta, e.cnpjs_proprios)))
        if (r := ativa("formato_suspeito")) is not None:
            p = r.parametros or {}
            achados.append(("formato_suspeito", formato_suspeito(
                e.resposta, _inteiro(p.get("max_chars"), 1200), _inteiro(p.get("max_bullets"), 6))))
        if (r := ativa("padroes_proibidos")) is not None:
            achados.append(("padroes_proibidos", padroes_proibidos(
                e.resposta, (r.parametros or {}).get("padroes") or [])))
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
