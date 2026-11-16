"""Estruturas -- the model's derivation reply is untrusted data (estruturas-contract.md sections 8.8, 12.2; EST-5).

``validar_derivacao`` turns the raw reply into a typed :class:`EstruturaDerivada` or raises :class:`SaidaIaFalha`
with a stable ``codigo``. It NEVER trims, repairs or half-accepts: a reply that fails any rule yields NO Estrutura
(the caller records the coded failure). The server -- not the model -- decides:

* exact key sets at every level (an extra key is a refusal, the model may not smuggle fields);
* ``objetivos`` 1..2 from the closed vocabulary, no duplicates;
* 1..:data:`MAX_BLOCOS_IA` blocks; each ``tipo`` is matched (case/accent-insensitive) to the ACTIVE catalogue the caller
  passes in, anything else becomes ``Outro`` (contract 8.8) -- the id is attached by the caller from its own rows;
* every text passes ``saida_ia``'s guard (no URL, storage path, secret-like token, prompt-injection echo) plus: no
  angle brackets / control characters, single line where a line is expected;
* it is a DERIVED structure, not a copy: a formula/name/instruction that reproduces a run of
  :data:`COPIA_JANELA_PALAVRAS` or more consecutive words of the source text is refused (``saida_copia_literal``) --
  the third creator's own sentences never become library content.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from noctusai_lib.primitives.accents import fold_accents

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation.estruturas_tipos_bloco import NOME_OUTRO
from app.modules.media_creation.saida_ia import (
    CAMPO_AUSENTE,
    CONTEUDO_PROIBIDO,
    FORMATO_INVALIDO,
    LIMITE_EXCEDIDO,
    SaidaIaFalha,
    _texto_seguro,
)

COPIA_LITERAL = "saida_copia_literal"

MAX_OBJETIVOS_IA = 2
MAX_BLOCOS_IA = 20
MAX_INSTRUCAO_IA = 600
#: A run of this many consecutive words (accent-folded, lower-cased) shared with the source = a copy.
COPIA_JANELA_PALAVRAS = 8

CHAVES_RAIZ = frozenset({"formula_headline", "objetivos", "blocos"})
CHAVES_BLOCO = frozenset({"tipo", "nome", "tempo", "instrucao"})

_CERCA = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL | re.IGNORECASE)
_MARCACAO = re.compile("[<>‹›〈〉⟨⟩〈〉＜＞]")
_CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f  ]")
_QUEBRA = re.compile(r"[\r\n\t]")  # a single-line field carries no line break or tab
_PALAVRA = re.compile(r"\w+", re.UNICODE)


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


def _chave_tipo(valor: str) -> str:
    return re.sub(r"\s+", " ", fold_accents(valor).casefold()).strip()


def _palavras(texto: str) -> list[str]:
    return _PALAVRA.findall(fold_accents(texto).casefold())


def _janelas(palavras: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(palavras[i : i + n]) for i in range(len(palavras) - n + 1)} if len(palavras) >= n else set()


def indice_de_copia(fontes: Iterable[Optional[str]]) -> set[tuple[str, ...]]:
    """Every :data:`COPIA_JANELA_PALAVRAS`-word window of the source texts (built once per reply)."""
    janelas: set[tuple[str, ...]] = set()
    for fonte in fontes:
        if fonte:
            janelas |= _janelas(_palavras(fonte), COPIA_JANELA_PALAVRAS)
    return janelas


def _linha(valor: Any, campo: str, *, maximo: int, obrigatorio: bool = True, copia: set[tuple[str, ...]]) -> str:
    texto = _texto_seguro(valor, campo, maximo=maximo, obrigatorio=obrigatorio)
    if _MARCACAO.search(texto) or _CONTROLE.search(texto) or _QUEBRA.search(texto):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém marcação ou caractere de controle", campo)
    if texto and copia & _janelas(_palavras(texto), COPIA_JANELA_PALAVRAS):
        raise SaidaIaFalha(COPIA_LITERAL, "reproduz trecho literal do post de origem", campo)
    return texto


def _texto_livre(valor: Any, campo: str, *, maximo: int, copia: set[tuple[str, ...]]) -> str:
    """Like :func:`_linha` but multi-line is allowed (an instruction); markup and control characters other than
    newline/tab are still refused."""
    texto = _texto_seguro(valor, campo, maximo=maximo)
    if _MARCACAO.search(texto) or _CONTROLE.search(texto.replace("\n", " ").replace("\t", " ")):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém marcação ou caractere de controle", campo)
    if copia & _janelas(_palavras(texto), COPIA_JANELA_PALAVRAS):
        raise SaidaIaFalha(COPIA_LITERAL, "reproduz trecho literal do post de origem", campo)
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
    extras = sorted(set(obj) - esperadas)
    if extras:
        raise SaidaIaFalha(FORMATO_INVALIDO, f"campos não previstos: {', '.join(str(e)[:40] for e in extras)}", onde)
    ausentes = sorted(esperadas - set(obj))
    if ausentes:
        raise SaidaIaFalha(CAMPO_AUSENTE, f"campo ausente: {', '.join(ausentes)}", onde)


def validar_derivacao(
    resposta: Any, *, tipos: Iterable[str], fontes: Iterable[Optional[str]] = (),
) -> EstruturaDerivada:
    """Validate one reply. ``tipos`` are the names of the ACTIVE catalogue (the closed set the prompt offered;
    ``Outro`` is always accepted), ``fontes`` the source texts the model saw (for the literal-copy guard)."""
    dados = _carregar(resposta)
    _exigir_chaves(dados, CHAVES_RAIZ, "raiz")
    copia = indice_de_copia(fontes)

    formula = _linha(dados["formula_headline"], "formula_headline", maximo=fmt.FORMULA_MAX, copia=copia)

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
        if not isinstance(b["tipo"], str) or not b["tipo"].strip() or len(b["tipo"]) > 120:
            raise SaidaIaFalha(FORMATO_INVALIDO, "tipo deve ser texto", f"{onde}.tipo")
        tipo_nome = catalogo.get(_chave_tipo(b["tipo"]), NOME_OUTRO)  # outside the catalogue => Outro (contract 8.8)
        tempo_bruto = b["tempo"]
        tempo = None
        if tempo_bruto is not None and not (isinstance(tempo_bruto, str) and not tempo_bruto.strip()):
            tempo = _linha(tempo_bruto, f"{onde}.tempo", maximo=fmt.BLOCO_TEMPO_MAX, copia=copia)
        blocos.append(BlocoDerivado(
            tipo_nome=tipo_nome,
            nome=_linha(b["nome"], f"{onde}.nome", maximo=fmt.BLOCO_NOME_MAX, copia=copia),
            tempo=tempo,
            instrucao=_texto_livre(b["instrucao"], f"{onde}.instrucao", maximo=MAX_INSTRUCAO_IA, copia=copia),
        ))
    return EstruturaDerivada(formula_headline=formula, objetivos=tuple(objetivos), blocos=tuple(blocos))


__all__ = [
    "BlocoDerivado", "COPIA_JANELA_PALAVRAS", "COPIA_LITERAL", "EstruturaDerivada", "MAX_BLOCOS_IA",
    "indice_de_copia", "validar_derivacao",
]
