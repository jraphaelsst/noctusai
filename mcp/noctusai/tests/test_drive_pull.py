"""Tests for `noctus.dev.drive_pull` — the zero-token Drive→private-disk mirror.

Zero network: these exercise the pure parts (path safety, NFC naming, dedupe, the refusals that
guard the OAuth hand-off). The live Drive path is verified by running the tool against a real
folder (roadmap `sw-drive-extraction-2026-09`, P0a).
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "seed" / "lib" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import drive_pull as D  # noqa: E402


@pytest.fixture()
def private(tmp_path, monkeypatch):
    root = tmp_path / "private"
    monkeypatch.setenv("NOCTUS_PRIVATE_DIR", str(root))
    return root


def test_private_root_refuses_a_path_inside_the_repo(monkeypatch) -> None:
    monkeypatch.setenv("NOCTUS_PRIVATE_DIR", str(Path(D.REPO_ROOT) / "private"))
    with pytest.raises(ValueError, match="inside the repo"):
        D.private_root()


def test_private_root_honours_env(private) -> None:
    assert D.private_root() == private.resolve()


def test_safe_segment_nfc_normalises_decomposed_names() -> None:
    decomposed = unicodedata.normalize("NFD", "CERTIDÕES")
    assert decomposed != "CERTIDÕES"
    assert D.safe_segment(decomposed) == "CERTIDÕES"


@pytest.mark.parametrize("raw,expected", [("a/b", "a∕b"), ("..", "_"), ("  ", "_"), ("x\x00y", "xy")])
def test_safe_segment_never_escapes_its_directory(raw: str, expected: str) -> None:
    assert D.safe_segment(raw) == expected


def test_dedupe_suffixes_same_named_siblings_with_their_drive_id() -> None:
    entries = [
        {"drive_id": "A1", "rel_path": "DOCS/x.pdf", "is_folder": False},
        {"drive_id": "B2", "rel_path": "DOCS/x.pdf", "is_folder": False},
        {"drive_id": "C3", "rel_path": "DOCS/y.pdf", "is_folder": False},
    ]
    D._dedupe_rel_paths(entries)
    assert [e["rel_path"] for e in entries] == ["DOCS/x [A1].pdf", "DOCS/x [B2].pdf", "DOCS/y.pdf"]


def test_auth_finish_reports_google_refusal(private) -> None:
    out = D.auth_finish("http://localhost:8011/cb?error=access_denied&state=abcdefghijklmnopqrst")
    assert out["ok"] is False and "access_denied" in out["error"]


def test_auth_finish_requires_code_and_state(private) -> None:
    out = D.auth_finish("http://localhost:8011/cb?code=xyz")
    assert out == {"ok": False, "action": "auth_finish", "error": "redirected_url has no code/state"}


def test_auth_finish_rejects_a_path_shaped_state(private) -> None:
    out = D.auth_finish("http://localhost:8011/cb?code=xyz&state=../../etc/passwd")
    assert out["error"] == "malformed state"


def test_auth_finish_rejects_unknown_state(private) -> None:
    out = D.auth_finish("http://localhost:8011/cb?code=xyz&state=abcdefghijklmnopqrst")
    assert "unknown state" in out["error"]


def test_auth_finish_rejects_an_expired_pending_consent(private) -> None:
    state = "abcdefghijklmnopqrst"
    pending = D._token_dir() / f".pending-{state}.json"
    pending.write_text(
        json.dumps(
            {
                "account_email": "a@b.c",
                "redirect_uri": D.DEFAULT_REDIRECT_URI,
                "code_verifier": "v",
                "created_at": time.time() - D._PENDING_TTL_S - 1,
            }
        ),
        encoding="utf-8",
    )
    out = D.auth_finish(f"http://localhost:8011/cb?code=xyz&state={state}")
    assert "expired" in out["error"]
    assert not pending.exists(), "a consumed pending consent must not be replayable"


def test_token_dir_is_owner_only(private) -> None:
    assert (D._token_dir().stat().st_mode & 0o777) == 0o700


def test_pull_without_a_token_names_the_auth_steps(private) -> None:
    with pytest.raises(FileNotFoundError, match="auth_start"):
        D.drive_pull(action="pull", folder_id="F", account_email="nobody@example.com")


def test_unknown_action_is_refused() -> None:
    with pytest.raises(ValueError, match="auth_start \\| auth_finish \\| pull"):
        D.drive_pull(action="download")


class _Resp:
    def __init__(self, status):
        self.status = status


class _HttpLike(Exception):
    def __init__(self, status):
        super().__init__(f"http {status}")
        self.resp = _Resp(status)


def test_a_transient_timeout_is_retried_then_succeeds() -> None:
    calls, sleeps = [], []

    def fetch():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("The read operation timed out")

    assert D._fetch_with_retry(fetch, sleep=sleeps.append) == 3
    assert sleeps == [2.0, 5.0]


def test_retries_are_bounded_and_the_last_error_surfaces() -> None:
    def fetch():
        raise _HttpLike(503)

    with pytest.raises(_HttpLike):
        D._fetch_with_retry(fetch, sleep=lambda _s: None)


@pytest.mark.parametrize("status", [403, 404])
def test_a_permanent_error_is_never_retried(status: int) -> None:
    calls = []

    def fetch():
        calls.append(1)
        raise _HttpLike(status)

    with pytest.raises(_HttpLike):
        D._fetch_with_retry(fetch, sleep=lambda _s: None)
    assert len(calls) == 1
