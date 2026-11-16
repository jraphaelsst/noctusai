"""Estruturas -- the model's derivation reply is untrusted data (estruturas-contract.md sections 8.8, 12.2; EST-5).

``validar_derivacao`` turns the raw reply into a typed :class:`EstruturaDerivada` or raises :class:`SaidaIaFalha`
with a stable ``codigo``. It NEVER trims, repairs or half-accepts: a reply that fails any rule yields NO Estrutura
(the caller records the coded failure). The server -- not the model -- decides:

* exact key sets at every level (an extra key is a refusal, the model may not smuggle fields; messages carry COUNTS,
  never a model-chosen key name);
* every text is NFKC-normalised first and refused if it carries a control or format character (Cc/Cf: newline,
  tab, zero-width, bidi), an angle-bracket look-alike, an ``@x`` mention, a ``#x`` hashtag, a phone-like digit run,
  or the source creator's handle / display name (passed to the VALIDATOR only, never to the model); every field is a
  single line;
* ``objetivos`` 1..2 from the closed vocabulary, no duplicates;
* 1..:data:`MAX_BLOCOS_IA` blocks; each ``tipo`` is matched (case/accent-insensitive) to the ACTIVE catalogue the caller
  passes in, anything else becomes ``Outro`` (contract 8.8) -- the id is attached by the caller from its own rows;
* every text passes ``saida_ia``'s guard (no URL, storage path, secret-like token, prompt-injection echo);
* it is a DERIVED structure, not a copy of the creator's text:
  - a field reproducing :data:`COPIA_JANELA_PALAVRAS` or more consecutive words of the source is refused
    (``saida_copia_literal``);
  - the headline formula must carry at least one ``[placeholder]``; with the placeholders stripped it must not share a
    :data:`HOOK_JANELA_PALAVRAS`-word run with the hook region (gancho, first caption line, first
    :data:`HOOK_TRANSCRICAO_PALAVRAS` transcript words), nor :data:`HOOK_SOBREPOSICAO_MAX` of its content words in order
    (longest common subsequence); block ``nome`` gets the same 5-word run test.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from noctusai_lib.primitives.accents import fold_accents

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation.estruturas_tipos_bloco import NOME_OUTRO
from app.modules.media_creation.prompts.biblioteca_classificador import _ANGULOS_RE
from app.modules.media_creation.saida_ia import (
    CAMPO_AUSENTE,
    CONTEUDO_PROIBIDO,
    FORMATO_INVALIDO,
    LIMITE_EXCEDIDO,
    SaidaIaFalha,
    _texto_seguro,
)

COPIA_LITERAL = "saida_copia_literal"
SEM_PLACEHOLDER = "saida_sem_placeholder"

MAX_OBJETIVOS_IA = 2
MAX_BLOCOS_IA = 20
MAX_INSTRUCAO_IA = 600
#: A run of this many consecutive words (accent-folded, lower-cased) shared with the source = a copy.
COPIA_JANELA_PALAVRAS = 8
#: ... and against the hook region a much shorter run is already the creator's phrasing.
HOOK_JANELA_PALAVRAS = 5
HOOK_TRANSCRICAO_PALAVRAS = 40
#: Share of the formula's content words found IN ORDER in a hook source that makes it a paraphrase of the hook.
HOOK_SOBREPOSICAO_MAX = 0.6
#: A "content word" is longer than this (articles, prepositions and "de/que/por" do not count).
PALAVRA_CONTEUDO_MIN = 3
#: Below this many content words the overlap ratio is meaningless and is not applied.
SOBREPOSICAO_MIN_PALAVRAS = 3

CHAVES_RAIZ = frozenset({"formula_headline", "objetivos", "blocos"})
CHAVES_BLOCO = frozenset({"tipo", "nome", "tempo", "instrucao"})

_CERCA = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL | re.IGNORECASE)
_PALAVRA = re.compile(r"\w+", re.UNICODE)
_PLACEHOLDER = re.compile(r"\[[^\[\]]{1,60}\]")
_MENCAO = re.compile(r"@\w")
_HASHTAG = re.compile(r"#\w")
_TELEFONE = re.compile(r"\+?\d(?:[\s().-]?\d){7,}")


@dataclass(frozen=True)
class BlocoDerivado:
    tipo_nome: str  # a catalogue name (or ``Outro``); the caller resolves the id from ITS rows
    nome: str
    tempo: Optional[str]
    instrucao: str


@dataclass(frozen=True)
class EstruturaDerivada:
    formula_headline: str
    objetivos: tuple[str, ...]
    blocos: tuple[BlocoDerivado, ...]


@dataclass(frozen=True)
class Origem:
    """What the validator may compare against (the model saw a MINIMISED version; the validator sees the real text so a
    leak of what was stripped is still caught). ``proibidos`` = the creator's handle and display name."""

    legenda: Optional[str] = None
    transcricao: Optional[str] = None
    gancho: Optional[str] = None
    blueprint: Optional[str] = None
    proibidos: tuple[str, ...] = ()

    def fontes(self) -> tuple[Optional[str], ...]:
        return (self.legenda, self.transcricao, self.gancho, self.blueprint)

    def hooks(self) -> tuple[str, ...]:
        primeira_linha = next((ln for ln in (self.legenda or "").splitlines() if ln.strip()), "")
        abertura = " ".join((self.transcricao or "").split()[:HOOK_TRANSCRICAO_PALAVRAS])
        return tuple(h for h in (self.gancho or "", primeira_linha, abertura) if h.strip())


