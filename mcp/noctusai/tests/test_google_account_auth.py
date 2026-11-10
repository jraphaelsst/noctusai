"""Tests for `noctus.dev.google_account_auth` — offline, Fakes injected through the tool's own seams."""
from __future__ import annotations

import json
import stat
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "seed" / "lib" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import google_account_auth as G  # noqa: E402

P = "https://www.googleapis.com/auth/"
WANT = [P + "calendar.events", P + "drive.readonly", P + "drive.file"]
EMAIL = "owner@example.com"


class FakeProvider:
    def __init__(self, granted: list[str], refresh: str | None = "rt-1") -> None:
        self.granted, self.refresh = granted, refresh
        self.asked: list[str] = []

    async def authorization_url(self, state, scopes, redirect_uri):
        self.asked = list(scopes)
        return SimpleNamespace(url=f"https://accounts.example/auth?state={state}", code_verifier="v" * 43)

    async def exchange_code(self, code, state, redirect_uri, code_verifier):
        assert code_verifier == "v" * 43
        return SimpleNamespace(refresh_token=self.refresh, scope=self.granted)


@pytest.fixture()
def private(tmp_path, monkeypatch):
    monkeypatch.setenv("NOCTUS_PRIVATE_DIR", str(tmp_path / "private"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "sec")
    return tmp_path / "private"


def _start(prov, profile="assistant", scopes=None):
    out = G.auth_start(profile, EMAIL, scopes or ["calendar.events", "drive.readonly", "drive.file"], prov=prov)
    return out, f"http://localhost:8011/cb?code=c&state={out['state']}"


def test_scope_allowlist_refuses_unknown_and_accepts_short_names() -> None:
    assert G.normalize_scopes(["calendar.events", P + "drive.file"]) == [P + "calendar.events", P + "drive.file"]
    with pytest.raises(ValueError, match="not allowed"):
        G.normalize_scopes(["gmail.send"])
    with pytest.raises(ValueError, match="not allowed"):
        G.normalize_scopes([P + "drive"])


def test_auth_start_requests_scopes_and_parks_pending_per_profile(private) -> None:
    prov = FakeProvider(WANT)
    out, _ = _start(prov)
    assert prov.asked == WANT and out["ok"] and "login_hint" in out["consent_url"]
    assert (private / "google-accounts" / "assistant" / f".pending-{out['state']}.json").exists()
    assert not (private / "google-accounts" / "other").exists()


def test_bad_profile_and_email_are_refused(private) -> None:
    with pytest.raises(ValueError, match="kebab"):
        G.auth_start("../x", EMAIL, ["drive.file"], prov=FakeProvider(WANT))
    with pytest.raises(ValueError, match="email"):
        G.auth_start("assistant", "a/b@c.d", ["drive.file"], prov=FakeProvider(WANT))


def test_finish_stores_0600_token_at_profile_path_and_status_hides_secrets(private) -> None:
    prov = FakeProvider(WANT)
    _, url = _start(prov)
    out = G.auth_finish("assistant", url, prov=prov, email_probe=lambda c, g: EMAIL)
    assert out["ok"] and out["missing_scopes"] == []
    path = private / "google-accounts" / "assistant" / f"{EMAIL}.json"
    assert out["token_path"] == str(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    st = G.status("assistant", EMAIL)
    assert st["authorized"] and st["accounts"][0]["scopes"] == WANT
    assert "rt-1" not in json.dumps(st)
    creds = G.load_credentials("assistant", EMAIL)
    assert creds.refresh_token == "rt-1" and list(creds.scopes) == WANT


def test_email_mismatch_is_refused_and_not_stored(private) -> None:
    prov = FakeProvider(WANT)
    _, url = _start(prov)
    out = G.auth_finish("assistant", url, prov=prov, email_probe=lambda c, g: "other@example.com")
    assert out["ok"] is False and "not stored" in out["error"]
    assert not list((private / "google-accounts" / "assistant").glob("*.json"))
    assert G.status("assistant", EMAIL)["authorized"] is False


def test_missing_scopes_are_reported_not_passed(private) -> None:
    prov = FakeProvider([P + "calendar.events", P + "drive.file"])
    _, url = _start(prov)
    out = G.auth_finish("assistant", url, prov=prov, email_probe=lambda c, g: EMAIL)
    assert out["ok"] is False and out["missing_scopes"] == [P + "drive.readonly"]
    assert out["scopes"] == [P + "calendar.events", P + "drive.file"]


def test_no_refresh_token_and_replay_and_expiry(private) -> None:
    prov = FakeProvider(WANT, refresh=None)
    _, url = _start(prov)
    assert "no refresh_token" in G.auth_finish("assistant", url, prov=prov)["error"]
    assert "unknown state" in G.auth_finish("assistant", url, prov=prov)["error"]  # consumed
    out, url2 = _start(FakeProvider(WANT))
    pend = private / "google-accounts" / "assistant" / f".pending-{out['state']}.json"
    d = json.loads(pend.read_text())
    d["created_at"] = time.time() - 10_000
    pend.write_text(json.dumps(d))
    assert "expired" in G.auth_finish("assistant", url2, prov=prov)["error"]


def test_profiles_do_not_share_state_or_tokens(private) -> None:
    prov = FakeProvider(WANT)
    _, url = _start(prov, profile="assistant")
    assert "unknown state" in G.auth_finish("other", url, prov=prov)["error"]


def test_load_credentials_without_token_names_the_steps(private) -> None:
    with pytest.raises(FileNotFoundError, match="auth_start"):
        G.load_credentials("assistant", EMAIL)


def test_unknown_action_is_refused() -> None:
    with pytest.raises(ValueError, match="auth_start \\| auth_finish \\| status"):
        G.google_account_auth(action="x", profile="assistant")


def test_default_provider_is_scope_exact(monkeypatch):
    """The real default provider for profile tokens never asks Google to merge earlier grants."""
    import asyncio
    from tools.noctus.dev import _google_oauth

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "sec")
    prov = _google_oauth.provider(include_granted_scopes=False)
    url = asyncio.run(prov.authorization_url("s", ["https://www.googleapis.com/auth/drive.file"], "http://x/cb")).url
    assert "include_granted_scopes" not in url
