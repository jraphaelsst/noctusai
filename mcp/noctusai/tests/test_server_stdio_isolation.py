"""The MCP JSON-RPC channel must survive subprocesses that touch inherited stdio.

🔴 THE INCIDENT THIS PINS (2026-09-16, recurring for weeks)
----------------------------------------------------------
``ssh`` / node children inherit the server's stdin and flip it to O_NONBLOCK
(a flag on the SHARED open file description). A request arriving in that
window is read, the next ``readline()`` hits EAGAIN and returns ``''``, the
stdio transport sees EOF, and the server exits cleanly — every in-flight call
dies with "Connection closed". ``stdio_guard.isolate_stdio_channel`` moves the
channel to private fds before any child can be spawned.

Each test runs a real child process holding an OPEN, idle stdin pipe (exactly
like Claude Code). The control case (guard OFF) must reproduce the EOF, which
proves the test exercises the real mechanism rather than passing vacuously.
A second pin covers the adjacent leak: a child writing to its stdout must not
land on the JSON-RPC channel.

Also pins ``dep_preflight.unsatisfied_requirements`` (the venv-drift startup
crash, ``No module named 'pillow_heif'``).
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]

# Stand-in server: optionally isolates, spawns a child that sets O_NONBLOCK on
# its inherited fd 0 and prints to its inherited fd 1, then reads the channel
# line by line the way mcp.server.stdio does and echoes each line back.
_SERVER = textwrap.dedent(
    """
    import fcntl, os, subprocess, sys, threading
    sys.path.insert(0, {mcp_root!r})
    guard = sys.argv[1] == "on"
    if guard:
        from stdio_guard import isolate_stdio_channel
        rpc_in, rpc_out = isolate_stdio_channel()
    else:
        import io
        rpc_in = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
        rpc_out = sys.stdout
    child = (
        "import fcntl, os, sys, time;"
        "fcntl.fcntl(0, fcntl.F_SETFL, fcntl.fcntl(0, fcntl.F_GETFL) | os.O_NONBLOCK);"
        "print('LEAKED-FROM-CHILD', flush=True);"
        "time.sleep(3)"
    )
    threading.Thread(
        target=subprocess.run, args=([sys.executable, "-c", child],), daemon=True
    ).start()
    for _ in range(2):
        line = rpc_in.readline()
        if line == "":
            rpc_out.write("EOF\\n"); rpc_out.flush()
            os._exit(4)
        rpc_out.write("ECHO " + line); rpc_out.flush()
    os._exit(0)
    """
)


def _run_stand_in(tmp_path: Path, guard: str) -> tuple[int, str]:
    script = tmp_path / "stand_in_server.py"
    script.write_text(_SERVER.format(mcp_root=str(MCP_ROOT)))
    proc = subprocess.Popen(
        [sys.executable, str(script), guard],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)  # child is alive and has flipped O_NONBLOCK
    proc.stdin.write(b'{"id":1}\n')
    proc.stdin.flush()
    time.sleep(0.5)  # still inside the child's lifetime
    proc.stdin.write(b'{"id":2}\n')
    proc.stdin.flush()
    out, _ = proc.communicate(timeout=15)
    return proc.returncode, out.decode()


def test_control_unguarded_channel_sees_spurious_eof(tmp_path):
    rc, out = _run_stand_in(tmp_path, "off")
    assert rc == 4, out
    assert "EOF" in out


def test_guarded_channel_survives_child_flipping_stdin_nonblocking(tmp_path):
    rc, out = _run_stand_in(tmp_path, "on")
    assert rc == 0, out
    assert out.splitlines() == ['ECHO {"id":1}', 'ECHO {"id":2}']


def test_guarded_channel_never_carries_child_stdout(tmp_path):
    _, out = _run_stand_in(tmp_path, "on")
    assert "LEAKED-FROM-CHILD" not in out


# ── dep_preflight ───────────────────────────────────────────────────────────


def _repo_with(tmp_path: Path, seed_deps: list[str], mcp_deps: list[str]) -> Path:
    for rel, deps in (
        ("seed/lib/backend/pyproject.toml", seed_deps),
        ("mcp/noctusai/pyproject.toml", mcp_deps),
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        body = ", ".join(f'"{d}"' for d in deps)
        p.write_text(f'[project]\nname = "x"\ndependencies = [{body}]\n')
    return tmp_path


def test_preflight_flags_missing_and_out_of_range(tmp_path):
    from dep_preflight import unsatisfied_requirements

    repo = _repo_with(
        tmp_path,
        ["pytest>=1.0", "noctus-definitely-not-installed>=1.0"],
        ["pytest>=999.0"],
    )
    assert unsatisfied_requirements(repo) == [
        "noctus-definitely-not-installed>=1.0",
        "pytest>=999.0",
    ]


def test_preflight_skips_requirements_whose_marker_does_not_apply(tmp_path):
    from dep_preflight import unsatisfied_requirements

    repo = _repo_with(
        tmp_path,
        ["noctus-definitely-not-installed>=1.0; python_version < '3.0'"],
        ["pytest>=1.0"],
    )
    assert unsatisfied_requirements(repo) == []


def test_preflight_report_only_mode_does_not_install(tmp_path, monkeypatch, caplog):
    import logging

    from dep_preflight import ensure_declared_deps

    monkeypatch.setenv("NOCTUS_MCP_DEP_AUTOSYNC", "0")
    repo = _repo_with(tmp_path, ["noctus-definitely-not-installed>=1.0"], [])
    with caplog.at_level(logging.WARNING):
        missing = ensure_declared_deps(repo, logging.getLogger("t"))
    assert missing == ["noctus-definitely-not-installed>=1.0"]
    assert "autosync disabled" in caplog.text


@pytest.mark.parametrize("rel", ["seed/lib/backend/pyproject.toml", "mcp/noctusai/pyproject.toml"])
def test_preflight_manifests_exist_in_repo(rel):
    from dep_preflight import MANIFESTS

    assert Path(rel) in MANIFESTS
    assert (MCP_ROOT.parents[1] / rel).is_file()
