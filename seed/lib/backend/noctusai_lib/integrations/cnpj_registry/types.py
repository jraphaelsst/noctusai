"""Value objects + Protocol for a public CNPJ registry lookup.

Pure: no IO. `CnpjRegistryFields` is the one shape every source (`BrasilAPI`,
`ReceitaWS`, or the Fake) returns, so a consumer never branches on which one
answered — mirrors `noctusai_lib.integrations.fx.types.PtaxRate`'s posture
(one dataclass for every real adapter + the Fake) and `documents.cartao_cnpj
.CartaoCnpjFields`'s own `situacao_cadastral` field, which this module is
deliberately shaped to line up with (see `situacao_cadastral.py`'s own
docstring for why the vocabulary is shared, not duplicated).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class CnpjRegistryFields:
    """One public-registry answer for one CNPJ.

    `situacao_cadastral` is normalised to the same closed vocabulary
    `documents.cartao_cnpj.CartaoCnpjFields.situacao_cadastral` uses
    (`documents.situacao_cadastral.normalizar`) — `None` when the source's
    own text doesn't match one of the five known words, in which case
    `situacao_cadastral_bruta` still carries whatever the source actually
    printed (same "never guess, keep the raw text for a human" contract
    `cartao_cnpj.py`'s own module header documents).

    `source` names which provider actually answered (`"brasilapi"` |
    `"receitaws"` | `"fake"`) — forensic only, never branched on by a
    consumer (same posture `PtaxRate.source` and `TextSource` already
    establish elsewhere in this seed).
    """

    cnpj: str
    razao_social: Optional[str]
    situacao_cadastral: Optional[str]
    situacao_cadastral_bruta: Optional[str]
    data_situacao_cadastral: Optional[date]
    source: str
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CnpjRegistryLookup(Protocol):
    """Surface every CNPJ-registry connector implements. Both
    `FakeCnpjRegistryLookup` and `RealCnpjRegistryLookup` satisfy this
    Protocol naturally."""

    async def lookup(self, cnpj: str) -> CnpjRegistryFields:
        """Return this CNPJ's current public registry data.

        Raises `CnpjNotFoundError` when every source consulted confirms the
        CNPJ does not exist in the public registry, or
        `CnpjRegistryUpstreamError` when no source could be reached / parsed
        — NEVER a silent `None` and NEVER a guessed result. See `errors.py`.
        """
        ...


__all__ = ["CnpjRegistryFields", "CnpjRegistryLookup"]
