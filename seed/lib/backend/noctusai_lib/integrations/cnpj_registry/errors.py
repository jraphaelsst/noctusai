"""Typed errors for the public CNPJ registry lookup.

Mirrors `noctusai_lib.integrations.fx.errors`'s split (a "the source
CONFIRMS there's nothing here" class vs. a "we simply couldn't get an
answer" class) — a consumer of `cnpj_registry` needs to tell those two
apart for the same reason a consumer of `fx` does: a confirmed absence is
durable (nothing to retry until the data actually changes), a network/parse
failure is transient (worth a later retry, e.g. the next sweep pass).

No silent fallback: a consumer that catches either of these and leaves the
company's `situacao_cadastral` at `NULL` is the CORRECT behaviour (the
office's own Cartão CNPJ upload path, or a later sweep pass, is still there)
— never a guessed value substituted in its place.
"""
from __future__ import annotations


class CnpjRegistryError(Exception):
    """Base for every public CNPJ registry lookup failure."""


class CnpjNotFoundError(CnpjRegistryError):
    """The source(s) consulted confirm this CNPJ does not exist in the
    public registry (or the request was rejected as structurally
    unanswerable, e.g. a malformed CNPJ the provider itself rejected).

    `source` names whichever provider produced the definitive "not found"
    verdict that this exception carries (see `real.py`'s fallback logic for
    how a primary/secondary disagreement is resolved).
    """

    def __init__(self, cnpj: str, *, source: str) -> None:
        super().__init__(f"CNPJ {cnpj!r} not found in {source}'s public registry")
        self.cnpj = cnpj
        self.source = source


class CnpjRegistryUpstreamError(CnpjRegistryError):
    """No source could be reached, answered non-2xx (other than a
    not-found signal), returned a non-JSON body, or returned a JSON shape
    the mapper could not read.

    Distinct from `CnpjNotFoundError`: this means "we don't know what the
    registry says" (worth a retry later), not "the registry confirmed
    there is nothing here" (durable until the underlying data changes).
    """


__all__ = [
    "CnpjNotFoundError",
    "CnpjRegistryError",
    "CnpjRegistryUpstreamError",
]
