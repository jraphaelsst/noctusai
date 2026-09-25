"""Colocated tests for ``noctus.dev.toolkit_freshness`` — the stale-MCP-server
guard (2026-09-18 incident: ~30 hours of two-day-old ``task_branch.py`` code
silently answered every ``noctus.dev.*`` call because a long-lived Python
process never re-reads a module's file after import).

Design of the fixtures below: `stale_toolkit` / `fresh_toolkit` seed
``toolkit_freshness``'s module-level baseline with a REAL, disposable tmp
file (via `monkeypatch.setattr`, auto-reverted after each test — no
cross-test leakage), then genuinely change (or not) that file's bytes on
disk. `check()` / `warn_gate()` / `refuse_gate()` are never mocked — every
test below exercises their REAL stat-comparison logic against a controlled
tmp file, never the actual `mcp/noctusai` tree (no repo file is ever
touched). This is dependency-injection of the STATE those functions read
(the same seam this codebase already uses everywhere — `products_dir=
tmp_path`, `git_runner=FakeGitRunner(...)`), not a monkeypatch of the guard's
decision logic — the guard itself always runs for real.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import deploy_image as DI  # noqa: E402
from tools.noctus.dev import deploy_verify as DV  # noqa: E402
from tools.noctus.dev import migrate_product as MP  # noqa: E402
from tools.noctus.dev import predeploy_check as PC  # noqa: E402
from tools.noctus.dev import release as REL  # noqa: E402
from tools.noctus.dev import spa_smoke as SS  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402
from tools.noctus.dev import toolkit_freshness as TF  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — seed the module's baseline with a disposable tmp file
# ---------------------------------------------------------------------------


def _seed_baseline(tmp_path: Path, monkeypatch, name: str) -> Path:
    f = tmp_path / name
    f.write_text("# v1 — the bytes this process 'loaded'\n")
    st = f.stat()
    monkeypatch.setattr(TF, "_baseline", {str(f): (st.st_mtime, st.st_size)})
    monkeypatch.setattr(TF, "_loaded_at", time.time())
    monkeypatch.setattr(TF, "_cached_verdict", None)
    monkeypatch.setattr(TF, "_cached_at", 0.0)
    return f


@pytest.fixture
def stale_toolkit(tmp_path, monkeypatch):
    """Seeds a baseline, then REALLY changes the file on disk afterwards —
    every consumer of `check()` should see genuine drift."""
    f = _seed_baseline(tmp_path, monkeypatch, "loaded_module.py")
    f.write_text("# v2 — genuinely changed on disk AFTER the baseline\n")
    return f


@pytest.fixture
def fresh_toolkit(tmp_path, monkeypatch):
    """Seeds a baseline that matches the current on-disk state exactly —
    the positive control: nothing should report stale."""
    return _seed_baseline(tmp_path, monkeypatch, "loaded_module_fresh.py")


def _minimal_fake_git():
    """Answers every git subcommand task_branch's `status` action needs with
    a trivially-empty, zero-worktree tree — zero real git processes."""
    def run(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "worktree":
            return (0, "", "")  # empty porcelain → no active self-branch worktrees
        return (0, "", "")
    return run


def _fake_git_with_refs(refs: dict[str, str]):
    """A slightly richer fake for `action='start'` dry-run: resolves the
    given ref names (e.g. `origin/dev`) via `rev-parse`, everything else
    answers empty/ok — zero real git processes."""
    calls: list[tuple] = []

    def run(cmd, cwd=None):
        calls.append((cmd, cwd))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "rev-parse":
            sha = refs.get(cmd[-1])
            return (0, sha + "\n", "") if sha else (1, "", "bad ref")
        if sub == "worktree":
            return (0, "", "")
        return (0, "", "")

    run.calls = calls
    return run


def _fake_release_git_all_up_to_date():
    """`release()`-shaped fake (F1, compliance review 2026-09-24): resolves
    EVERY ref (`origin/dev`, `origin/main`, `origin/prod`, `origin/prod-
    backup`) to the SAME sha, so `stage='promote'` reads `prod == target`
    and returns `up_to_date` before any push is even considered — the
    safest possible fixture for "does the wrapper refuse to push", never
    the real repo. Any `push` call is a hard test failure via
    `AssertionError`, doubling the sitewide conftest guard for this one
    call site specifically."""
    def run(cmd, env_extra=None, stdin=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "push":
            raise AssertionError(f"fake release git must never push: {cmd!r}")
        if sub == "fetch":
            return (0, "", "")
        if sub == "rev-parse":
            return (0, "same-sha\n", "")
        if sub == "merge-base":
            return (0, "", "")  # --is-ancestor: rc=0 -> "is an ancestor"
        if sub in ("log", "diff"):
            return (0, "", "")
        return (0, "", "")

    return run


SHELL = '<html><body><div id="root"></div><script src="/assets/index-abc.js"></script></body></html>'
BUNDLE = ("// app\n" + "x" * 20_000).encode()


def _spa_responder():
    mapping = {
        "/assets/index-abc.js": (200, BUNDLE, "application/javascript"),
        "/login": (200, b"<html></html>", "text/html"),
        "/": (200, SHELL.encode(), "text/html"),
    }

    def _fetch(url, timeout=25):
        for suffix, resp in mapping.items():
            if url.endswith(suffix):
                return resp
        return 404, b"", ""
    return _fetch


# ---------------------------------------------------------------------------
# Core mechanism
# ---------------------------------------------------------------------------


def test_fresh_when_baseline_matches_disk(fresh_toolkit):
    v = TF.check(bypass_cache=True)
    assert v["status"] == "fresh"
    assert v["changed_files"] == []
    assert v["deleted_files"] == []


def test_changed_file_is_detected(stale_toolkit):
    v = TF.check(bypass_cache=True)
    assert v["status"] == "stale"
    assert len(v["changed_files"]) == 1
    assert v["changed_files"][0]["path"] == str(stale_toolkit)
    assert v["deleted_files"] == []


def test_deleted_file_is_detected(fresh_toolkit):
    fresh_toolkit.unlink()
    v = TF.check(bypass_cache=True)
    assert v["status"] == "stale"
    assert v["deleted_files"] == [str(fresh_toolkit)]
    assert v["changed_files"] == []


def test_ttl_cache_does_not_mask_a_change_forever(tmp_path, monkeypatch):
    f = _seed_baseline(tmp_path, monkeypatch, "ttl_module.py")

    v0 = TF.check(ttl_seconds=0.2)
    assert v0["status"] == "fresh" and v0["from_cache"] is False

    # Genuinely change the file, but stay INSIDE the TTL window.
    f.write_text("# v2 — changed inside the TTL window\n")
    v1 = TF.check(ttl_seconds=0.2)
    assert v1["status"] == "fresh" and v1["from_cache"] is True, (
        "expected the TTL-cached (stale-in-the-good-sense) verdict to still "
        "mask the change inside the window"
    )

    # Cross the TTL boundary — a real stat pass must now see the change.
    time.sleep(0.25)
    v2 = TF.check(ttl_seconds=0.2)
    assert v2["status"] == "stale" and v2["from_cache"] is False, (
        "a change must be seen after the TTL elapses — the cache must not "
        "mask it indefinitely"
    )


def test_check_is_cheap_under_a_burst_of_calls():
    """The cheapness claim, measured: once the verdict is cached, a burst of
    calls (the '185 tools might all call this' scenario) costs microseconds
    each, not one stat pass each."""
    TF.capture_baseline(force=False)  # idempotent; real baseline either way
    first = TF.check(bypass_cache=True)
    assert "check_duration_ms" in first and first["check_duration_ms"] >= 0

    t0 = time.perf_counter()
    for _ in range(1000):
        TF.check(ttl_seconds=5.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50, (
        f"1000 cached checks took {elapsed_ms:.2f}ms total — caching is not "
        "doing its job"
    )


# ---------------------------------------------------------------------------
# WARN posture: predeploy_check, deploy_verify, spa_smoke,
# task_branch action='status' / any confirm=False plan call
# ---------------------------------------------------------------------------


def test_predeploy_check_warns_and_still_answers_when_stale(stale_toolkit):
    r = PC.predeploy_check("")  # the empty-product fast, zero-IO error path
    assert r["status"] == "error"  # never refused — WARN posture still answers
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_deploy_verify_warns_and_still_answers_when_stale(stale_toolkit):
    r = DV.deploy_verify(run_local=lambda cmd: (1, "", "no real git in tests"))
    assert r["status"] == "error"  # can't resolve expected sha — zero real IO
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_spa_smoke_warns_and_still_answers_when_stale(stale_toolkit, monkeypatch):
    monkeypatch.setattr(SS, "_fetch", _spa_responder())
    r = SS.spa_smoke(products=["core"])
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_task_branch_status_action_warns_and_still_answers_when_stale(stale_toolkit):
    r = T.task_branch(action="status", run=_minimal_fake_git())
    assert r["status"] == "status"  # never refused — WARN posture still answers
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_task_branch_status_action_never_refused_even_with_confirm_true(stale_toolkit):
    """`action='status'` never inspects `confirm` — it must stay WARN-only
    regardless of what a caller passes for it."""
    r = T.task_branch(action="status", confirm=True, run=_minimal_fake_git())
    assert r["status"] != "refused_stale_toolkit"
    assert r["toolkit_stale"] is True


def test_task_branch_start_dry_run_is_only_warned_not_refused_when_stale(stale_toolkit):
    """confirm=False never provisions anything — WARN, never REFUSE."""
    fake = _fake_git_with_refs({"origin/dev": "d0"})
    r = T.task_branch(action="start", slug="feat-x", confirm=False, run=fake)
    assert r["status"] != "refused_stale_toolkit"
    assert r["toolkit_stale"] is True


def test_warn_posture_fresh_call_carries_no_warning(fresh_toolkit):
    """The verdict rides on every return, but a fresh toolkit never gets a
    manufactured warning — no silent-swallow in either direction."""
    r = PC.predeploy_check("")
    assert r["toolkit_stale"] is False
    assert "warnings" not in r


# ---------------------------------------------------------------------------
# R4 (release-no-freeze, 2026-09-24): a stale-and-confirm=True write no
# longer hard-refuses — it re-runs FRESH, in a brand-new `python
# mcp/noctusai/cli.py` subprocess, against the current on-disk code. Every
# test below injects a `subprocess_run` DI seam (zero real subprocesses,
# matching every OTHER "zero real X" seam already used in this file) and
# deliberately prefixes the canned payload with realistic log noise, so a
# passing test proves the TRAILING-JSON extraction, not a lucky clean-stdout
# accident.
# ---------------------------------------------------------------------------


def _canned_subprocess(payload: dict, rc: int = 0, prefix_noise: bool = True):
    """A fake `subprocess_run(cmd) -> (rc, stdout, stderr)` DI seam. Spawns
    ZERO real processes. `prefix_noise=True` (default) prepends a realistic
    INFO log line ahead of the JSON — `cli.py`'s own env_bootstrap logging
    lands on stdout too, not only stderr (found wiring this very
    fallback) — so a test using this exercises `_extract_trailing_json`,
    never a naive whole-blob `json.loads`."""
    import json as _json

    text = _json.dumps(payload, indent=2)
    if prefix_noise:
        text = "2026-09-24 00:00:00 | INFO | noise emitted before the final JSON\n" + text
    calls: list[list[str]] = []

    def run(cmd: list[str]):
        calls.append(cmd)
        return rc, text, ""

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _forbidden_subprocess():
    """A `subprocess_run` DI seam that must NEVER be invoked — records every
    call (never raises: `_run_via_fresh_subprocess` catches broad launcher
    exceptions, which would otherwise swallow a raised assertion into a
    plain refusal payload instead of failing the test loudly). Assert
    `spy.calls == []` after the call under test."""
    calls: list[list[str]] = []

    def spy(cmd: list[str]):
        calls.append(cmd)
        return 0, '{"status": "should_never_be_read", "exit_code": 0}', ""

    spy.calls = calls  # type: ignore[attr-defined]
    return spy


def test_extract_trailing_json_skips_leading_log_noise():
    noisy = "INFO some log line\nmore noise\n{\n  \"status\": \"ok\",\n  \"n\": 1\n}\n"
    assert TF._extract_trailing_json(noisy) == {"status": "ok", "n": 1}


def test_extract_trailing_json_returns_none_on_garbage():
    assert TF._extract_trailing_json("not json at all, no brace line") is None
    assert TF._extract_trailing_json("") is None


def test_extract_trailing_json_picks_the_top_level_brace_not_a_nested_one():
    """A payload with a list-of-dicts value (e.g. release's rider `commits`)
    has NESTED `{` lines too — indented, never at column 0. A naive
    `.strip() == "{"` match would wrongly grab the LAST (nested) one and
    fail to parse; the real top-level brace must win."""
    import json as _json

    payload = {"status": "manifest", "commits": [{"sha": "abc", "project": "p"},
                                                  {"sha": "def", "project": "q"}]}
    noisy = "INFO noise\n" + _json.dumps(payload, indent=2) + "\n"
    assert TF._extract_trailing_json(noisy) == payload


def test_tool_cli_argv_mapping_for_every_wired_tool():
    """The exact serialization each `refuse_gate` consumer's fresh-subprocess
    fallback would invoke — pinned so a future param rename in one of these
    4 tools is caught here, not silently mis-mapped at 2am. `--flag=value`
    (F3, compliance review 2026-09-24), never a bare value as its own argv
    element — see `_tool_cli_argv`'s module comment for why."""
    assert TF._tool_cli_argv("release", {"stage": "bless", "confirm": True}) == [
        "--release=bless", "--release-confirm",
    ]
    assert TF._tool_cli_argv("release", {
        "stage": "promote", "confirm": True, "sha": "abc123", "mode": "ff",
    }) == ["--release=promote", "--release-confirm", "--release-sha=abc123"]
    assert TF._tool_cli_argv("migrate_product", {
        "product": "widgets", "confirm": True, "sha": "deadbeef",
    }) == ["--migrate-product=widgets", "--migrate-product-confirm",
           "--migrate-product-sha=deadbeef"]
    assert TF._tool_cli_argv("migrate_product", {"confirm": True}) is None  # no product
    assert TF._tool_cli_argv("deploy_image", {
        "product": "core", "confirm": True, "tag": "v2", "source": "local",
    }) == ["--deploy-image=core", "--deploy-image-confirm",
           "--deploy-image-tag=v2", "--deploy-image-source=local"]
    assert TF._tool_cli_argv("task_branch", {
        "action": "start", "slug": "feat-x", "confirm": True, "wire_env": False,
    }) == ["--task-branch=start", "--task-branch-slug=feat-x",
           "--task-branch-confirm", "--task-branch-no-wire-env"]
    assert TF._tool_cli_argv("no_such_tool", {}) is None


def test_tool_cli_argv_value_starting_with_dash_is_unambiguous():
    """F3: a value that itself starts with `-` must not be misread by
    argparse as a second flag — `--flag=value` (a single argv element) is
    immune to this regardless of what `value` contains; two SEPARATE
    elements (`["--flag", "-value"]`) would not be."""
    import cli as _cli  # local: importing cli.py has module-level side effects
                        # (logging reconfiguration) — scope them to this test.

    argv = TF._tool_cli_argv("release", {"stage": "promote", "confirm": True, "sha": "-abc123"})
    assert argv == ["--release=promote", "--release-confirm", "--release-sha=-abc123"]
    parser = _cli.build_parser()
    args = parser.parse_args(argv)
    assert args.release_sha == "-abc123"


class _FakeMcpServer:
    """F3 (compliance review, 2026-09-24): captures each `@server.tool(...)`-
    decorated function by its MCP name, unchanged — the SAME `.tool(name=...,
    description=...)` shape this suite already fakes elsewhere (e.g.
    `test_deploy_image.py::test_tool_registers_with_dotted_name`), just
    keeping every registration instead of only the last one (`migrate_
    product.py` registers TWO tools)."""

    def __init__(self):
        self.captured: dict[str, Callable] = {}

    def tool(self, *, name, description=""):
        def deco(fn):
            self.captured[name] = fn
            return fn
        return deco


def _register_all_gated_tools() -> dict[str, Callable]:
    from tools.noctus.dev import deploy_image as _di_mod
    from tools.noctus.dev import migrate_product as _mp_mod
    from tools.noctus.dev import release as _rel_mod
    from tools.noctus.dev import task_branch as _tb_mod

    srv = _FakeMcpServer()
    _rel_mod.register(srv)
    _mp_mod.register(srv)
    _di_mod.register(srv)
    _tb_mod.register(srv)
    return srv.captured


def test_every_register_wrapper_param_is_in_mapped_params():
    """F3: `_MAPPED_PARAMS[tool]` must cover EVERY parameter an MCP caller
    can actually pass (the `register()` wrapper's own signature — the real
    ceiling on what a caller can ask for) — not just whatever `_tool_cli_
    argv` happens to read today. A wrapper param missing from the mapped
    set would be silently unreachable by the fresh-subprocess fallback
    even though a real MCP caller (not just a test) could pass it."""
    import inspect as _inspect

    captured = _register_all_gated_tools()
    checks = {
        "release": captured["noctus.dev.release"],
        "migrate_product": captured["noctus.dev.migrate_product"],
        "deploy_image": captured["noctus.dev.deploy_image"],
        "task_branch": captured["noctus.dev.task_branch"],
    }
    for tool_name, wrapper_fn in checks.items():
        wrapper_params = set(_inspect.signature(wrapper_fn).parameters) - {"allow_stale_toolkit"}
        mapped = TF._MAPPED_PARAMS[tool_name]
        missing = wrapper_params - mapped
        assert not missing, (
            f"{tool_name}: register()'s MCP-exposed param(s) {missing} are "
            f"NOT in _MAPPED_PARAMS[{tool_name!r}] — an MCP caller could "
            "pass one of these and have it silently dropped on the "
            "fresh-subprocess hop."
        )


def test_every_wired_tools_argv_parses_cleanly_through_cli_argparse():
    """F3: every `_tool_cli_argv` output for every wired tool must actually
    parse through the REAL `cli.py` parser (built once, `build_parser()`,
    never a second hand-maintained copy) into the exact values the fake
    kwargs specified — not just 'well-formed enough to eyeball'."""
    import cli as _cli  # local: scope the module-level side effect to this test

    parser = _cli.build_parser()

    cases = [
        ("release", {"stage": "bless", "confirm": True, "mode": "cut",
                     "release_branch": "release/20260924-0000"},
         {"release": "bless", "release_confirm": True, "release_mode": "cut",
          "release_branch": "release/20260924-0000"}),
        ("migrate_product", {"product": "widgets", "confirm": True, "sha": "deadbeef",
                             "allow_stale_tree": True},
         {"migrate_product": "widgets", "migrate_product_confirm": True,
          "migrate_product_sha": "deadbeef", "migrate_product_allow_stale_tree": True}),
        ("deploy_image", {"product": "core", "confirm": True, "tag": "v2",
                          "skip_ancestry_check": True},
         {"deploy_image": "core", "deploy_image_confirm": True,
          "deploy_image_tag": "v2", "deploy_image_skip_ancestry_check": True}),
        ("task_branch", {"action": "cleanup", "slug": "feat-x", "confirm": True,
                         "verbose": True},
         {"task_branch": "cleanup", "task_branch_slug": "feat-x",
          "task_branch_confirm": True, "task_branch_verbose": True}),
    ]
    for tool_name, kwargs, expect_attrs in cases:
        argv = TF._tool_cli_argv(tool_name, kwargs)
        args = parser.parse_args(argv)
        for attr, expected in expect_attrs.items():
            assert getattr(args, attr) == expected, (
                f"{tool_name}: argv {argv} -> args.{attr} = "
                f"{getattr(args, attr)!r}, expected {expected!r}"
            )


def test_fresh_subprocess_hard_refuses_when_no_cli_entry_is_wired(stale_toolkit):
    """Fail-closed for a FUTURE `refuse_gate` consumer that forgot to add a
    `_tool_cli_argv` entry — never guesses at a CLI shape."""

    @TF.refuse_gate("no_such_tool")
    def _toy(confirm: bool = False):
        return {"status": "should_never_run", "exit_code": 0}

    r = _toy(confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert "no_such_tool" in r["error"] and "No fresh-subprocess CLI entry" in r["error"]


def test_fresh_subprocess_hard_refuses_when_the_launch_itself_fails(stale_toolkit):
    """PRE-LAUNCH failure — the child process never actually started (e.g.
    the interpreter itself could not be exec'd) — so 'refused, nothing
    touched' is still an accurate status. Distinct from a POST-LAUNCH
    failure (below), which must NEVER claim a refusal."""
    def boom(cmd):
        raise OSError("no such file or directory")

    r = MP.migrate_product("widgets", confirm=True, subprocess_run=boom)
    assert r["status"] == "refused_stale_toolkit"
    assert "before the child could start" in r["error"]


# ── F2 (compliance review, 2026-09-24): POST-LAUNCH failures ───────────────
# Once the child process has actually STARTED, it may have begun (or even
# completed) a real write before we lost the ability to read its answer.
# Reporting `refused_stale_toolkit` here would be a LIE — a refusal means
# nothing was touched, and we no longer know that. Every case below must
# land on `status='fresh_subprocess_outcome_unknown'`, never a refusal.


def test_fresh_subprocess_outcome_unknown_on_unparseable_output(stale_toolkit):
    fake_run_broken = lambda cmd: (1, "not json, no brace line, just noise", "some stderr")  # noqa: E731

    r = MP.migrate_product("widgets", confirm=True, subprocess_run=fake_run_broken)
    assert r["status"] == "fresh_subprocess_outcome_unknown"
    assert r["exit_code"] == 1
    assert r["executed_via"] == "fresh_subprocess"
    assert r["rc"] == 1
    assert "some stderr" in r["stderr_tail"]
    assert "unparseable output" in r["error"]
    assert "not a refusal" in r["error"].lower() or "NOT a refusal" in r["error"]
    assert "migrate_product confirm=False" in r["verification_step"]


def test_fresh_subprocess_outcome_unknown_on_timeout(stale_toolkit):
    """A timeout means the child was KILLED — it may have been mid-write.
    `subprocess.TimeoutExpired` carries whatever stdout/stderr the child
    produced before it died; that partial output must ride on the result,
    not be swallowed."""
    import subprocess as _sp

    def times_out(cmd):
        raise _sp.TimeoutExpired(cmd=cmd, timeout=1800, output="partial stdout",
                                 stderr="partial stderr")

    r = REL.release(stage="promote", confirm=True, subprocess_run=times_out)
    assert r["status"] == "fresh_subprocess_outcome_unknown"
    assert r["exit_code"] == 1
    assert r["rc"] is None
    assert "partial stdout" in r["stdout_tail"]
    assert "partial stderr" in r["stderr_tail"]
    assert "timed out" in r["error"]
    assert "release stage='status'" in r["verification_step"]


def test_fresh_subprocess_outcome_unknown_verification_step_per_tool(stale_toolkit):
    """Every wired tool names ITS OWN verification step — never a generic
    one another tool's caller could misread as applicable to them."""
    fake_run_broken = lambda cmd: (1, "no brace here", "")  # noqa: E731

    r_deploy = DI.deploy_image("erp-imobiliario", confirm=True, subprocess_run=fake_run_broken)
    assert r_deploy["status"] == "fresh_subprocess_outcome_unknown"
    assert "deploy_verify" in r_deploy["verification_step"]

    r_task = T.task_branch(action="start", slug="feat-x", confirm=True,
                           subprocess_run=fake_run_broken)
    assert r_task["status"] == "fresh_subprocess_outcome_unknown"
    assert "task_branch action='status'" in r_task["verification_step"]


def test_fresh_subprocess_returns_the_childs_own_result_when_stale_on_stale(
    stale_toolkit,
):
    """The child ran to completion and its OWN refuse_gate ALSO saw a stale
    module graph and refused before writing — a fully KNOWN, verified
    outcome (refused, nothing touched). Must return the CHILD's own result
    (whatever status it legitimately carries) flagged, never a second,
    fabricated wrapper-level refusal."""
    fake_run = _canned_subprocess({"status": "refused_stale_toolkit", "exit_code": 1,
                                   "toolkit_stale": True, "error": "child's own refusal text"})
    r = MP.migrate_product("widgets", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "refused_stale_toolkit"  # the CHILD's own status, passed through
    assert r["error"] == "child's own refusal text"  # untouched — not rewritten by the wrapper
    assert r["executed_via"] == "fresh_subprocess"
    assert r["nested_toolkit_stale"] is True
    assert any("CHILD's own" in w for w in r["warnings"])


def test_fresh_subprocess_never_leaks_pythonpath_into_the_child_env(stale_toolkit, monkeypatch):
    """F2: the child must resolve mcp/noctusai/** the SAME way a bare
    `python mcp/noctusai/cli.py` invocation from a clean shell would —
    never inherit a stray PYTHONPATH some enclosing harness set. The
    cmd-only `subprocess_run=` DI seam can't see the real default runner's
    `env=` kwarg, so this patches `subprocess.run` itself (the one seam
    that CAN observe it) — a spy on the boundary call, not on our own
    decision logic."""
    monkeypatch.setenv("PYTHONPATH", "/some/worktree/products/x/backend")
    calls: list[dict] = []

    def spy(cmd, **kw):
        calls.append(kw)

        class _P:
            returncode = 0
            stdout = '{"status": "ok", "exit_code": 0}'
            stderr = ""

        return _P()

    monkeypatch.setattr(TF.subprocess, "run", spy)
    MP.migrate_product("widgets", confirm=True)
    assert calls, "subprocess.run was never invoked"
    assert "PYTHONPATH" not in calls[0]["env"]


def test_migrate_product_falls_back_to_fresh_subprocess_when_stale(stale_toolkit):
    fake_run = _canned_subprocess({"status": "applied", "exit_code": 0,
                                   "applied": ["001_seed.sql"]})
    r = MP.migrate_product("widgets", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "applied" and r["applied"] == ["001_seed.sql"]
    assert r["executed_via"] == "fresh_subprocess"
    # The PRIMARY process's own (stale) verdict rides on the result too —
    # distinguishable from the CHILD's own toolkit_stale (False here, since
    # the canned child result never set it).
    assert r["primary_toolkit_stale"] is True
    assert r["primary_toolkit_freshness"]["status"] == "stale"
    assert any("FRESH subprocess" in w for w in r["warnings"])
    assert len(fake_run.calls) == 1
    cmd = fake_run.calls[0]
    assert cmd[0] == sys.executable and cmd[1].endswith("cli.py")
    assert "--migrate-product=widgets" in cmd
    assert "--migrate-product-confirm" in cmd


def test_migrate_product_dry_run_is_only_warned_not_refused_when_stale(stale_toolkit):
    """confirm=False never touches the database — WARN, never REFUSE."""
    r = MP.migrate_product(
        "definitely-not-a-real-product-xyz", confirm=False,
        live_products_fn=lambda: ["definitely-not-a-real-product-xyz"],
    )
    assert r["status"] != "refused_stale_toolkit"
    assert r["toolkit_stale"] is True


def test_migrate_product_allow_stale_toolkit_reaches_the_real_function(
    stale_toolkit, tmp_path,
):
    """The escape hatch must actually bypass the refusal (proceed into the
    real function body), not just relabel the refusal."""
    products_dir = tmp_path / "products"
    mig_dir = products_dir / "widgets" / "backend" / "migrations"
    mig_dir.mkdir(parents=True)
    (mig_dir / "001_seed.sql").write_text("CREATE SCHEMA IF NOT EXISTS widgets;")
    fake_executor = MP.FakeSqlExecutor()
    fake_git = MP.FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            ("rev-list", "--count", "HEAD..origin/dev"): "0",
            ("status", "--porcelain"): "",
        }
    )
    spy = _forbidden_subprocess()
    r = MP.migrate_product(
        "widgets", confirm=True, allow_stale_toolkit=True,
        executor=fake_executor, products_dir=products_dir,
        git_runner=fake_git, live_products_fn=lambda: ["widgets"],
        subprocess_run=spy,
    )
    assert r["status"] != "refused_stale_toolkit"
    # The real function ran for real: it actually applied the migration via
    # the injected fake executor (proof the wrapper truly proceeded IN this
    # process), and the R4 subprocess fallback was never even attempted.
    assert r["applied"] == ["001_seed.sql"]
    assert r["toolkit_stale"] is True
    assert r["allow_stale_toolkit"] is True
    assert "executed_via" not in r
    assert spy.calls == []


def test_release_falls_back_to_fresh_subprocess_when_stale(stale_toolkit):
    fake_run = _canned_subprocess({"status": "promoted", "exit_code": 0})
    r = REL.release(stage="promote", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "promoted"
    assert r["executed_via"] == "fresh_subprocess"
    cmd = fake_run.calls[0]
    assert "--release=promote" in cmd
    assert "--release-confirm" in cmd


def test_deploy_image_falls_back_to_fresh_subprocess_when_stale(stale_toolkit):
    fake_run = _canned_subprocess({"status": "deployed", "exit_code": 0})
    r = DI.deploy_image("erp-imobiliario", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "deployed"
    assert r["executed_via"] == "fresh_subprocess"
    cmd = fake_run.calls[0]
    assert "--deploy-image=erp-imobiliario" in cmd
    assert "--deploy-image-confirm" in cmd


# task_branch is the INCIDENT tool: "mutates prod" was never the real line —
# "can a stale version silently produce a plausible-looking wrong result?"
# is. A stale `action=start confirm=True` once returned status='started',
# exit 0, and a worktree that looked fine, while silently skipping the
# .env/node_modules provisioning. Every test below still runs ZERO real git
# (and, R4, ZERO real subprocesses) — the fresh-subprocess DI seam short-
# circuits before task_branch's body (and therefore any real git call) runs.
def test_task_branch_falls_back_to_fresh_subprocess_for_start_when_stale(stale_toolkit):
    fake_run = _canned_subprocess({"status": "started", "exit_code": 0})
    r = T.task_branch(action="start", slug="feat-x", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "started"
    assert r["executed_via"] == "fresh_subprocess"
    cmd = fake_run.calls[0]
    assert "--task-branch=start" in cmd
    assert "--task-branch-slug=feat-x" in cmd
    assert "--task-branch-confirm" in cmd


def test_task_branch_falls_back_to_fresh_subprocess_for_integrate_when_stale(stale_toolkit):
    fake_run = _canned_subprocess({"status": "integrated", "exit_code": 0})
    r = T.task_branch(action="integrate", slug="feat-x", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "integrated"
    assert r["executed_via"] == "fresh_subprocess"


def test_task_branch_falls_back_to_fresh_subprocess_for_cleanup_when_stale(stale_toolkit):
    fake_run = _canned_subprocess({"status": "cleaned", "exit_code": 0})
    r = T.task_branch(action="cleanup", slug="feat-x", confirm=True, subprocess_run=fake_run)
    assert r["status"] == "cleaned"
    assert r["executed_via"] == "fresh_subprocess"


def test_task_branch_allow_stale_toolkit_reaches_the_real_function_not_the_subprocess(
    stale_toolkit,
):
    """The escape hatch must actually bypass the refusal AND the R4
    fresh-subprocess fallback — proven by (a) the REAL function's own
    `requires slug` validation firing (it can only fire if task_branch's
    body actually ran in-process) and (b) the injected `subprocess_run`
    NEVER being called."""
    spy = _forbidden_subprocess()
    r = T.task_branch(action="start", confirm=True, allow_stale_toolkit=True,
                       subprocess_run=spy, run=_minimal_fake_git())
    assert r["status"] != "refused_stale_toolkit"
    assert "executed_via" not in r
    assert r["status"] == "error" and "requires slug" in r["error"]
    assert spy.calls == []


def test_refuse_posture_fresh_write_is_never_refused(fresh_toolkit):
    """Positive control: a fresh toolkit never manufactures a refusal, and
    never even looks at the fresh-subprocess fallback.

    F1 (compliance review, 2026-09-24): this MUST inject `run=` — without
    it, `release()` falls through to `_default_run_local`, which shells out
    to the REAL repo. `stage='promote' confirm=True` against a genuinely
    fast-forwardable real prod could have pushed for real. The sitewide
    conftest guard (`_guard_release_default_runner_never_pushes`) is a
    backstop for exactly this mistake, never a substitute for injecting the
    fake here."""
    spy = _forbidden_subprocess()
    r = REL.release(stage="promote", confirm=True, subprocess_run=spy,
                    run=_fake_release_git_all_up_to_date())
    assert r["status"] == "up_to_date"
    assert r["status"] != "refused_stale_toolkit" and "executed_via" not in r
    assert T.task_branch(action="start", slug="feat-x", confirm=True,
                          subprocess_run=spy,
                          run=_fake_git_with_refs({"origin/dev": "d0"}))["status"] != "refused_stale_toolkit"
    assert spy.calls == []
