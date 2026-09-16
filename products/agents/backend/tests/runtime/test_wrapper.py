"""``bin/julia-cli-exec`` + ``bin/julia-cli-slot`` — the per-conversation
slot wrapper and slot script (contract §E.11, supersedes §E.5; roadmap
D1, per-conversation isolation, architect review 2026-09-15).

§E.11 splits the old single-file wrapper into two root-owned scripts:
``julia-cli-exec`` reads the kernel-set real uid, range-checks it against
``[2000, 2000+JULIA_CLI_SLOTS)``, drift-checks the inherited
``CLAUDE_CONFIG_DIR``, then does a same-uid self-switch + `--clear-groups`
+ cap-strip before handing off to ``julia-cli-slot`` — which does the
fail-closed sweep, the handoff-file copy, and the final ``env -i`` exec of
the real bundled CLI.

Both scripts hardcode their ONE absolute exec target
(``/app/bin/julia-cli-slot`` and ``/usr/local/bin/claude-bundled``
respectively) — never an env var (the ``JULIA_CLAUDE_BIN`` seam was
dropped deliberately under §E.5 and that decision carries forward). Tests
that need a stub therefore copy each script's TEXT with its own single
hardcoded literal substituted — never an env var — mirroring exactly how
the real image's Dockerfile bakes those paths via COPY + a build-time
symlink.

Reproduce-as-CI-runner (feedback_privilege_skip_guard_reproduce_as_ci_runner,
2026-09-14): a Linux-privilege skip guard that is green on macOS proves
nothing. Every skip decision below reads the kernel's own answer
(``/proc/self/status`` CapEff, or the Linux platform check for the
GNU-coreutils-flavored sweep logic) — never a uid comparison. Before
pushing, reproduce in a container as the GitHub runner shape
(``docker run --rm --user 1001:118 ...python:3.11-slim``, expect a clean
skip) AND as root (expect the privileged/Linux-gated tests to actually
run and pass) — a guard that always skips in CI gives no automated
coverage of the thing it claims to test.
"""
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / "bin"
_WRAPPER = _BIN_DIR / "julia-cli-exec"
_SLOT = _BIN_DIR / "julia-cli-slot"

_SLOT_TARGET_LITERAL = "/app/bin/julia-cli-slot"
_CLI_TARGET_LITERAL = "/usr/local/bin/claude-bundled"
_JULIA_PREFIX_LITERAL = "/run/julia-"

# `setpriv` (util-linux) is Linux-only — present in the real image's base
# (python:3.11-slim / Debian trixie, verified live: `setpriv from
# util-linux 2.41.5`) but absent on a macOS dev host. The wrapper always
# execs it via the ABSOLUTE path `/usr/bin/setpriv` (never via PATH
# lookup), so gate every test that actually SPAWNS the wrapper THROUGH a
# real setpriv call on that exact path existing — a clear skip, never a
# silent pass that would hide a real regression under "well it exited
# nonzero, as some tests expect."
_HAS_SETPRIV = Path("/usr/bin/setpriv").exists()

# `julia-cli-slot`'s own sweep (top-down `find -exec chmod` then
# `find -delete`) is written against GNU findutils semantics (verified
# live against the real image's Debian trixie base) — gate its direct-
# invocation tests on the actual platform, not a proxy binary's presence,
# since these tests need no `setpriv` at all (they never switch uid).
_IS_LINUX = platform.system() == "Linux"

# The wrapper's OWN `setpriv --reuid=$REAL_UID --regid=$REAL_UID
# --clear-groups` (contract §E.11's self-switch) needs BOTH CAP_SETUID and
# CAP_SETGID in the caller's effective set — root has them, the real
# container's uvicorn has them as ambient caps. Being already at the
# target uid is NOT enough: `--clear-groups` calls setgroups(2), which
# requires CAP_SETGID for every caller, regardless of whether the uid
# itself is changing. That was the original single-slot guard's bug — it
# accepted euid in (0, 1001), and GitHub's ubuntu runner user IS uid 1001,
# so those tests ran unprivileged in CI and failed with "setpriv:
# setgroups failed: Operation not permitted" (dev CI run 34914554800,
# 2026-09-14; feedback_privilege_skip_guard_reproduce_as_ci_runner). The
# skip is decided from the kernel's own answer (`/proc/self/status`
# CapEff), never inferred from a uid.
_CAP_SETGID_BIT = 1 << 6
_CAP_SETUID_BIT = 1 << 7


