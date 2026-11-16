"""CoreStudio — AI output is untrusted (CORESTUDIO-STRUCTURE.md §4, slice S6).

Every roteiro / legenda the model returns passes through here before it can move toward publish:
a schema, length caps, and a refusal of URLs, storage paths, secret-like tokens and prompt-injection
echoes. Rejected output is a :class:`SaidaIaFalha` carrying a stable ``codigo`` and a reason; it is
NEVER silently trimmed or cleaned.

The roteiro schema is a registry (``CAMPOS_ROTEIRO``): the text body (``conteudo``) is the only
field today. Fields that will drive video editing (hook, beats with spoken text, on-screen text,
layout, b-roll cue, motion cue, emphasis) are added by registering a :class:`CampoRoteiro`; the
generic loop (type, cap, text-safety) applies to each without touching :func:`validar_roteiro`.

Caption limits per network. ``instagram``: 2200 chars, 30 hashtags (Instagram's documented caption
limits, long-standing; not re-verified against a live source on 2026-11-13). ``tiktok`` 2200 and
``youtube_shorts`` 5000 (description) are UNVERIFIED and listed only as conservative placeholders.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# --- coded failures ---------------------------------------------------------------------------
FORMATO_INVALIDO = "saida_formato_invalido"
CAMPO_AUSENTE = "saida_campo_ausente"
LIMITE_EXCEDIDO = "saida_limite_excedido"
CONTEUDO_PROIBIDO = "saida_conteudo_proibido"


class SaidaIaFalha(ValueError):
    """AI output rejected. ``codigo`` is stable, ``campo`` names where, ``motivo`` says why."""

    def __init__(self, codigo: str, motivo: str, campo: Optional[str] = None):
        super().__init__(f"{codigo}: {motivo}" + (f" ({campo})" if campo else ""))
        self.codigo = codigo
        self.motivo = motivo
        self.campo = campo

    def como_falha(self) -> dict[str, Any]:
        return {"status": "falha", "codigo": self.codigo, "motivo": self.motivo, "campo": self.campo}


# --- limits -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class LimitesRede:
    legenda: int
    hashtags: int
    primeiro_comentario: int
    verificado: bool


LIMITES_REDE: dict[str, LimitesRede] = {
    "instagram": LimitesRede(2200, 30, 2200, verificado=True),
    "tiktok": LimitesRede(2200, 30, 2200, verificado=False),  # UNVERIFIED placeholder
    "youtube_shorts": LimitesRede(5000, 15, 2200, verificado=False),  # UNVERIFIED placeholder
}
REDE_PADRAO = "instagram"
MAX_ROTEIRO = 12_000
MAX_HASHTAG_CHARS = 100

# --- unsafe-content detection -----------------------------------------------------------------
_PADROES: list[tuple[str, re.Pattern[str]]] = [
    ("url", re.compile(r"(?:https?|ftp|file|data|javascript)\s*:|\bwww\.|"
                       r"\b[a-z0-9-]+\.(?:com|net|org|io|app|ly|gl|me|co|dev|ai|xyz|link|site)(?:\.br)?\b|"
                       r"\b[a-z0-9-]+\.com\.br\b", re.I)),
    ("caminho de storage", re.compile(
        r"\b(?:s3|gs|supabase)://|/storage/v1|\bstorage/[\w.-]+/|\bbucket[\w-]*/|"
        r"(?<![\w])(?:/(?:Users|home|etc|var|tmp|opt|mnt)/|[A-Za-z]:\\|\.\./)", re.I)),
    ("token parecido com segredo", re.compile(
        r"\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}|"
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}|"
        r"\bBearer\s+[A-Za-z0-9._-]{16,}|(?:api[_-]?key|secret|token|password|senha)\s*[:=]\s*\S{6,}|"
        r"\b[A-Fa-f0-9]{40,}\b|\b[A-Za-z0-9+/]{40,}={0,2}(?![\w/])", re.I)),
    ("eco de injeção de prompt", re.compile(
        r"ignor[ea]\w*\s+(?:todas?\s+)?(?:as\s+)?(?:instru|regras|anteriores|previous|prior)|"
        r"ignore\s+(?:all\s+|the\s+)?(?:previous|prior|above)|disregard\s+(?:the\s+)?(?:previous|above|instructions)|"
        r"desconsidere\s+(?:as\s+)?(?:instru|regras)|\bsystem\s*prompt\b|prompt\s+do\s+sistema|"
        r"</?dados_nao_confiaveis|\bvocê\s+agora\s+é\b|\byou\s+are\s+now\b|\bnew\s+instructions\b|"
        r"<\|?(?:im_start|im_end|system)\|?>", re.I)),
]


def detectar_proibido(texto: str) -> Optional[str]:
    """Name of the first forbidden class found in ``texto`` (url, storage path, secret, injection)."""
    for nome, rx in _PADROES:
        if rx.search(texto):
            return nome
    return None


def _texto_seguro(valor: Any, campo: str, *, maximo: int, obrigatorio: bool = True) -> str:
    if not isinstance(valor, str):
        if valor is None and not obrigatorio:
            return ""
        raise SaidaIaFalha(FORMATO_INVALIDO if valor is not None else CAMPO_AUSENTE,
                           "o campo deve ser texto" if valor is not None else "campo ausente", campo)
    texto = valor.strip()
    if obrigatorio and not texto:
        raise SaidaIaFalha(CAMPO_AUSENTE, "campo vazio", campo)
    if len(texto) > maximo:
        raise SaidaIaFalha(LIMITE_EXCEDIDO, f"{len(texto)} caracteres; o máximo é {maximo}", campo)
    achado = detectar_proibido(texto)
    if achado:
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, f"contém {achado}", campo)
    return texto


# --- roteiro (extensible schema) --------------------------------------------------------------
@dataclass(frozen=True)
class CampoRoteiro:
    """One roteiro field. ``validar(valor, campo)`` returns the validated value or raises
    :class:`SaidaIaFalha`. Add editing-driving fields (hook, beats, on-screen text, layout,
    b-roll/motion cue, emphasis) by registering one of these; no other code changes."""

    nome: str
    validar: Callable[[Any, str], Any]
    obrigatorio: bool = True


def _campo_texto(maximo: int, *, obrigatorio: bool = True) -> Callable[[Any, str], Any]:
    return lambda valor, campo: _texto_seguro(valor, campo, maximo=maximo, obrigatorio=obrigatorio)


CAMPOS_ROTEIRO: dict[str, CampoRoteiro] = {
    "conteudo": CampoRoteiro("conteudo", _campo_texto(MAX_ROTEIRO)),
}


def validar_roteiro(saida: Any, *, campos: Optional[dict[str, CampoRoteiro]] = None) -> dict[str, Any]:
    """Validate a roteiro. ``saida`` is the body text (wrapped as ``{"conteudo": ...}``) or a dict
    of registered fields. Unknown fields are refused (the model may not smuggle extra data)."""
    registro = CAMPOS_ROTEIRO if campos is None else campos
    if isinstance(saida, str):
        saida = {"conteudo": saida}
    if not isinstance(saida, dict):
        raise SaidaIaFalha(FORMATO_INVALIDO, "o roteiro deve ser texto ou objeto")
    extras = sorted(set(saida) - set(registro))
    if extras:
        raise SaidaIaFalha(FORMATO_INVALIDO, f"campos não previstos: {', '.join(extras)}", extras[0])
    validado: dict[str, Any] = {}
    for nome, campo in registro.items():
        if nome not in saida or saida[nome] is None:
            if campo.obrigatorio:
                raise SaidaIaFalha(CAMPO_AUSENTE, "campo ausente", nome)
            continue
        validado[nome] = campo.validar(saida[nome], nome)
    return validado


# --- legenda ----------------------------------------------------------------------------------
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_CHAVES_LEGENDA = {"legenda", "hashtags", "primeiro_comentario"}


def validar_legenda(saida: Any, *, rede: str = REDE_PADRAO) -> dict[str, Any]:
    """Validate a caption reply (raw JSON string or already-parsed dict) for ``rede``.
    Returns ``{legenda, hashtags[], primeiro_comentario}`` or raises :class:`SaidaIaFalha`.
    Nothing is truncated: an over-limit field, an excess of hashtags or a duplicate-free list
    that is too long is a failure."""
    limites = LIMITES_REDE.get(rede)
    if limites is None:
        raise SaidaIaFalha(FORMATO_INVALIDO, f"rede desconhecida: {rede}")
    if isinstance(saida, str):
        try:
            saida = json.loads(_FENCE.sub("", saida.strip()).strip())
        except ValueError as exc:
            raise SaidaIaFalha(FORMATO_INVALIDO, "a resposta da IA não é um JSON válido") from exc
    if not isinstance(saida, dict):
        raise SaidaIaFalha(FORMATO_INVALIDO, "a resposta da IA não é um objeto JSON")
    extras = sorted(set(saida) - _CHAVES_LEGENDA)
    if extras:
        raise SaidaIaFalha(FORMATO_INVALIDO, f"campos não previstos: {', '.join(extras)}", extras[0])
    legenda = _texto_seguro(saida.get("legenda"), "legenda", maximo=limites.legenda)
    comentario = _texto_seguro(
        saida.get("primeiro_comentario"), "primeiro_comentario",
        maximo=limites.primeiro_comentario, obrigatorio=False,
    )
    brutas = saida.get("hashtags", [])
    if brutas is None:
        brutas = []
    if not isinstance(brutas, list):
        raise SaidaIaFalha(FORMATO_INVALIDO, "hashtags deve ser uma lista", "hashtags")
    tags: list[str] = []
    for item in brutas:
        if not isinstance(item, str):
            raise SaidaIaFalha(FORMATO_INVALIDO, "hashtag deve ser texto", "hashtags")
        tag = re.sub(r"\s+", "", item).lstrip("#")
        if not tag:
            continue
        if not re.fullmatch(r"\w+", tag):
            raise SaidaIaFalha(FORMATO_INVALIDO, "hashtag com caractere inválido", "hashtags")
        _texto_seguro(tag, "hashtags", maximo=MAX_HASHTAG_CHARS)
        if f"#{tag}".casefold() not in {t.casefold() for t in tags}:
            tags.append(f"#{tag}")
    if len(tags) > limites.hashtags:
        raise SaidaIaFalha(LIMITE_EXCEDIDO, f"{len(tags)} hashtags; o máximo é {limites.hashtags}", "hashtags")
    return {"legenda": legenda, "hashtags": tags, "primeiro_comentario": comentario}


# --- roteiro per formato (estruturas-contract.md section 8.7) ----------------------------------
# ADDITIVE: reels keep ``validar_roteiro``. carrossel / post / stories are markdown grammars; an
# invalid shape is a coded ``SaidaIaFalha`` and nothing is ever trimmed. Callers pass the script
# WITHOUT the ``=== ESTRUTURAS_USADAS ===`` trailer (``prompts.roteiro_formatos.separar_sentinela``).
FORMATOS_ROTEIRO = ("reels", "carrossel", "post", "stories")
MAX_SLIDES, MAX_SLIDE_CHARS = 20, 400
MAX_TELAS, MAX_TELA_CHARS = 8, 200
MAX_QUADROS, MAX_QUADRO_CHARS = 15, 300
MAX_LEGENDA_POST = 2200
HEADLINE_AUSENTE = "saida_headline_ausente"

_HTML = re.compile(r"<\s*/?\s*[A-Za-z!][^>]*>|&(?:#\d+|#x[0-9a-f]+|[a-z]{2,8});", re.I)
_SEP = r"[\u2014\u2013-]"
_RX_SLIDE = re.compile(rf"^\*\*Slide\s+(\d+)(?:\s*{_SEP}\s*(.*?))?\s*\*\*\s*$", re.I)
_RX_QUADRO = re.compile(rf"^\*\*Quadro\s+(\d+)(?:\s*{_SEP}\s*(.*?))?\s*\*\*\s*$", re.I)
_RX_TELA = re.compile(r"^\*\*Tela\s+(\d+)\*\*\s*[:\u2014\u2013-]?\s*(.*)$", re.I)
_H_TELA, _H_LEGENDA = "### texto na tela", "### legenda"


def _sem_html(texto: str, campo: str) -> None:
    if _HTML.search(texto):
        raise SaidaIaFalha(CONTEUDO_PROIBIDO, "contém HTML", campo)


def _unidades(texto: str, rx: "re.Pattern[str]", rotulo: str, *, maximo: int, max_chars: int,
              inline: bool = False) -> list[dict[str, Any]]:
    """Split ``texto`` into numbered units (headers matched by ``rx``) and validate each one."""
    antes: list[str] = []
    brutas: list[tuple[int, str, list[str]]] = []
    for linha in texto.splitlines():
        m = rx.match(linha.strip())
        if m:
            resto = (m.group(2) or "") if inline else ""
            brutas.append((int(m.group(1)), "" if inline else (m.group(2) or "").strip(), [resto] if resto else []))
        elif brutas:
            brutas[-1][2].append(linha)
        else:
            antes.append(linha)
    if not brutas:
        raise SaidaIaFalha(CAMPO_AUSENTE, f"nenhum {rotulo} encontrado", rotulo)
    if "".join(antes).strip():
        raise SaidaIaFalha(FORMATO_INVALIDO, f"texto antes do primeiro {rotulo}", rotulo)
    if len(brutas) > maximo:
        raise SaidaIaFalha(LIMITE_EXCEDIDO, f"{len(brutas)} itens ({rotulo}); o máximo é {maximo}", rotulo)
    unidades: list[dict[str, Any]] = []
    for pos, (n, nome, linhas) in enumerate(brutas, 1):
        campo = f"{rotulo} {pos}"
        if n != pos:
            raise SaidaIaFalha(FORMATO_INVALIDO, f"numeração fora de ordem: esperado {pos}, veio {n}", campo)
        corpo = "\n".join(linhas).strip()
        _sem_html(corpo, campo)
        _texto_seguro(corpo, campo, maximo=max_chars)
        if nome:
            _sem_html(nome, campo)
            _texto_seguro(nome, campo, maximo=120)
        unidades.append({"n": pos, "nome": nome, "texto": corpo})
    return unidades


def _checar_headline(headline: Optional[str], primeiro: str, campo: str) -> None:
    if headline and headline.strip():
        norm = lambda t: " ".join(t.casefold().split())  # noqa: E731
        if norm(headline) not in norm(primeiro):
            raise SaidaIaFalha(HEADLINE_AUSENTE, "a primeira unidade não traz a headline", campo)


def validar_roteiro_formato(formato: str, texto: Any, *, headline: Optional[str] = None) -> dict[str, Any]:
    """Validate the script of ``formato`` (carrossel | post | stories) per section 8.7.

    Returns ``{"conteudo": <script as received, stripped>, "unidades": [{n, nome, texto}], "legenda": str|None}``
    (``legenda`` only for ``post``). ``reels`` is handled by :func:`validar_roteiro` and refused here so a caller
    cannot silently skip the beat checks. ``headline`` (optional) must appear in carrossel slide 1."""
    if formato == "reels":
        raise SaidaIaFalha(FORMATO_INVALIDO, "reels usa validar_roteiro", "formato")
    if formato not in FORMATOS_ROTEIRO:
        raise SaidaIaFalha(FORMATO_INVALIDO, f"formato desconhecido: {formato}", "formato")
    if not isinstance(texto, str):
        raise SaidaIaFalha(CAMPO_AUSENTE if texto is None else FORMATO_INVALIDO, "o roteiro deve ser texto", "conteudo")
    corpo = texto.strip()
    if not corpo:
        raise SaidaIaFalha(CAMPO_AUSENTE, "campo vazio", "conteudo")
    if len(corpo) > MAX_ROTEIRO:
        raise SaidaIaFalha(LIMITE_EXCEDIDO, f"{len(corpo)} caracteres; o máximo é {MAX_ROTEIRO}", "conteudo")
    if formato == "carrossel":
        un = _unidades(corpo, _RX_SLIDE, "slide", maximo=MAX_SLIDES, max_chars=MAX_SLIDE_CHARS)
        _checar_headline(headline, un[0]["texto"], "slide 1")
        return {"conteudo": corpo, "unidades": un, "legenda": None}
    if formato == "stories":
        un = _unidades(corpo, _RX_QUADRO, "quadro", maximo=MAX_QUADROS, max_chars=MAX_QUADRO_CHARS)
        return {"conteudo": corpo, "unidades": un, "legenda": None}
    secoes: dict[str, list[str]] = {}
    atual: Optional[str] = None
    for linha in corpo.splitlines():
        h = linha.strip().casefold()
        if h in (_H_TELA, _H_LEGENDA):
            if h in secoes:
                raise SaidaIaFalha(FORMATO_INVALIDO, f"seção repetida: {linha.strip()}", "post")
            atual = h
            secoes[h] = []
        elif atual is None:
            if linha.strip():
                raise SaidaIaFalha(FORMATO_INVALIDO, "texto antes de `### Texto na tela`", "post")
        else:
            secoes[atual].append(linha)
    if _H_TELA not in secoes:
        raise SaidaIaFalha(CAMPO_AUSENTE, "falta a seção `### Texto na tela`", "texto na tela")
    if _H_LEGENDA not in secoes:
        raise SaidaIaFalha(CAMPO_AUSENTE, "falta a seção `### Legenda`", "legenda")
    if list(secoes) != [_H_TELA, _H_LEGENDA]:
        raise SaidaIaFalha(FORMATO_INVALIDO, "`### Legenda` deve vir depois de `### Texto na tela`", "post")
    un = _unidades("\n".join(secoes[_H_TELA]), _RX_TELA, "tela", maximo=MAX_TELAS, max_chars=MAX_TELA_CHARS,
                   inline=True)
    legenda_txt = "\n".join(secoes[_H_LEGENDA]).strip()
    _sem_html(legenda_txt, "legenda")
    legenda = validar_legenda({"legenda": legenda_txt})["legenda"]  # cap = LIMITES_REDE[instagram] = 2200
    return {"conteudo": corpo, "unidades": un, "legenda": legenda}


def extrair_legenda_do_post(texto: str) -> Optional[str]:
    """The validated ``### Legenda`` of a stored ``post`` roteiro, or ``None`` when absent/invalid (the caption
    service then falls back to its own model path). Never raises."""
    try:
        return validar_roteiro_formato("post", texto)["legenda"]
    except SaidaIaFalha:
        return None


__all__ = [
    "CAMPOS_ROTEIRO", "CampoRoteiro", "LIMITES_REDE", "SaidaIaFalha", "detectar_proibido",
    "validar_legenda", "validar_roteiro", "validar_roteiro_formato", "extrair_legenda_do_post",
    "FORMATOS_ROTEIRO", "HEADLINE_AUSENTE",
    "FORMATO_INVALIDO", "CAMPO_AUSENTE", "LIMITE_EXCEDIDO", "CONTEUDO_PROIBIDO",
]
