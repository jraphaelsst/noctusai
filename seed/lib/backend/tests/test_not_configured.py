"""`noctusai_lib.primitives.not_configured` — the fleet-wide "integration
deliberately off: configuration absent" marker (2026-10-10)."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.vista.client import VistaConfigError, VistaError
from noctusai_lib.primitives.not_configured import (
    IntegrationNotConfigured,
    is_integration_not_configured,
)
from noctusai_lib.security.api_keys import EncryptionNotConfigured


def test_marked_seed_classes_keep_their_original_hierarchy():
    assert issubclass(EncryptionNotConfigured, RuntimeError)
    assert issubclass(EncryptionNotConfigured, IntegrationNotConfigured)
    assert issubclass(VistaConfigError, VistaError)
    assert issubclass(VistaConfigError, IntegrationNotConfigured)
    with pytest.raises(RuntimeError):  # existing `except RuntimeError` still catches
        raise EncryptionNotConfigured("ENCRYPTION_KEY is empty")


def test_direct_and_wrapped_raises_are_recognised():
    try:
        try:
            raise VistaConfigError("VISTA_BASE_URL is empty")
        except VistaConfigError as exc:
            raise ValueError("503 vista_nao_configurado") from exc
    except ValueError as wrapped:
        assert is_integration_not_configured(wrapped)
    assert is_integration_not_configured(EncryptionNotConfigured("x"))


def test_implicit_context_is_followed():
    try:
        try:
            raise EncryptionNotConfigured("x")
        except EncryptionNotConfigured:
            raise KeyError("during handling")
    except KeyError as exc:
        assert is_integration_not_configured(exc)


def test_unmarked_exceptions_are_not_recognised():
    assert not is_integration_not_configured(RuntimeError("ENCRYPTION_KEY is empty"))
    assert not is_integration_not_configured(None)


def test_cause_cycle_terminates():
    a, b = RuntimeError("a"), RuntimeError("b")
    a.__cause__, b.__cause__ = b, a
    assert not is_integration_not_configured(a)
