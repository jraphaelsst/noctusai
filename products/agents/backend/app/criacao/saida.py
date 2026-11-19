"""The Diretor de Criacao's output contract: the per-option PUBLICATION block, and the deterministic checks of it.

The scripts/headlines themselves keep the grammar SW's ``propostas.py`` already parses (numbered ``(estrutura #N)``
headline lines; ``### Roteiro <n>: <titulo> (estrutura #N)`` sections; ``### Estruturas usadas``). Everything the
creation pipeline adds rides in ONE header per option, which the SW parser reads as a section end and ignores:

    ### Publicação <n>
    - Objetivo do post: <alcance|salvamentos|conversa|seguidores|autoridade|reflexão>
    - CTA: <the call to action, or "nenhum">
    - Justificativa do CTA: <why this count, type and position serve the objective>
    - Legenda: <caption>
    - Hashtags: #a #b #c #d #e                      (exactly five)
    - Primeiro comentário: <text>
    - Link:                                          (always empty: the owner pastes the post URL later)
    - Fontes: <url (verificada) | afirmação (não verificada) | nenhuma>
    - Voz: <amostras | cérebro: <nome> | sem amostras>

Every check here is PURE (text in, codes out); a failure is a CODE, never reply text. The checks are the mechanism the
fleet prompt is held to: they run against Fake-driven turns in tests and are the reference for the Studio eval cases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from noctusai_lib.primitives.accents import fold_accents

OBJETIVOS = ("alcance", "salvamentos", "conversa", "seguidores", "autoridade", "reflexão")
HASHTAGS_EXATAS = 5
#: share of spoken sentences under 8 words a humanized script must reach (a narrator's rhythm is short-heavy)
FRASES_CURTAS_MIN = 0.25
FRASE_CURTA_PALAVRAS = 8
#: how many leading words two consecutive blocks may NOT share (a repeated anchor reads as a template)
ABERTURA_PALAVRAS = 2

_PUB_RE = re.compile(r"^\s*###\s+publica[cç][aã]o\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
_CAMPO_RE = re.compile(r"^\s*[-*]\s*([^:\n]{2,40}):[ \t]*(.*)$")
_HASHTAG_RE = re.compile(r"(?<![\w#])#[^\W\d_][\w]*", re.UNICODE)
_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_ROTEIRO_RE = re.compile(r"^\s*###\s+roteiro\s+\d+\s*:.*$", re.IGNORECASE | re.MULTILINE)
_CABECALHO_RE = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_NAO_VERIFICADA = re.compile(r"n[aã]o\s+verificad", re.IGNORECASE)


def _sem_acento(t: str) -> str:
    return fold_accents(t).casefold()


@dataclass(frozen=True)
class Publicacao:
    numero: int
    campos: Mapping[str, str]  # keys folded: no accent, lower, spaces -> '_'
    #: folded names that appeared more than once in the block: a duplicated field is never silently resolved
    #: (first-wins or last-wins); the block is invalid (``checar_publicacao`` -> ``campo_duplicado``), same as SW's parser
    duplicados: tuple[str, ...] = ()

    def get(self, chave: str) -> str:
        return self.campos.get(chave, "")


def _chave(nome: str) -> str:
    return re.sub(r"\s+", "_", _sem_acento(nome).strip())


def extrair_publicacoes(texto: str) -> list[Publicacao]:
    """Every ``### Publicação <n>`` block, its ``- campo: valor`` bullets keyed by folded name."""
    marcas = list(_PUB_RE.finditer(texto or ""))
    out: list[Publicacao] = []
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
                campos[chave] = c.group(2).strip()
        out.append(Publicacao(int(m.group(1)), campos, tuple(duplicados)))
    return out


def corpos_de_roteiro(texto: str) -> list[str]:
    """The body of each ``### Roteiro n:`` section (until the next header that is not a post's own text header)."""
    linhas = (texto or "").split("\n")
    corpos: list[list[str]] = []
    atual: list[str] | None = None
    for ln in linhas:
        if _ROTEIRO_RE.match(ln):
            atual = []
            corpos.append(atual)
            continue
        if atual is not None and _CABECALHO_RE.match(ln) and _sem_acento(ln.strip("# ").strip()) not in ("texto na tela", "legenda"):
            atual = None
        if atual is not None:
            atual.append(ln)
    return ["\n".join(c).strip() for c in corpos]


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────────────

