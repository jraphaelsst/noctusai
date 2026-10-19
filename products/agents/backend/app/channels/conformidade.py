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
* ``tentativa_extracao`` -- INPUT side, signal only: the lead's message tries to extract instructions.

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
    "EntradaConformidade",
    "GuardaVazamento",
    "canario",
    "avaliar_resposta",
    "casar_padroes",
    "detectar_vazamento",
    "garantir_impressao",
    "impressao_de",
    "sinal_extracao",
    "termina_com_pergunta",
    "texto_fonte_do_prompt",
    "violacoes_bloqueantes",
]

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


def garantir_impressao(
    store: ConformidadeStore, org_id: UUID, version_id: UUID, compiled: Any,
) -> Impressao:
    """The stored fingerprint of the version, computing + storing it when publish has not (an older
    version). Publish calls this too, so a turn normally only reads."""
    atual = store.obter_impressao(org_id, version_id)
    if atual is not None:
        return atual
    nova = impressao_de(version_id, texto_fonte_do_prompt(compiled))
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
    resposta: str, codigos_permitidos: Iterable[str], links_permitidos: Iterable[str],
    padrao_codigo: str | None,
) -> dict[str, Any] | None:
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
    ok_links = {l.rstrip(_TRAILING_URL).casefold() for l in links_permitidos}
    links = {u.rstrip(_TRAILING_URL).casefold() for u in _URL.findall(resposta)}
    if links - ok_links:
        achado["links"] = len(links - ok_links)
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


# ── input side + deterministic escalation (patterns are data, with a code-side floor for extraction) ──

#: A security heuristic, not prompt content: phrasings of an attempt to read the instructions. The rule's
#: ``parametros.padroes`` (regexes, data) extend it.
_EXTRACAO_BASE = (
    r"\b(ignore|ignora|esque[cç]a)\b.{0,40}\b(instru|regras|prompt|anterior)",
    r"\b(system|developer|sistema)\s*(prompt|message|mensagem)\b",
    r"\b(repita|mostre|revele|imprima|liste|copie|diga|print|show|reveal|repeat)\b.{0,50}\b(suas|seu|your|the)\b.{0,20}\b(instru[cç][oõ]es|prompt|regras internas|configura[cç][aã]o|instructions|rules)\b",
    r"\bcomo voc[eê] foi (programad|configurad|instru[ií]d)",
    r"\b(jailbreak|DAN mode|modo desenvolvedor|developer mode)\b",
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
            e.resposta, e.codigos_permitidos, e.links_permitidos, (r.parametros or {}).get("padrao_codigo"))))
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