def _effective_caps() -> int:
    """This process's CapEff mask, or 0 where `/proc` is unavailable (macOS)."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("CapEff:"):
                return int(line.split()[1], 16)
    except OSError:
        return 0
    return 0


_CAN_SELF_SWITCH = os.geteuid() == 0 or (
    _effective_caps() & (_CAP_SETUID_BIT | _CAP_SETGID_BIT)
) == (_CAP_SETUID_BIT | _CAP_SETGID_BIT)

_SKIP_NO_SETPRIV = pytest.mark.skipif(
    not _HAS_SETPRIV,
    reason="setpriv (util-linux) is Linux-only; the wrapper only ever runs "
    "inside the Linux container, never on this test host",
)
_SKIP_CANNOT_SELF_SWITCH = pytest.mark.skipif(
    not (_HAS_SETPRIV and _CAN_SELF_SWITCH),
    reason=(
        "the wrapper's own `setpriv --reuid=$K --regid=$K --clear-groups` "
        "needs CAP_SETUID and CAP_SETGID (setgroups always needs CAP_SETGID, "
        f"even for an already-matching uid); this process is euid={os.geteuid()} "
        f"with CapEff={_effective_caps():#x} and setpriv "
        f"{'present' if _HAS_SETPRIV else 'absent'} — skipping rather than "
        "asserting a spawn failure that says nothing about the wrapper. The "
        "privilege drop itself is proven on the real image (SEC-C)."
    ),
)
_SKIP_NOT_LINUX = pytest.mark.skipif(
    not _IS_LINUX,
    reason="julia-cli-slot's sweep is written against GNU findutils "
    "top-down chmod-then-delete ordering (verified against the real "
    "image's Debian trixie base) — skip on a non-Linux dev host rather "
    "than assert behaviour a different find/chmod implementation may not "
    "share",
)

_ALLOWLIST = {
    "HOME",
    "TMPDIR",
    "CLAUDE_CONFIG_DIR",
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
# before a single line of the script body runs — so a Python stub CLI
# reports a key the wrapper/slot script never added. Confirmed directly:
# `env -i python3 -c "print(os.environ)"` shows LC_CTYPE=C.UTF-8. Excluded
# unconditionally, by exact name, with this evidence trail.
_INTERPRETER_NOISE = {"LC_CTYPE"}


def _copy_with_subs(source: Path, dest_dir: Path, name: str, subs: dict[str, str]) -> Path:
    """The ONE test seam: a temp copy of a real script with its own
    hardcoded literal(s) swapped for a test target. Never an env var — the
    production scripts take none."""
    text = source.read_text()
    for old, new in subs.items():
        assert old in text, (
            f"expected {source} to contain {old!r} — if this fails, the "
            "script's hardcoded literal changed and this test's "
            "substitution seam must be updated to match"
        )
        text = text.replace(old, new)
    copy_path = dest_dir / name
    copy_path.write_text(text)
    copy_path.chmod(0o755)
    return copy_path


def _fake_id_dir(dest_dir: Path, fake_uid: str) -> Path:
    """A scratch bin/ dir whose `id` stub reports `fake_uid` for `id -u`
    and fails for anything else. Both scripts read their real uid via a
    BARE `id -u` (PATH-resolved) — this is the test's own controllable
    seam for exercising the uid-range / slot-derivation logic without
    ever needing to actually run as a different uid."""
    bindir = dest_dir / "fakebin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "id"
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-u" ]; then\n'
        f'  printf "%s\\n" {fake_uid!r}\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    stub.chmod(0o755)
    return bindir


def _path_with_fake_id(bindir: Path) -> str:
    return f"{bindir}:/usr/bin:/bin"


@pytest.fixture
def julia_tmp() -> Iterator[Path]:
    """A world-writable scratch dir a post-switch uid can traverse AND
    create its own subdirectory in.

    Both scripts drop to a different uid before exec'ing the next stage —
    every directory above the final stub, AND (for the slot script) the
    scratch parent it creates its own `julia-<K>` subdirectory under, must
    be writable by "other" (pytest's own `tmp_path` lives under
    `/tmp/pytest-of-<user>/`, mode 0700, which a switched-to uid cannot
    even enter — a harness defect, not a wrapper regression; see
    feedback_privilege_skip_guard_reproduce_as_ci_runner). Only reached
    when `_SKIP_CANNOT_SELF_SWITCH` lets the test run (root, or
    CAP_SETUID+CAP_SETGID)."""
    scratch = Path(tempfile.mkdtemp(prefix="julia-wrapper-test-", dir="/tmp"))
    scratch.chmod(0o777)
    yield scratch
    shutil.rmtree(scratch, ignore_errors=True)


def _run(args, env, timeout=10):
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)


class TestScriptsExistAndAreExecutable:
    def test_wrapper_exists_and_is_executable(self):
        assert _WRAPPER.exists(), _WRAPPER
        assert _WRAPPER.stat().st_mode & stat.S_IXUSR, (
            "bin/julia-cli-exec must be committed with the executable bit set"
        )

    def test_slot_script_exists_and_is_executable(self):
        assert _SLOT.exists(), _SLOT
        assert _SLOT.stat().st_mode & stat.S_IXUSR, (
            "bin/julia-cli-slot must be committed with the executable bit set"
        )

    def test_wrapper_hardcodes_the_slot_script_absolute_path(self):
        text = _WRAPPER.read_text()
        assert _SLOT_TARGET_LITERAL in text
        code_lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        code = "\n".join(code_lines)
        assert "JULIA_CLAUDE_BIN" not in code, (
            "the wrapper's CODE (comments may still explain the removal) "
            "must not read a JULIA_CLAUDE_BIN env var — dropped deliberately"
        )

    def test_slot_script_hardcodes_the_bundled_cli_absolute_path(self):
        text = _SLOT.read_text()
        assert _CLI_TARGET_LITERAL in text
        code_lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        assert "JULIA_CLAUDE_BIN" not in "\n".join(code_lines)


class TestWrapperNeverTrustsArgsOrEnvForTheSlot:
    """Contract §E.11: "It never reads the slot number from any argument
    or env var." — a static check over the wrapper's CODE (comments may
    discuss the rule; only code lines are asserted)."""

    def test_slot_is_derived_only_from_id_dash_u(self):
        code_lines = [
            line
            for line in _WRAPPER.read_text().splitlines()
            if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "id -u" in code, "the wrapper must derive its slot from `id -u`"
        for forbidden in ("JULIA_SLOT", "SLOT_ARG", "$1", "${1"):
            assert forbidden not in code, (
                f"the wrapper's code must never read the slot number from "
                f"{forbidden!r} — found it outside a comment"
            )

    def test_slot_script_also_never_trusts_args_or_env_for_its_own_slot(self):
        code_lines = [
            line for line in _SLOT.read_text().splitlines() if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "id -u" in code
        for forbidden in ("JULIA_SLOT", "SLOT_ARG"):
            assert forbidden not in code


class TestWrapperUidRangeRefusal:
    """Contract §E.11 step 1: exit 126 unless the real uid is in
    `[2000, 2000+JULIA_CLI_SLOTS)`. None of these reach `setpriv` — no
    privilege needed to run them anywhere."""

    @pytest.mark.parametrize(
        "fake_uid",
        ["1000", "1999", "2003", "9999"],
    )
    def test_uid_outside_range_is_refused_with_exit_126(self, tmp_path, fake_uid):
        bindir = _fake_id_dir(tmp_path, fake_uid)
        result = _run(
            [str(_WRAPPER)],
            env={"PATH": _path_with_fake_id(bindir)},
        )
        assert result.returncode == 126, result.stderr
        assert "outside the slot range" in result.stderr

    @pytest.mark.parametrize("fake_uid", ["2000", "2001", "2002"])
    def test_uid_inside_default_range_passes_the_range_check(self, tmp_path, fake_uid):
        bindir = _fake_id_dir(tmp_path, fake_uid)
        result = _run(
            [str(_WRAPPER)],
            env={"PATH": _path_with_fake_id(bindir)},
        )
        # No CLAUDE_CONFIG_DIR was supplied, so it must fail the NEXT gate
        # instead — proving it passed the range check without needing any
        # privilege to observe that.
        assert result.returncode == 126, result.stderr
        assert "outside the slot range" not in result.stderr
        assert "does not match the expected" in result.stderr

    def test_unreadable_uid_is_refused(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "not-a-number")
        result = _run([str(_WRAPPER)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode == 126, result.stderr
        assert "unreadable real uid" in result.stderr

    def test_malformed_julia_cli_slots_is_refused(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        result = _run(
            [str(_WRAPPER)],
            env={"PATH": _path_with_fake_id(bindir), "JULIA_CLI_SLOTS": "banana"},
        )
        assert result.returncode == 126, result.stderr
        assert "JULIA_CLI_SLOTS" in result.stderr

    def test_custom_julia_cli_slots_widens_the_range(self, tmp_path):
        # uid 2004 is outside the DEFAULT range (3 slots) but inside a
        # widened one (5 slots) — proving the bound is read from
        # JULIA_CLI_SLOTS, not hardcoded to 3.
        bindir = _fake_id_dir(tmp_path, "2004")
        result = _run(
            [str(_WRAPPER)],
            env={"PATH": _path_with_fake_id(bindir), "JULIA_CLI_SLOTS": "5"},
        )
        assert result.returncode == 126, result.stderr
        assert "outside the slot range" not in result.stderr


class TestWrapperConfigDirDriftCheck:
    """Contract §E.11 step 2: refuse unless the inherited
    `CLAUDE_CONFIG_DIR` equals `/run/julia-<K>/home/.claude` for the
    uid-derived slot — a drift check only; the value is recomputed, never
    trusted as the slot's own source."""

    def test_missing_config_dir_is_refused(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        result = _run([str(_WRAPPER)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode == 126, result.stderr
        assert "does not match the expected '/run/julia-0/home/.claude'" in result.stderr

    def test_config_dir_for_the_wrong_slot_is_refused(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")  # slot 0
        result = _run(
            [str(_WRAPPER)],
            env={
                "PATH": _path_with_fake_id(bindir),
                "CLAUDE_CONFIG_DIR": "/run/julia-1/home/.claude",  # slot 1
            },
        )
        assert result.returncode == 126, result.stderr
        assert "does not match the expected '/run/julia-0/home/.claude'" in result.stderr

    def test_matching_config_dir_passes_the_drift_check(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2001")  # slot 1
        result = _run(
            [str(_WRAPPER)],
            env={
                "PATH": _path_with_fake_id(bindir),
                "CLAUDE_CONFIG_DIR": "/run/julia-1/home/.claude",
            },
        )
        # Whatever happens next (a real setpriv attempt, which may itself
        # fail for lack of privilege or lack of the binary on this host)
        # is NOT this refusal — proving the drift check itself passed.
        assert "does not match the expected" not in result.stderr
        assert "outside the slot range" not in result.stderr


class TestWrapperSelfSwitchOrdering:
    """Tech-lead + architect review 2026-09-15: the wrapper does a
    same-uid self-switch (needing no capability for the uid/gid change
    itself) but STILL clears supplementary groups and strips caps before
    handing off — whichever way this process arrived at its slot uid, it
    can carry CAP_SETUID/CAP_SETGID/CAP_KILL in its AMBIENT set."""

    def test_setpriv_switch_then_drop_then_absolute_handoff(self):
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
        switch_idx = code.index("--reuid=")
        clear_groups_idx = code.index("--clear-groups")
        drop_idx = code.index("--ambient-caps=-all")
        handoff_idx = code.index(_SLOT_TARGET_LITERAL)
        assert switch_idx < clear_groups_idx < drop_idx < handoff_idx, (
            "expected order: self-switch (--reuid=), THEN --clear-groups, "
            "THEN the cap drop (--ambient-caps=-all), THEN the absolute "
            "handoff to julia-cli-slot — any other order leaves a window "
            "where caps/groups from the prior identity are still live"
        )
        assert "/usr/bin/setpriv" in full_text, (
            "must exec setpriv via its ABSOLUTE path, never a bare "
            "`setpriv` that resolves against this process's own "
            "(potentially attacker-influenced) PATH"
        )


@_SKIP_CANNOT_SELF_SWITCH
class TestWrapperPrivilegedChain:
    """These actually invoke `setpriv` for real — gated on the kernel's
    own CapEff answer (see feedback_privilege_skip_guard_reproduce_as_ci_runner),
    never a uid comparison."""

    def test_child_caps_are_all_empty_after_the_drop(self, julia_tmp: Path):
        bindir = _fake_id_dir(julia_tmp, "2000")
        caps_dumper = julia_tmp / "caps-dumper.py"
        caps_dumper.write_text(
            f"#!{sys.executable}\n"
            "with open('/proc/self/status') as f:\n"
            "    for line in f:\n"
            "        if line.startswith('Cap'):\n"
            "            print(line.strip())\n"
        )
        caps_dumper.chmod(0o755)
        wrapper_copy = _copy_with_subs(
            _WRAPPER, julia_tmp, "julia-cli-exec-under-test",
            {_SLOT_TARGET_LITERAL: str(caps_dumper)},
        )

        result = _run(
            [str(wrapper_copy)],
            env={
                "PATH": _path_with_fake_id(bindir),
                "CLAUDE_CONFIG_DIR": "/run/julia-0/home/.claude",
            },
        )
        assert result.returncode == 0, result.stderr
        caps: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if line.startswith("Cap") and ":" in line:
                key, value = line.split(":", 1)
                caps[key.strip()] = value.strip()
        zero_mask = "0" * 16
        for key in ("CapInh", "CapPrm", "CapEff", "CapAmb"):
            assert key in caps, f"{key} missing from child status: {result.stdout}"
            assert caps[key] == zero_mask, f"{key} should be all-zero after the drop, got {caps[key]}"

    def test_child_cannot_signal_pid_1(self, julia_tmp: Path):
        bindir = _fake_id_dir(julia_tmp, "2000")
        killer = julia_tmp / "killer.py"
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
        killer.chmod(0o755)
        wrapper_copy = _copy_with_subs(
            _WRAPPER, julia_tmp, "julia-cli-exec-under-test",
            {_SLOT_TARGET_LITERAL: str(killer)},
        )

        result = _run(
            [str(wrapper_copy)],
            env={
                "PATH": _path_with_fake_id(bindir),
                "CLAUDE_CONFIG_DIR": "/run/julia-0/home/.claude",
            },
        )
        assert result.returncode == 0, result.stderr
        assert "KILL_DENIED" in result.stdout, (
            f"expected the capability-stripped child to be denied signalling "
            f"pid 1 (root-owned, never this child's own uid), got: "
            f"{result.stdout!r}"
        )

    def test_full_chain_env_allowlist_reaches_the_real_slot_script(self, julia_tmp: Path):
        """The real, unmodified sweep/handoff/exec logic of `julia-cli-slot`
        — only its OWN two hardcoded literals (the `/run/julia-` prefix and
        the final CLI target) are substituted, exactly as sanctioned by the
        module docstring's test-seam rule. Proves the full wrapper->slot
        handoff produces EXACTLY the 9-key allowlist, with HOME/TMPDIR/
        CLAUDE_CONFIG_DIR correctly rooted under this slot's own directory."""
        bindir = _fake_id_dir(julia_tmp, "2000")
        env_dumper = julia_tmp / "env-dumper.py"
        env_dumper.write_text(
            f"#!{sys.executable}\n"
            "import os\n"
            "for k, v in sorted(os.environ.items()):\n"
            "    print(f'{k}={v}')\n"
        )
        env_dumper.chmod(0o755)
        scratch_prefix = str(julia_tmp / "julia-")

        slot_copy = _copy_with_subs(
            _SLOT, julia_tmp, "julia-cli-slot-under-test",
            {
                _JULIA_PREFIX_LITERAL: scratch_prefix,
                _CLI_TARGET_LITERAL: str(env_dumper),
            },
        )
        wrapper_copy = _copy_with_subs(
            _WRAPPER, julia_tmp, "julia-cli-exec-under-test",
            {_SLOT_TARGET_LITERAL: str(slot_copy)},
        )

        parent_env = {
            "PATH": _path_with_fake_id(bindir),
            "CLAUDE_CONFIG_DIR": "/run/julia-0/home/.claude",
            "ANTHROPIC_API_KEY": "sk-ant-fake",
            "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
            "CLAUDE_AGENT_SDK_VERSION": "0.2.152",
            # Must be stripped — the whole point of the allowlist.
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-fake",
            "ACADEMIA_API_TOKEN": "pk_fake_academia_token",
            "APPROVAL_ASSERTION_SECRETS": "secret-one,secret-two",
            "SOCIAL_WIRING_API_TOKEN": "pk_fake_social_wiring",
            "SOME_RANDOM_INHERITED_VAR": "should-not-survive",
        }

        result = _run([str(wrapper_copy)], env=parent_env, timeout=15)
        assert result.returncode == 0, result.stderr
        out = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        child_keys = set(out.keys())

        unexpected = child_keys - _ALLOWLIST - _PLATFORM_NOISE - _INTERPRETER_NOISE
        missing = _ALLOWLIST - child_keys
        assert not unexpected and not missing, (
            f"child env leaked or dropped keys: extra={unexpected} missing={missing}"
        )
        assert out["HOME"] == f"{julia_tmp}/julia-0/home"
        assert out["TMPDIR"] == f"{julia_tmp}/julia-0/tmp"
        assert out["CLAUDE_CONFIG_DIR"] == f"{julia_tmp}/julia-0/home/.claude"
        assert out["PATH"] == "/usr/bin:/bin"
        assert out["DISABLE_AUTOUPDATER"] == "1"
        assert out["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
        assert "service-role-fake" not in result.stdout
        assert "pk_fake_academia_token" not in result.stdout
        assert "secret-one" not in result.stdout

        # And the slot script actually created the fresh state on disk.
        project_dir = julia_tmp / "julia-0" / "home" / ".claude" / "projects" / "-app"
        assert project_dir.is_dir()
        assert (julia_tmp / "julia-0" / "tmp").is_dir()


@_SKIP_NOT_LINUX
class TestSlotScriptSweep:
    """Direct invocation of a (path-substituted) `julia-cli-slot` copy —
    no uid switch, no privilege needed: the sweep/handoff logic runs fine
    as the test's own uid once the `/run/julia-` prefix points at a
    tmp_path the test itself owns throughout."""

    def _slot_copy(self, tmp_path: Path, cli_stub: Path) -> Path:
        scratch_prefix = str(tmp_path / "julia-")
        return _copy_with_subs(
            _SLOT, tmp_path, "julia-cli-slot-under-test",
            {_JULIA_PREFIX_LITERAL: scratch_prefix, _CLI_TARGET_LITERAL: str(cli_stub)},
        )

    def _env_dumper(self, tmp_path: Path) -> Path:
        stub = tmp_path / "cli-stub.py"
        stub.write_text(
            f"#!{sys.executable}\nimport sys\nsys.exit(0)\n"
        )
        stub.chmod(0o755)
        return stub

    def test_sweeps_junk_files_and_a_chmod_000_directory(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        slot0 = tmp_path / "julia-0"
        slot0.mkdir(mode=0o700)
        (slot0 / "junk.txt").write_text("leftover from a SIGKILLed turn")
        locked_dir = slot0 / "locked"
        locked_dir.mkdir()
        (locked_dir / "inside.txt").write_text("nested leftover")
        locked_dir.chmod(0o000)
        big = slot0 / "big.bin"
        big.write_bytes(b"\0" * (1024 * 1024))  # 1MiB stand-in for "a 10MB file"

        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode == 0, result.stderr
        remaining = sorted(p.name for p in slot0.iterdir())
        assert remaining == ["home", "tmp"], remaining

    def test_julia_sweep_mode_only_sweeps_and_never_creates_fresh_state(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        slot0 = tmp_path / "julia-0"
        slot0.mkdir(mode=0o700)
        (slot0 / "junk.txt").write_text("leftover")

        result = _run(
            [str(slot_copy), "--julia-sweep"], env={"PATH": _path_with_fake_id(bindir)}
        )
        assert result.returncode == 0, result.stderr
        assert list(slot0.iterdir()) == [], "the sweep-only mode must not create home/tmp"

    def test_julia_sweep_mode_on_a_missing_slot_dir_is_a_clean_pass(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)
        # /run/julia-0 (here: tmp_path/julia-0) never created — the real
        # tmpfs mountpoint always pre-exists, but a vacuously-empty
        # nonexistent slot must not be treated as a failure.
        result = _run(
            [str(slot_copy), "--julia-sweep"], env={"PATH": _path_with_fake_id(bindir)}
        )
        assert result.returncode == 0, result.stderr


@_SKIP_NOT_LINUX
class TestSlotScriptHandoff:
    def _slot_copy(self, tmp_path: Path, cli_stub: Path) -> Path:
        scratch_prefix = str(tmp_path / "julia-")
        return _copy_with_subs(
            _SLOT, tmp_path, "julia-cli-slot-under-test",
            {_JULIA_PREFIX_LITERAL: scratch_prefix, _CLI_TARGET_LITERAL: str(cli_stub)},
        )

    def _env_dumper(self, tmp_path: Path) -> Path:
        stub = tmp_path / "cli-stub.py"
        stub.write_text(f"#!{sys.executable}\nimport sys\nsys.exit(0)\n")
        stub.chmod(0o755)
        return stub

    _VALID_SID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

    def test_copies_the_single_valid_uuid_handoff_file(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        handoff_dir = tmp_path / "julia-handoff" / "0"
        handoff_dir.mkdir(parents=True)
        handoff_file = handoff_dir / f"{self._VALID_SID}.jsonl"
        handoff_file.write_text('{"type": "mirror-frame"}\n')

        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode == 0, result.stderr
        copied = (
            tmp_path / "julia-0" / "home" / ".claude" / "projects" / "-app"
            / f"{self._VALID_SID}.jsonl"
        )
        assert copied.is_file()
        assert copied.read_text() == '{"type": "mirror-frame"}\n'

    def test_no_handoff_directory_is_a_normal_fresh_session(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)
        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode == 0, result.stderr

    def test_refuses_more_than_one_handoff_file(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        handoff_dir = tmp_path / "julia-handoff" / "0"
        handoff_dir.mkdir(parents=True)
        (handoff_dir / f"{self._VALID_SID}.jsonl").write_text("{}")
        (handoff_dir / "11111111-1111-1111-1111-111111111111.jsonl").write_text("{}")

        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode != 0
        assert "more than one entry" in result.stderr

    def test_refuses_a_non_uuid_named_handoff_file(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        handoff_dir = tmp_path / "julia-handoff" / "0"
        handoff_dir.mkdir(parents=True)
        (handoff_dir / "not-a-uuid.jsonl").write_text("{}")

        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode != 0
        assert "not a UUID-named .jsonl file" in result.stderr

    def test_refuses_a_symlinked_handoff_file(self, tmp_path):
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        handoff_dir = tmp_path / "julia-handoff" / "0"
        handoff_dir.mkdir(parents=True)
        real_target = tmp_path / "elsewhere.jsonl"
        real_target.write_text("{}")
        symlink = handoff_dir / f"{self._VALID_SID}.jsonl"
        symlink.symlink_to(real_target)

        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode != 0
        assert "is a symlink" in result.stderr

    def test_refuses_a_uuid_named_subdirectory(self, tmp_path):
        # Not a regular file at all — must be refused, not silently
        # ignored or (worse) recursed into.
        bindir = _fake_id_dir(tmp_path, "2000")
        cli_stub = self._env_dumper(tmp_path)
        slot_copy = self._slot_copy(tmp_path, cli_stub)

        handoff_dir = tmp_path / "julia-handoff" / "0"
        handoff_dir.mkdir(parents=True)
        (handoff_dir / f"{self._VALID_SID}.jsonl").mkdir()

        result = _run([str(slot_copy)], env={"PATH": _path_with_fake_id(bindir)})
        assert result.returncode != 0
        assert "not a regular file" in result.stderr
