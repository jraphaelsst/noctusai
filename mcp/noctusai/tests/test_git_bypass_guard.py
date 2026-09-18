"""Regression tests for the PreToolUse git-hooks-bypass guard
(`primary_write_guard.decide_git_bypass`).

THE INCIDENT THIS ENCODES
──────────────────────────
`git -c core.hooksPath=.git/hooks commit -q -F - <<'MSG' … MSG` committed with
**no hooks at all, exit 0, no warning**. This repo configures `core.hooksPath`
to an ABSOLUTE path (`<primary>/.git/hooks`, entries symlinked to
`scripts/hooks/`); the override above was RELATIVE, and git resolves a
relative `core.hooksPath` against the CWD. Run from a linked worktree — where
`.git` is a FILE (`gitdir: …`), not a directory — `.git/hooks` under that cwd
never existed, so every hook was silently skipped.

Why this is worse than `--no-verify`: `--no-verify` is named in CLAUDE.md §1,
means "skip the gate" on its face, and the harness classifier catches it. A
`-c core.hooksPath=…` override reads as being MORE careful about hooks and
nothing catches it — the one SILENT rationalization shape in
`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`.

WHY THIS IS A SEPARATE GUARD FROM `decide()`
──────────────────────────────────────────────
`decide()` (tested in `test_primary_write_guard.py`) answers "does this write
land in the wrong TREE". This answers "does this git invocation skip its own
SAFETY MECHANISM" — true or false independent of branch or worktree, so it
does not take a `GuardContext` at all.

KB § PATTERNS/common/self-branching-mode.md ·
KB § PATTERNS/common/bypass-rationalization-anti-patterns.md ·
KB § PATTERNS/common/gate-methodology-sync.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.primary_write_guard import (  # noqa: E402
    HOOK_BYPASS_ALLOW_ENV,
    decide_git_bypass,
)


def _decide(command, allow_override=False):
    return decide_git_bypass("Bash", {"command": command}, allow_override=allow_override)


# ── the incident, verbatim ──────────────────────────────────────────────────

def test_THE_incident_command_verbatim_is_refused():
    """🔴 THE incident, exact command. If this stops failing, the slip is live
    again — no hedging, no paraphrase."""
    incident = (
        "git -c core.hooksPath=.git/hooks commit -q -F - <<'MSG'\n"
        "some commit message\n"
        "MSG"
    )
    verdict = _decide(incident)
    assert verdict is not None
    assert "core.hooksPath" in verdict["reason"]
    assert "silently" in verdict["reason"]


# ── (1) `-c core.hooksPath=…` in every spelling ─────────────────────────────

def test_dash_c_core_hookspath_is_refused():
    assert _decide("git -c core.hooksPath=/dev/null commit -m x") is not None


def test_dash_c_and_value_as_separate_argv_entries_is_refused():
    """The normal shlex tokenization of `-c core.hooksPath=x` — `-c` and
    `core.hooksPath=x` land as two separate tokens with no `=` between them;
    this is not an edge case, it is how every real invocation tokenizes."""
    assert _decide("git -c core.hooksPath=x commit -m x") is not None


def test_long_config_flag_two_token_form_is_refused():
    assert _decide("git --config core.hooksPath=x commit -m x") is not None


def test_long_config_flag_fused_form_is_refused():
    assert _decide("git --config=core.hooksPath=x commit -m x") is not None


def test_config_env_two_token_form_is_refused():
    assert _decide("git --config-env core.hooksPath=SOME_ENV commit -m x") is not None


def test_config_env_fused_form_is_refused():
    assert _decide("git --config-env=core.hooksPath=SOME_ENV commit -m x") is not None


def test_case_insensitive_key_spelling_is_refused():
    assert _decide("git -c Core.HooksPath=x commit -m x") is not None


def test_dash_c_hookspath_fires_regardless_of_subcommand():
    """There is no legitimate reason to override core.hooksPath inline, on
    ANY subcommand — refusing unconditionally is the safe default."""
    assert _decide("git -c core.hooksPath=x status") is not None
    assert _decide("git -c core.hooksPath=x log") is not None


# ── (2) `core.hooksPath` set to anything other than the configured value ──

def test_bare_config_set_to_relative_path_is_refused():
    assert _decide("git config core.hooksPath .git/hooks") is not None


def test_bare_config_set_to_dev_null_is_refused():
    assert _decide("git config core.hooksPath /dev/null") is not None


def test_bare_config_set_to_empty_string_is_refused():
    assert _decide('git config core.hooksPath ""') is not None


def test_config_unset_is_refused():
    assert _decide("git config --unset core.hooksPath") is not None


def test_config_global_scope_is_refused_unconditionally():
    """--global affects every OTHER checkout on the machine too — never
    assumed harmless just because a value looks plausible."""
    assert _decide("git config --global core.hooksPath /dev/null") is not None


# ── (3) `--no-verify` / `-n` on commit and push ─────────────────────────────

def test_no_verify_on_commit_is_refused():
    assert _decide("git commit -m x --no-verify") is not None


def test_no_verify_on_push_is_refused():
    assert _decide("git push --no-verify origin dev") is not None


def test_bare_dash_n_on_commit_is_refused():
    assert _decide("git commit -n -m x") is not None


def test_clustered_dash_n_on_commit_is_refused():
    assert _decide("git commit -qn -m x") is not None
    assert _decide("git commit -nq -m x") is not None


def test_dash_n_on_push_is_ALLOWED_it_means_dry_run_not_no_verify():
    """`git push -h`: '-n, --[no-]dry-run  dry run' — push's `--no-verify` has
    NO short alias. Treating `-n` as a bypass on push would refuse an
    ordinary dry run on every use."""
    assert _decide("git push -n origin dev") is None
    assert _decide("git push --dry-run origin dev") is None


def test_dash_n_on_log_is_ALLOWED_it_limits_count():
    """`git log -n 5` is the single most common use of `-n` in this
    ecosystem; a scoped check (commit/push only) must never touch it."""
    assert _decide("git log --oneline -n 5") is None


# ── (4) GIT_CONFIG_* env-prefix injection ───────────────────────────────────

def test_inline_git_config_env_prefix_is_refused():
    cmd = "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x"
    assert _decide(cmd) is not None


def test_exported_git_config_env_prefix_on_an_earlier_line_is_refused():
    cmd = "export GIT_CONFIG_KEY_0=core.hooksPath; export GIT_CONFIG_VALUE_0=/dev/null; git commit -m x"
    assert _decide(cmd) is not None


# ── the command appearing anywhere in a compound line ───────────────────────

def test_after_a_cd_and_double_ampersand_is_refused():
    assert _decide("cd worktree && git -c core.hooksPath=x commit -m y") is not None


def test_after_a_semicolon_is_refused():
    assert _decide("echo hi; git -c core.hooksPath=x commit -m y") is not None


def test_inside_a_subshell_is_refused():
    assert _decide('(cd wt && git -c core.hooksPath=x commit -m y)') is not None


def test_after_a_pipe_via_xargs_is_refused():
    assert _decide("echo hi | xargs -I{} git commit --no-verify -m {}") is not None


def test_after_a_redirect_noise_token_is_still_refused():
    """`2>&1` tokenizes as ordinary argv without redirect-stripping — the
    exact `_strip_redirections` regression class documented in
    `primary_write_guard.py`."""
    assert _decide("some_cmd 2>&1 | git commit --no-verify -m x") is not None


# ── what must keep working ───────────────────────────────────────────────

def test_a_plain_commit_is_allowed():
    assert _decide('git commit -m "normal commit"') is None


def test_a_plain_push_is_allowed():
    assert _decide("git push origin dev") is None


def test_an_unrelated_dash_c_flag_is_allowed():
    assert _decide("git -c user.name=Bob -c user.email=a@b commit -m x") is None


def test_reading_hookspath_is_allowed_a_read_not_an_override():
    assert _decide("git config core.hooksPath") is None
    assert _decide("git config --get core.hooksPath") is None


def test_merge_rebase_am_cherry_pick_without_a_bypass_flag_are_allowed():
    for cmd in (
        "git merge origin/dev",
        "git rebase origin/dev",
        "git am /tmp/x.patch",
        "git cherry-pick abc123",
    ):
        assert _decide(cmd) is None, cmd


def test_a_non_git_command_is_allowed():
    assert _decide("echo core.hooksPath --no-verify") is None


def test_only_bash_is_relevant_edit_cannot_express_a_hooks_bypass():
    verdict = decide_git_bypass("Edit", {"file_path": "/repo/x.py"})
    assert verdict is None


# ── the escape hatch ─────────────────────────────────────────────────────

def test_allow_override_true_permits_the_incident():
    assert _decide("git -c core.hooksPath=.git/hooks commit -m x", allow_override=True) is None


def test_env_var_escape_hatch_is_separate_from_the_primary_write_one():
    """Distinct env var from `primary_write_guard.ALLOW_ENV` — allowing a
    primary-checkout write says nothing about allowing a hooks bypass."""
    assert HOOK_BYPASS_ALLOW_ENV == "NOCTUS_ALLOW_HOOK_BYPASS"
    from tools.noctus.dev.primary_write_guard import ALLOW_ENV
    assert HOOK_BYPASS_ALLOW_ENV != ALLOW_ENV