def _chave_tipo(valor: str) -> str:
    return re.sub(r"\s+", " ", fold_accents(valor).casefold()).strip()


def _palavras(texto: str) -> list[str]:
    return _PALAVRA.findall(fold_accents(texto).casefold())


def _janelas(palavras: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(palavras[i : i + n]) for i in range(len(palavras) - n + 1)} if len(palavras) >= n else set()


def indice_de_copia(fontes: Iterable[Optional[str]], n: int = COPIA_JANELA_PALAVRAS) -> set[tuple[str, ...]]:
    """Every ``n``-word window of the source texts (built once per reply)."""
    janelas: set[tuple[str, ...]] = set()
    for fonte in fontes:
        if fonte:
            janelas |= _janelas(_palavras(fonte), n)
    return janelas


def _conteudo(palavras: list[str]) -> list[str]:
    return [p for p in palavras if len(p) > PALAVRA_CONTEUDO_MIN]


def _lcs(a: list[str], b: list[str]) -> int:
    """Length of the longest common subsequence (in-order overlap)."""
    if not a or not b:
        return 0
    anterior = [0] * (len(b) + 1)
    for x in a:
        atual = [0]
        for j, y in enumerate(b, start=1):
            atual.append(anterior[j - 1] + 1 if x == y else max(anterior[j], atual[j - 1]))
        anterior = atual
    return anterior[-1]


def _normalizar(valor: Any, campo: str) -> Any:
    """NFKC, then refuse any Cc/Cf character (newline and tab included: every field is a single line) and any
    angle-bracket look-alike. A non-string is returned untouched for the type check that follows."""
    if not isinstance(valor, str):
        return valor
    texto = unicodedata.normalize("NFKC", valor)
    if any(unicodedata.category(c) in ("Cc", "Cf") for c in texto):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém caractere de controle ou invisível", campo)
    if _ANGULOS_RE.search(texto):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém marcação", campo)
    return texto


def _termo_proibido(texto: str, proibidos: Iterable[str]) -> bool:
    dobrado = fold_accents(texto).casefold()
    for termo in proibidos:
        t = fold_accents(termo or "").casefold().lstrip("@").strip()
        if len(t) >= 3 and re.search(r"(?<!\w)@?" + re.escape(t) + r"(?!\w)", dobrado):
            return True
    return False


