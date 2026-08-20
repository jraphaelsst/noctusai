"""Regression tests for the PreToolUse primary-checkout WRITE guard.

WHY A SECOND GATE EXISTS
────────────────────────
`check_primary_checkout_commit` (and its own test file next door) already
refuses a work COMMIT on a shared branch in the primary checkout. On 2026-08-18
an agent still did the work in the primary checkout twice in one session, with
that keeper installed and passing — because neither slip ever reached `git
commit`. It was caught by eye, and the remedy was a hand migration: diff the
primary, re-apply in a worktree, revert the primary.

A gate that fires after the work is done prevents the divergence but not the
waste. This one fires on the WRITE, which is the moment the mistake is actually
made. The two are deliberately independent: the Bash leg here can only ever be a
good parser of an arbitrary shell command, never a proof, so the commit keeper
stays as the backstop for whatever it misses.

WHY EVERY INPUT IS INJECTED
───────────────────────────
Same reason as the commit keeper's tests: the forbidden state is "primary
checkout on a shared branch", which a test must never create for real. The
`GuardContext` is constructed directly instead.

KB § PATTERNS/common/self-branching-mode.md ·
KB § PATTERNS/common/gate-methodology-sync.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.primary_write_guard import (  # noqa: E402
    SHARED_BRANCHES,
    GuardContext,
    bash_write_targets,
    decide,
    is_guarded_path,
)

PRIMARY = "/repo/noctusai"
WT = "/repo/noctusai/.claude/worktrees/my-slice"
OTHER_WT = "/repo/noctusai/.claude/worktrees/other-slice"


def _ctx(branch="dev"):
    return GuardContext(primary_root=PRIMARY, branch=branch, worktrees=(WT, OTHER_WT))


def _decide(tool, tool_input, cwd=WT, branch="dev"):
    return decide(tool, tool_input, cwd, ctx=_ctx(branch), allow_override=False)


# ── the block ──────────────────────────────────────────────────────────────

def test_editing_the_primary_checkout_on_dev_is_refused():
    """🔴 THE incident. If this stops failing, the slip is live again."""
    verdict = _decide("Edit", {"file_path": f"{PRIMARY}/products/social-wiring/backend/app/main.py"})
    assert verdict is not None
    # The refusal must hand over the next command, not just say no — a message
    # that only forbids gets routed around with a different tool.
    assert "task_branch" in verdict["reason"]
    assert "dev" in verdict["reason"]


def test_every_shared_branch_is_guarded_not_just_dev():
    for branch in SHARED_BRANCHES:
        assert _decide("Edit", {"file_path": f"{PRIMARY}/CLAUDE.md"}, branch=branch), branch


def test_a_feature_branch_in_the_primary_checkout_is_not_guarded():
    """The gate is about SHARED branches, not about the primary checkout."""
    assert _decide("Edit", {"file_path": f"{PRIMARY}/CLAUDE.md"}, branch="feat/x") is None


def test_write_and_notebookedit_are_covered_too():
    assert _decide("Write", {"file_path": f"{PRIMARY}/x.py"}) is not None
    assert _decide("NotebookEdit", {"notebook_path": f"{PRIMARY}/x.ipynb"}) is not None


# ── what must keep working ────────────────────────────────────────────────

def test_a_write_inside_a_linked_worktree_is_allowed():
    """The whole point. Worktrees live UNDER the primary root on disk, so a
    naive containment test would refuse the one place work belongs."""
    assert _decide("Edit", {"file_path": f"{WT}/products/social-wiring/x.tsx"}) is None
    assert _decide("Edit", {"file_path": f"{OTHER_WT}/x.tsx"}) is None


def test_ledger_paths_stay_writable():
    """Same exemption the commit keeper grants: the append-only ledgers are
    pushed straight to `dev` by design."""
    assert _decide("Write", {"file_path": f"{PRIMARY}/project-history/branch-tree.ndjson"}) is None


def test_reads_are_never_blocked():
    assert _decide("Read", {"file_path": f"{PRIMARY}/CLAUDE.md"}) is None
    assert _decide("Bash", {"command": f"cd {PRIMARY} && git status --short"}) is None
    assert _decide("Bash", {"command": f"grep -rn foo {PRIMARY}/products"}) is None


def test_the_orchestrators_own_git_duties_are_exempt_by_name():
    """Syncing and integrating the primary checkout on `dev` IS the job. A
    guard that fought it would be switched off, which costs more than it saves."""
    for command in (
        f"cd {PRIMARY} && git pull --ff-only",
        f"cd {PRIMARY} && git merge --no-ff feat/x",
        f"cd {PRIMARY} && git fetch origin",
        f"cd {PRIMARY} && git worktree list",
        f"cd {PRIMARY} && git push origin dev",
    ):
        assert _decide("Bash", {"command": command}) is None, command


def test_the_env_escape_hatch_is_honoured_when_asked_for_explicitly():
    assert decide(
        "Edit", {"file_path": f"{PRIMARY}/x.py"}, WT, ctx=_ctx(), allow_override=True
    ) is None


# ── the Bash leg: the shape the slip actually took ────────────────────────

def test_cd_into_the_primary_then_write_is_caught():
    """Both 2026-08-18 slips were this: a `cd` inside one Bash call re-points
    the write, and the harness's reported cwd still says the worktree."""
    verdict = _decide("Bash", {"command": f"cd {PRIMARY} && sed -i '' 's/a/b/' CLAUDE.md"})
    assert verdict is not None
    assert any(t.endswith("CLAUDE.md") for t in verdict["targets"])


