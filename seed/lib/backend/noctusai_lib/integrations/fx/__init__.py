"""BCB PTAX FX-rate integration — venda (sell), fechamento (closing) bulletin.

This platform spends in USD (OpenAI) and charges in BRL. Every LLM cost
record needs the native amount, the BRL conversion, AND the rate used —
so a historical cost never silently re-prices when the exchange rate
moves later. This module is the single source of that rate: Banco
Central do Brasil's PTAX via the public Olinda OData API (no API key,
no secret — see `bcb_adapter.py` for the shape learned by probing it).

Public surface:
- `PtaxRate`, `FxRateAdapter` Protocol (`types.py`).
- `FakeFxRateAdapter` — deterministic offline fake (`fake_adapter.py`).
- `BcbPtaxAdapter` — real BCB Olinda adapter (`bcb_adapter.py`).
- `FxError` / `FxBulletinNotFoundError` / `FxUpstreamError` typed errors
  (`errors.py`) — no silent fallback; see the module-level `errors.py`
  docstring for why `LLM_USD_TO_BRL` must never substitute for a real
  lookup here.
- `get_fx_rate_adapter(live=...)` factory.
- Pure-function mappers (`format_bcb_date`, `parse_ptax_response`).
"""

from __future__ import annotations

from noctusai_lib.integrations.fx.bcb_adapter import BcbPtaxAdapter
from noctusai_lib.integrations.fx.errors import (
    FxBulletinNotFoundError,
    FxError,
    FxUpstreamError,
)
from noctusai_lib.integrations.fx.fake_adapter import FakeFxRateAdapter
from noctusai_lib.integrations.fx.mappers import format_bcb_date, parse_ptax_response
from noctusai_lib.integrations.fx.types import FxRateAdapter, PtaxRate


def get_fx_rate_adapter(live: bool = False, **kwargs: object) -> FxRateAdapter:
    """Return `BcbPtaxAdapter` when `live=True`; `FakeFxRateAdapter` otherwise.

    Unlike most seed adapters (`get_routing_adapter`, `get_calendar_adapter`)
    there is no credential/URL signal to branch on — BCB's Olinda PTAX
    service is public and keyless. `live` is therefore an EXPLICIT choice,
    mirroring `make_redis_client`/`make_fake_redis_client`'s explicit-pair
    shape rather than a coincidental-signal factory. Defaults to Fake — a
    consumer must opt IN to live network calls; `**kwargs` forward to
    whichever adapter is chosen (e.g. `lookback_days`, `http_client`,
    `bulletins`).
    """
    if live:
        return BcbPtaxAdapter(**kwargs)  # type: ignore[arg-type]
    return FakeFxRateAdapter(**kwargs)  # type: ignore[arg-type]


__all__ = [
    "BcbPtaxAdapter",
    "FakeFxRateAdapter",
    "FxBulletinNotFoundError",
    "FxError",
    "FxRateAdapter",
    "FxUpstreamError",
    "PtaxRate",
    "format_bcb_date",
    "get_fx_rate_adapter",
    "parse_ptax_response",
]