def _linha(valor: Any, campo: str, *, maximo: int, origem: Origem, copia: set[tuple[str, ...]],
           hook_janela: bool = False, obrigatorio: bool = True) -> str:
    valor = _normalizar(valor, campo)
    texto = _texto_seguro(valor, campo, maximo=maximo, obrigatorio=obrigatorio)
    if not texto:
        return texto
    if _MENCAO.search(texto) or _HASHTAG.search(texto):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém menção ou hashtag", campo)
    if _TELEFONE.search(texto):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém sequência de dígitos de contato", campo)
    if _termo_proibido(texto, origem.proibidos):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém identificação do criador", campo)
    palavras = _palavras(texto)
    if copia & _janelas(palavras, COPIA_JANELA_PALAVRAS):
        raise SaidaIaFalha(COPIA_LITERAL, "reproduz trecho literal do post de origem", campo)
    if hook_janela:
        sem_placeholders = _palavras(_PLACEHOLDER.sub(" ", texto))
        janelas = _janelas(sem_placeholders, HOOK_JANELA_PALAVRAS)
        for hook in origem.hooks():
            if janelas & _janelas(_palavras(hook), HOOK_JANELA_PALAVRAS):
                raise SaidaIaFalha(COPIA_LITERAL, "reproduz o gancho do post de origem", campo)
    return texto


def _formula(valor: Any, origem: Origem, copia: set[tuple[str, ...]]) -> str:
    texto = _linha(valor, "formula_headline", maximo=fmt.FORMULA_MAX, origem=origem, copia=copia, hook_janela=True)
    if not _PLACEHOLDER.search(texto):
        raise SaidaIaFalha(SEM_PLACEHOLDER, "a fórmula precisa de ao menos um [placeholder]", "formula_headline")
    conteudo = _conteudo(_palavras(_PLACEHOLDER.sub(" ", texto)))
    if len(conteudo) >= SOBREPOSICAO_MIN_PALAVRAS:
        for hook in origem.hooks():
            if _lcs(conteudo, _conteudo(_palavras(hook))) / len(conteudo) >= HOOK_SOBREPOSICAO_MAX:
                raise SaidaIaFalha(COPIA_LITERAL, "parafraseia o gancho do post de origem", "formula_headline")
    return texto


def _carregar(resposta: Any) -> dict[str, Any]:
    if isinstance(resposta, str):
        bruto = resposta.strip()
        cerca = _CERCA.match(bruto)
        if cerca:
            bruto = cerca.group(1).strip()
        try:
            resposta = json.loads(bruto)
        except ValueError as exc:
            raise SaidaIaFalha(FORMATO_INVALIDO, "a resposta da IA não é um JSON válido") from exc
    if not isinstance(resposta, dict):
        raise SaidaIaFalha(FORMATO_INVALIDO, "a resposta da IA não é um objeto JSON")
    return resposta


def _exigir_chaves(obj: Mapping[str, Any], esperadas: frozenset[str], onde: str) -> None:
    """Counts only: a model-chosen key name is never put in a message, a log line or a response."""
    extras = set(obj) - esperadas
    if extras:
        raise SaidaIaFalha(FORMATO_INVALIDO, f"{len(extras)} campo(s) não previsto(s)", onde)
    ausentes = esperadas - set(obj)
    if ausentes:
        raise SaidaIaFalha(CAMPO_AUSENTE, f"{len(ausentes)} campo(s) ausente(s)", onde)