def test_heredoc_into_the_primary_is_caught():
    verdict = _decide("Bash", {"command": f"cat > {PRIMARY}/CLAUDE.md <<'EOF'\nx\nEOF"})
    assert verdict is not None


def test_heredoc_into_a_worktree_is_allowed():
    assert _decide("Bash", {"command": f"cat > {WT}/note.md <<'EOF'\nx\nEOF"}) is None


def test_git_dash_c_into_the_primary_is_caught():
    assert _decide("Bash", {"command": f"git -C {PRIMARY} commit -am wip"}) is not None


def test_redirecting_to_a_sink_is_not_a_write():
    assert _decide("Bash", {"command": f"cd {PRIMARY} && grep -rn foo . > /dev/null"}) is None


def test_an_unparseable_interpreter_write_is_refused_conservatively():
    """`python -c "open(...).write(...)"` cannot be resolved to a target. The
    permissive answer is the one that lets the slip through, so it is refused
    against its effective cwd and the message says so."""
    verdict = _decide("Bash", {"command": f"cd {PRIMARY} && python -c \"open('x','w').write('1')\""})
    assert verdict is not None
    assert verdict["uncertain"] is True
    assert "could not be parsed" in verdict["reason"]


def test_writes_outside_the_repo_are_none_of_our_business():
    assert _decide("Bash", {"command": "cd /tmp && rm -rf junk"}) is None
    assert _decide("Write", {"file_path": "/tmp/scratch/plan.md"}) is None


def test_plain_sed_is_a_reader_but_sed_dash_i_is_not():
    assert _decide("Bash", {"command": f"cd {PRIMARY} && sed -n '1,5p' CLAUDE.md"}) is None
    assert _decide("Bash", {"command": f"cd {PRIMARY} && sed -i.bak 's/a/b/' CLAUDE.md"}) is not None


# ── the primitives ────────────────────────────────────────────────────────

def test_is_guarded_path_excludes_git_metadata():
    assert is_guarded_path(f"{PRIMARY}/CLAUDE.md", _ctx())
    assert not is_guarded_path(f"{PRIMARY}/.git/config", _ctx())
    assert not is_guarded_path("/elsewhere/file.py", _ctx())


def test_bash_write_targets_resolves_relative_paths_against_the_cd():
    targets, uncertain = bash_write_targets(f"cd {PRIMARY} && touch a/b.txt", WT)
    assert f"{PRIMARY}/a/b.txt" in targets
    assert uncertain is False


# ── the OVER-refusals, which are their own failure mode ───────────────────
#
# Both of these fired within minutes of the guard going live, on work that was
# already correctly aimed at a worktree. An over-refusing gate is not the safe
# direction — it is the direction where someone switches the gate off, and a
# gate that is off protects nothing.

def test_a_heredoc_body_is_data_not_shell():
    """The house style pipes Markdown and Python through `python - <<'PY'`.
    Prose contains `|` (Markdown tables) and `>` (blockquotes), so an unstripped
    body split into segments and `> **Fix:**` parsed as a redirect into a file
    named `**Fix:**` — resolved under the primary root, and refused."""
    command = (
        f"python - '{WT}/x.py' <<'PYEOF'\n"
        "| Origin | Result |\n"
        "> **Fix:** ship start.sh\n"
        "rm -rf /etc\n"
        "PYEOF"
    )
    assert _decide("Bash", {"command": command}) is None


def test_a_write_AFTER_a_heredoc_is_still_caught():
    """Stripping the body must not blind the guard to the rest of the line."""
    command = (
        f"python - <<'PY'\nprint('hi')\nPY\n"
        f"touch {PRIMARY}/leaked.txt"
    )
    assert _decide("Bash", {"command": command}) is not None


def test_two_heredocs_in_one_command_both_get_stripped():
    command = (
        f"cat <<'A' > {WT}/a.txt\n| x |\nA\n"
        f"cat <<'B' > {WT}/b.txt\n> y\nB"
    )
    assert _decide("Bash", {"command": command}) is None


