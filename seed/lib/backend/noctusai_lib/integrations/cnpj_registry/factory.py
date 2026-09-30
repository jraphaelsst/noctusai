"""`make_cnpj_registry_lookup(*, real=...)` — Fake-by-default, same shape
`documents.cartao_cnpj.make_cartao_cnpj_extractor` and `turnstile.factory.
make_turnstile_verifier` both use."""
from __future__ import annotations

from typing import Any

from .fake import FakeCnpjRegistryLookup
from .real import RealCnpjRegistryLookup
from .types import CnpjRegistryLookup


def make_cnpj_registry_lookup(*, real: bool = False, **kwargs: Any) -> CnpjRegistryLookup:
    """Return a public CNPJ registry lookup. Fake-by-default — a consumer
    must opt IN to live network calls (`real=True`), same posture
    `fx.get_fx_rate_adapter` takes for the same reason (no credential to
    branch on; BrasilAPI/ReceitaWS are both keyless).

    `**kwargs` forward to whichever implementation is chosen —
    `RealCnpjRegistryLookup(http_client=..., timeout=..., transport=...)`
    or `FakeCnpjRegistryLookup(erro=...)`.
    """
    if real:
        return RealCnpjRegistryLookup(**kwargs)
    return FakeCnpjRegistryLookup(**kwargs)


__all__ = ["make_cnpj_registry_lookup"]
