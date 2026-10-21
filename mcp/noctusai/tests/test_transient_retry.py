"""Transient-retry chokepoint + verify_db_guards `unverified_transient` / `probe_ids` rerun.
Hermetic: injected sleep/rng and a stubbed urlopen-free executor; no network."""
from __future__ import annotations

import io
import socket
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev import _transient_retry as TR  # noqa: E402
from tools.noctus.dev.verify_db_guards import GuardProbe, run_probe, verify_db_guards  # noqa: E402


def _http(code, retry_after=None):
    h = Message()
    if retry_after is not None:
        h["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("http://x", code, "r", h, io.BytesIO(b"{}"))


def _dns():
    return urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided, or not known"))


def _run(errors, **kw):
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return "ok"

    out = TR.call_with_transient_retry(fn, sleep=sleeps.append, rng=lambda: 0.0, **kw)
    return out, len(calls), sleeps


def test_retries_dns_then_succeeds_paced_1_3_9():
    out, n, sleeps = _run([_dns(), _dns(), _dns()])
    assert (out, n, sleeps) == ("ok", 4, [1.0, 3.0, 9.0])


def test_gives_up_after_three_retries_raising_original():
    err = _dns()
    calls = []

    def fn():
        calls.append(1)
        raise err

    with pytest.raises(urllib.error.URLError) as ei:
        TR.call_with_transient_retry(fn, sleep=lambda s: None, rng=lambda: 0.0)
    assert ei.value is err and len(calls) == 4


def test_http_400_is_never_retried():
    """A NOC_PROBE refusal is a 400 and a PASS -- must never be retried."""
    calls = []

    def fn():
        calls.append(1)
        raise _http(400)

    with pytest.raises(urllib.error.HTTPError):
        TR.call_with_transient_retry(fn, sleep=lambda s: None)
    assert len(calls) == 1


@pytest.mark.parametrize("code", [429, 502, 503, 504])
def test_retryable_http_statuses(code):
    out, n, _ = _run([_http(code)])
    assert (out, n) == ("ok", 2)


def test_retry_after_is_respected_and_capped():
    _, _, sleeps = _run([_http(429, 5)])
    assert sleeps == [5.0]
    _, _, sleeps = _run([_http(429, 9999)])
    assert sleeps == [30.0]


def test_read_timeout_retried_unless_ambiguous_disabled():
    out, n, _ = _run([TimeoutError("The read operation timed out")])
    assert (out, n) == ("ok", 2)
    with pytest.raises(TimeoutError):
        _run([TimeoutError("t")], retry_ambiguous=False)
    # a request that provably never left (DNS) is still retried for writers
    out, n, _ = _run([_dns()], retry_ambiguous=False)
    assert (out, n) == ("ok", 2)


def test_non_transport_error_not_retried():
    with pytest.raises(ValueError):
        _run([ValueError("boom")])


# -- verify_db_guards -------------------------------------------------------

def _probe(i):
    return GuardProbe(
        id=i, product="core", schema="public", guard_name="g", kind="write_refusal",
        sql="DO $noc_probe$ BEGIN RAISE EXCEPTION 'NOC_PROBE:refused: x'; END $noc_probe$;",
        rationale="r",
    )


class _Exec:
    def __init__(self, transient_ids):
        self.transient_ids = set(transient_ids)
        self.ran = []

    def execute(self, sql):
        pid = next((p for p in ("p1", "p2", "p3") if f"/*{p}*/" in sql), None)
        self.ran.append(pid)
        if pid in self.transient_ids:
            return {"ok": False, "rows": None, "error": "The read operation timed out", "transient": True}
        return {"ok": False, "rows": None, "error": "HTTP 400: NOC_PROBE:refused: x"}


def _tagged(i):
    p = _probe(i)
    return GuardProbe(**{**p.__dict__, "sql": p.sql.replace("DO $noc_probe$", f"DO $noc_probe$ /*{i}*/ ", 1)})


def test_run_probe_marks_transient_distinct_from_failure():
    r = run_probe(_tagged("p1"), _Exec({"p1"}))
    assert r["status"] == "unverified_transient"


def test_verify_returns_retry_ids_and_probe_ids_reruns_only_those():
    reg = tuple(_tagged(i) for i in ("p1", "p2", "p3"))
    ex = _Exec({"p2"})
    r = verify_db_guards(executor=ex, registry=reg, ledger_lookup=lambda p: None)
    assert r["status"] == "unverified_transient" and r["retry_probe_ids"] == ["p2"] and not r["failures"]
    ex2 = _Exec(set())
    r2 = verify_db_guards(executor=ex2, registry=reg, ledger_lookup=lambda p: None, probe_ids=r["retry_probe_ids"])
    assert ex2.ran == ["p2"] and r2["status"] == "clean" and r2["checked"] == 1


def test_unknown_probe_ids_is_error():
    r = verify_db_guards(executor=_Exec(set()), registry=(_tagged("p1"),), probe_ids=["nope"])
    assert r["status"] == "error"
