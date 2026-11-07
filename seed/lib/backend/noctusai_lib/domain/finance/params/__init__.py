"""BR tax-parameter registry: effective-dated, sourced numbers the finance organ READS instead of hard-coding.

Contract (canon: ``KB § PATTERNS/finance/br-tax-advisor-canon.md``):
* One YAML per family (simples, mei, nfse, reforma_tributaria, obrigacoes) under this package + ``_policy.yaml``.
* ``param(key, on=date)`` returns the row in force on that day (vigencia bounds inclusive) or RAISES -- never a default and never a
  "latest row" fallback. Tier ``pratica`` rows are pointers only and are never returned.
* Staleness (``stale_params``) NEVER blocks a computation; callers surface ``staleness_warning`` in ``warnings[]``.
* Load-time invariants fail loudly naming file + key: no overlapping vigencia for key+scope, ``verificado_em`` <= today, tier
  ``especialista`` needs >= 2 URLs, floats refused (money = int centavos, rates = Decimal strings), unknown fields refused.
"""
from __future__ import annotations

from .registry import (
    ParamAmbiguous,
    ParamNotDefined,
    ParamRegistryError,
    ParamValue,
    StaleRow,
    load_registry,
    param,
    params_for,
    stale_params,
    staleness_warning,
)

__all__ = [
    "ParamAmbiguous", "ParamNotDefined", "ParamRegistryError", "ParamValue", "StaleRow",
    "load_registry", "param", "params_for", "stale_params", "staleness_warning",
]
