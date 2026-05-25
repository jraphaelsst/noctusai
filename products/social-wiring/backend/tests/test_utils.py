"""Tests for ``app.utils.has_oauth_credential`` — the N=3 OAuth-gate
formalization (calendar / drive_api / meta previously each carried a local
``_has_oauth_credential``)."""
from types import SimpleNamespace
from uuid import uuid4

from app.utils import has_oauth_credential


class _Store:
    """Minimal credential-store stub: ``get(org, provider)`` over a dict."""

    def __init__(self, rows=None, *, raises=False):
        self._rows = rows or {}
        self._raises = raises

    def get(self, org_id, provider):
        if self._raises:
            raise RuntimeError("vault unreachable")
        return self._rows.get((org_id, provider))


def test_hit_returns_true():
    org = uuid4()
    store = _Store({(str(org), "google"): SimpleNamespace(tokens={"access_token": "x"})})
    assert has_oauth_credential(store, org, "google") is True


def test_miss_returns_false():
    assert has_oauth_credential(_Store({}), uuid4(), "google") is False


def test_lookup_exception_returns_false_and_logs(caplog):
    with caplog.at_level("ERROR"):
        assert has_oauth_credential(_Store(raises=True), uuid4(), "google") is False
    assert any(
        "credential lookup failed" in r.getMessage().lower() for r in caplog.records
    ), "exception path must log (never a silent swallow)"


def test_require_token_true_needs_access_token():
    org = "org-1"
    # row present but empty tokens → not connected under require_token
    no_token = _Store({(org, "meta"): SimpleNamespace(tokens={})})
    assert has_oauth_credential(no_token, org, "meta", require_token=True) is False
    # row with a non-empty access_token → connected
    with_token = _Store({(org, "meta"): SimpleNamespace(tokens={"access_token": "tok"})})
    assert has_oauth_credential(with_token, org, "meta", require_token=True) is True


def test_require_token_false_ignores_token_presence():
    org = "org-2"
    store = _Store({(org, "google"): SimpleNamespace(tokens={})})
    # presence of the row is enough when require_token is not set (calendar/drive gate)
    assert has_oauth_credential(store, org, "google") is True


def test_org_id_coerced_to_str():
    org = uuid4()
    # store is keyed by str(org) — the helper must coerce UUID → str
    store = _Store({(str(org), "google"): SimpleNamespace(tokens={"access_token": "x"})})
    assert has_oauth_credential(store, org, "google") is True
