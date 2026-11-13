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


__all__ = [
    "CAMPOS_ROTEIRO", "CampoRoteiro", "LIMITES_REDE", "SaidaIaFalha", "detectar_proibido",
    "validar_legenda", "validar_roteiro",
    "FORMATO_INVALIDO", "CAMPO_AUSENTE", "LIMITE_EXCEDIDO", "CONTEUDO_PROIBIDO",
]
