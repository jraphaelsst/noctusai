"""Public CNPJ registry lookup — BrasilAPI primary, ReceitaWS fallback,
both keyless, no scraping, both public government-backed data mirrors.

**What this is.** One Protocol (`CnpjRegistryLookup`) + Fake + Real +
factory (`make_cnpj_registry_lookup`), so any product that already knows a
company's CNPJ can resolve its CURRENT `situação cadastral` / `razão
social` without waiting on a human to upload a Cartão CNPJ PDF.

**Why it lives here and not in a product.** The first consumer
(`products/social-wiring`'s `empresas` module, 2026-09-30) hit a live-prod
block: every company a party holds a participação in (auto-created from a
Serasa Crednet report) has `situacao_cadastral IS NULL` until a human
uploads its Cartão CNPJ — and 5 real deals had 8 such companies with only
3 cards on file. The owner's rule is "the system resolves itself; humans
only when it truly can't" — and this data is PUBLIC, so a machine lookup is
the honest first move, the Cartão CNPJ upload staying the (higher-trust,
still-available) fallback for whatever this can't resolve. Nothing about
"look up a CNPJ's registration status" is social-wiring-specific — any
future product with the same "we already have a CNPJ, we need to know if
it's still active" need reuses this verbatim, per `KB § 03-SEED-
ARCHITECTURE.md`.

**Recipe:**

    from noctusai_lib.integrations.cnpj_registry import make_cnpj_registry_lookup
    from noctusai_lib.integrations.cnpj_registry.errors import CnpjRegistryError

    lookup = make_cnpj_registry_lookup(real=True)
    try:
        fields = await lookup.lookup(empresa["cnpj"])
    except CnpjRegistryError as exc:
        logger.warning("cnpj_registry: lookup failed for %s: %s", empresa["cnpj"], exc)
        return  # leave situacao_cadastral untouched — never a guess
    # fields.situacao_cadastral is one of the five migration-167 values, or
    # None if the source's own text didn't match — see `types.py`.

**Real adapter posture.** `RealCnpjRegistryLookup` calls BrasilAPI first,
ReceitaWS second — never raises for a network/shape failure of ONE source
alone; only when BOTH fail (see `real.py`'s module header for the exact
fallback-resolution rule).

**Fake adapter posture.** `FakeCnpjRegistryLookup` returns a synthetic
`ativa` company by default; `registrar(cnpj, fields)` scripts a specific
CNPJ's answer, `erro=` scripts a failure — see `fake.py`.

**Shared vocabulary.** `situacao_cadastral`/`situacao_cadastral_bruta`
follow `noctusai_lib.integrations.documents.situacao_cadastral`'s closed
five-word vocabulary — the SAME normaliser `documents.cartao_cnpj` uses, so
a Cartão CNPJ reading and a public-registry reading of the same field can
never silently disagree about what "ativa" even means.
"""
from __future__ import annotations

from .errors import CnpjNotFoundError, CnpjRegistryError, CnpjRegistryUpstreamError
from .factory import make_cnpj_registry_lookup
from .fake import FakeCnpjRegistryLookup
from .real import RealCnpjRegistryLookup
from .types import CnpjRegistryFields, CnpjRegistryLookup

__all__ = [
    "CnpjNotFoundError",
    "CnpjRegistryError",
    "CnpjRegistryFields",
    "CnpjRegistryLookup",
    "CnpjRegistryUpstreamError",
    "FakeCnpjRegistryLookup",
    "RealCnpjRegistryLookup",
    "make_cnpj_registry_lookup",
]
