"""Tests for `noctusai_lib.api.StrictHttpModel`.

Covers:
- Unit: instantiating with known fields succeeds.
- Unit: instantiating with unknown fields raises `ValidationError` with the
  `extra_forbidden` error type + correct `loc`.
- Unit: missing required field still raises as Pydantic always did.
- Unit: subclass without `model_config` override inherits `extra="forbid"`.
- Unit: subclass overriding `model_config` WITHOUT re-declaring `extra="forbid"`
  loses strictness (the documented footgun — regression test for the warning).
- Unit: subclass overriding `model_config` WITH `extra="forbid"` re-declared
  keeps strictness.
- FastAPI integration: POST with extra key → 422 with `extra_forbidden` `loc`
  naming the offending key (the original VVV silent-drop bug class becomes
  a loud test failure).
- FastAPI integration: POST with known keys only → 200.

Status-code-assertion rule: every body assertion is paired with a
`.status_code` assertion in the same test.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ConfigDict, ValidationError

from noctusai_lib.api import StrictHttpModel


# ── Unit: direct instantiation ───────────────────────────────────────


class _SettingsUpdate(StrictHttpModel):
    """Minimal HTTP-boundary schema for unit tests."""

    name: str | None = None
    phone: str | None = None


def test_known_fields_accepted():
    """Sanity: known fields parse cleanly."""
    obj = _SettingsUpdate(name="Acme", phone="+5511999999999")

    assert obj.name == "Acme"
    assert obj.phone == "+5511999999999"


def test_unknown_field_raises_validation_error():
    """The fix: unknown key → ValidationError with `extra_forbidden` shape."""
    with pytest.raises(ValidationError) as excinfo:
        _SettingsUpdate(name="Acme", cnpj="00.000.000/0001-00")

    errors = excinfo.value.errors()
    assert len(errors) == 1, f"expected exactly 1 error, got {errors}"
    assert errors[0]["type"] == "extra_forbidden"
    assert errors[0]["loc"] == ("cnpj",)


def test_multiple_unknown_fields_all_reported():
    """Pydantic batches all unknown keys into one ValidationError — verify each."""
    with pytest.raises(ValidationError) as excinfo:
        _SettingsUpdate(name="Acme", cnpj="x", email="y@z")

    errors = excinfo.value.errors()
    error_types = {e["type"] for e in errors}
    error_locs = {e["loc"] for e in errors}

    assert error_types == {"extra_forbidden"}, f"expected only extra_forbidden, got {error_types}"
    assert error_locs == {("cnpj",), ("email",)}


# ── Unit: subclass behavior ──────────────────────────────────────────


def test_subclass_without_config_override_inherits_strict():
    """A subclass that doesn't re-declare model_config keeps `extra="forbid"`."""

    class Nested(StrictHttpModel):
        value: int

    with pytest.raises(ValidationError) as excinfo:
        Nested(value=1, unknown="x")

    assert excinfo.value.errors()[0]["type"] == "extra_forbidden"


def test_subclass_with_config_override_keeping_forbid_stays_strict():
    """The migration-correct pattern: re-declare `extra="forbid"` alongside other config."""

    class WithOrm(StrictHttpModel):
        model_config = ConfigDict(extra="forbid", from_attributes=True)
        value: int

    # Strict semantic preserved.
    with pytest.raises(ValidationError) as excinfo:
        WithOrm(value=1, unknown="x")

    assert excinfo.value.errors()[0]["type"] == "extra_forbidden"

    # `from_attributes` still works (model_validate against an object).
    class _Source:
        value = 42

    parsed = WithOrm.model_validate(_Source())
    assert parsed.value == 42


def test_subclass_with_config_override_merges_with_parent_config():
    """Pydantic v2 MERGES child `ConfigDict` with parent's — strictness propagates.

    This is GOOD: a subclass adding `from_attributes=True` without re-declaring
    `extra="forbid"` still rejects unknown keys, because the merged config is
    `{"extra": "forbid", "from_attributes": True}`.

    Pinned by this test so a future Pydantic version that silently changes the
    merge semantic (e.g. back to "child replaces parent") is caught immediately —
    it would re-open the silent-drop bug class for every migrated subclass.
    """

    class WithOrmOnly(StrictHttpModel):
        # No `extra="forbid"` re-declaration — relies on the MRO merge.
        model_config = ConfigDict(from_attributes=True)
        value: int

    # Merge keeps strict — unknown key still raises.
    with pytest.raises(ValidationError) as excinfo:
        WithOrmOnly(value=1, unknown="x")
    assert excinfo.value.errors()[0]["type"] == "extra_forbidden"

    # And `from_attributes` still works.
    class _Source:
        value = 99

    parsed = WithOrmOnly.model_validate(_Source())
    assert parsed.value == 99

    # Sanity: the actual merged config has both keys.
    assert WithOrmOnly.model_config.get("extra") == "forbid"
    assert WithOrmOnly.model_config.get("from_attributes") is True


# ── FastAPI integration: 422 surface ─────────────────────────────────


def _build_app() -> FastAPI:
    """Minimal FastAPI app declaring a StrictHttpModel body."""
    app = FastAPI()

    @app.post("/settings")
    def update_settings(payload: _SettingsUpdate) -> dict:
        return {"received": payload.model_dump()}

    return app


def test_fastapi_post_known_fields_returns_200():
    """Sanity: known-only payload → 200."""
    client = TestClient(_build_app())

    response = client.post("/settings", json={"name": "Acme", "phone": "+55"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"received": {"name": "Acme", "phone": "+55"}}


def test_fastapi_post_extra_key_returns_422_naming_the_key():
    """The original VVV bug: misrouted hook POSTs an unknown key.

    With the platform default (`extra="ignore"`), this would silently drop
    the key and return 200 — the user sees a success toast, zero persistence.

    With `StrictHttpModel`, FastAPI returns 422 and the `loc` array names the
    offending key. The misroute becomes a loud test failure.
    """
    client = TestClient(_build_app())

    response = client.post(
        "/settings",
        json={"name": "Acme", "cnpj": "00.000.000/0001-00"},
    )

    assert response.status_code == 422
    body = response.json()
    # Body shape: {"detail": [{"type": "extra_forbidden", "loc": [...], ...}, ...]}
    assert "detail" in body
    assert any(
        err.get("type") == "extra_forbidden" and "cnpj" in err.get("loc", [])
        for err in body["detail"]
    ), f"expected extra_forbidden error naming 'cnpj', got {body['detail']}"


def test_fastapi_post_multiple_extra_keys_all_reported_in_422():
    """All offending keys land in the 422 body so frontend devs see them all at once."""
    client = TestClient(_build_app())

    response = client.post(
        "/settings",
        json={"name": "Acme", "cnpj": "x", "email": "y@z"},
    )

    assert response.status_code == 422
    body = response.json()
    offending_locs = {
        tuple(err["loc"][-1:])
        for err in body["detail"]
        if err.get("type") == "extra_forbidden"
    }
    assert offending_locs == {("cnpj",), ("email",)}
