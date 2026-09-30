"""Deterministic, offline `CepLookupAdapter` fake.

Seed with `enderecos={"01310-100": CepEndereco(...)}` (or call `register`
after construction) — an unregistered CEP returns `None`, the SAME
"resolution failed" shape `ViaCepAdapter` returns for a genuine not-found —
a consumer cannot tell the two apart, by design, which is exactly why every
caller already has to treat "not found" as ordinary and non-fatal.
"""

from __future__ import annotations

import re

from noctusai_lib.integrations.cep.types import CepEndereco


def _digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")


class FakeCepLookupAdapter:
    """In-memory CEP fake. `lookups` records every CEP looked up (test-
    observable, mirrors `FakeFxRateAdapter.lookups`)."""

    def __init__(self, enderecos: dict[str, CepEndereco] | None = None) -> None:
        self._enderecos: dict[str, CepEndereco] = {
            _digits(cep): endereco for cep, endereco in (enderecos or {}).items()
        }
        self.lookups: list[str] = []

    def register(self, cep: str, endereco: CepEndereco) -> None:
        """Seed/override a single CEP (test convenience)."""
        self._enderecos[_digits(cep)] = endereco

    def lookup(self, cep: str) -> CepEndereco | None:
        self.lookups.append(cep)
        return self._enderecos.get(_digits(cep))


__all__ = ["FakeCepLookupAdapter"]
