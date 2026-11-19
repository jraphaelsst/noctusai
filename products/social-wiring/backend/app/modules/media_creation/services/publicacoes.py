"""The ``### Publicação <n>`` block of the Diretor de Criação's reply (``criacao-pipeline-contract.md`` 2.3 / 4).

PURE parser/validator, sibling of ``propostas.py`` (no DB, no writes). The agent product defines the block
(``products/agents/.../criacao/saida.py``: one header per option, ``- campo: valor`` bullets); SW is the only writer
and never trusts the model, so every rule the cards rely on is re-checked here::

    ### Publicação <n>
    - Objetivo do post: <alcance|salvamentos|conversa|seguidores|autoridade|reflexão>
    - CTA: <the call to action, or "nenhum">
    - Justificativa do CTA: <why>
    - Legenda: <caption>                       (required, <= 2200 chars: the card column's CHECK)
    - Hashtags: #a #b #c #d #e                 (EXACTLY five, distinct: the contract; the column allows <= 5)
    - Primeiro comentário: <text>              (<= 2200)
    - Link:                                    (NEVER read: the owner pastes the post URL by hand, contract section 10.2)
    - Fontes: <url (verificada) | afirmação (não verificada) | nenhuma>
    - Voz: <...>                               (the agent's own declaration; not persisted)

A field that appears twice in one block makes the block invalid (``campo_duplicado``): no first-wins / last-wins pick.

A block that fails any rule is dropped whole and COUNTED (``invalidas`` -> the ``publicacao_invalida`` event); a text
with no block at all is not invalid (a legacy-path reply carries none). :func:`vincular_publicacoes` binds each valid
block to the option it belongs to: the block's ``n`` is the option's own number in the reply (``PropostaValidada.numero``;
a bullet headline, which has none, is addressed by its ``ordem``). A ``n`` that matches no option, or more than one (a
numbered headline and a ``### Roteiro n`` sharing it), attaches to nothing and is counted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from noctusai_lib.primitives.accents import fold_accents

HASHTAGS_EXATAS = 5
MAX_LEGENDA = 2200
MAX_COMENTARIO = 2200

#: ``cs_posts.cta_objetivo`` (contract M-A) minus ``nenhum``, which is derived from the CTA itself.
OBJETIVOS = ("alcance", "salvamentos", "conversa", "seguidores", "autoridade", "reflexao")
CTA_NENHUM = "nenhum"

_PUB_RE = re.compile(r"^\s*###\s+publica[cç][aã]o\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
_CAMPO_RE = re.compile(r"^\s*[-*]\s*([^:\n]{2,40}):[ \t]*(.*)$")
_CABECALHO_RE = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_HASHTAG_RE = re.compile(r"(?<![\w#])#[^\W\d_][\w]*", re.UNICODE)
_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_MARCA_RE = re.compile(r"\(\s*(n[aã]o\s+)?verificad[ao]\s*\)\s*$", re.IGNORECASE)


def _sem_acento(t: str) -> str:
    return fold_accents(t).casefold()


def _chave(nome: str) -> str:
    return re.sub(r"\s+", "_", _sem_acento(nome).strip())


@dataclass(frozen=True)
class PublicacaoValidada:
    numero: int
    legenda: str
    hashtags: tuple[str, ...]  # exactly HASHTAGS_EXATAS, with the leading ``#``
    primeiro_comentario: Optional[str]
    cta: Optional[str]  # None when the post carries no CTA ("nenhum")
    cta_objetivo: str  # OBJETIVOS | "nenhum"
    cta_justificativa: Optional[str]
    fontes: tuple[dict[str, Any], ...]  # {"url"|"afirmacao": str, "verificada": bool}


@dataclass(frozen=True)
class ResultadoPublicacoes:
    por_numero: dict[int, PublicacaoValidada]
    invalidas: int


@dataclass(frozen=True)
class Vinculo:
    por_ordem: dict[int, PublicacaoValidada]  # proposta.ordem -> its publicação
    invalidas: int


def _blocos(texto: str) -> list[tuple[int, dict[str, str], tuple[str, ...]]]:
    marcas = list(_PUB_RE.finditer(texto or ""))
    out: list[tuple[int, dict[str, str], tuple[str, ...]]] = []
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        resto = texto[m.end():fim]
        proximo = _CABECALHO_RE.search(resto)
        corpo = resto[: proximo.start()] if proximo else resto
        campos: dict[str, str] = {}
        duplicados: list[str] = []
        for linha in corpo.splitlines():
            c = _CAMPO_RE.match(linha)
            if c:
                chave = _chave(c.group(1))
                if chave in campos and chave not in duplicados:
                    duplicados.append(chave)
                campos.setdefault(chave, c.group(2).strip())
        out.append((int(m.group(1)), campos, tuple(duplicados)))
    return out


def _fontes(valor: str) -> tuple[dict[str, Any], ...]:
    if not valor or _sem_acento(valor).strip(" .") == "nenhuma":
        return ()
    itens: list[dict[str, Any]] = []
    for parte in (p.strip() for p in valor.split("|")):
        if not parte:
            continue
        marca = _MARCA_RE.search(parte)
        verificada = bool(marca) and not marca.group(1)
        sem_marca = _MARCA_RE.sub("", parte).strip()
        url = _URL_RE.search(sem_marca)
        if url:
            itens.append({"url": url.group(0).rstrip(".,;"), "verificada": verificada})
        elif sem_marca:
            itens.append({"afirmacao": sem_marca, "verificada": False})
    return tuple(itens)


def _validar(numero: int, campos: dict[str, str]) -> Optional[PublicacaoValidada]:
    legenda = campos.get("legenda", "").strip()
    if not legenda or len(legenda) > MAX_LEGENDA:
        return None
    tags = _HASHTAG_RE.findall(campos.get("hashtags", ""))
    if len(tags) != HASHTAGS_EXATAS or len({_sem_acento(t) for t in tags}) != HASHTAGS_EXATAS:
        return None
    objetivo = _sem_acento(campos.get("objetivo_do_post", "")).strip(" .")
    if objetivo not in OBJETIVOS:
        return None
    comentario = campos.get("primeiro_comentario", "").strip() or None
    if comentario is not None and len(comentario) > MAX_COMENTARIO:
        return None
    cta = campos.get("cta", "").strip()
    if not cta:
        return None
    justificativa = campos.get("justificativa_do_cta", "").strip() or None
    if _sem_acento(cta).strip(" .") == CTA_NENHUM:
        cta, cta_objetivo = None, CTA_NENHUM
    else:
        if justificativa is None:
            return None
        cta_objetivo = objetivo
    return PublicacaoValidada(
        numero=numero, legenda=legenda, hashtags=tuple(tags), primeiro_comentario=comentario, cta=cta,
        cta_objetivo=cta_objetivo, cta_justificativa=justificativa, fontes=_fontes(campos.get("fontes", "")),
    )


def extrair_publicacoes(texto: str) -> ResultadoPublicacoes:
    """Every valid ``### Publicação <n>`` block keyed by ``n``; the rest are counted (a repeated ``n`` keeps the first)."""
    por_numero: dict[int, PublicacaoValidada] = {}
    invalidas = 0
    for numero, campos, duplicados in _blocos(texto):
        # a field written twice is never silently resolved: the block is invalid (reason ``campo_duplicado``, as the agent side)
        pub = None if duplicados else _validar(numero, campos)
        if pub is None or numero in por_numero:
            invalidas += 1
            continue
        por_numero[numero] = pub
    return ResultadoPublicacoes(por_numero=por_numero, invalidas=invalidas)


def vincular_publicacoes(propostas: Sequence[Any], res: ResultadoPublicacoes) -> Vinculo:
    """Bind each valid block to the option whose number it carries (see the module docstring)."""
    por_chave: dict[int, list[Any]] = {}
    for p in propostas:
        chave = getattr(p, "numero", None) or p.ordem
        por_chave.setdefault(int(chave), []).append(p)
    por_ordem: dict[int, PublicacaoValidada] = {}
    invalidas = 0
    for numero, pub in res.por_numero.items():
        alvos = por_chave.get(numero, [])
        if len(alvos) != 1:
            invalidas += 1
            continue
        por_ordem[alvos[0].ordem] = pub
    return Vinculo(por_ordem=por_ordem, invalidas=invalidas)


__all__ = [
    "CTA_NENHUM", "HASHTAGS_EXATAS", "OBJETIVOS", "PublicacaoValidada", "ResultadoPublicacoes", "Vinculo",
    "extrair_publicacoes", "vincular_publicacoes",
]
