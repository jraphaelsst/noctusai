"""CEP lookup value objects + Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class CepEndereco:
    """The address a CEP resolves to — ViaCEP/BrasilAPI's own shape,
    already the fields `social-wiring.clientes`' address group needs.

    F3 (live prod test, 2026-09-30): `cidade`/`uf` are the AUTHORITY once a
    CEP resolves (a document's own cidade/uf, when they disagree, are
    REPLACED by these — see the calling site's own docstring); `logradouro`/
    `bairro` are advisory only, kept beside the document's own reading
    rather than overwriting it (a document's own street text is usually
    MORE specific than a CEP range's, which can span several streets).
    """

    cep: str
    cidade: str
    uf: str
    logradouro: Optional[str] = None
    bairro: Optional[str] = None


@runtime_checkable
class CepLookupAdapter(Protocol):
    """Surface every CEP connector implements. Both `FakeCepLookupAdapter`
    and `ViaCepAdapter` satisfy this Protocol naturally."""

    def lookup(self, cep: str) -> Optional[CepEndereco]:
        """Resolve a CEP (any punctuation) to its address, or `None` when
        it cannot be resolved — an unregistered/not-found CEP, a
        malformed one, or (Real only) an upstream failure. NEVER raises:
        this is advisory enrichment of an address already read off a
        document, not a precondition for applying one — see `ViaCepAdapter`'s
        own docstring for why a lookup failure is logged, not propagated."""
        ...
