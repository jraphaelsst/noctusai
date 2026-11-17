"""Server-side validation of the chat agent's headline proposals (estruturas-contract.md section 8.5).

PURE parser/validator: no DB access, no writes. UNI-1a persists ``cs_chat_propostas`` +
``cs_chat_proposta_estruturas`` + the events in the same pass that saves the assistant message.
This is the Python port of the FE ``components/geracao/chat/citacoes.ts :: extrairHeadlines`` -- the single
derivation (the FE parser is retired by FE-2) -- extended with the unified-chat citation grammar
``(estrutura #N)`` / ``(estrutura #N + #M [+ #K])``.

What it enforces (the model is never trusted):
- a code outside ``codigos_permitidos`` is dropped (event ``citacao_rejeitada``);
- a code whose Estrutura ``formato`` differs from the principal's (the first valid code) is dropped
  (``formato_misturado``); at most 3 codes per proposta (extras count as ``citacao_rejeitada``);
- a headline left with NO valid code is not a proposta (an uncited numbered line counts as ``citacao_rejeitada``);
- a headline that still matches ``\\[[^\\]]+\\]`` is dropped (``placeholder_remanescente``);
- at most 10 propostas; the ``### Estruturas usadas`` attribution list is never read as headlines.

Roteiro-first (contract 16.3 / 16.4): the same pass also reads COMPLETE scripts. A section headed EXACTLY
``### Roteiro <n>: <título curto> (estrutura #N [+ #M [+ #K]])`` is one roteiro option; its body runs until the next
markdown header -- except a ``post`` script's own ``### Texto na tela`` / ``### Legenda`` -- and a trailing horizontal
rule (``---``) is not part of it. Citations are validated exactly like a headline's; the body is validated by the
EST-FMT grammar of the principal Estrutura's formato (``saida_ia.validar_roteiro_formato``; ``reels`` by
``saida_ia.validar_roteiro``, its only grammar) -- a refusal, a title outside 1..120 chars and every option past the 5th
drop the option and count ``roteiro_invalido``; a leftover ``[...]`` counts ``placeholder_remanescente``. Lines inside a
script are never read as headlines. Both kinds share one ``ordem`` sequence, by appearance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from noctusai_lib.primitives.accents import fold_accents

from app.modules.media_creation.saida_ia import SaidaIaFalha, validar_roteiro, validar_roteiro_formato

MAX_PROPOSTAS = 10
MAX_ROTEIROS = 5
MAX_TITULO = 120
MAX_ESTRUTURAS_POR_PROPOSTA = 3
_MIN_CHARS = 5

_ITEM_RE = re.compile(r"^\s*(?:(\d+)[.)]|[-*•])\s+(.*\S)\s*$")
_CITACAO_RE = re.compile(r"\(\s*estrutura\s*#\s*(\d+(?:\s*\+\s*#\s*\d+)*)\s*\)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
_TAG_FINAL_RE = re.compile(r"\s*\(\s*([^()]{3,40}?)\s*\)\s*[.!?]?\s*$")
_TITULO_RE = re.compile(r"^\s*#{1,6}\s*(.*?)\s*#*\s*$")
_ROTEIRO_RE = re.compile(r"^\s*###\s+roteiro\s+\d+\s*:\s*(.*\S)\s*$", re.IGNORECASE)
_CABECALHO_RE = re.compile(r"^\s*#{1,6}\s+(.*?)\s*#*\s*$")  # a real markdown header (``#tag`` is not one)
_REGRA_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
#: the headers a ``post`` script carries INSIDE its body (``prompts/roteiro_formatos.py``): never a section end
_TITULOS_DO_CORPO = frozenset({"texto na tela", "legenda"})

#: The attention-trigger names the agent appends in parentheses (BE prompt ``chat_headline.py`` + methodology).
GATILHOS_TAG = (
    "Popularidade/Autoridade", "Recompensa", "Mistério", "Reconhecimento", "Crença", "Disrupção", "Autoridade",
    "Popularidade",
)


def _sem_acento(t: str) -> str:
    return fold_accents(t).lower()


_GATILHOS_NORM = {_sem_acento(g): g for g in GATILHOS_TAG}


@dataclass(frozen=True)
class EstruturaCitavel:
    id: UUID
    codigo: str  # the N shown to the model as "estrutura #N"
    formato: str


@dataclass(frozen=True)
class PropostaValidada:
    ordem: int
    headline: str  # the proposta's text: the headline, or the WHOLE script when ``tipo == "roteiro"``
    gatilho: str | None
    estrutura_ids: tuple[UUID, ...]  # [0] = principal, len 1..3
    tipo: str = "headline"  # "headline" | "roteiro"
    titulo: str | None = None  # roteiro only: the section's short title (1..120)
    formato: str | None = None  # roteiro only: the principal Estrutura's formato

    @property
    def texto(self) -> str:
        return self.headline


@dataclass(frozen=True)
class ResultadoPropostas:
    propostas: tuple[PropostaValidada, ...]
    eventos: tuple[dict, ...]  # {"tipo": <one of EVENTOS>, "contagem": int}


#: The rejection counters the parser reports (each a ``cs_fluxo_eventos.tipo``).
EVENTOS = ("citacao_rejeitada", "formato_misturado", "placeholder_remanescente", "roteiro_invalido")


def _tag_final(texto: str) -> tuple[str, str] | None:
    m = _TAG_FINAL_RE.search(texto)
    if not m:
        return None
    nome = _GATILHOS_NORM.get(_sem_acento(m.group(1)))
    return (texto[: m.start()].strip(), nome) if nome else None


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\*\*|__", "", texto)).strip().strip('"“”').strip()


class _Contador:
    def __init__(self) -> None:
        self.n = dict.fromkeys(EVENTOS, 0)

    def __call__(self, tipo: str, quantos: int = 1) -> None:
        self.n[tipo] += quantos


def _citacoes_validas(
    codigos: list[str], codigos_permitidos: Mapping[str, EstruturaCitavel], conta: _Contador
) -> list[EstruturaCitavel]:
    """Known, same formato as the principal (the first valid code), at most 3 -- the rest counted."""
    validos: list[EstruturaCitavel] = []
    for cod in dict.fromkeys(codigos):
        est = codigos_permitidos.get(cod)
        if est is None:
            conta("citacao_rejeitada")
        elif validos and est.formato != validos[0].formato:
            conta("formato_misturado")
        elif len(validos) >= MAX_ESTRUTURAS_POR_PROPOSTA:
            conta("citacao_rejeitada")
        else:
            validos.append(est)
    return validos


def _codigos(citacoes: list[re.Match[str]]) -> list[str]:
    out: list[str] = []
    for c in citacoes:
        out += re.findall(r"\d+", c.group(1))
    return out


def _corpo_valido(formato: str, corpo: str) -> bool:
    """The EST-FMT grammar of ``formato`` (section 8.7). ``reels`` has no beat grammar beyond ``validar_roteiro``."""
    try:
        if formato == "reels":
            validar_roteiro(corpo)
        else:
            validar_roteiro_formato(formato, corpo)
    except SaidaIaFalha:
        return False
    return True


def _secoes(texto: str) -> list[tuple[str, str | list[str]]]:
    """Split the answer into ``("linha", line)`` items (outside scripts) and ``("roteiro", [header, *body])`` items."""
    itens: list[tuple[str, str | list[str]]] = []
    atual: list[str] | None = None
    for linha in (texto or "").split("\n"):
        if _ROTEIRO_RE.match(linha):
            atual = [linha]
            itens.append(("roteiro", atual))
            continue
        titulo = _CABECALHO_RE.match(linha)
        if atual is not None and titulo and _sem_acento(titulo.group(1)) not in _TITULOS_DO_CORPO:
            atual = None  # any other header ends the script
        if atual is not None:
            atual.append(linha)
        else:
            itens.append(("linha", linha))
    return itens


def _corpo(linhas: list[str]) -> str:
    fim = len(linhas)
    while fim and (not linhas[fim - 1].strip() or _REGRA_RE.match(linhas[fim - 1])):
        fim -= 1
    return "\n".join(linhas[:fim]).strip()


def extrair_propostas(texto: str, codigos_permitidos: Mapping[str, EstruturaCitavel]) -> ResultadoPropostas:
    conta = _Contador()
    propostas: list[PropostaValidada] = []
    vistas: set[tuple[str, str]] = set()
    headlines = roteiros = 0
    ignorar_secao = False

    def aceitar(chave: tuple[str, str], **campos: object) -> None:
        if chave in vistas:
            return
        vistas.add(chave)
        propostas.append(PropostaValidada(ordem=len(propostas) + 1, **campos))  # type: ignore[arg-type]

    for tipo, item in _secoes(texto):
        if tipo == "roteiro":
            assert isinstance(item, list)
            roteiros += 1
            if roteiros > MAX_ROTEIROS:
                conta("roteiro_invalido")  # a 6th+ option is dropped -- and counted, never silently
                continue
            cabecalho = _ROTEIRO_RE.match(item[0])
            assert cabecalho is not None
            resto = cabecalho.group(1)
            citacoes = list(_CITACAO_RE.finditer(resto))
            if not citacoes:
                conta("citacao_rejeitada")
                continue
            titulo = _limpar(_CITACAO_RE.sub("", resto))
            validos = _citacoes_validas(_codigos(citacoes), codigos_permitidos, conta)
            if not validos:
                continue
            corpo = _corpo(item[1:])
            if _PLACEHOLDER_RE.search(corpo):
                conta("placeholder_remanescente")
                continue
            formato = validos[0].formato
            if not 1 <= len(titulo) <= MAX_TITULO or not _corpo_valido(formato, corpo):
                conta("roteiro_invalido")
                continue
            aceitar(("roteiro", corpo.casefold()), headline=corpo, gatilho=None,
                    estrutura_ids=tuple(e.id for e in validos), tipo="roteiro", titulo=titulo, formato=formato)
            continue

        linha = item
        assert isinstance(linha, str)
        titulo_md = _TITULO_RE.match(linha)
        if titulo_md:
            ignorar_secao = _sem_acento(titulo_md.group(1)).startswith("estruturas usadas")
            continue
        m = _ITEM_RE.match(linha)
        if not m or ignorar_secao:
            continue
        numerado, corpo_linha = m.group(1) is not None, m.group(2)
        citacoes = list(_CITACAO_RE.finditer(corpo_linha))
        if not citacoes:
            # an uncited NUMBERED line that reads like a headline is a citation the model forgot; bullets are prose
            limpa = _limpar(corpo_linha)
            if numerado and len(limpa) >= _MIN_CHARS and not limpa.endswith("?") and headlines < MAX_PROPOSTAS:
                conta("citacao_rejeitada")
            continue
        if headlines >= MAX_PROPOSTAS:
            continue
        limpa = _limpar(_CITACAO_RE.sub("", corpo_linha))
        gatilho = None
        tag = _tag_final(limpa)
        if tag and tag[0]:
            limpa, gatilho = _limpar(tag[0]), tag[1]
        if len(limpa) < _MIN_CHARS:
            continue
        validos = _citacoes_validas(_codigos(citacoes), codigos_permitidos, conta)
        if not validos:
            continue
        if _PLACEHOLDER_RE.search(limpa):
            conta("placeholder_remanescente")
            continue
        antes = len(propostas)
        aceitar(("headline", limpa.casefold()), headline=limpa, gatilho=gatilho,
                estrutura_ids=tuple(e.id for e in validos))
        headlines += len(propostas) - antes

    eventos = tuple({"tipo": tipo, "contagem": n} for tipo, n in conta.n.items() if n)
    return ResultadoPropostas(propostas=tuple(propostas), eventos=eventos)


__all__ = [
    "EVENTOS", "EstruturaCitavel", "GATILHOS_TAG", "MAX_ROTEIROS", "PropostaValidada", "ResultadoPropostas",
    "extrair_propostas",
]