def hashtags_de(valor: str) -> list[str]:
    return _HASHTAG_RE.findall(valor or "")


def _frases(corpo: str) -> list[str]:
    limpo = re.sub(r"^\s*[-*•]\s+|\[[^\]]*\]|\([^)]*\)", " ", corpo, flags=re.MULTILINE)
    return [f.strip() for f in re.split(r"(?<=[.!?…])\s+|\n+", limpo) if len(f.split()) >= 1]


def _blocos(corpo: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", corpo) if b.strip()]


def _urls(valor: str) -> set[str]:
    return {u.rstrip(".,;") for u in _URL_RE.findall(valor or "")}


def urls_das_ferramentas(resultados: Iterable[tuple[str, Mapping[str, Any]]]) -> set[str]:
    """Every URL a tool of the turn returned (``pesquisas``/``virais``): the only citable sources."""
    achadas: set[str] = set()

    def varrer(o: Any) -> None:
        if isinstance(o, str):
            achadas.update(_urls(o))
        elif isinstance(o, Mapping):
            for v in o.values():
                varrer(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                varrer(v)

    for _nome, payload in resultados:
        varrer(payload)
    return achadas


# ── the checks (each returns the failure CODES; empty = pass) ─────────────────────────────────────────────

def checar_publicacao(pub: Publicacao) -> list[str]:
    p = f"pub{pub.numero}"
    falhas: list[str] = [f"{p}:campo_duplicado:{d}" for d in pub.duplicados]
    tags = hashtags_de(pub.get("hashtags"))
    if len(tags) != HASHTAGS_EXATAS or len({_sem_acento(t) for t in tags}) != HASHTAGS_EXATAS:
        falhas.append(f"{p}:hashtags:{len(tags)}")
    objetivo = _sem_acento(pub.get("objetivo_do_post"))
    if objetivo not in {_sem_acento(o) for o in OBJETIVOS}:
        falhas.append(f"{p}:objetivo_nao_declarado")
    cta = pub.get("cta")
    if not cta:
        falhas.append(f"{p}:cta_ausente")
    elif _sem_acento(cta).strip(" .") != "nenhum" and len(pub.get("justificativa_do_cta").split()) < 4:
        falhas.append(f"{p}:cta_sem_justificativa")
    for campo in ("legenda", "primeiro_comentario"):
        if not pub.get(campo):
            falhas.append(f"{p}:{campo}_ausente")
    if pub.get("link"):
        falhas.append(f"{p}:link_preenchido")
    if "voz" not in pub.campos:
        falhas.append(f"{p}:voz_nao_declarada")
    return falhas


def checar_cta_proibido(pubs: Sequence[Publicacao], proibidos: Sequence[str]) -> list[str]:
    """No CTA (nor caption) may carry a call the brand forbids (``proibidos``: lowercase terms/phrases read from tools)."""
    falhas = []
    for pub in pubs:
        alvo = _sem_acento(f"{pub.get('cta')} {pub.get('legenda')} {pub.get('primeiro_comentario')}")
        for termo in proibidos:
            if _sem_acento(termo) in alvo:
                falhas.append(f"pub{pub.numero}:cta_proibido:{_sem_acento(termo)}")
    return falhas


def checar_nomes(texto: str, nomes_proibidos: Sequence[str]) -> list[str]:
    """No client/tenant name from ``nomes_proibidos`` (e.g. another tenant's creator) may appear in the output."""
    t = _sem_acento(texto)
    return [f"nome:{i + 1}" for i, n in enumerate(nomes_proibidos) if _sem_acento(n) in t]


def checar_fontes(pubs: Sequence[Publicacao], citaveis: set[str]) -> list[str]:
    """A cited URL must have come back from a tool; a claim without one must be marked 'não verificada'."""
    falhas = []
    for pub in pubs:
        fontes = pub.get("fontes")
        if not fontes:
            falhas.append(f"pub{pub.numero}:fontes_ausente")
            continue
        for u in _urls(fontes):
            if u not in citaveis:
                falhas.append(f"pub{pub.numero}:fonte_inventada")
        if not _urls(fontes) and _sem_acento(fontes).strip(" .") != "nenhuma" and not _NAO_VERIFICADA.search(fontes):
            falhas.append(f"pub{pub.numero}:fonte_sem_url_nao_marcada")
    return falhas


def checar_humanizacao(texto: str) -> list[str]:
    """Rhythm of the spoken bodies: enough short sentences, no two consecutive blocks opening with the same words."""
    falhas = []
    for i, corpo in enumerate(corpos_de_roteiro(texto), start=1):
        frases = _frases(corpo)
        if frases:
            curtas = sum(1 for f in frases if len(f.split()) < FRASE_CURTA_PALAVRAS) / len(frases)
            if curtas < FRASES_CURTAS_MIN:
                falhas.append(f"roteiro{i}:frases_curtas:{curtas:.2f}")
        aberturas = [" ".join(_sem_acento(b).split()[:ABERTURA_PALAVRAS]) for b in _blocos(corpo)]
        for a, b in zip(aberturas, aberturas[1:]):
            if a and a == b:
                falhas.append(f"roteiro{i}:abertura_repetida:{a}")
    return falhas


def checar_voz(pubs: Sequence[Publicacao], *, voz_disponivel: bool) -> list[str]:
    """Never pretend to a voice: with no samples (tool empty AND no voice brain) the block says ``sem amostras``;
    with samples it must not."""
    falhas = []
    for pub in pubs:
        voz = _sem_acento(pub.get("voz"))
        if not voz:
            continue  # reported by checar_publicacao
        declarou_sem = "sem amostras" in voz
        if not voz_disponivel and not declarou_sem:
            falhas.append(f"pub{pub.numero}:voz_fingida")
        if voz_disponivel and declarou_sem:
            falhas.append(f"pub{pub.numero}:voz_ignorada")
    return falhas


def voz_disponivel(resultados: Iterable[tuple[str, Mapping[str, Any]]]) -> bool:
    """Voice samples exist when ``voz_amostras`` returned some, or a custom brain whose name signals voice/reference
    scripts came back non-empty from ``cerebros`` (the fallback the prompt follows)."""
    for nome, p in resultados:
        if nome == "voz_amostras" and p.get("amostras"):
            return True
        if nome == "cerebros":
            for c in p.get("cerebros") or []:
                alvo = _sem_acento(str(c.get("nome") or ""))
                if not c.get("vazio") and any(k in alvo for k in ("voz", "amostra", "referencia")):
                    return True
    return False


def avaliar_saida(
    texto: str, resultados: Sequence[tuple[str, Mapping[str, Any]]], *,
    cta_proibidos: Sequence[str] = (), nomes_proibidos: Sequence[str] = (),
) -> list[str]:
    """Every deterministic check of one reply against the turn's tool answers. Empty list == pass."""
    pubs = extrair_publicacoes(texto)
    if not pubs:
        return ["sem_publicacao"]
    falhas: list[str] = []
    for pub in pubs:
        falhas += checar_publicacao(pub)
    falhas += checar_cta_proibido(pubs, cta_proibidos)
    falhas += checar_nomes(texto, nomes_proibidos)
    falhas += checar_fontes(pubs, urls_das_ferramentas(resultados))
    falhas += checar_humanizacao(texto)
    falhas += checar_voz(pubs, voz_disponivel=voz_disponivel(resultados))
    return falhas


__all__ = [
    "HASHTAGS_EXATAS", "OBJETIVOS", "Publicacao", "avaliar_saida", "checar_cta_proibido", "checar_fontes",
    "checar_humanizacao", "checar_nomes", "checar_publicacao", "checar_voz", "corpos_de_roteiro",
    "extrair_publicacoes", "hashtags_de", "urls_das_ferramentas", "voz_disponivel",
]
