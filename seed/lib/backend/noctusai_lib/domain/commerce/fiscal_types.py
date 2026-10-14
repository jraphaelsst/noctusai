"""Fiscal vocabulary of the commerce organ.

`InvoiceKind`, `InvoiceStatus` and `NfseMode` are OWNED by
`noctusai_lib.integrations.invoices.types` (integrations never import domain);
commerce re-exports them here so a commerce caller has one import and the
frontend parity test pins ONE list. Everything else below is commerce policy.
"""
from __future__ import annotations

from noctusai_lib.integrations.invoices.types import InvoiceKind, InvoiceStatus, NfseMode

from .types import TaxRegime

#: Regimes the Emissor Nacional is mandatory for (D37, CGSN 191/2026): MEI today,
#: Simples Nacional ME/EPP from 2026-11-01. A store on one of these can never hold `municipal`.
NACIONAL_FORCED_REGIMES: frozenset[str] = frozenset({TaxRegime.MEI.value, TaxRegime.SIMPLES.value})

#: Typed confirmation phrases (the owner types them -- the approved-cutover pattern).
CUTOVER_PHRASE = "MIGRAR PARA NFS-E NACIONAL"
ROLLBACK_PHRASE = "VOLTAR PARA NFS-E MUNICIPAL"

#: How long the rollback to `municipal` stays available after a cutover.
VALIDATION_WINDOW_DAYS = 60

#: Provider cancel needs a justification of at least this many characters.
MIN_CANCEL_REASON_CHARS = 15

#: Certificate upload bounds (also enforced inside `inspect_pkcs12`).
MAX_CERTIFICATE_BYTES = 64 * 1024
MAX_CERTIFICATE_PASSWORD_CHARS = 128

#: Statuses after which a (order, kind) may be issued again with a NEW ref.
REISSUABLE_STATUSES: frozenset[str] = frozenset({InvoiceStatus.REJECTED.value, InvoiceStatus.ERROR.value})

#: Statuses that block a second invoice for the same (order, kind): one document per treatment.
LIVE_STATUSES: frozenset[str] = frozenset(
    {InvoiceStatus.PROCESSING.value, InvoiceStatus.AUTHORIZED.value, InvoiceStatus.CANCELLED.value}
)


def forced_nacional(tax_regime: str) -> bool:
    return str(getattr(tax_regime, "value", tax_regime)) in NACIONAL_FORCED_REGIMES


def effective_nfse_mode(profile: dict) -> NfseMode:
    """The stored mode, else the regime default (`nacional` when forced, else `municipal`)."""
    stored = profile.get("nfse_mode")
    if stored:
        return NfseMode(stored)
    return NfseMode.NACIONAL if forced_nacional(profile.get("tax_regime", "")) else NfseMode.MUNICIPAL


__all__ = [
    "CUTOVER_PHRASE",
    "InvoiceKind",
    "InvoiceStatus",
    "LIVE_STATUSES",
    "MAX_CERTIFICATE_BYTES",
    "MAX_CERTIFICATE_PASSWORD_CHARS",
    "MIN_CANCEL_REASON_CHARS",
    "NACIONAL_FORCED_REGIMES",
    "NfseMode",
    "REISSUABLE_STATUSES",
    "ROLLBACK_PHRASE",
    "VALIDATION_WINDOW_DAYS",
    "effective_nfse_mode",
    "forced_nacional",
]