def validar_derivacao(
    resposta: Any, *, tipos: Iterable[str], origem: Optional[Origem] = None, fontes: Iterable[Optional[str]] = (),
) -> EstruturaDerivada:
    """Validate one reply. ``tipos`` are the names of the ACTIVE catalogue (the closed set the prompt offered;
    ``Outro`` is always accepted); ``origem`` the real source text and the creator's identifiers to compare against
    (``fontes`` alone = the literal-copy guard only, kept for callers without a profile)."""
    if origem is None:
        origem = Origem(legenda=" ".join(f or "" for f in fontes) or None)
    dados = _carregar(resposta)
    _exigir_chaves(dados, CHAVES_RAIZ, "raiz")
    copia = indice_de_copia(origem.fontes())

    formula = _formula(dados["formula_headline"], origem, copia)

    brutos = dados["objetivos"]
    if not isinstance(brutos, list) or not 1 <= len(brutos) <= MAX_OBJETIVOS_IA:
        raise SaidaIaFalha(LIMITE_EXCEDIDO if isinstance(brutos, list) else FORMATO_INVALIDO,
                           f"objetivos deve ser uma lista de 1 a {MAX_OBJETIVOS_IA}", "objetivos")
    objetivos: list[str] = []
    for o in brutos:
        if not isinstance(o, str) or o not in fmt.OBJETIVOS:
            raise SaidaIaFalha(FORMATO_INVALIDO, "objetivo fora do vocabulário", "objetivos")
        if o in objetivos:
            raise SaidaIaFalha(FORMATO_INVALIDO, "objetivos repetidos", "objetivos")
        objetivos.append(o)

    lista = dados["blocos"]
    if not isinstance(lista, list):
        raise SaidaIaFalha(FORMATO_INVALIDO, "blocos deve ser uma lista", "blocos")
    if not 1 <= len(lista) <= MAX_BLOCOS_IA:
        raise SaidaIaFalha(LIMITE_EXCEDIDO if lista else CAMPO_AUSENTE, f"blocos deve ter de 1 a {MAX_BLOCOS_IA} itens", "blocos")

    catalogo = {_chave_tipo(nome): nome for nome in tipos}
    catalogo[_chave_tipo(NOME_OUTRO)] = NOME_OUTRO
    blocos: list[BlocoDerivado] = []
    for i, b in enumerate(lista, start=1):
        onde = f"blocos[{i}]"
        if not isinstance(b, dict):
            raise SaidaIaFalha(FORMATO_INVALIDO, "bloco deve ser um objeto", onde)
        _exigir_chaves(b, CHAVES_BLOCO, onde)
        tipo_bruto = _normalizar(b["tipo"], f"{onde}.tipo")
        if not isinstance(tipo_bruto, str) or not tipo_bruto.strip() or len(tipo_bruto) > 120:
            raise SaidaIaFalha(FORMATO_INVALIDO, "tipo deve ser texto", f"{onde}.tipo")
        tipo_nome = catalogo.get(_chave_tipo(tipo_bruto), NOME_OUTRO)  # outside the catalogue => Outro (contract 8.8)
        tempo_bruto = b["tempo"]
        tempo = None
        if tempo_bruto is not None and not (isinstance(tempo_bruto, str) and not tempo_bruto.strip()):
            tempo = _linha(tempo_bruto, f"{onde}.tempo", maximo=fmt.BLOCO_TEMPO_MAX, origem=origem, copia=copia)
        blocos.append(BlocoDerivado(
            tipo_nome=tipo_nome,
            nome=_linha(b["nome"], f"{onde}.nome", maximo=fmt.BLOCO_NOME_MAX, origem=origem, copia=copia, hook_janela=True),
            tempo=tempo,
            instrucao=_linha(b["instrucao"], f"{onde}.instrucao", maximo=MAX_INSTRUCAO_IA, origem=origem, copia=copia),
        ))
    return EstruturaDerivada(formula_headline=formula, objetivos=tuple(objetivos), blocos=tuple(blocos))


__all__ = [
    "BlocoDerivado", "COPIA_JANELA_PALAVRAS", "COPIA_LITERAL", "EstruturaDerivada", "HOOK_JANELA_PALAVRAS", "MAX_BLOCOS_IA",
    "Origem", "SEM_PLACEHOLDER", "indice_de_copia", "validar_derivacao",
]
