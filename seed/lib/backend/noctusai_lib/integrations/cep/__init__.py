"""CEP (Código de Endereçamento Postal) lookup — ViaCEP, BrasilAPI fallback.

F3 (live prod test on 5 historical deals, 2026-09-30): the platform had NO
CEP lookup at all, and a document's own `cidade` free-text field was wrong
for 4/19 people measured while the CEP on the SAME document was correct for
15/19 — see `viacep_adapter.py`'s own docstring for the full measured
numbers. This module is the single source of a CEP-resolved address;
`app.modules.card_hub.identidade_extracao_service.aplicar_endereco_ao_cliente`
(social-wiring) is the one place every address reader's applied value flows
through, so that is where this adapter is consumed — never per-reader.

Public surface:
- `CepEndereco`, `CepLookupAdapter` Protocol (`types.py`).
- `FakeCepLookupAdapter` — deterministic offline fake (`fake_adapter.py`).
- `ViaCepAdapter` — real ViaCEP+BrasilAPI adapter (`viacep_adapter.py`).
- `get_cep_lookup_adapter(live=...)` factory.
"""

from __future__ import annotations

from noctusai_lib.integrations.cep.fake_adapter import FakeCepLookupAdapter
from noctusai_lib.integrations.cep.types import CepEndereco, CepLookupAdapter
from noctusai_lib.integrations.cep.viacep_adapter import ViaCepAdapter


def get_cep_lookup_adapter(live: bool = False, **kwargs: object) -> CepLookupAdapter:
    """Return `ViaCepAdapter` when `live=True`; `FakeCepLookupAdapter`
    otherwise.

    Same explicit-pair shape `fx.get_fx_rate_adapter` uses: ViaCEP/BrasilAPI
    are public and keyless, so there is no credential/URL signal to branch
    on — `live` is an explicit opt-in, mirroring `noctusai_lib.integrations.
    fx`'s own factory rather than a coincidental-signal one. Defaults to
    Fake; a consumer must opt IN to live network calls. `**kwargs` forward
    to whichever adapter is chosen (e.g. `http_client`, `timeout`,
    `enderecos`).
    """
    if live:
        return ViaCepAdapter(**kwargs)  # type: ignore[arg-type]
    return FakeCepLookupAdapter(**kwargs)  # type: ignore[arg-type]


__all__ = [
    "CepEndereco",
    "CepLookupAdapter",
    "FakeCepLookupAdapter",
    "ViaCepAdapter",
    "get_cep_lookup_adapter",
]