def test_a_shell_variable_cd_is_not_read_as_a_relative_path():
    """`cd "$W" && …` — the variable could point anywhere. Treating it as a
    relative path under the primary root refused a correct worktree edit."""
    assert _decide("Bash", {"command": 'cd "$W" && python cli.py --verify'}) is None


def test_a_shell_variable_write_target_falls_back_to_the_known_cwd():
    """Unresolvable target ⇒ judge the cwd we DO know. From a worktree that is
    a pass; from the primary it still blocks."""
    assert _decide("Bash", {"command": 'touch "$W/out.txt"'}, cwd=WT) is None
    assert _decide("Bash", {"command": 'touch "$W/out.txt"'}, cwd=PRIMARY) is not None


def test_a_glob_target_is_not_resolved_literally():
    assert _decide("Bash", {"command": f"rm -f {WT}/dist/*.js"}) is None


# ── ledger parity with the commit keeper ──────────────────────────────────
#
# `check_primary_checkout_commit` allows a commit whose ENTIRE staged set lives
# under `project-history/` — that is how parallel agents publish branch
# pointers, and blocking it breaks coordination. This guard refused exactly
# that on 2026-08-19, one commit after a docstring claiming the two gates
# "cannot drift into disagreeing". They had.

def test_git_add_of_a_ledger_path_is_allowed():
    assert _decide("Bash", {"command": f"cd {PRIMARY} && git add project-history/"}) is None


def test_git_add_of_a_source_path_is_still_refused():
    assert _decide("Bash", {"command": f"cd {PRIMARY} && git add products/x/app.py"}) is not None


def test_git_add_mixing_ledger_and_source_is_refused():
    """The mixed case is how the exemption would be laundered — same reasoning
    as the commit keeper's `test_work_MIXED_INTO_a_ledger_commit_is_still_blocked`."""
    assert _decide(
        "Bash", {"command": f"cd {PRIMARY} && git add project-history/x.ndjson products/x/app.py"}
    ) is not None


def test_bare_git_add_with_no_pathspec_is_refused():
    """`git add -A` stages whatever happens to be dirty — unknowable here, and
    an unanswerable probe must fall through to the refusal, not past it."""
    assert _decide("Bash", {"command": f"cd {PRIMARY} && git add -A"}) is not None


# ── `>` that is not a redirect ────────────────────────────────────────────
#
# Fourth over-refusal of the same family (2026-08-19/20). The guard read the
# `>` inside `${ao:-<BLOCKED>}` as a redirect into a file named `}`, resolved
# it under the primary root, and refused a correct call. Bash performs no
# redirection inside `${…}`, `$((…))`, `((…))` or `[[…]]` — those spans are
# masked before the command grammar is applied, exactly as heredoc bodies are.

def test_a_default_value_containing_an_angle_bracket_is_not_a_redirect():
    """`${x:-<Y>}` — the over-refusal the user hit, worked around, and reported."""
    assert _decide("Bash", {"command": 'echo "ao=${ao:-<BLOCKED>}"'}, cwd=PRIMARY) is None
    assert bash_write_targets('printf "%s" "${x:-<Y>}"', PRIMARY) == ([], False)


def test_arithmetic_comparison_is_not_a_redirect():
    """`(( a > b ))` and `$(( x > 1 ))` compare; they do not open a file."""
    assert bash_write_targets("if (( a > b )); then echo hi; fi", PRIMARY) == ([], False)
    assert bash_write_targets('echo "$(( x > 1 ))"', PRIMARY) == ([], False)


def test_a_string_test_is_not_a_redirect():
    assert bash_write_targets('[[ "$a" > "$b" ]] && echo hi', PRIMARY) == ([], False)


def test_nested_parameter_expansion_is_masked_whole():
    assert bash_write_targets('echo "${a:-${b:-<Z>}}"', PRIMARY) == ([], False)


def test_masking_does_not_swallow_a_redirect_that_follows_it():
    """The mask must end at the closing brace, not run to end-of-command."""
    targets, _ = bash_write_targets(f'echo "${{x:-<Y>}}" > {PRIMARY}/out.txt', PRIMARY)
    assert targets == [f"{PRIMARY}/out.txt"]


def test_a_command_substitution_redirect_is_still_a_write():
    """`$( … )` runs real commands — masking it would trade a false refusal for
    a false PASS, which is the wrong direction to be wrong in."""
    assert _decide("Bash", {"command": f"echo $(ls > {PRIMARY}/sub.txt)"}, cwd=WT) is not None


