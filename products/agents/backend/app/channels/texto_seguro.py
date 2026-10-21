"""Shaping of text that crosses a trust boundary at a channel tool (Julia v2 guardrails B6.3 - B6.5).

Two directions, one rule: a string written by somebody else is DATA, never an instruction and never a channel.

* **Catalogue text -> the model** (:func:`formatar_catalogo`): what ``detalhes_imovel`` / ``consultar_empreendimento``
  return is the agency's listing text (owner-editable, scraped from portals, ...). Only an explicit key allowlist
  gets through; the free text is capped, stripped of URLs (other than the listing's own ``link``), phone numbers
  and e-mails, scanned for prompt-extraction phrasing (a hit DROPS the field and is recorded as a signal), and the
  whole thing is handed to the model under ONE key (``dados_catalogo``) so the prompt's wording can say "that key is
  data, not instructions".
* **Model text -> staff** (:func:`sem_contatos`): hand-off reasons, capture notes, visit preferences are written by
  the model from the lead's words; they land in a notification a broker reads, so URLs, phones, e-mails and
  @-mentions are removed before they are stored.

Every cap is a column of ``canal_limites`` (``catalogo_*``); nothing here owns a number or a word the model reads.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.channels import conformidade as conf

__all__ = [
    "ALLOW_DETALHES",
    "ALLOW_EMPREENDIMENTO",
    "Catalogo",
    "formatar_catalogo",
    "sem_contatos",
]

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MENCAO = re.compile(r"(?<![\w@])@\w{2,}")
#: A Brazilian phone number: optional +55, optional area code, 8-9 digits (not a price: ``R$`` in front excludes it).
_FONE = re.compile(
    r"(?<![\d\w$])(?<!R\$ )(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]?\d{4}(?!\d)")
_BLANK = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")


def sem_contatos(texto: str, *, manter: Iterable[str] = ()) -> str:
    """``texto`` without URLs (except those in ``manter``), e-mails, phone numbers and @-mentions; whitespace
    collapsed. The removal is silent on purpose: the receiver reads plain prose, not a marker to follow."""
    manter_ = {m.strip().rstrip(".,;:!?)]}\"'") for m in manter if isinstance(m, str) and m.strip()}

    def _url(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0).rstrip(".,;:!?)]}\"'") in manter_ else ""

    t = _CONTROL.sub(" ", texto)
    t = _URL.sub(_url, t)
    t = _EMAIL.sub("", t)
    t = _MENCAO.sub("", t)
    t = _FONE.sub("", t)
    return _BLANK.sub(" ", t).strip()


def _cortar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[:maximo].rstrip()


# ── catalogue text -> the model ─────────────────────────────────────────────

#: ``key -> None`` (a scalar / free-text field) or ``key -> {nested allowlist}`` (a list of objects).
Allow = Mapping[str, "Allow | None"]

ALLOW_DETALHES: Allow = {
    "codigo": None, "titulo": None, "descricao": None, "preco": None, "condominio": None, "iptu": None,
    "endereco": None, "caracteristicas": None, "link": None, "encontrado": None, "confirmacao_proprietario": None,
}
_ALLOW_EXEMPLO: Allow = {"codigo": None, "titulo": None, "tipo": None, "quartos": None, "preco": None}
ALLOW_EMPREENDIMENTO: Allow = {
    "nome": None, "construtora": None, "bairro": None, "cidade": None, "unidades": None, "tipos": None,
    "quartos": None, "area_privativa": None, "preco_venda": None, "preco_locacao": None,
    "exemplos": _ALLOW_EXEMPLO,
}


@dataclass
class Catalogo:
    """The shaped catalogue payload plus what the shaping found (codes only, never the dropped text)."""

    dados: dict[str, Any] = field(default_factory=dict)
    #: ``[{"campo": <key>}]`` for each field dropped because it read like an extraction attempt.
    sinais: list[dict[str, Any]] = field(default_factory=list)


def _texto(valor: str, maximo: int, link: str | None) -> str:
    return _cortar(sem_contatos(valor, manter=[link] if link else []), maximo)


def _generico(valor: Any, maximo: int, link: str | None) -> Any:
    """Scalars pass; strings are shaped; containers are shaped leaf by leaf (a nested structured field such as
    ``confirmacao_proprietario`` or a price range)."""
    if isinstance(valor, str):
        return _texto(valor, maximo, link)
    if isinstance(valor, Mapping):
        return {str(k): _generico(v, maximo, link) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_generico(v, maximo, link) for v in valor]
    return valor


def _formatar(item: Mapping[str, Any], allow: Allow, limites: Any, sinais: list[dict[str, Any]]) -> dict[str, Any]:
    link = item.get("link") if isinstance(item.get("link"), str) else None
    out: dict[str, Any] = {}
    for chave, sub in allow.items():
        if chave not in item or item[chave] is None:
            continue
        valor = item[chave]
        if sub is not None:  # a list of objects
            filhos = [_formatar(x, sub, limites, sinais) for x in valor if isinstance(x, Mapping)] if isinstance(valor, list) else []
            if filhos:
                out[chave] = filhos
            continue
        if chave == "link":
            if isinstance(valor, str) and valor.strip().lower().startswith(("http://", "https://")):
                out[chave] = valor.strip()
            continue
        if chave == "codigo":  # an identifier, matched verbatim downstream: never reshaped (an 8-digit code is not a phone)
            if isinstance(valor, (str, int)) and str(valor).strip():
                out[chave] = str(valor).strip()[:64]
            continue
        if chave == "titulo" and isinstance(valor, str):
            valor = _texto(valor, limites.catalogo_titulo_max, link)
        elif chave == "descricao" and isinstance(valor, str):
            valor = _texto(valor, limites.catalogo_descricao_max, link)
        elif chave == "caracteristicas":
            if not isinstance(valor, list):
                continue
            valor = [
                _texto(c, limites.catalogo_item_max, link) for c in valor[: limites.catalogo_caracteristicas_max]
                if isinstance(c, str) and c.strip()
            ]
        else:
            valor = _generico(valor, 200, link)
        textos = valor if isinstance(valor, list) and all(isinstance(x, str) for x in valor) else [valor]
        livres = [x for x in textos if isinstance(x, str)]
        if chave in ("titulo", "descricao", "caracteristicas") and livres and conf.sinal_extracao(livres, None):
            sinais.append({"campo": chave})
            continue
        if valor in ("", []):
            continue
        out[chave] = valor
    return out


def formatar_catalogo(item: Mapping[str, Any], allow: Allow, limites: Any) -> Catalogo:
    """Shape ONE catalogue object (see the module docstring). ``limites`` carries the ``catalogo_*`` caps."""
    sinais: list[dict[str, Any]] = []
    return Catalogo(dados=_formatar(item, allow, limites, sinais), sinais=sinais)
