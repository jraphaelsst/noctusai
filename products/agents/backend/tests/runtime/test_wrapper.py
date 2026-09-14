"""``bin/julia-cli-exec`` — the ``env -i`` wrapper (contract §E.5, SEC-C).

Spawns the wrapper for real (it is POSIX ``sh``, no network, no LLM call)
with ``JULIA_CLAUDE_BIN`` pointed at a tiny stub that prints its own
environment, from a parent env carrying FAKE secrets the wrapper must
strip. Asserts the child's env key set is EXACTLY the allowlist.
"""
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_WRAPPER = Path(__file__).resolve().parents[2] / "bin" / "julia-cli-exec"

_ALLOWLIST = {
    "HOME",
    "PATH",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_AGENT_SDK_VERSION",
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
# before a single line of the script body runs — so the env-dumper stub
# (a Python process, used *because* `sh`/`dash` inject their own PWD/SHLVL
# noise, see the fixture above) reports a key the wrapper never added.
# Confirmed directly: `env -i python3 -c "print(os.environ)"` shows
# LC_CTYPE=C.UTF-8; `env -i PYTHONCOERCECLOCALE=0 python3 -c ...` does not
# — and `env -i` cannot forward `PYTHONCOERCECLOCALE` to disable it without
# adding an unrelated key to the wrapper's real allowlist. This reproduces
# identically on Linux (CI run 34873469229 first surfaced it there) and
# macOS, so it is excluded unconditionally, by exact name, with this
# evidence trail — not a platform guess and not a blanket allowance for
# whatever a given run happens to emit.
_INTERPRETER_NOISE = {"LC_CTYPE"}


@pytest.fixture
def env_dumper_script(tmp_path: Path) -> Path:
    # A Python stub, not a shell script: `sh`/`dash` auto-populate `PWD` /
    # `SHLVL` / `_` into a NEW shell's own environment regardless of what
    # `env -i` handed it (a property of nested shells, not a wrapper leak)
    # — the real `JULIA_CLAUDE_BIN` target is a compiled CLI binary, not a
    # shell, so a Python stub is the closer analogue and keeps this test
    # measuring only what the wrapper itself controls.
    script = tmp_path / "env-dumper.py"
    script.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "for k, v in sorted(os.environ.items()):\n"
        "    print(f'{k}={v}')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


class TestWrapperExists:
    def test_wrapper_file_exists_and_is_executable(self):
        assert _WRAPPER.exists(), _WRAPPER
        mode = _WRAPPER.stat().st_mode
        assert mode & stat.S_IXUSR, "bin/julia-cli-exec must be committed with the executable bit set"


class TestWrapperStripsInheritedEnv:
    def test_child_env_key_set_is_exactly_the_allowlist(self, env_dumper_script):
        parent_env = {
            "JULIA_CLAUDE_BIN": str(env_dumper_script),
            "ANTHROPIC_API_KEY": "sk-ant-fake",
            "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
            "CLAUDE_AGENT_SDK_VERSION": "0.2.152",
            # Everything below MUST be stripped — the whole point of the wrapper.
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-fake",
            "ACADEMIA_API_TOKEN": "pk_fake_academia_token",
            "APPROVAL_ASSERTION_SECRETS": "secret-one,secret-two",
            "SOCIAL_WIRING_API_TOKEN": "pk_fake_social_wiring",
            "SOME_RANDOM_INHERITED_VAR": "should-not-survive",
            # A real subprocess needs SOME PATH to exec `/bin/sh` at all —
            # supplied here for the TEST's own subprocess.run call, not
            # forwarded by the wrapper (the wrapper hardcodes its own PATH).
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }

        result = subprocess.run(
            [str(_WRAPPER)],
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

    def test_secret_values_never_appear_in_child_output(self, env_dumper_script):
        parent_env = {
            "JULIA_CLAUDE_BIN": str(env_dumper_script),
            "ANTHROPIC_API_KEY": "sk-ant-fake",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-fake-marker",
            "ACADEMIA_API_TOKEN": "pk_fake_academia_token_marker",
            "APPROVAL_ASSERTION_SECRETS": "secret-marker-one,secret-marker-two",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        result = subprocess.run(
            [str(_WRAPPER)], env=parent_env, capture_output=True, text=True, timeout=10
        )
        assert "service-role-fake-marker" not in result.stdout
        assert "pk_fake_academia_token_marker" not in result.stdout
        assert "secret-marker-one" not in result.stdout

    def test_home_and_path_are_fixed_literals_not_inherited(self, env_dumper_script):
        parent_env = {
            "JULIA_CLAUDE_BIN": str(env_dumper_script),
            "HOME": "/Users/attacker-controlled-home",
            "PATH": "/attacker/bin:" + os.environ.get("PATH", "/usr/bin:/bin"),
        }
        result = subprocess.run(
            [str(_WRAPPER)], env=parent_env, capture_output=True, text=True, timeout=10
        )
        out = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )
        assert out["HOME"] != "/Users/attacker-controlled-home"
        assert "attacker" not in out["PATH"]

    def test_missing_julia_claude_bin_fails_loud(self):
        parent_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        result = subprocess.run(
            [str(_WRAPPER)], env=parent_env, capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0
