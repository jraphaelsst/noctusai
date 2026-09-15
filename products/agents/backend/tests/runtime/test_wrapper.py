"""``bin/julia-cli-exec`` — the wrapper (contract §E.5, SEC-C; roadmap D1,
tech-lead + security-advisor review 2026-09-14).

The wrapper now does its OWN uid switch (``setpriv --reuid=1001
--regid=1001``) before the cap-drop + ``env -i`` handoff — it no longer
reads a ``JULIA_CLAUDE_BIN`` env var (dropped deliberately, see the
wrapper's own header comment). Tests that need a stub CLI binary
therefore copy the wrapper's TEXT with its one hardcoded exec target
(``/usr/local/bin/claude-bundled``) substituted for a stub script — never
an env var — mirroring exactly how the real image's Dockerfile bakes that
one absolute path via a build-time symlink.
"""
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_WRAPPER = Path(__file__).resolve().parents[2] / "bin" / "julia-cli-exec"
_REAL_CLAUDE_TARGET = "/usr/local/bin/claude-bundled"

# `setpriv` (util-linux) is Linux-only — present in the real image's base
# (python:3.11-slim / Debian trixie, verified live: `setpriv from
# util-linux 2.41.5`) but absent on a macOS dev host. The wrapper always
# execs it via the ABSOLUTE path `/usr/bin/setpriv` (never via PATH
# lookup), so gate every test that actually SPAWNS the wrapper on that
# exact path existing — a clear skip, never a silent pass that would hide
# a real regression under "well it exited nonzero, as some tests expect."
_HAS_SETPRIV = Path("/usr/bin/setpriv").exists()

# The wrapper's OWN `setpriv --reuid=1001 --regid=1001` (contract §E.5's
# uid switch, now living IN the wrapper so it also covers the SDK's
# no-`user=` version-check spawn) only succeeds if the CALLING process is
# already uid 1001 (an allowed self-setresuid no-op) OR holds CAP_SETUID
# (root, or an explicit `cap_add`). A bare test host/CI runner is neither
# in general — gate on it explicitly rather than let the switch fail and
# be misread as a wrapper bug.
_CAN_SWITCH_TO_1001 = os.geteuid() in (0, 1001)

_SKIP_NO_SETPRIV = pytest.mark.skipif(
    not _HAS_SETPRIV,
    reason="setpriv (util-linux) is Linux-only; the wrapper only ever runs "
    "inside the Linux container, never on this test host",
)
_SKIP_CANNOT_SELF_SWITCH = pytest.mark.skipif(
    not (_HAS_SETPRIV and _CAN_SWITCH_TO_1001),
    reason=(
        "the wrapper's own `setpriv --reuid=1001` needs CAP_SETUID or an "
        f"already-uid-1001 caller; this test process is euid={os.geteuid()} "
        "on a host without setpriv or that capability — skipping rather "
        "than asserting a spawn failure that says nothing about the wrapper"
    ),
)

_ALLOWLIST = {
    "HOME",
    "TMPDIR",
    "PATH",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_AGENT_SDK_VERSION",
    "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
}

# macOS's dyld/CoreFoundation unconditionally injects this into EVERY
# exec'd process (confirmed live on this dev machine) — entirely outside
# `env -i`'s control and irrelevant to the wrapper's own guarantee. Linux
# never sees it.
_PLATFORM_NOISE = {"__CF_USER_TEXT_ENCODING"} if platform.system() == "Darwin" else set()

# CPython's own PEP 538 C-locale coercion — NOT the wrapper, NOT the OS.
# `env -i` hands the child an env with zero LANG/LC_* keys, which CPython
# reads as the "C"/"POSIX" locale; on startup it picks a UTF-8 coercion
# target (`C.UTF-8` here) and WRITES `LC_CTYPE` into its own `os.environ`
# before a single line of the script body runs — so the stub CLI (a
# Python process, used *because* `sh`/`dash` inject their own PWD/SHLVL
# noise) reports a key the wrapper never added. Confirmed directly: `env
# -i python3 -c "print(os.environ)"` shows LC_CTYPE=C.UTF-8. Excluded
# unconditionally, by exact name, with this evidence trail — not a
# platform guess and not a blanket allowance for whatever a run emits.
_INTERPRETER_NOISE = {"LC_CTYPE"}


