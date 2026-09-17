"""`make_signature_adapter` — Fake by default, Real on request. Contract §1.5.

Same posture every seed IO module takes: a consumer that forgets to
configure the real provider gets deterministic behaviour, never a
surprise vendor call. The mirror rule (`real=True` + missing credential)
is what makes this module different from most other seed factories
(`make_identity_extractor`, `get_image_edit_adapter`): those silently
degrade to their Fake when a key is absent, because an unconfigured LLM
key is a soft feature gap. An unconfigured e-signature provider is not —
a contract silently never sent for signature is the exact failure mode
`projects/signature-integration-CONTRACT.md` §0/F1 exists to close, so
`real=True` here NEVER returns a Fake. It raises `ProvedorNaoConfigurado`
naming every missing credential instead.
"""
from __future__ import annotations

from typing import Callable, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.signature.exceptions import ProvedorNaoConfigurado
from noctusai_lib.integrations.signature.fake import FakeSignatureAdapter
from noctusai_lib.integrations.signature.types import SignatureAdapter

#: v1 ships D4Sign only (contract §0 — 7 of 8 sample contracts name it).
#: The Protocol admits others later without a shape change.
PROVEDORES_SUPORTADOS: tuple[str, ...] = ("d4sign",)

#: Credential keys resolved through `noctusai_lib.config.credentials.
#: resolve_credential`, org-scoped. Keyed by provider so a second provider
#: can be added here later without touching the resolution loop.
_CREDENCIAIS_POR_PROVEDOR: dict[str, tuple[str, ...]] = {
    "d4sign": ("d4sign_api_token", "d4sign_crypt_key", "d4sign_safe_uuid"),
}

#: The Class-B DI test seam (`KB § PATTERNS/backend/di-test-seam.md`) —
#: `(key, org_id) -> value | None`, identical shape to `resolve_credential`
#: itself. Tests inject a fake resolver here; production code never
#: monkeypatches `noctusai_lib.config.credentials.resolve_credential`.
CredentialResolver = Callable[[str, Optional[str]], Optional[str]]


def make_signature_adapter(
    *,
    real: bool = False,
    provedor: str = "d4sign",
    org_id: Optional[str] = None,
    resolver: CredentialResolver = resolve_credential,
) -> SignatureAdapter:
    """Return a `SignatureAdapter`.

    Args:
        real: `False` (default) → `FakeSignatureAdapter`, always, regardless
            of any credential being configured. `True` → build the real
            provider adapter, or raise if it can't be configured.
        provedor: which provider to build when `real=True`. Only `"d4sign"`
            is supported in v1.
        org_id: forwarded to `resolver` for org-scoped credential lookup.
        resolver: the credential-lookup callable. Defaults to the seed's
            `resolve_credential` (org_settings → platform_settings → env);
            override in tests instead of patching the module attribute.

    Raises:
        ValueError: `real=True` and `provedor` is not one of
            `PROVEDORES_SUPORTADOS`.
        ProvedorNaoConfigurado: `real=True` and one or more of the
            provider's required credentials resolved to nothing.
            `exc.faltando` (and `exc.details["faltando"]`) names every
            missing key, not just the first.
    """
    if not real:
        return FakeSignatureAdapter()

    if provedor not in PROVEDORES_SUPORTADOS:
        raise ValueError(
            f"make_signature_adapter: unsupported provedor {provedor!r} "
            f"(v1 ships {PROVEDORES_SUPORTADOS!r} only)"
        )

    # Imported lazily: the Real leg pulls httpx's async client machinery,
    # and the Fake-by-default path above must stay importable without it.
    from noctusai_lib.integrations.signature.real import D4SignAdapter

    chaves = _CREDENCIAIS_POR_PROVEDOR[provedor]
    valores = {chave: resolver(chave, org_id) for chave in chaves}
    faltando = [chave for chave, valor in valores.items() if not valor]
    if faltando:
        raise ProvedorNaoConfigurado(faltando, provedor=provedor)

    return D4SignAdapter(
        api_token=valores["d4sign_api_token"],
        crypt_key=valores["d4sign_crypt_key"],
        safe_uuid=valores["d4sign_safe_uuid"],
    )


__all__ = ["CredentialResolver", "PROVEDORES_SUPORTADOS", "make_signature_adapter"]