def test_a_variable_cd_written_with_braces_stays_unresolvable():
    """`cd "${W}"` must behave exactly like `cd "$W"` — the masked span keeps
    its `$`, so it is opaque rather than quietly knowable."""
    assert _decide("Bash", {"command": 'cd "${W}" && python cli.py --verify'}) is None


# ── redirect targets the old char class could not see ─────────────────────

def test_a_quoted_redirect_target_is_still_a_write():
    """The original char class excluded `"`, so this matched NOTHING and the
    guard waved a primary-checkout write through. A quoting style is not a
    capability boundary."""
    assert _decide("Bash", {"command": f'echo hi > "{PRIMARY}/quoted.txt"'}, cwd=WT) is not None
    assert _decide("Bash", {"command": f"echo hi > '{PRIMARY}/quoted.txt'"}, cwd=WT) is not None


def test_a_quoted_sink_is_still_a_sink():
    assert _decide("Bash", {"command": 'echo hi > "/dev/null"'}, cwd=PRIMARY) is None


def test_an_fd_numbered_redirect_is_a_write():
    """`2> file` redirects stderr to a real file; the digit lookbehind hid it."""
    assert _decide("Bash", {"command": f"cmd 2> {PRIMARY}/err.log"}, cwd=WT) is not None


def test_stderr_to_stdout_is_not_a_file():
    assert bash_write_targets("cmd 2>&1", PRIMARY) == ([], False)


def test_an_unresolvable_redirect_target_falls_back_to_the_known_cwd():
    """Same rule the `_ALWAYS_WRITE` branch already applied to `cp $X`."""
    assert _decide("Bash", {"command": "echo hi > $TARGET"}, cwd=WT) is None
    assert _decide("Bash", {"command": "echo hi > $TARGET"}, cwd=PRIMARY) is not None


def test_an_unterminated_expansion_terminates():
    """A stray `${` must not spin the masker.

    This is not a parse-quality test. `decide()` runs in a PreToolUse hook on
    every Bash call, so a non-terminating parse is a frozen session, not a
    wrong answer — the first cut of the masker did exactly that on `echo ${foo`.
    """
    for command in ("echo ${foo", "echo $((1+2", "echo [[ a", "echo (( a"):
        assert bash_write_targets(command, PRIMARY) == ([], False)


def test_masking_survives_a_realistic_house_one_liner():
    """The shape that triggered the report: a status line built from a default
    value, inside a worktree, next to a real command."""
    assert _decide(
        "Bash",
        {"command": 'ao="$(git rev-parse HEAD)"; echo "ao=${ao:-<BLOCKED>}" && git status --short'},
        cwd=WT,
    ) is None


# ── quotes: the two defects a regex cannot separate ───────────────────────
#
# Widening the target char class to accept quotes fixed the invisible quoted
# redirect and immediately broke its mirror image: a `>` INSIDE a quoted
# argument started parsing as a redirect. Both were measured against the live
# hook on 2026-08-20 — the second one refused the very command written to
# verify the first. Tracking quote state is what tells them apart.

def test_an_arrow_inside_a_quoted_argument_is_not_a_redirect():
    """`python3 -c "print('->', x)"` — program text, not shell grammar."""
    assert _decide(
        "Bash",
        {"command": """python3 -c "print(repr(c), '->', targets(c, '/tmp'))\""""},
        cwd=PRIMARY,
    ) is None


def test_an_angle_bracket_inside_a_plain_quoted_string_is_not_a_redirect():
    assert bash_write_targets('echo "a > b"', PRIMARY) == ([], False)
    assert bash_write_targets("echo 'a > b'", PRIMARY) == ([], False)


def test_a_quoted_redirect_target_is_a_write_in_both_quote_styles():
    assert _decide("Bash", {"command": f'echo hi > "{PRIMARY}/q.txt"'}, cwd=WT) is not None
    assert _decide("Bash", {"command": f"echo hi > '{PRIMARY}/q.txt'"}, cwd=WT) is not None


def test_append_and_fd_and_ampersand_redirects_are_all_writes():
    for command in (
        f"echo hi >> {PRIMARY}/a.txt",
        f"cmd 2> {PRIMARY}/err.log",
        f"cmd &> {PRIMARY}/both.log",
    ):
        assert _decide("Bash", {"command": command}, cwd=WT) is not None, command


def test_descriptor_duplication_names_no_file():
    assert bash_write_targets("cmd 2>&1", PRIMARY) == ([], False)
    assert bash_write_targets("cmd > /dev/null 2>&1", PRIMARY) == ([], False)


def test_a_redirect_inside_a_quoted_span_does_not_leak_across_a_pipe():
    """Redirects are scanned over the whole command, because `_segments` splits
    on `|` without regard for quotes and would cut a quoted span in half."""
    assert bash_write_targets('echo "a | b > c" | cat', PRIMARY) == ([], False)
