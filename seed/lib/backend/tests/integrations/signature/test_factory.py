"""`make_signature_adapter` — the one seam a consumer touches.

Class-B DI test seam (`resolver=`) throughout — never
`monkeypatch.setattr(noctusai_lib.config.credentials, "resolve_credential", ...)`.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.signature import (
    D4SignAdapter,
    FakeSignatureAdapter,
    ProvedorNaoConfigurado,
    make_signature_adapter,
)

_TODAS_AS_CREDENCIAIS = {
    "d4sign_api_token": "tok-123",
    "d4sign_crypt_key": "crypt-456",
    "d4sign_safe_uuid": "safe-789",
}


def _resolver_de(valores: dict):
    def resolver(chave, org_id=None):
        return valores.get(chave)

    return resolver


def test_default_is_fake() -> None:
    adapter = make_signature_adapter()
    assert isinstance(adapter, FakeSignatureAdapter)


def test_real_false_is_fake_even_with_full_credentials() -> None:
    adapter = make_signature_adapter(real=False, resolver=_resolver_de(_TODAS_AS_CREDENCIAIS))
    assert isinstance(adapter, FakeSignatureAdapter)


def test_real_true_with_full_credentials_builds_d4sign() -> None:
    adapter = make_signature_adapter(
        real=True, org_id="org-1", resolver=_resolver_de(_TODAS_AS_CREDENCIAIS)
    )
    assert isinstance(adapter, D4SignAdapter)


def test_real_true_unknown_provedor_raises_value_error() -> None:
    with pytest.raises(ValueError):
        make_signature_adapter(
            real=True, provedor="clicksign", resolver=_resolver_de(_TODAS_AS_CREDENCIAIS)
        )


def test_real_true_never_returns_a_fake() -> None:
    """The single most important assertion in this slice: whatever branch
    `real=True` takes, it is never a `FakeSignatureAdapter` — either a
    real adapter or an exception, never a silent mock."""
    for valores in (
        {},
        {"d4sign_api_token": "tok"},
        _TODAS_AS_CREDENCIAIS,
    ):
        try:
            adapter = make_signature_adapter(real=True, resolver=_resolver_de(valores))
        except ProvedorNaoConfigurado:
            continue
        assert not isinstance(adapter, FakeSignatureAdapter)
        assert isinstance(adapter, D4SignAdapter)


@pytest.mark.parametrize(
    "presentes, faltando_esperado",
    [
        ({}, ["d4sign_api_token", "d4sign_crypt_key", "d4sign_safe_uuid"]),
        ({"d4sign_api_token": "tok"}, ["d4sign_crypt_key", "d4sign_safe_uuid"]),
        (
            {"d4sign_api_token": "tok", "d4sign_crypt_key": "crypt"},
            ["d4sign_safe_uuid"],
        ),
    ],
)
def test_provedor_nao_configurado_names_every_missing_credential(
    presentes: dict, faltando_esperado: list
) -> None:
    with pytest.raises(ProvedorNaoConfigurado) as excinfo:
        make_signature_adapter(real=True, resolver=_resolver_de(presentes))

    exc = excinfo.value
    assert exc.faltando == faltando_esperado
    assert exc.details["faltando"] == faltando_esperado
    assert exc.provedor == "d4sign"


def test_resolver_receives_org_id() -> None:
    seen: list[tuple[str, object]] = []

    def resolver(chave, org_id=None):
        seen.append((chave, org_id))
        return _TODAS_AS_CREDENCIAIS.get(chave)

    make_signature_adapter(real=True, org_id="org-42", resolver=resolver)

    assert seen == [
        ("d4sign_api_token", "org-42"),
        ("d4sign_crypt_key", "org-42"),
        ("d4sign_safe_uuid", "org-42"),
    ]
