"""Provenance and tripwires of a channel turn (Julia v2 guardrails B2 + B7).

Pure helpers; the wording around them is DB text. Three jobs:

* **Envelopes.** A line that is NOT the lead's (a human attendant, another agent, a thread event) is shown to the
  model as its own ``system`` message holding ONE JSON literal keyed ``plataforma_<tag>`` where ``<tag>`` is a
  per-turn random value the model was told (in DB wording) marks platform data. The lead's words stay in the ``user``
  role and are never prefixed, so a label, a name or an envelope-shaped string the lead types is just lead text.
* **Forgery signals.** A lead message that contains the turn's tag, the prompt canary / a run of the compiled
  prompt, or the honeytoken proves a leak happened: each is a violation CODE (never the text).
* **Honeytoken.** The per-version marker (the per-version marker store) is searched in a reply, in the lead's
  messages and in the arguments a tool call carried to staff.

No human-readable word is defined here; the only literals are machine identifiers (JSON keys, rule codes).
"""
from __future__ import annotations

import json
import secrets
from collections.abc import Iterable, Mapping
from typing import Any

from app.channels import conformidade as conf
from app.channels.contexto import lit
from app.stores.conformidade import Impressao

__all__ = [
    "MARCADOR_HONEYTOKEN",
    "canario_recebido",
    "chave_envelope",
    "envelope",
    "forja_proveniencia",
    "literal_midia",
    "marcador_em",
    "nova_tag",
    "texto_da_acao",
]

#: ``detalhe`` flag of a ``vazamento_prompt`` hit that came from the honeytoken (no wording, a flag).
MARCADOR_HONEYTOKEN = "honeytoken"


def nova_tag() -> str:
    """The turn's provenance tag: 4 random bytes (8 hex chars), fresh for every turn."""
    return secrets.token_hex(4)


def chave_envelope(tag: str) -> str:
    return f"plataforma_{tag}"


def envelope(tag: str, campos: Mapping[str, Any]) -> str:
    """ONE physical line: ``{"plataforma_<tag>": {...}}`` with empty fields dropped."""
    return lit({chave_envelope(tag): {k: v for k, v in campos.items() if v not in (None, "")}})


def literal_midia(rotulo: str, midia: Mapping[str, Any]) -> str:
    """The media a lead message carried, as a labelled literal object: ``{"<rotulo>": {tipo, texto_extraido,
    legenda?}}``. The label is the DB text ``historico.rotulo_midia``; the content is data, never an instruction."""
    campos = {k: midia.get(k) for k in ("tipo", "texto_extraido", "legenda") if midia.get(k) not in (None, "")}
    campos.setdefault("texto_extraido", "")
    return lit({rotulo.strip(): campos})


def forja_proveniencia(mensagens_lead: Iterable[str], tag: str) -> dict[str, Any] | None:
    """A lead message carries the turn's tag. The tag is never shown to a lead, so this is the model repeating
    platform data back (or a guess that happened to land): a signal, counts only."""
    n = sum(1 for m in mensagens_lead if tag and tag in (m or ""))
    return {"mensagens": n} if n else None


def canario_recebido(
    mensagens_lead: Iterable[str], *, canario: str | None, impressao: Impressao | None,
) -> dict[str, Any] | None:
    """The lead SENT us the prompt canary or a run of the compiled prompt: the prompt leaked earlier. ``detalhe``
    holds counts and the high severity flag, never the text."""
    canarios = janelas = mensagens = 0
    for m in mensagens_lead:
        achado = conf.detectar_vazamento(m or "", canario_do_prompt=canario, impressao=impressao)
        if achado:
            mensagens += 1
            canarios += 1 if achado.get("canario") else 0
            janelas += int(achado.get("janelas", 0))
    if not mensagens:
        return None
    out: dict[str, Any] = {"severidade": "alta", "mensagens": mensagens}
    if canarios:
        out["canario"] = canarios
    if janelas:
        out["janelas"] = janelas
    return out


def marcador_em(textos: Iterable[str], marcador: str | None) -> int:
    """How many of ``textos`` contain the honeytoken (case-insensitive: a model may upper-case an id)."""
    if not marcador:
        return 0
    m = marcador.casefold()
    return sum(1 for t in textos if m in (t or "").casefold())


def texto_da_acao(acao: Any) -> str:
    """One tool action as the text a marker search should read (its arguments, as a model wrote them)."""
    return json.dumps(acao, ensure_ascii=False, default=str)