def _wrapper_copy_targeting(tmp_path: Path, stub: Path) -> Path:
    """The ONE test seam: a temp copy of the real wrapper with its single
    hardcoded exec target swapped for `stub`. Never an env var — the
    production wrapper takes none."""
    real_text = _WRAPPER.read_text()
    assert _REAL_CLAUDE_TARGET in real_text, (
        f"expected the wrapper to hardcode {_REAL_CLAUDE_TARGET!r} — if "
        "this fails, the wrapper's exec target changed and this test's "
        "substitution seam must be updated to match"
    )
    substituted = real_text.replace(_REAL_CLAUDE_TARGET, str(stub))
    copy_path = tmp_path / "julia-cli-exec-under-test"
    copy_path.write_text(substituted)
    copy_path.chmod(copy_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return copy_path


@pytest.fixture
def env_dumper_wrapper(tmp_path: Path) -> Path:
    # A Python stub, not a shell script: `sh`/`dash` auto-populate `PWD` /
    # `SHLVL` / `_` into a NEW shell's own environment regardless of what
    # `env -i` handed it (a property of nested shells, not a wrapper leak)
    # — the real target is a compiled CLI binary, not a shell, so a Python
    # stub is the closer analogue and keeps this test measuring only what
    # the wrapper itself controls.
    stub = tmp_path / "env-dumper.py"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "for k, v in sorted(os.environ.items()):\n"
        "    print(f'{k}={v}')\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return _wrapper_copy_targeting(tmp_path, stub)


class TestWrapperExists:
    def test_wrapper_file_exists_and_is_executable(self):
        assert _WRAPPER.exists(), _WRAPPER
        mode = _WRAPPER.stat().st_mode
        assert mode & stat.S_IXUSR, "bin/julia-cli-exec must be committed with the executable bit set"

    def test_wrapper_hardcodes_the_bundled_cli_absolute_path(self):
        # Roadmap D1: dropped the `JULIA_CLAUDE_BIN` env seam deliberately
        # — an env-var-controlled exec target is an extra thing a
        # caller-influenced `env` could redirect. Pin the exact literal so
        # a regression back to an env var (or to a relative/PATH-resolved
        # target) is caught here, not discovered live.
        text = _WRAPPER.read_text()
        assert _REAL_CLAUDE_TARGET in text
        code_lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        assert "JULIA_CLAUDE_BIN" not in "\n".join(code_lines), (
            "the wrapper's CODE (comments may still explain the removal) "
            "must not read a JULIA_CLAUDE_BIN env var — dropped deliberately"
        )


@_SKIP_CANNOT_SELF_SWITCH
class TestWrapperStripsInheritedEnv:
    def test_child_env_key_set_is_exactly_the_allowlist(self, env_dumper_wrapper):
        parent_env = {
            "ANTHROPIC_API_KEY": "sk-ant-fake",
            "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
            "CLAUDE_AGENT_SDK_VERSION": "0.2.152",
            # Everything below MUST be stripped — the whole point of the wrapper.
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-fake",
            "ACADEMIA_API_TOKEN": "pk_fake_academia_token",
            "APPROVAL_ASSERTION_SECRETS": "secret-one,secret-two",
            "SOCIAL_WIRING_API_TOKEN": "pk_fake_social_wiring",
            "SOME_RANDOM_INHERITED_VAR": "should-not-survive",
            # A real subprocess needs SOME PATH to exec `/usr/bin/setpriv` at
            # all — supplied here for the TEST's own subprocess.run call, not
            # forwarded by the wrapper (the wrapper hardcodes its own PATH).
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }

        result = subprocess.run(
            [str(env_dumper_wrapper)],
            env=parent_env,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, result.stderr
        child_keys = {
            line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line
        }

        unexpected = child_keys - _ALLOWLIST - _PLATFORM_NOISE - _INTERPRETER_NOISE
        missing = _ALLOWLIST - child_keys
        assert not unexpected and not missing, (
            f"child env leaked or dropped keys: extra={unexpected} missing={missing}"
        )

    def test_secret_values_never_appear_in_child_output(self, env_dumper_wrapper):
        parent_env = {
            "ANTHROPIC_API_KEY": "sk-ant-fake",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-fake-marker",
            "ACADEMIA_API_TOKEN": "pk_fake_academia_token_marker",
            "APPROVAL_ASSERTION_SECRETS": "secret-marker-one,secret-marker-two",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        result = subprocess.run(
            [str(env_dumper_wrapper)], env=parent_env, capture_output=True, text=True, timeout=10
        )
        assert "service-role-fake-marker" not in result.stdout
        assert "pk_fake_academia_token_marker" not in result.stdout
        assert "secret-marker-one" not in result.stdout

    def test_home_and_path_are_fixed_literals_not_inherited(self, env_dumper_wrapper):
        parent_env = {
            "HOME": "/Users/attacker-controlled-home",
            "PATH": "/attacker/bin:" + os.environ.get("PATH", "/usr/bin:/bin"),
        }
        result = subprocess.run(
            [str(env_dumper_wrapper)], env=parent_env, capture_output=True, text=True, timeout=10
        )
        out = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )
        assert out["HOME"] != "/Users/attacker-controlled-home"
        assert out["HOME"] == "/run/julia"
        assert "attacker" not in out["PATH"]

    def test_disable_autoupdater_and_nonessential_traffic_are_always_set(self, env_dumper_wrapper):
        # The CLI must never phone home to check for updates or emit
        # telemetry from inside this sandboxed subprocess (roadmap D1) —
        # assert these two are present REGARDLESS of what the parent env
        # carries (or doesn't).
        result = subprocess.run(
            [str(env_dumper_wrapper)],
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )
        assert out.get("DISABLE_AUTOUPDATER") == "1"
        assert out.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC") == "1"


class TestWrapperDropsCapsBeforeExec:
    """Tech-lead + security-advisor review 2026-09-14: this wrapper does
    its OWN uid switch (covering the SDK's no-`user=` version-check spawn
    too), and whichever way it arrived at uid 1001, it can carry
    CAP_SETUID/CAP_SETGID/CAP_KILL in its AMBIENT set (inherited across a
    non-root->non-root uid change, or never dropped at all on the
    no-`user=` path). Without an explicit drop, the CLI binary (and
    anything it spawns) would inherit those on its own exec and could
    `setuid`/`setgid` to become `noctus`, or `kill` it — defeating SEC-C.
    """

    def test_setpriv_appears_twice_switch_then_drop(self):
        # Static, platform-independent: proves the SHAPE of the fix — the
        # uid switch happens FIRST, the cap-drop SECOND, both before
        # `env -i` ever runs. No `--bounding-set=` anywhere (verified
        # empirically that it needs CAP_SETPCAP, which this process never
        # has: `setpriv: apply bounding set: Operation not permitted`).
        full_text = _WRAPPER.read_text()
        code_lines = [
            line for line in full_text.splitlines() if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "--bounding-set=" not in code, (
            "no `--bounding-set=` clause belongs in this wrapper — it needs "
            "CAP_SETPCAP, which this process never has (verified "
            "empirically); Docker's own cap_drop/cap_add already bounds "
            "the set, and --no-new-privs keeps the leftover bits inert"
        )
        switch_idx = code.index("--reuid=1001")
        drop_idx = code.index("--ambient-caps=-all")
        env_i_idx = code.index("env -i")
        assert switch_idx < drop_idx < env_i_idx, (
            "expected order: uid switch (--reuid=1001), THEN the cap drop "
            "(--ambient-caps=-all), THEN env -i hands off to the CLI binary "
            "— any other order leaves a window where the wrong identity "
            "either can't drop its own caps, or still carries them into exec"
        )
        assert "/usr/bin/setpriv" in full_text, (
            "must exec setpriv via its ABSOLUTE path, never a bare "
            "`setpriv` that resolves against this process's own "
            "(potentially attacker-influenced) PATH"
        )
        assert "/usr/bin/env -i" in full_text, (
            "must exec env via its ABSOLUTE path too, same reasoning"
        )

    @_SKIP_CANNOT_SELF_SWITCH
    def test_child_caps_are_all_empty_after_the_drop(self, tmp_path: Path):
        # A Python stub that dumps ITS OWN /proc/self/status Cap* lines —
        # this is what the wrapper's final `env -i <target>` actually
        # execs into, standing in for the real bundled `claude` binary.
        caps_dumper = tmp_path / "caps-dumper.py"
        caps_dumper.write_text(
            f"#!{sys.executable}\n"
            "with open('/proc/self/status') as f:\n"
            "    for line in f:\n"
            "        if line.startswith('Cap'):\n"
            "            print(line.strip())\n"
        )
        caps_dumper.chmod(caps_dumper.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        wrapper_copy = _wrapper_copy_targeting(tmp_path, caps_dumper)

        result = subprocess.run(
            [str(wrapper_copy)],
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        caps: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if line.startswith("Cap") and ":" in line:
                key, value = line.split(":", 1)
                caps[key.strip()] = value.strip()
        # CapInh/CapPrm/CapEff/CapAmb must all be the all-zero mask —
        # verified against the real compose-hardened container (D1
        # report's proof table) that this ALSO holds when the CALLING
        # process genuinely carries SETUID/SETGID/KILL beforehand (the
        # live-turn case); here it proves the drop command itself runs
        # cleanly and produces the all-zero shape on whatever caps this
        # test process happened to have.
        zero_mask = "0" * 16
        for key in ("CapInh", "CapPrm", "CapEff", "CapAmb"):
            assert key in caps, f"{key} missing from child status: {result.stdout}"
            assert caps[key] == zero_mask, f"{key} should be all-zero after the drop, got {caps[key]}"

    @_SKIP_CANNOT_SELF_SWITCH
    def test_child_cannot_signal_pid_1(self, tmp_path: Path):
        """A concrete exercise of the drop's actual guarantee: the exec'd
        child can no longer signal an arbitrary uid — probed via
        `os.kill(pid, 0)` (a permission probe, no actual signal delivered)
        against PID 1, which is root-owned on any Linux host this test can
        run on, giving a target uid that is NEVER this child's own uid
        (uid 1001 after a real switch, or the current test uid after a
        same-uid no-op switch — either way, not 0). Never trusts a bare
        `Popen.terminate()`/`.wait()` return, which reaps silently either
        way and proves nothing about permission.
        """
        killer = tmp_path / "killer.py"
        killer.write_text(
            f"#!{sys.executable}\n"
            "import os\n"
            "try:\n"
            "    os.kill(1, 0)\n"
            "    print('KILL_ALLOWED')\n"
            "except PermissionError:\n"
            "    print('KILL_DENIED_EPERM')\n"
            "except ProcessLookupError:\n"
            "    print('KILL_DENIED_NO_SUCH_PROCESS')\n"
        )
        killer.chmod(killer.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        wrapper_copy = _wrapper_copy_targeting(tmp_path, killer)

        result = subprocess.run(
            [str(wrapper_copy)],
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "KILL_DENIED" in result.stdout, (
            f"expected the capability-stripped child to be denied signalling "
            f"pid 1 (root-owned, never this child's own uid), got: "
            f"{result.stdout!r}"
        )
