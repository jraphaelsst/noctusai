"""Refuse a WRITE aimed at the primary checkout while it sits on a shared branch.

**The gap this closes.** `check_primary_checkout_commit` (compliance.py) already
refuses a *work commit* on `dev`/`main`/`prod` in the primary checkout. It is the
right gate in the wrong place: by the time a commit is attempted the work has
already been done in the wrong tree, and the only remedy left is a hand
migration — diff the primary, re-apply in a worktree, revert the primary, and
hope nothing was missed. On 2026-08-18 that happened twice inside a single
session, to an agent that had the rule in context both times, with the commit
keeper installed and working. The keeper caught neither, because neither slip
ever reached `git commit`.

**Why it keeps happening.** Nothing fails at the moment of the mistake. The
harness runs a tool call per turn, each with its own working directory, and a
`cd <primary> && …` inside one Bash call silently re-points the *next* relative
edit at the primary tree. The rule is absolute, stated in `CLAUDE.md` §1 and in
skill `noc-self-branch`, and it is still a rule enforced by memory across a
context window that gets summarized. That is precisely the class of rule that
`KB § PATTERNS/common/gate-methodology-sync.md` says must ship a mechanism.

**Where it runs.** As a `PreToolUse` hook over `Edit`/`Write`/`NotebookEdit` and
`Bash` (`.claude/settings.json` → `scripts/hooks/claude-guard-primary-write.py`),
so the write is refused BEFORE it lands rather than reported after. The commit
keeper stays as the backstop for anything the heuristics below miss — two
independent gates, deliberately, because the Bash leg can only ever be a good
parser of an arbitrary shell command, never a proof.

**Design constraints.**

* *Stdlib only, no `settings` import.* The hook pays this module's import cost on
  EVERY tool call. `compliance.py` costs ~0.27 s to import; that is a quarter of
  a second added to every command in every session, which is how a gate becomes
  the thing people disable. This module imports in single-digit milliseconds.
* *Linked worktrees live INSIDE the primary root.* `.claude/worktrees/<slug>/`
  is a path under the primary checkout, so a naive "is it under the repo root?"
  test would refuse every write the methodology actually wants. Worktree roots
  come from `git worktree list --porcelain`, never from a path convention.
* *Reads are never blocked.* Only a detected write INTENT with a target that
  resolves into the guarded region is refused.
* *Everything is injectable* so the decision is testable without creating the
  very state it forbids (a real primary checkout dirty on a real shared branch).

**Escape hatch.** `NOCTUS_ALLOW_PRIMARY_WRITE=1`, matching the commit keeper's
`NOCTUS_ALLOW_PRIMARY_COMMIT=1` — an env var rather than a flag, so it cannot be
set once and forgotten inside a script, and it is reported loudly when used.

🔴 **It is NOT usable from inside a denied command, and that is by design.**
This runs as a `PreToolUse` hook: a SEPARATE process that reads its OWN
`os.environ` and answers *before* the command is ever executed. So prefixing
the command — `NOCTUS_ALLOW_PRIMARY_WRITE=1 rm -rf x/` — is inert; the hook
sees that text as part of a string it is about to refuse, and the assignment
would only have applied to a child process that never runs. The variable has to
be in the environment of the Claude Code process itself (its launching shell,
or `.claude/settings.json` → `env`), which makes reaching for it a deliberate
human act rather than something an agent can type its way into mid-task.

That property is worth keeping, so the answer to a false positive is never
"hand the agent the hatch" — it is to design the legitimate case out of the
guard. Two are already designed out: orchestration writes (`git pull`,
`git merge` during an integrate, `git worktree`) are exempt BY NAME below, and
anything `.gitignore` declares out-of-repo is exempt via `_git_ignores` —
because content that cannot become a commit cannot cause the divergence this
gate exists to prevent.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: Branches nobody may hold work on in the primary checkout. Same set the
#: commit keeper uses; kept here because this module is the one with no
#: heavyweight imports, and `compliance.py` imports it back.
SHARED_BRANCHES = frozenset({"dev", "main", "prod"})

#: The ONE sanctioned reason to write the primary checkout on a shared branch:
#: the MCP toolkit's append-only ledgers, which are committed straight to `dev`
#: by design (branch_pointer, worktree-salvage, auto-improvement, vector-costs).
LEDGER_PREFIXES = ("project-history/",)

ALLOW_ENV = "NOCTUS_ALLOW_PRIMARY_WRITE"

#: Escape hatch for `decide_git_bypass` below — deliberately a SEPARATE env
#: var from `ALLOW_ENV`: allowing a primary-checkout write says nothing about
#: allowing a hooks bypass, and vice versa. See that function's docstring
#: block for why this is a distinct concern living in the same module.
HOOK_BYPASS_ALLOW_ENV = "NOCTUS_ALLOW_HOOK_BYPASS"

#: Tools that name their target outright — no parsing, no ambiguity.
_FILE_PATH_TOOLS = {
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}

#: Commands whose whole purpose is to modify a file. `sed` is deliberately
#: absent — plain `sed` is a reader; only `sed -i` writes, handled below.
_ALWAYS_WRITE = {
    "tee", "cp", "mv", "rm", "mkdir", "rmdir", "touch", "patch", "dd",
    "truncate", "install", "ln", "chmod", "chown", "rsync", "unzip", "tar",
}

#: `SOURCE… DEST` commands: the sources are READS, and the only write is the
#: destination. Judging every path-looking argument as a target refused
#: `cp <primary-file> <scratchpad-dest>` — copying OUT of the primary, which
#: this guard has no business blocking (hit for real 2026-09-17, three times in
#: one session, while trying to preserve a file BEFORE removing it).
#:
#: `mv` is deliberately ABSENT: it creates the destination *and* removes the
#: source, so both really are writes. So are `tar`/`unzip`/`dd`/`tee`/`patch`,
#: whose target is flag- or stdin-driven rather than positional — narrowing
#: those would be a guess, and a guess here fails OPEN.
_DEST_ONLY_WRITE = {"cp", "install", "rsync", "ln"}

#: `chmod`/`chown` option flags that take no operand. Anything else in the
#: leading position is the MODE/OWNER operand. A chmod mode can itself look
#: like a flag (`chmod -x f`), which is why this is an allow-list of real
#: options, not a "starts with -" test.
_CHMOD_CHOWN_FLAGS = {
    "-R", "-v", "-c", "-f", "-h", "-H", "-L", "-P",
    "--recursive", "--verbose", "--changes", "--silent", "--quiet",
    "--no-dereference", "--dereference", "--preserve-root", "--no-preserve-root",
}
#: `install` options whose NEXT token is a value, not a path.
_INSTALL_VALUE_FLAGS = {"-m", "-o", "-g", "--mode", "--owner", "--group"}


def _drop_non_path_operands(name: str, args: list[str]) -> list[str]:
    """Remove operands that are never a write target, so they can't be judged
    as a path: `chmod`'s MODE and `chown`'s OWNER[:GROUP] (the first non-option
    operand, unless `--reference=` supplies it), and `install`'s `-m/-o/-g`
    values. Seen 2026-09-24: `chmod 700 ~/x` was refused because `700`
    resolved to `<primary>/700`."""
    if name in ("chmod", "chown"):
        if any(a.startswith("--reference") for a in args):
            return list(args)
        out, dropped = [], False
        for a in args:
            if not dropped and a not in _CHMOD_CHOWN_FLAGS:
                dropped = True
                continue
            out.append(a)
        return out
    if name == "install":
        out, skip = [], False
        for a in args:
            if skip:
                skip = False
                continue
            if a in _INSTALL_VALUE_FLAGS:
                skip = True
                continue
            if any(a.startswith(f + "=") for f in ("--mode", "--owner", "--group")):
                continue
            out.append(a)
        return out
    return list(args)


#: GNU `-t DIR` / `--target-directory=DIR` inverts the argument order, so the
#: destination is that flag's operand and NOT the last positional.
_TARGET_DIR_FLAGS = {"-t", "--target-directory"}

#: `git reset` modes that touch the WORKING TREE. The pathspec form
#: (`git reset -- <paths>`) touches only the index, which is why it is eligible
#: for the ledger exemption; these three are not.
_RESET_WORKTREE_FLAGS = {"--hard", "--merge", "--keep"}

#: `git` subcommands that mutate the working tree or the index of the checkout
#: they run in. `pull`, `fetch`, `merge`, `push`, `worktree`, `tag` and `branch`
#: are NOT here: syncing and integrating the primary checkout on `dev` is the
#: orchestrator's actual job, and a guard that fought it would be switched off.
_GIT_WRITE_SUBCOMMANDS = {
    "commit", "add", "apply", "am", "cherry-pick", "revert", "rebase", "reset",
    "checkout", "switch", "restore", "stash", "clean", "mv", "rm",
}

#: `<subcommand> <first-non-flag-token>` pairs that are READS despite `sub`
#: living in `_GIT_WRITE_SUBCOMMANDS` above. `stash` bare/`push` writes, but
#: `stash list`/`stash show` only print — verified 2026-08-31 against
#: `git stash -h`, which lists these as the read-only sub-verbs.
_GIT_READ_ONLY_SUBVERBS = {
    "stash": {"list", "show"},
}

#: Flags that turn an otherwise write-capable subcommand into a dry run —
#: verified 2026-08-31 against each command's own `-h`: `git rm -n`,
#: `git mv -n`, `git clean -n` all print `dry run` in their own help text;
#: `git apply --check` "instead of applying the patch, see if it applies".
#: Audited over every member of `_GIT_WRITE_SUBCOMMANDS`; the rest
#: (`commit`, `add`, `am`, `cherry-pick`, `revert`, `rebase`, `reset`,
#: `checkout`, `switch`, `restore`) have no such flag, so they are absent
#: rather than silently assumed safe.
_GIT_DRY_RUN_FLAGS = {
    "clean": {"-n", "--dry-run"},
    "rm": {"-n", "--dry-run"},
    "mv": {"-n", "--dry-run"},
    "apply": {"--check"},
}

#: `-h`/`--help` on ANY write-capable subcommand prints usage and exits
#: without touching the tree — true for every git subcommand, not just the
#: ones enumerated above, so this is checked independently of `sub`.
_HELP_FLAGS = {"-h", "--help"}


def _is_read_only_git(sub: str, rest: Sequence[str]) -> bool:
    """Is `git <sub> …` a READ despite `sub` being write-capable in general?

    Two shapes, both audited off `_GIT_WRITE_SUBCOMMANDS` itself rather than
    hardcoded to the one instance that got reported (`git stash list`,
    2026-08-31): a SUB-verb that only prints, and a flag that turns an
    otherwise-mutating verb into a dry run or a help screen.
    """
    if _HELP_FLAGS & set(rest):
        return True
    tail = rest[rest.index(sub) + 1:] if sub in rest else []
    subverb = next((a for a in tail if not a.startswith("-")), "")
    if subverb in _GIT_READ_ONLY_SUBVERBS.get(sub, set()):
        return True
    if _GIT_DRY_RUN_FLAGS.get(sub, set()) & set(tail):
        return True
    return False


#: Redirection targets that are sinks, not files.
_SINKS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"}

#: `cd <dir>` in command position. MULTILINE is load-bearing: a bare `^` anchors
#: to the START OF THE COMMAND only, so a `cd` on the second or later LINE of a
#: multi-line Bash call was invisible — the guard then judged the write against
#: the session cwd (the primary) and refused a call that was correctly aimed at a
#: worktree. Measured 2026-08-20, on a command whose only sin was putting a
#: `pkill` on the line above the `cd`.
_CD_RE = re.compile(
    r"(?:^|[;&|]|&&)\s*cd\s+(?P<path>'[^']*'|\"[^\"]*\"|[^\s;|&]+)",
    re.MULTILINE,
)
_PY_WRITE_RE = re.compile(r"open\s*\([^)]*['\"][arw]b?\+?['\"]|Path\([^)]*\)\.write_")
#: `cmd <<'TAG'` / `<<TAG` / `<<-TAG` — the body up to the terminator is DATA.
_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _strip_heredocs(command: str) -> str:
    """Drop every heredoc BODY, keeping the command lines around it.

    Without this the guard reads prose as shell, and it is not a rare edge: the
    house style pipes Markdown and Python into `python - <<'PY'` constantly, and
    a Markdown table's `|` splits into segments while `> **Fix:**` parses as a
    redirect into a file literally named `**Fix:**`. That resolved under the
    primary root and refused the call — an over-refusal on 2026-08-19, minutes
    after the guard went live, on a docs edit that was already correctly aimed
    at a worktree.

    An over-refusing gate is not the safe direction. It is the direction where
    someone switches the gate off, and then it protects nothing
    (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`).
    """
    lines = command.split("\n")
    out: list[str] = []
    pending: list[str] = []
    skipping_until: str | None = None

    for line in lines:
        if skipping_until is not None:
            if line.strip() == skipping_until:
                skipping_until = None
            continue
        out.append(line)
        tags = [m.group(2) for m in _HEREDOC_RE.finditer(line)]
        if tags:
            pending = tags
        if pending:
            skipping_until = pending.pop(0)
    return "\n".join(out)


#: Regions where `<` and `>` are NOT redirects. Bash performs no redirection
#: inside any of them, so a `>` there is a default-value literal, an arithmetic
#: comparison, or a string test — never a file to write.
#:
#: `$( … )` is deliberately ABSENT: command substitution runs real commands, and
#: `echo $(ls > /primary/f)` really does write. Masking it would trade a false
#: refusal for a false pass, which is the wrong direction to be wrong in.
_MASKABLE = (
    ("${", "}", "$_NOCEXP"),    # parameter expansion — `${x:-<Y>}`
    ("$((", "))", "$_NOCEXP"),  # arithmetic expansion — `$(( x > 1 ))`
    ("((", "))", "_NOCTEST"),   # arithmetic command  — `(( a > b ))`
    ("[[", "]]", "_NOCTEST"),   # conditional expr    — `[[ a > b ]]`
)


def _mask_expansions(command: str) -> str:
    """Blank out expansion/test regions so their `>` is not read as a redirect.

    Same move as :func:`_strip_heredocs`, one level down: remove the spans that
    are not command grammar BEFORE applying command grammar to what is left.
    Without it `echo "${ao:-<BLOCKED>}"` parses as a redirect into a file named
    `}`, resolves it under the primary root, and refuses the call — an
    over-refusal on 2026-08-19, and the fourth of its family.

    The `$`-bearing placeholder is load-bearing: it keeps the masked span
    UNRESOLVABLE (:func:`_is_unresolvable`), so `cd "${W}"` still means "we
    cannot know where this lands" exactly as `cd "$W"` already did, rather than
    quietly becoming a knowable path.
    """
    out: list[str] = []
    i, n = 0, len(command)
    while i < n:
        span = _masked_span(command, i)
        if span is None:
            out.append(command[i])
            i += 1
            continue
        placeholder, end = span
        out.append(placeholder)
        i = end
    return "".join(out)


def _masked_span(command: str, i: int) -> tuple[str, int] | None:
    """`(placeholder, end_index)` if a maskable region opens at `i`, else None.

    Returning None for an UNTERMINATED opener is what keeps the caller advancing.
    An earlier cut folded this into the caller's loop and left `i` unchanged on
    that path — `echo ${foo` spun forever, which in a PreToolUse hook is not a
    parse bug but a frozen session.
    """
    for opener, closer, placeholder in _MASKABLE:
        if not command.startswith(opener, i):
            continue
        depth, j, n = 1, i + len(opener), len(command)
        while j < n:
            if command.startswith(closer, j):
                depth -= 1
                j += len(closer)
                if not depth:
                    return placeholder, j
            elif command.startswith(opener, j):
                depth += 1
                j += len(opener)
            else:
                j += 1
        # Unterminated: leave the text verbatim rather than swallowing a real
        # redirect that follows a stray brace.
        return None
    return None


#: Characters that end an unquoted word.
_WORD_BREAK = set(" \t\n;|&<>()")


def _redirect_targets(command: str) -> list[str]:
    """Every file a redirect in `command` would write, as written.

    A SCANNER, not a regex, because the two things a regex cannot tell apart
    here are exactly the two that matter:

      echo hi > "/primary/f"      ← a quoted TARGET. The original char class
                                    excluded quotes, so this matched nothing at
                                    all and the guard waved a primary-checkout
                                    write straight through.
      python3 -c "print('->')"    ← a `>` INSIDE a quoted argument. Widening the
                                    char class to accept quotes made this parse
                                    as a redirect and refused the call — traded
                                    one defect for its mirror image.

    Tracking quote state answers both: a `>` seen inside quotes is never a
    redirect, and a quoted word following an unquoted `>` always is. Both
    measured against the live hook on 2026-08-20.

    `2>&1` and `>&2` duplicate a descriptor rather than naming a file, so a
    target starting with `&` is skipped. `2> file` and `&> file` are real writes
    and are returned — a digit-blind lookbehind used to hide the first.
    """
    out: list[str] = []
    i, n = 0, len(command)
    quote: str | None = None

    while i < n:
        ch = command[i]
        if quote is not None:
            # Inside a quoted span nothing is shell grammar. `\` escapes only
            # within double quotes; a single-quoted span is fully literal.
            if ch == "\\" and quote == '"' and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch != ">":
            i += 1
            continue

        i += 1
        if i < n and command[i] == ">":  # `>>` append
            i += 1
        while i < n and command[i] in " \t":
            i += 1
        if i < n and command[i] == "&":  # `2>&1` — a dup, not a file
            i += 1
            continue

        word, i = _read_word(command, i)
        if word:
            out.append(word)

    return out


def _read_word(command: str, i: int) -> tuple[str, int]:
    """Read one shell word from `i`, honouring quotes. Returns (word, next_i)."""
    n = len(command)
    parts: list[str] = []
    quote: str | None = None
    while i < n:
        ch = command[i]
        if quote is not None:
            if ch == quote:
                quote = None
            else:
                parts.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch in _WORD_BREAK:
            break
        parts.append(ch)
        i += 1
    return "".join(parts), i


def _normalize(command: str) -> str:
    """The ONE pre-parse normalization, shared by every reader of a command.

    Both `_effective_cwd` and `bash_write_targets` must see the same string. The
    2026-08-19 ledger-parity bug was two gates applying the same rule through
    two code paths; this keeps that from recurring one layer down.
    """
    return _mask_expansions(_strip_heredocs(command))


@dataclass
class GuardContext:
    """Everything the decision needs about the checkout layout."""

    primary_root: str
    branch: str
    worktrees: tuple[str, ...] = field(default_factory=tuple)

    @property
    def guarded(self) -> bool:
        return self.branch in SHARED_BRANCHES


def _run_git(args: Sequence[str], cwd: str | None) -> str:
    ok, out = _run_git_checked(args, cwd)
    return out if ok else ""


def _run_git_rc(args: Sequence[str], cwd: str | None = None) -> int:
    """The git EXIT CODE, for probes whose answer *is* the code.

    `git check-ignore -q` is the caller that needs this: 0 = ignored,
    1 = not ignored, 128 = could not answer. `_run_git` collapses 1 and 128 into
    the same empty string, which would make "this path is tracked" and "git is
    broken" indistinguishable — and those must land on the same SIDE here
    (refuse) but for different reasons, so the distinction is kept readable.

    Returns 128 when git cannot be run at all, so an unavailable probe is never
    mistaken for a clean 0.
    """
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 128
    return out.returncode


def _run_git_checked(args: Sequence[str], cwd: str | None) -> tuple[bool, str]:
    """`(probe_answered, stdout)` — the distinction `_run_git` throws away.

    🔴 `_run_git` returns `""` both when git SAID nothing and when git could not
    be asked, which is fine for every caller that treats an empty answer as
    "unknown ⇒ refuse". `_is_ledger_only_git`'s commit leg is the one caller for
    which the two differ in DIRECTION: an empty staged set is a positive answer
    (a compound whose ledger-only `add` has not run yet ⇒ allow), while a failed
    probe is no answer at all (⇒ refuse). Collapsing them would turn every
    environment where the probe breaks into a blanket allow — the exact
    fail-OPEN inversion this module's docstring forbids.
    """
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if out.returncode != 0:
        return False, ""
    return True, out.stdout.strip()


def discover_context(cwd: str | None = None) -> GuardContext | None:
    """The primary checkout's root + current branch + every linked worktree.

    Returns None when the probe cannot answer — outside a repo, or git itself
    failing. A guard that cannot see MUST NOT block: an unreadable probe is our
    problem, and turning it into a refused edit would make every non-repo
    directory unusable.
    """
    common = _run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    if not common:
        return None
    primary = os.path.dirname(os.path.normpath(common))
    if not primary:
        return None

    branch = _run_git(["-C", primary, "symbolic-ref", "--short", "HEAD"], None)
    if not branch:
        return None  # detached HEAD in the primary: not a shared-branch slip

    worktrees: list[str] = []
    for line in _run_git(["-C", primary, "worktree", "list", "--porcelain"], None).splitlines():
        if line.startswith("worktree "):
            path = os.path.normpath(line[len("worktree "):].strip())
            if path and os.path.normpath(path) != primary:
                worktrees.append(path)
    return GuardContext(primary_root=primary, branch=branch, worktrees=tuple(worktrees))


def _within(path: str, root: str) -> bool:
    path = os.path.normpath(path)
    root = os.path.normpath(root)
    return path == root or path.startswith(root + os.sep)


def _git_ignores(path: str, ctx: GuardContext) -> bool:
    """Does git itself say this path is NOT part of the repository?

    🔴 WHY AN IGNORED PATH IS NOT A GUARDED PATH (added 2026-08-30)
    ---------------------------------------------------------------
    This guard exists to stop WORK landing in the primary checkout, and its own
    refusal message states the harm exactly: "committing here diverges local
    'dev' from origin". A gitignored path cannot be committed — `git add`
    refuses it without `-f` — so it can never diverge anything. Refusing it
    protects nothing and blocks a large class of ordinary, necessary work:

        npm install            → node_modules/         (ignored)
        pytest / any import    → __pycache__/, *.pyc   (ignored)
        vite build             → dist/                 (ignored)
        rm -rf a scratch dir   → whatever .gitignore says is scratch

    Every one of those was refused, and the only documented way out —
    `NOCTUS_ALLOW_PRIMARY_WRITE=1` — is unreachable from inside a command (see
    the ESCAPE HATCH note in the module docstring). So the gate had no correct
    path for work it should never have been stopping, which is precisely how a
    gate teaches people to route around it.

    This is the SAME reasoning that already exempts `LEDGER_PREFIXES`: content
    that cannot become a divergent commit is not what this gate is about. The
    difference is that git — not a hardcoded prefix list — decides, so the
    exemption tracks the repo's own declaration and cannot drift from it.

    🔴 STILL GUARDED, and this is the whole point: every TRACKED path, and every
    untracked-but-not-ignored path (a NEW source file an agent is about to
    create in the wrong tree — the original 2026-08-18 incident) stays refused.
    `tmp/` was in that second category, which is why the session that found this
    was right to be blocked until `.gitignore` said otherwise.

    COST. `git check-ignore` is a subprocess, and this hook runs on EVERY tool
    call — but this is only reached for a path that is already inside the
    primary, outside every worktree, outside `.git/`, and outside the ledgers.
    That is the about-to-refuse set, which is rare; the common allow-path
    (a worktree write) returns before ever getting here.

    FAILS CLOSED. `check-ignore` exits 0 = ignored, 1 = not ignored, 128 = it
    could not answer. Only a clean 0 exempts; an unanswerable probe keeps the
    refusal, same posture as everywhere else in this module.
    """
    rc = _run_git_rc(["-C", ctx.primary_root, "check-ignore", "-q", "--", path])
    return rc == 0


def is_guarded_path(path: str, ctx: GuardContext) -> bool:
    """True when writing `path` means writing the primary checkout's own tree.

    Excluded: anything inside a LINKED worktree (they physically live under the
    primary root — see the module docstring), git's own metadata, the ledger
    prefixes the commit keeper already exempts, and anything `.gitignore`
    declares out-of-repo (see `_git_ignores`).
    """
    if not path:
        return False
    if not _within(path, ctx.primary_root):
        return False
    if any(_within(path, wt) for wt in ctx.worktrees):
        return False
    rel = os.path.relpath(os.path.normpath(path), ctx.primary_root)
    if rel == ".git" or rel.startswith(".git" + os.sep):
        return False
    if any(rel.startswith(prefix) for prefix in LEDGER_PREFIXES):
        return False
    return not _git_ignores(path, ctx)


def _is_unresolvable(token: str) -> bool:
    """A token whose real value only exists at shell-expansion time.

    `cd "$W" && …` must NOT be read as a relative path called `$W` under the
    primary root: the variable could point anywhere, and guessing "inside"
    refuses correct work (it did, on 2026-08-19). Unresolvable tokens make the
    parse UNCERTAIN instead, which falls back to judging the effective cwd —
    conservative where it matters, silent where it does not.
    """
    return any(ch in token for ch in ("$", "`", "*", "?"))


def _resolve(token: str, cwd: str) -> str:
    token = token.strip().strip("'\"")
    if not token or _is_unresolvable(token):
        return ""
    token = os.path.expanduser(token)
    return os.path.normpath(token if os.path.isabs(token) else os.path.join(cwd, token))


def _effective_cwd(command: str, cwd: str) -> str:
    """The directory a relative path in `command` actually resolves against.

    `cd <primary> && <write>` in a single Bash call is exactly how both 2026-08-18
    slips happened: the harness reports the SESSION cwd, and the `cd` that
    re-points the write is invisible to anything that only reads that field.
    """
    current = cwd
    for match in _CD_RE.finditer(_normalize(command)):
        target = match.group("path").strip().strip("'\"")
        if not target or target.startswith("-"):
            continue
        if _is_unresolvable(target):
            # `cd "$W"` — we cannot know where it lands. Keep the last cwd we
            # DO know rather than inventing one under the primary root.
            continue
        current = _resolve(target, current)
    return current


def _segments(command: str) -> list[str]:
    return [seg for seg in re.split(r"&&|\|\||[;|\n]", command) if seg.strip()]


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return segment.split()


def _looks_like_path(token: str) -> bool:
    return bool(token) and not token.startswith("-") and "=" not in token.split("/")[0]


# `>`, `>>`, `<`, `2>`, `&>`, `2>&1` — with or without the filename fused on.
_REDIRECT_TOKEN_RE = re.compile(r"^(?:[0-9]*|&)(?:>>?|<)")


def _strip_redirections(tokens: Sequence[str]) -> list[str]:
    """Drop redirection operators + their operands from a tokenized segment.

    🔴 WHY. `_tokens` is `shlex.split`, which knows nothing about redirection:
    `git reset --hard origin/dev 2>&1` tokenizes to
    `[…, 'origin/dev', '2>&1']`, and `>/dev/null` arrives fused as one token.
    Both call sites below then read POSITIONAL arguments — the refs of a reset,
    the pathspecs of an add — so a redirect landed in the list as if it were an
    argument. `_is_sync_to_remote_git` saw two refs where the user wrote one and
    refused; `_is_ledger_only_git` saw a pathspec that resolves nowhere and
    refused. Both exemptions therefore evaporated the moment anyone appended
    `2>&1 | tail`, which is exactly how an agent habitually writes a command.
    Measured 2026-08-27: the bare form passed, the piped form did not.

    WHY IT DOES NOT WEAKEN THE GUARD. A redirect that writes into the primary is
    caught by a DIFFERENT leg — `bash_write_targets` scans `_redirect_targets`
    over the whole command and appends every one of them to `targets`. Removing
    them here removes them only from the ARGUMENT reading, never from the write
    accounting: `git reset --hard origin/dev > <primary>/f` is still refused,
    for the file write, which is the accurate reason.

    A bare operator (`… > out.txt`) also consumes the token after it; a fused
    one (`>out.txt`, `2>&1`) carries its own operand and consumes nothing.

    🔴 EXTENDED TO EVERY COMMAND-READING BRANCH (2026-08-31). The three call
    sites below were the git-specific instance; the identical defect lived,
    unfixed, in every OTHER branch of `bash_write_targets` that reads
    positional args (`sed -i`'s file list, `_ALWAYS_WRITE`'s candidates) — all
    of them also just `shlex.split` a segment and then filter by
    `_looks_like_path`, which does not know `2>&1` is not a path either. Fixed
    once, at the single `args = tokens[1:]` assignment `bash_write_targets`
    shares across every branch, rather than per-branch: confirmed on
    `rm -rf .claude/worktrees/<slug> 2>&1`, refused because the guard read
    `2>&1` itself as the rm target — the SAME command without the trailing
    redirect passed immediately, and the path being removed was gitignored
    scratch the whole time.
    """
    out: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        match = _REDIRECT_TOKEN_RE.match(tok)
        if match:
            # Bare operator ⇒ the filename is the next token.
            skip_next = match.group(0) == tok
            continue
        out.append(tok)
    return out


def _is_autostaging_commit(rest: Sequence[str]) -> bool:
    """Does this `git commit` stage content BY ITSELF?

    `-a` bundles every modified tracked file at commit time and `-p` stages
    interactively, so for either of them an empty index proves nothing about
    what the commit will contain. Short flags cluster (`-am`), which is why the
    letters of a single-dash token are inspected rather than whole tokens
    compared.
    """
    for tok in rest:
        if tok in {"--all", "--patch"}:
            return True
        if tok.startswith("-") and not tok.startswith("--") and len(tok) > 1:
            if "a" in tok[1:] or "p" in tok[1:]:
                return True
    return False


def _ledger_pathspecs(tail: Sequence[str], cwd: str) -> bool:
    """True when `tail` names at least one path and every one is a ledger."""
    paths = [a for a in tail if not a.startswith("-")]
    if not paths:
        return False
    return all(_under_ledger(p, cwd) for p in paths)


def _primary_diverged(ctx: GuardContext) -> bool:
    """Has the primary checkout diverged from its own upstream?

    Only used to DECIDE WHETHER TO MENTION the sync remedy in a refusal, never
    to allow anything — so an unanswerable probe simply means "no hint", which
    leaves the refusal exactly as it was before.

    WHY THE HINT EXISTS (2026-09-17). `_is_sync_to_remote_git` below already
    permits `git reset --hard <remote-tracking-ref>` precisely for a diverged
    primary, but the refusal text only ever named `task_branch`. An agent that
    hit the wall on `git reset`, `git stash` and `rm` in turn was never told
    the one command that works: this session concluded the state was an
    unbreakable deadlock and had begun escalating to the user before reading
    this module and finding the exemption. A gate whose escape hatch is real
    but undiscoverable from its own refusal is, in practice, a gate without one.
    """
    answered, out = _run_git_checked(
        ["-C", ctx.primary_root, "rev-list", "--count", "--left-right",
         f"{ctx.branch}...origin/{ctx.branch}"],
        None,
    )
    if not answered or not out:
        return False
    parts = out.split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return False
    ahead, behind = int(parts[0]), int(parts[1])
    # Diverged = local has commits the remote does not AND vice versa. A tree
    # that is merely behind fast-forwards, and `pull` is already exempt.
    return ahead > 0 and behind > 0


def _dest_only_candidates(args: Sequence[str]) -> list[str] | None:
    """The DESTINATION operand of a `SOURCE… DEST` command, or None.

    None means "could not be identified unambiguously", and the caller then
    keeps judging every argument — narrowing on a guess would fail OPEN, which
    is the one direction this module never errs in.

    Two shapes, both off the commands' own `-h`:
      · `-t DIR` / `--target-directory[=]DIR` — the destination is that
        operand, because the flag inverts the usual argument order.
      · otherwise the LAST path-looking positional, with at least two present:
        one positional cannot be split into a source and a destination, and
        `cp x` on its own is a usage error rather than a write we should guess at.
    """
    tokens = list(args)
    for i, tok in enumerate(tokens):
        if tok in _TARGET_DIR_FLAGS:
            return [tokens[i + 1]] if i + 1 < len(tokens) else None
        if tok.startswith("--target-directory="):
            value = tok.split("=", 1)[1]
            return [value] if value else None
    positional = [a for a in tokens if _looks_like_path(a)]
    return [positional[-1]] if len(positional) >= 2 else None


def _is_ledger_only_git(sub: str, args: Sequence[str], cwd: str) -> bool:
    """Is this `git add`/`commit`/`restore` confined to the append-only ledgers?

    Mirrors `check_primary_checkout_commit`'s one sanctioned exception: a change
    whose ENTIRE content lives under `LEDGER_PREFIXES` is bookkeeping, not work,
    and parallel agents publish their branch pointers that way.

    - `git add <paths>` — judged on the pathspecs.
    - `git restore <paths>` / `git checkout -- <paths>` — judged on the
      pathspecs, same as `add`.
    - `git commit` — judged on the real STAGED SET, read the same way the commit
      keeper reads it. Guessing from the command line would be wrong: `git
      commit -am …` names no paths at all.

    Anything unreadable returns False — an unanswerable probe must fall through
    to the refusal, never past it.

    🔴 WHY `restore` BELONGS HERE (added 2026-08-27)
    ------------------------------------------------
    The guard let a ledger be DIRTIED and refused to let it be CLEANED. Writing
    `project-history/x.ndjson` is exempt via `is_guarded_path`; `git add` of it
    is exempt here; `git commit` of it is exempt here — but `git checkout --`
    and `git restore` of that same file were refused, because a git write is
    otherwise scoped to its whole CHECKOUT rather than to its pathspecs.

    That asymmetry is not theoretical. `noctus.dev.auto_improvement_log` and its
    siblings write their ledger into the PRIMARY checkout by design. When the
    orchestrator decides those lines belong elsewhere, the only remedies left
    were `reset --hard origin/dev` — which also discards unrelated pointer
    commits sitting in the same tree — or `NOCTUS_ALLOW_PRIMARY_WRITE`, i.e.
    switching the gate off to undo something the gate itself had permitted. A
    gate escapable only by disabling it is the shape
    `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` warns about,
    and it cost a real session on 2026-08-27.

    It widens nothing: `restore`/`checkout` with an explicit ledger pathspec can
    only touch files the guard already treats as bookkeeping. The PATHLESS forms
    stay refused, and those are the destructive ones — `git checkout .`,
    `git restore :/`, and above all `git checkout <branch>`, which switches the
    shared HEAD out from under a peer worktree. A bare `checkout` therefore
    qualifies ONLY via an explicit `--` separator, because before that separator
    a lone token is ambiguous between a path and a branch name.

    🔴 WHY AN EMPTY STAGED SET IS ALLOWED FOR `commit`
    --------------------------------------------------
    `git add <ledger> && git commit -m …` in ONE call could never pass. The hook
    runs BEFORE the command, so the `add` has not executed yet and
    `diff --cached` is empty — the probe read "nothing staged", returned False,
    and refused. Splitting it across two tool calls worked, which makes it a
    trap rather than a rule: the compound form is how the command is habitually
    written, and a gate that fights the orchestrator's normal spelling is one
    that gets switched off.

    Allowing it is safe because of how the CALLER composes: a command is refused
    if ANY of its segments is a guarded write. A preceding `git add` of
    non-ledger paths therefore refuses the whole command on its own leg, so any
    `commit` reaching an empty index inside a compound was necessarily preceded
    by a ledger-only `add` that already passed.

    Two forms stay refused, because for them an empty index proves nothing: a
    commit that stages by itself (`-a`/`-p`), and a commit naming pathspecs,
    which bypass the index entirely.
    """
    if sub == "add":
        return _ledger_pathspecs(_strip_redirections(args[args.index(sub) + 1:]), cwd)

    if sub in {"restore", "checkout"}:
        tail = _strip_redirections(args[args.index(sub) + 1:])
        if "--" in tail:
            return _ledger_pathspecs(tail[tail.index("--") + 1:], cwd)
        # No separator: only `restore` is unambiguous, since it never takes a
        # branch to switch to. `checkout dev` must stay refused.
        return _ledger_pathspecs(tail, cwd) if sub == "restore" else False

    if sub == "reset":
        # 🔴 THE INDEX-SIDE TWIN of `restore`, overlooked by the 2026-08-27 fix
        # above (added 2026-09-17). That fix cured "a ledger may be DIRTIED but
        # not CLEANED" for the WORKING TREE and left the INDEX behind: a stale
        # staged entry on `project-history/vector-costs.ndjson` — put there by
        # the very ledger writers this module exempts — could not be unstaged,
        # and an un-unstageable index blocks the `rebase` that re-syncs the
        # primary. Same asymmetry, same argument, one subcommand.
        #
        # ONLY the pathspec form qualifies. After `--` git parses every token as
        # a path, so this shape provably cannot move HEAD; the ref forms
        # (`reset --hard origin/dev`, `reset HEAD~3`) are decided by
        # `_is_sync_to_remote_git` or stay refused. The worktree-touching modes
        # are excluded outright rather than assumed harmless.
        tail = _strip_redirections(args[args.index(sub) + 1:])
        if "--" not in tail or _RESET_WORKTREE_FLAGS & set(tail):
            return False
        return _ledger_pathspecs(tail[tail.index("--") + 1:], cwd)

    if sub == "commit":
        rest = list(args[args.index(sub) + 1:])
        if _is_autostaging_commit(rest):
            return False
        answered, staged = _run_git_checked(["-C", cwd, "diff", "--cached", "--name-only"], None)
        if not answered:
            # The probe could not be run at all. No answer is not a permissive
            # answer — fall through to the refusal, same posture as everywhere
            # else in this module.
            return False
        names = [n for n in staged.splitlines() if n.strip()]
        if names:
            return all(any(n.startswith(prefix) for prefix in LEDGER_PREFIXES) for n in names)
        # Genuinely nothing staged: a no-op, or a compound whose ledger-only
        # `add` has not run yet. Pathspecs still have to be ledger-confined,
        # because they commit their paths regardless of the index.
        tail = _strip_redirections(rest)
        if "--" in tail:
            return _ledger_pathspecs(tail[tail.index("--") + 1:], cwd)
        return True

    return False


#: `restore` flags that keep the operation scoped to HEAD/the index. Anything
#: else before the `--` (above all `--source=<ref>` / `-s <ref>`) names a
#: DIFFERENT source to restore from — not "back to HEAD" — and must stay
#: outside this exemption.
_RESTORE_TO_HEAD_FLAGS = {"--staged", "--worktree"}


def _is_restore_to_head_git(sub: str, args: Sequence[str]) -> bool:
    """Is this `git checkout -- <paths>` / `git restore -- <paths>` an
    unambiguous PATH restore back to HEAD (or the index, which on a guarded
    primary can only ever equal HEAD — see below) — never a branch switch,
    never a restore from an arbitrary ref?

    🔴 THE CONTRADICTION THIS CLOSES (2026-09-23). `measure_posttool_dirt`'s
    own refusal text (`format_primary_dirt_warning`, this module) hands the
    agent an exact remedy for stray primary dirt: "`git -C <primary>
    checkout -- <file>` for a tracked change". Before this function existed,
    running exactly that command was refused by `decide()` — the ledger
    exemption above (`_is_ledger_only_git`) only covers `project-history/`
    paths, and every OTHER tracked file fell through to the generic
    "git write is scoped to its whole checkout" refusal. The guard handed out
    a remedy it then blocked, so the agent was stuck and a human had to fix
    the primary by hand — the precise "safety net becomes a wall" failure
    `KB § PATTERNS/common/gate-methodology-sync.md` names.

    WHY THIS IS SAFE TO WIDEN PAST THE LEDGER PREFIX. This module's whole
    premise (`_is_sync_to_remote_git`'s docstring says it outright) is that a
    guarded primary is a READ-ONLY tree BY CONSTRUCTION: every genuine WRITE
    into it is refused, so the only things that can ever be sitting there
    dirty are (a) regenerated artifacts a hook wrote without asking, and
    (b) the ledger appends `LEDGER_PREFIXES` already exempts. Restoring EITHER
    kind to HEAD can only ever DISCARD dirt the guard never should have let
    land, or no-op on a path that was never dirty. There is no path through
    this exemption that can make the primary diverge from origin further than
    it already has — which is exactly why the docstring on `decide()`'s
    refusal text says "Restoring to HEAD cannot diverge dev".

    NARROWED, DELIBERATELY, to the two forms the brief actually asks for —
    anything else stays refused rather than guessed at:

    * An explicit `--` separator is MANDATORY, same reasoning as
      `_is_ledger_only_git`'s restore/checkout leg: before it, a lone token is
      ambiguous between a path and a branch/ref name, and `git checkout dev`
      is the one shape (§9a) that must never pass as "just a path".
    * `checkout`: NOTHING may precede `--`. `git checkout <tree-ish> --
      <path>` restores from an arbitrary commit/branch, not HEAD — a
      different, wider operation this function does not cover.
    * `restore`: only `--staged` and/or `--worktree` may precede `--`. Those
      pick WHICH half of the restore-to-HEAD-or-index runs; anything else —
      above all `--source=<ref>` — names a different source and is refused.

    Deliberately does NOT check whether the named paths are actually tracked:
    a `checkout --`/`restore --` naming an untracked path is a harmless git
    error ("did not match any file(s) known to git"), never a write, so the
    trackedness question changes nothing about whether this is safe to allow
    — and checking it would cost a subprocess this module otherwise avoids on
    every string-parseable branch (see the module docstring's design
    constraints).
    """
    if sub not in {"restore", "checkout"}:
        return False
    tail = _strip_redirections(args[args.index(sub) + 1:])
    if "--" not in tail:
        return False
    sep = tail.index("--")
    before, paths = tail[:sep], tail[sep + 1:]
    if not paths:
        return False  # `git checkout --` / `git restore --` name nothing.
    if sub == "checkout":
        return not before
    return all(tok in _RESTORE_TO_HEAD_FLAGS for tok in before)


def _is_sync_to_remote_git(sub: str, args: Sequence[str], cwd: str) -> bool:
    """Is this `git reset --hard <remote-tracking-ref>` — i.e. RE-SYNCING the
    primary checkout to its remote, rather than writing work into it?

    🔴 WHY THIS EXEMPTION EXISTS. This module's own `_GIT_WRITE_SUBCOMMANDS`
    note says `pull`/`fetch`/`merge`/`push`/`worktree`/`tag`/`branch` are
    deliberately absent because "syncing and integrating the primary checkout
    on `dev` is the orchestrator's actual job, and a guard that fought it would
    be switched off." `reset` was on the list anyway — and the moment the
    primary DIVERGES (which `task_branch action=cleanup` causes by design: it
    writes a recovery pointer into the primary and cannot commit it), a
    fast-forward can no longer re-sync it. `reset --hard origin/<branch>` is
    then the ONLY repair, and the guard refused precisely the operation that
    fixes the state it exists to prevent. It fought the sync, exactly as the
    note predicted, and cost several sessions real time.

    WHY IT IS SAFE, and not merely convenient: this guard makes the primary a
    read-only tree BY CONSTRUCTION. Every write into it is refused, so the only
    things that can accumulate there are (a) regenerated artifacts and (b)
    ledger appends under `LEDGER_PREFIXES` — the one exemption above. Neither
    is work anybody can lose. A reset to the tree's own remote therefore
    discards nothing the guard ever let land.

    DELIBERATELY NARROW. The ref must resolve to a REMOTE-TRACKING ref
    (`refs/remotes/…`). Still refused, unchanged:
      · `git reset --hard HEAD~3` / `<sha>` / `<local-branch>` — a rewind, not
        a sync, and the one shape that CAN destroy unpushed history.
      · `git reset` (mixed/soft), which unstages rather than re-syncing.
      · every other verb in `_GIT_WRITE_SUBCOMMANDS`.

    Anything unreadable returns False — an unanswerable probe falls through to
    the refusal, never past it (same posture as `_is_ledger_only_git`).
    """
    if sub != "reset":
        return False

    rest = list(args[args.index(sub) + 1:])
    if "--hard" not in rest:
        # A soft/mixed reset moves the index, not the tree, and is not how a
        # checkout is re-synced. Out of scope rather than quietly allowed.
        return False

    refs = [a for a in _strip_redirections(rest) if not a.startswith("-")]
    if len(refs) != 1:
        # Zero refs (`git reset --hard`, implicit HEAD) discards the working
        # tree without syncing anything; more than one is a pathspec reset.
        return False

    # Ask git what the ref actually IS. A name that merely LOOKS remote
    # (`origin/dev` as a local branch someone created) must not pass on
    # spelling alone.
    full = _run_git(["-C", cwd, "rev-parse", "--symbolic-full-name", refs[0]], None).strip()
    return full.startswith("refs/remotes/")


def _under_ledger(path: str, cwd: str) -> bool:
    if _is_unresolvable(path):
        return False
    resolved = _resolve(path, cwd)
    if not resolved:
        return False
    try:
        rel = os.path.relpath(resolved, cwd)
    except ValueError:
        return False
    return any(rel.startswith(prefix.rstrip("/")) for prefix in LEDGER_PREFIXES)


def bash_write_targets(command: str, cwd: str) -> tuple[list[str], bool]:
    """Paths `command` would write, plus whether the parse is UNCERTAIN.

    Uncertain means "write intent detected, target not resolvable" — an
    interpreted one-liner, an unparseable quoting soup. The caller treats that
    as a write against the effective cwd, because guessing wrong in the
    permissive direction is what this module exists to stop.
    """
    cwd = _effective_cwd(command, cwd)
    command = _normalize(command)
    targets: list[str] = []
    uncertain = False

    # Redirects are scanned over the WHOLE command, not per segment: `_segments`
    # splits on `|` and `;` without regard for quotes, which would cut a quoted
    # span in half and leave the scanner reading an unbalanced quote.
    for raw in _redirect_targets(command):
        if raw in _SINKS:
            continue
        resolved = _resolve(raw, cwd)
        if resolved:
            targets.append(resolved)
        else:
            # `> $TARGET` — a write is happening somewhere we cannot name. That
            # is the same condition the `_ALWAYS_WRITE` branch below already
            # marks uncertain; a redirect staying silent about it was an
            # inconsistency, not a decision.
            uncertain = True

    for segment in _segments(command):
        tokens = _tokens(segment)
        while tokens and "=" in tokens[0] and "/" not in tokens[0].split("=")[0]:
            tokens = tokens[1:]  # leading VAR=value assignments
        if not tokens:
            continue
        name = os.path.basename(tokens[0])
        # `_tokens` is `shlex.split`, which knows nothing about redirection:
        # `rm -rf x/ 2>&1` tokenizes `2>&1` as an ordinary trailing argument,
        # and every branch below that reads POSITIONAL args (`sed`'s files,
        # `_ALWAYS_WRITE`'s candidates) then saw it and read it as a PATH —
        # `_looks_like_path('2>&1')` is True, so the guard resolved a file
        # named `2>&1` under the cwd and refused on it. `bash_write_targets`
        # already strips redirections before reading `git`'s positional refs
        # (see `_strip_redirections`'s own docstring for the git-side version
        # of this bug, fixed 2026-08-27); every other command-reading branch
        # had the identical defect, unfixed, until 2026-08-31 — confirmed on
        # `rm -rf .claude/worktrees/<slug> 2>&1`, which the SAME command
        # without the redirect passed immediately. The actual file write is
        # still caught: `_redirect_targets` above scans the WHOLE command for
        # every real redirect independent of this per-command arg reading.
        args = _strip_redirections(tokens[1:])

        if name == "sed":
            if any(a == "-i" or a.startswith("-i") for a in args):
                positional = [a for a in args if _looks_like_path(a)]
                targets += [_resolve(a, cwd) for a in positional[1:]]
                if len(positional) <= 1:
                    uncertain = True
            continue

        if name in {"python", "python3"}:
            if _PY_WRITE_RE.search(segment):
                uncertain = True
            continue

        if name == "git":
            sub_cwd = cwd
            rest = list(args)
            if "-C" in rest:
                idx = rest.index("-C")
                if idx + 1 < len(rest):
                    sub_cwd = _resolve(rest[idx + 1], cwd)
                    rest = rest[:idx] + rest[idx + 2:]
            sub = next((a for a in rest if not a.startswith("-")), "")
            if sub in _GIT_WRITE_SUBCOMMANDS:
                if _is_read_only_git(sub, rest):
                    # `git stash list`, `git clean -n`, `git apply --check`,
                    # `git <anything> -h` — the sub-verb/flag makes this
                    # invocation a READ despite `sub` itself being
                    # write-capable in general. See `_is_read_only_git`.
                    continue
                if _is_sync_to_remote_git(sub, rest, sub_cwd):
                    # Re-syncing the primary to its remote is the orchestrator's
                    # job, not a write of work — see the function's docstring for
                    # why refusing it was the guard fighting its own purpose.
                    continue
                if _is_ledger_only_git(sub, rest, sub_cwd):
                    # The ledger exemption, honoured identically to
                    # `check_primary_checkout_commit`. Without this the two
                    # gates DISAGREE: the commit keeper lets a
                    # `project-history/`-only commit through by design (that is
                    # how parallel agents publish branch pointers), and this one
                    # refused it — which happened for real on 2026-08-19, one
                    # commit after the docstring claiming they could not drift.
                    continue
                if _is_restore_to_head_git(sub, rest):
                    # `git checkout -- <path>` / `git restore -- <path>` — a
                    # path-scoped restore back to HEAD, not a branch switch
                    # and not a restore from an arbitrary ref. See the
                    # function's own docstring for the contradiction this
                    # closes: the PostToolUse leg's own remedy text names
                    # exactly this command, and refusing it left the guard
                    # handing out a fix it then blocked.
                    continue
                # Otherwise a git write is scoped to its CHECKOUT, not to the
                # pathspecs: `git checkout .` and `git reset --hard` name no
                # path at all.
                targets.append(sub_cwd)
            continue

        if name in _ALWAYS_WRITE:
            args = _drop_non_path_operands(name, args)
            candidates = [a for a in args if _looks_like_path(a)]
            if name in _DEST_ONLY_WRITE:
                dest = _dest_only_candidates(args)
                if dest is not None:
                    # Sources are reads; only the destination is written. When
                    # the destination cannot be named unambiguously
                    # `_dest_only_candidates` returns None and we stay on the
                    # conservative all-arguments path below.
                    candidates = dest
            positional = [t for t in (_resolve(a, cwd) for a in candidates) if t]
            targets += positional
            if len(positional) < len(candidates) or not candidates:
                # Either no target at all, or one we could not expand (`$VAR`,
                # a glob). Both mean "a write is happening somewhere we cannot
                # name" — decided against the effective cwd, and said so.
                uncertain = True
            continue

    return [t for t in targets if t], uncertain


def decide(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = None,
    ctx: GuardContext | None = None,
    allow_override: bool | None = None,
) -> dict[str, Any] | None:
    """None to allow; a dict describing the refusal otherwise.

    The dict carries `reason` (shown verbatim to the agent, and it names the
    remedy — a refusal that does not say what to do instead just gets retried
    a different way).
    """
    if allow_override is None:
        allow_override = os.environ.get(ALLOW_ENV, "") == "1"
    if allow_override:
        return None

    cwd = cwd or os.getcwd()
    if ctx is None:
        ctx = discover_context(cwd)
    if ctx is None or not ctx.guarded:
        return None

    uncertain = False
    if tool_name in _FILE_PATH_TOOLS:
        raw = (tool_input or {}).get(_FILE_PATH_TOOLS[tool_name]) or ""
        targets = [_resolve(raw, cwd)] if raw else []
    elif tool_name == "Bash":
        command = (tool_input or {}).get("command") or ""
        targets, uncertain = bash_write_targets(command, cwd)
        # 🔴 MEASURE, DON'T PREDICT (2026-09-23). This used to fall back to
        # `targets = [_effective_cwd(command, cwd)]` whenever the parse was
        # uncertain and nothing concrete resolved — refusing the WHOLE
        # command against its cwd on the strength of a guess. That guess is
        # what turned this leg into a wall: 13 `fix(guard)` commits since
        # 2026-08 chasing one more shell quoting shape, and it still refused
        # `cd <scratchpad-abs-path> && curl … -o <scratchpad-abs-path>/x.js`
        # on 2026-09-23 — an absolute target OUTSIDE the repo, unparsed only
        # because `curl -o` is not (and can never exhaustively be) a shape
        # this parser recognizes. A PreToolUse hook can only ever be a good
        # PARSER of an arbitrary shell command, never a proof of what it will
        # do; guessing in the refusing direction is not more careful, it is
        # wrong in the direction that gets the gate switched off
        # (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`).
        #
        # An EXPLICITLY resolved target is still judged exactly below (`hits`)
        # — that part of the parser is a real proof, not a guess, and stays a
        # refusal. An unresolvable one is now ALLOWED here; if it actually
        # lands in the primary, `measure_posttool_dirt` (this module, paired
        # PostToolUse hook `claude-guard-primary-write-post.py`) reports it
        # AFTER the fact by diffing real `git status --porcelain` output —
        # measuring what happened instead of predicting what might.
    else:
        return None

    hits = sorted({t for t in targets if is_guarded_path(t, ctx)})
    if not hits:
        return None

    shown = ", ".join(os.path.relpath(h, ctx.primary_root) or "." for h in hits[:4])
    if len(hits) > 4:
        shown += f", +{len(hits) - 4} more"
    return {
        "tool": tool_name,
        "branch": ctx.branch,
        "primary_root": ctx.primary_root,
        "targets": hits,
        "uncertain": uncertain,
        "reason": (
            f"REFUSED — this would write the PRIMARY checkout while it is on the "
            f"shared branch '{ctx.branch}' ({shown}).\n"
            f"Self-branching mode is absolute (CLAUDE.md §1, skill noc-self-branch): "
            f"every writing task isolates in its own worktree off origin/dev.\n"
            f"Do this instead:\n"
            f"  1. noctus.dev.task_branch action='start' slug='<kebab-slug>' confirm=True\n"
            f"  2. make the edit under {os.path.join(ctx.primary_root, '.claude/worktrees/<slug>')}/ "
            f"(absolute paths — a bare `cd` does not survive to the next tool call)\n"
            f"  3. noctus.dev.task_branch action='integrate' slug='<kebab-slug>' confirm=True\n"
            f"Committing here diverges local '{ctx.branch}' from origin, and the failure "
            f"surfaces much later as a non-fast-forward at integrate or deploy time."
            + ("\nThis command also names at least one OTHER target this guard "
               "could not resolve exactly (an interpreted string, a shell "
               "variable, a glob) — it is not part of this refusal, but check "
               "`git -C <primary> status --porcelain` after running it."
               if uncertain else "")
            + (f"\nNOTE: this primary has DIVERGED from origin/{ctx.branch}, so it can "
               f"no longer fast-forward. Re-syncing it is sanctioned and allowed: "
               f"`git reset --hard origin/{ctx.branch}`. Nothing you can lose lives "
               f"here — every write is refused except regenerated artifacts and "
               f"append-only ledgers. Preserve any ledger rows first "
               f"(`git diff origin/{ctx.branch}...HEAD > <path outside the repo>`)."
               if _primary_diverged(ctx) else "")
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# The measurement net — PostToolUse leg for Bash, paired with the now-
# permissive uncertain-target path in `decide()` above (see the
# "MEASURE, DON'T PREDICT" note there for why this exists as a SEPARATE pass
# rather than a stricter parse).
# ═══════════════════════════════════════════════════════════════════════════

#: Where the PreToolUse leg stashes its pre-Bash snapshot for the PostToolUse
#: leg to diff against. ONE file, not one per invocation: tool calls run
#: sequentially far more often than not, and no per-call id is available to a
#: stdlib-only hook to pair them precisely anyway. A concurrent sibling call
#: only widens or narrows the reported window by one call's worth of dirt —
#: acceptable because this net is advisory ONLY (it never refuses anything;
#: see `measure_posttool_dirt`'s docstring), so the imprecise-attribution cost
#: of a shared baseline is strictly cheaper than the correctness cost of
#: guessing a target beforehand ever was.
_BASELINE_CACHE_REL = os.path.join(".claude", "cache", "primary-write-guard-baseline.txt")


def _baseline_cache_path(ctx: GuardContext) -> str:
    return os.path.join(ctx.primary_root, _BASELINE_CACHE_REL)


def primary_status_snapshot(ctx: GuardContext) -> str | None:
    """`git status --porcelain` of the primary checkout, or None if unanswerable.

    The measurement net's one subprocess call. Only ever reached when
    `ctx.guarded` — a feature-branch primary (the overwhelmingly common case)
    never pays this cost at all, on either the Pre or the Post leg.
    """
    answered, out = _run_git_checked(["-C", ctx.primary_root, "status", "--porcelain"], None)
    return out if answered else None


def capture_pretool_baseline(ctx: GuardContext) -> None:
    """Write the current primary status as the baseline the NEXT PostToolUse
    measurement diffs against.

    Best-effort BY DESIGN: an unwritable cache dir, or an unanswerable probe,
    silently skips rather than raising. This net is advisory — see
    `measure_posttool_dirt` — so "no report this time" is the correct failure
    direction, not an exception the PreToolUse hook now has to handle on a
    path that must never block the write it already decided to allow.
    """
    snapshot = primary_status_snapshot(ctx)
    if snapshot is None:
        return
    path = _baseline_cache_path(ctx)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(snapshot)
    except OSError:
        pass


def _read_baseline(ctx: GuardContext) -> str | None:
    try:
        with open(_baseline_cache_path(ctx), "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _porcelain_path(line: str) -> str:
    """The PATH half of one `git status --porcelain` line.

    Format is two status chars + a space + the path (`XY PATH`), or for a
    rename `XY ORIG -> PATH`. The rename's NEW path is what matters here —
    that is where dirt actually landed, not where it came from.
    """
    body = line[3:] if len(line) > 3 else ""
    if " -> " in body:
        body = body.split(" -> ", 1)[1]
    return body.strip().strip('"')


def _is_ledger_ndjson(path: str) -> bool:
    """The one sanctioned kind of "new dirt": an append-only ledger the MCP
    toolkit writes into the primary BY DESIGN (`LEDGER_PREFIXES`, same set
    `decide()`'s own git leg exempts). Narrowed to `.ndjson` specifically —
    unlike the pre-write exemption above, this is a POST-HOC report about
    what a tool actually did, and a ledger directory is not a blanket pass
    for an unrelated file that happens to share its prefix.
    """
    return path.endswith(".ndjson") and any(path.startswith(prefix) for prefix in LEDGER_PREFIXES)


def diff_new_primary_dirt(before: str | None, after: str | None) -> list[str]:
    """Paths dirty in `after` but not in `before`, minus the ledger exemption.

    Line-set difference, not per-path status comparison: a path that changed
    STATUS between snapshots (e.g. `??` becomes `A `) is a different line and
    correctly still reads as "new", because a still-open question either way
    it changes shape.
    """
    if not after:
        return []
    before_lines = {ln for ln in (before or "").splitlines() if ln}
    after_lines = {ln for ln in after.splitlines() if ln}
    out: list[str] = []
    for line in sorted(after_lines - before_lines):
        path = _porcelain_path(line)
        if not path or _is_ledger_ndjson(path):
            continue
        out.append(path)
    return out


def format_primary_dirt_warning(paths: Sequence[str], ctx: GuardContext) -> str:
    shown = ", ".join(paths[:8])
    if len(paths) > 8:
        shown += f", +{len(paths) - 8} more"
    return (
        f"PRIMARY CHECKOUT GOT NEW DIRT on shared branch '{ctx.branch}' from this "
        f"Bash call: {shown}.\n"
        f"This guard allowed the write pre-emptively because its target could not "
        f"be predicted, and measured the actual result afterward instead — it "
        f"landed in the primary checkout ({ctx.primary_root}), which must stay "
        f"clean here (CLAUDE.md §1, skill noc-self-branch).\n"
        f"Fix it: move the intended output into your worktree, then clean the "
        f"primary — `git -C {ctx.primary_root} checkout -- <file>` for a tracked "
        f"change, `rm <file>` for a new untracked one."
    )


def measure_posttool_dirt(cwd: str | None = None, ctx: GuardContext | None = None) -> str | None:
    """The PostToolUse entry point: None to say nothing, else warning text.

    NEVER refuses anything — there is nothing left to refuse, the Bash call
    already ran. This only diffs the primary's real `git status --porcelain`
    against the baseline the paired PreToolUse leg captured and reports
    anything genuinely new, minus the ledger exemption. Silent whenever the
    context is unguarded, the probe cannot answer, or no baseline was ever
    captured (e.g. this hook's own install postdates the Bash call) — an
    advisory net that cannot see must not invent a finding, same posture as
    every refusal path in this module toward an unanswerable probe, applied
    in the opposite (never-block) direction.
    """
    cwd = cwd or os.getcwd()
    if ctx is None:
        ctx = discover_context(cwd)
    if ctx is None or not ctx.guarded:
        return None
    after = primary_status_snapshot(ctx)
    if after is None:
        return None
    new_dirt = diff_new_primary_dirt(_read_baseline(ctx), after)
    if not new_dirt:
        return None
    return format_primary_dirt_warning(new_dirt, ctx)


# ═══════════════════════════════════════════════════════════════════════════
# `decide_git_bypass` — refuse a git invocation that silently disables its
# own hooks (SEPARATE concern from `decide()` above; see rationale below).
# ═══════════════════════════════════════════════════════════════════════════
"""
**The incident.** `git -c core.hooksPath=.git/hooks commit -q -F - <<'MSG' …`
committed with no hooks at all, exit 0, no warning. This repo configures
`core.hooksPath` to an ABSOLUTE path (`<primary>/.git/hooks`, symlinked to
`scripts/hooks/`); the override above was RELATIVE, and git resolves a
relative `core.hooksPath` against the CWD. Run from a linked worktree — where
`.git` is a FILE (`gitdir: …`), not a directory — `.git/hooks` under that cwd
never existed, so every hook was skipped. `git commit --amend --no-edit` with
the override removed printed `[pre-commit] OK`, proving the gate had been live
all along and only THIS invocation skipped it.

**Why this is worse than `--no-verify`.** `--no-verify` is named in CLAUDE.md
§1, means "skip the gate" on its face, and the harness classifier catches it.
A `-c core.hooksPath=…` override reads as being MORE careful about hooks,
prints nothing, and nothing catches it. It is a bypass that looks like
diligence — the one SILENT rationalization shape in
`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`.

**Why this is a SEPARATE function, not a branch inside `decide()`.**
`decide()` answers "does this write land in the wrong TREE" (primary checkout
vs. worktree, on a shared branch). This answers "does this git invocation
skip its own SAFETY MECHANISM" — true or false independent of which tree the
write lands in, which branch is checked out, or whether the write is even
guarded by `decide()` at all: bypassing hooks on a feature-branch worktree
commit is just as bad as on the primary, because it is the commit ITSELF —
not the destination — that stops being verified. Merging the two into one
function would couple two independently-true-or-false questions behind one
early-return, which is exactly the shape that made the 2026-08-18 primary-
write slip invisible to the (unrelated) commit keeper: a gate answering two
questions answers neither reliably.

**Why this lives in THIS module rather than a new sibling file.** The
by-path loader in `scripts/hooks/claude-guard-primary-write.py` pays this
module's compile+exec cost on every Bash/Edit/Write call already (see the
module docstring's "Design constraints"). A second `git_bypass_guard.py`
loaded the same way would not meaningfully change that per-call cost (the
bytes compiled are the same either way — one bigger file or two smaller
ones) but WOULD force the wrapper into a second `importlib.util.
spec_from_file_location(...).exec_module(...)` round-trip and, worse, would
have to duplicate this file's shell-tokenizing primitives (`_normalize`,
`_segments`, `_tokens`, `_strip_redirections`) — a by-path-loaded module
cannot `import primary_write_guard` normally (it is registered in
`sys.modules` under the wrapper's own synthetic name, not a resolvable
package path), so the honest alternatives were "duplicate ~150 lines of
already-audited quoting/heredoc/redirection logic" or "live here." A
function, not a module: separate concern, same file, zero extra import.

**Escape hatch.** `NOCTUS_ALLOW_HOOK_BYPASS=1` — same shape as `ALLOW_ENV`
above (a PreToolUse hook reads its OWN process's `os.environ`, so this is
unreachable from inside the denied command itself; see the module docstring's
🔴 note, which applies here verbatim). There genuinely is no scripted
legitimate use of `-c core.hooksPath=`/`--no-verify` in THIS repo — there is
no agent-sanctioned shape at all since 2026-09-22 (the former `engineer-seed.md`
§2 carve-out, the architect's scoped commit in a dirty multi-agent tree, was
retired with stage-only: every engineer commits in its own worktree, and the
pre-commit hook no longer sweeps peer edits). What remains is a rare,
deliberate, human act, which is exactly what an env var — set once, by a
person, in their own shell — is for.
"""

#: The config KEY this gate exists to protect, lower-cased for comparison
#: (git itself lower-cases section/variable names when matching `-c`/
#: `--config`, so a caller spelling it `Core.HooksPath` is not a loophole).
_HOOKS_PATH_KEY = "core.hookspath"

#: `git <sub>` verbs whose hooks are the whole point of this gate — the exact
#: set named in the brief. `merge`/`rebase`/`am`/`cherry-pick` matter for the
#: `-c core.hooksPath=`/`--config`/`--config-env` leg (any subcommand really,
#: see below); `--no-verify`/`-n` only exists as a flag on `commit`/`push`.
_HOOK_TRIGGERING_SUBCOMMANDS = {"commit", "push", "merge", "rebase", "am", "cherry-pick"}

#: `-n`/`--no-verify` is `commit`'s alias for skipping hooks (`git commit -h`:
#: "-n, --no-verify  bypass pre-commit and commit-msg hooks"). It is NOT an
#: alias on `push` — `git push -h`: "-n, --[no-]dry-run  dry run" — a
#: harmless, unrelated flag. Scoping `-n` detection to `commit` only is
#: therefore load-bearing, not a simplification: treating `git push -n` as a
#: hooks bypass would refuse an ordinary dry run on every use.
_NO_VERIFY_SHORT_SUBCOMMANDS = {"commit"}
#: `--no-verify` (long form) has no such trap — both `commit` and `push`
#: accept only the one spelling, with the one meaning.
_NO_VERIFY_LONG_SUBCOMMANDS = {"commit", "push"}

#: Flags that consume the NEXT token as their operand, so the scanner does
#: not mis-read that operand as the subcommand or another flag.
_GIT_GLOBAL_FLAGS_WITH_OPERAND = {"-C", "--git-dir", "--work-tree", "--namespace"}

#: `GIT_CONFIG_KEY_<n>=core.hooksPath` (paired with `GIT_CONFIG_VALUE_<n>=…`)
#: is git's env-var config-injection mechanism — functionally identical to
#: `-c core.hooksPath=…` but spelled as shell environment rather than argv,
#: so a literal-string scan for `-c`/`--config` alone would miss it entirely.
_GIT_CONFIG_ENV_KEY_RE = re.compile(
    r"GIT_CONFIG_KEY_\d+\s*=\s*['\"]?core\.hookspath\b", re.IGNORECASE,
)


def _kv_key(value: str) -> str:
    """The KEY half of a `key=value` (or bare `key`) operand, lower-cased."""
    return value.split("=", 1)[0].strip().strip("'\"").lower()


#: `git config` flags that make ANY subsequent invocation a READ, regardless
#: of positional-argument count — `--get core.hooksPath` has two "args" the
#: same as a SET would, but is unambiguously a read.
_CONFIG_READ_ONLY_FLAGS = {
    "--get", "--get-all", "--get-regexp", "--get-urlmatch",
    "--list", "-l", "--show-origin", "--show-scope",
}
#: Flags that mutate even with only ONE positional (the key) — `--unset core.
#: hooksPath` removes the value rather than setting a new one, but a removal
#: is still "core.hooksPath [changed to] anything other than the repo's
#: configured absolute value" — the exact shape this leg exists to catch.
_CONFIG_MUTATING_FLAGS = {"--unset", "--unset-all", "--replace-all", "--add"}


def _git_config_hookspath_set_reason(config_args: Sequence[str]) -> str | None:
    """Is `git config <config_args>` a MUTATION (not a read) of core.hooksPath?

    `git config core.hooksPath` (one positional, no mutating flag) reads —
    the explicit ALLOW case this module's own refusal text below names
    ("a read, not an override"). `git config core.hooksPath <value>` (two
    positionals) or `git config --unset core.hooksPath` mutates the PERSISTENT
    config, which is a different, slower-acting version of the same harm an
    inline `-c core.hooksPath=…` override causes: every git command run in
    this checkout AFTER this one resolves hooks against the new value, not
    just the one invocation that set it.

    `--global`/`--system` scope makes this worse, not exempt: it affects
    every OTHER checkout on the machine too, so it is flagged unconditionally
    (never assumed correct-by-coincidence).
    """
    args = _strip_redirections(list(config_args))
    flags = {a for a in args if a.startswith("-")}
    if flags & _CONFIG_READ_ONLY_FLAGS:
        return None
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals or _kv_key(positionals[0]) != _HOOKS_PATH_KEY:
        return None
    is_mutation = len(positionals) >= 2 or bool(flags & _CONFIG_MUTATING_FLAGS)
    if not is_mutation:
        return None
    scope = (
        " with --global/--system scope (repo-INDEPENDENT — every checkout "
        "on this machine, not just this one)"
        if ({"--global", "--system"} & flags) else ""
    )
    change = f" to `{positionals[1]}`" if len(positionals) >= 2 else " (removed, via --unset)"
    return (
        f"`git config … core.hooksPath` is being SET{change}{scope} — this changes "
        f"which hooks fire on EVERY subsequent git command in this checkout, not "
        f"just this one invocation."
    )


def _find_git_start(tokens: Sequence[str]) -> int | None:
    """Index of the first `git` token, or None.

    Deliberately the FIRST occurrence only, and deliberately ANYWHERE in the
    segment rather than only at position 0: `env X=Y git …`, a leading
    `VAR=value` shell assignment, `xargs -I{} git …`, and a subshell's stray
    `(` (which `shlex.split` reads as its own token when space-separated)
    all put real argv before the real `git` token. Treating everything from
    there on as the invocation's argv is a superset of "position 0 only" and
    costs nothing extra to compute.
    """
    for i, tok in enumerate(tokens):
        if os.path.basename(tok) == "git":
            return i
    return None


def _git_hooks_bypass_reason(tokens: Sequence[str]) -> str | None:
    """A violation reason for ONE segment's tokens, or None.

    `tokens` is already `_tokens(segment)` with `_strip_redirections`
    applied by the caller — this function does no shell parsing of its own,
    only positional-argument reading, mirroring every other git-argument
    reader in this module (`_is_ledger_only_git`, `_is_sync_to_remote_git`).
    """
    gi = _find_git_start(tokens)
    if gi is None:
        return None
    rest = tokens[gi + 1:]
    n = len(rest)
    i = 0
    sub = ""
    while i < n:
        tok = rest[i]

        if tok in ("-c", "--config") and i + 1 < n:
            if _kv_key(rest[i + 1]) == _HOOKS_PATH_KEY:
                return (
                    f"`git {tok} {rest[i + 1]}` overrides core.hooksPath inline for "
                    f"this one invocation — every hook is skipped, silently."
                )
            i += 2
            continue
        if tok.startswith("--config="):
            if _kv_key(tok[len("--config="):]) == _HOOKS_PATH_KEY:
                return (
                    f"`git {tok}` overrides core.hooksPath inline for this one "
                    f"invocation — every hook is skipped, silently."
                )
            i += 1
            continue
        if tok == "--config-env" and i + 1 < n:
            if _kv_key(rest[i + 1]) == _HOOKS_PATH_KEY:
                return (
                    f"`git {tok} {rest[i + 1]}` redirects core.hooksPath through an "
                    f"environment variable — every hook is skipped, silently."
                )
            i += 2
            continue
        if tok.startswith("--config-env="):
            if _kv_key(tok[len("--config-env="):]) == _HOOKS_PATH_KEY:
                return (
                    f"`git {tok}` redirects core.hooksPath through an environment "
                    f"variable — every hook is skipped, silently."
                )
            i += 1
            continue

        if not sub:
            if tok in _GIT_GLOBAL_FLAGS_WITH_OPERAND:
                i += 2
                continue
            if not tok.startswith("-"):
                sub = tok
                if sub == "config":
                    # `config`'s own args are a wholly different grammar
                    # (`--global`/`--unset`/positionals) from `--no-verify`
                    # below; hand off rather than fold it into this loop.
                    return _git_config_hookspath_set_reason(rest[i + 1:])
            i += 1
            continue

        # Inside the subcommand's own arguments now.
        if sub in _NO_VERIFY_LONG_SUBCOMMANDS and tok == "--no-verify":
            return f"`git {sub} --no-verify` skips the pre-{sub} hook entirely."
        if (
            sub in _NO_VERIFY_SHORT_SUBCOMMANDS
            and tok.startswith("-")
            and not tok.startswith("--")
            and len(tok) > 1
            and "n" in tok[1:]
        ):
            return (
                f"`git {sub} {tok}` bundles `-n` (== `--no-verify` for `commit`) — "
                f"skips the pre-commit and commit-msg hooks entirely."
            )
        i += 1
    return None


def _git_config_env_injection(command: str) -> str | None:
    """`GIT_CONFIG_KEY_<n>=core.hooksPath` anywhere in the (normalized)
    command text — see `_GIT_CONFIG_ENV_KEY_RE`'s docstring above. Whole-text
    regex rather than segment/token scanning: the paired `GIT_CONFIG_KEY_n`/
    `GIT_CONFIG_VALUE_n` assignments and `GIT_CONFIG_COUNT` are frequently on
    an EARLIER segment (`export …`) than the `git` invocation itself, so a
    per-segment token reader would miss the cross-segment correlation.
    """
    if _GIT_CONFIG_ENV_KEY_RE.search(command):
        return (
            "a `GIT_CONFIG_KEY_*=core.hooksPath` environment-variable injection is "
            "present — git's env-var config mechanism, functionally identical to "
            "`-c core.hooksPath=…` but invisible to a plain argv scan."
        )
    return None


def decide_git_bypass(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    allow_override: bool | None = None,
) -> dict[str, Any] | None:
    """None to allow; a dict describing the refusal otherwise.

    Unlike `decide()` above, this does NOT depend on `GuardContext` — no
    branch, no worktree, no primary-checkout test. A hooks bypass is exactly
    as harmful on a feature-branch worktree commit as on the primary: the
    hooks that stop running are the SAME ones either way. Only `Bash` is
    relevant (a git hooks bypass is inherently a shell invocation; `Edit`/
    `Write`/`NotebookEdit` cannot express one).
    """
    if allow_override is None:
        allow_override = os.environ.get(HOOK_BYPASS_ALLOW_ENV, "") == "1"
    if allow_override:
        return None
    if tool_name != "Bash":
        return None

    raw_command = (tool_input or {}).get("command") or ""
    if not raw_command:
        return None
    command = _normalize(raw_command)

    reason = _git_config_env_injection(command)
    if reason is None:
        for segment in _segments(command):
            tokens = _strip_redirections(_tokens(segment))
            reason = _git_hooks_bypass_reason(tokens)
            if reason is not None:
                break
    if reason is None:
        return None

    return {
        "tool": tool_name,
        "reason": (
            f"REFUSED — {reason}\n"
            f"This repo already configures core.hooksPath (an absolute path — "
            f"see `git config core.hooksPath`); any override is a no-op at best "
            f"and a SILENT bypass at worst. A `-c core.hooksPath=…` override that "
            f"reads as 'being careful about hooks' still skips every keeper "
            f"(kb_sync · check_claude_md_router · check_eight_way_sync · "
            f"keeper-pattern-cache refresh) with no warning and exit 0 — worse "
            f"than `--no-verify`, which is at least named in CLAUDE.md §1 and "
            f"caught by the harness classifier.\n"
            f"Diagnose instead of overriding: `git config core.hooksPath` then "
            f'`ls -la "$(git config core.hooksPath)"` — if that is empty or '
            f"missing, the fix is `bash scripts/install-hooks.sh`, not a "
            f"per-invocation override.\n"
            f"No agent or brief can authorize a bypass. If a human genuinely "
            f"needs one, the rationale belongs in the commit message and the "
            f"ONLY mechanism is `{HOOK_BYPASS_ALLOW_ENV}=1` set in the launching "
            f"shell's environment — never inside the command being refused."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# `decide_hook_integrity` — refuse tampering with the HOOK FILES THEMSELVES.
# ═══════════════════════════════════════════════════════════════════════════
"""
**Why this exists, on top of `decide_git_bypass`.** `-c core.hooksPath=…` and
`--no-verify` are not the only way to make a hook stop running. `rm .git/
hooks/pre-commit`, `> .git/hooks/pre-commit` (truncate), `chmod -x .git/
hooks/pre-commit`, or writing `.git/config` directly (`Edit`/`Write`, or a
Bash `echo >> .git/config`) all disable a hook exactly as effectively —
git silently skips a missing or non-executable hook, no error, no warning —
and none of them are a `git` invocation at all, so `decide_git_bypass`'s
argv-shaped detection cannot see them. `decide()` above cannot help either:
`.git/` is DELIBERATELY excluded from its guarded region (see that function's
own docstring and `is_guarded_path`) precisely because git's own metadata is
where legitimate worktree management, ledger commits, and sync-to-remote
resets all have to write. Walking that exclusion back would break more than
it protects.

**The fix is a narrow deny-list INSIDE the excluded region, not a wider
region.** This function does not touch `is_guarded_path` or `decide()` at
all. It asks one question, orthogonal to "is this the primary checkout on a
shared branch": does this write target `<git-common-dir>/hooks/*` or
`<git-common-dir>/config`? Everything else under `.git/` — `HEAD`, `index`,
`refs/`, `worktrees/`, `objects/` — stays exactly as unguarded as it always
was; the worktree-add/remove, ledger-commit, and `git gc`-class operations
the primary-write guard fights to allow never touch `hooks/` or `config` and
are untouched by this function.

**Resolving through `gitdir:` — the reason this is not a path-string
special-case.** A linked worktree's `.git` is a FILE containing `gitdir:
<primary>/.git/worktrees/<name>`, not a directory — and `core.hooksPath`
(when unset, as here it is NOT: see the module docstring — but even when it
IS set, the value lives in the SHARED `config`) resolves to the PRIMARY's
`hooks/` regardless of which worktree a command runs from. `git rev-parse
--path-format=absolute --git-common-dir`, run FROM the candidate cwd, is
what actually performs that resolution — the same probe `discover_context`
already uses — so a `rm .git/hooks/pre-commit` typed from inside a worktree
is judged against the PRIMARY's real hooks directory, not a non-existent
`<worktree>/.git/hooks/` that a naive string-join would compute.

**Reuses `bash_write_targets` wholesale for the generic shapes.** `rm`, `mv`,
`cp` (dest-only), `tee`, `install`, `ln`, and every real-redirect
(`>`/`>>`/fused forms) already compute correctly-resolved write targets in
that function; this only adds the ONE judgment `bash_write_targets` does not
make and should not — `chmod`'s MODE matters here (`+x` repairs a hook,
`-x`/an all-even octal disables one) where it never mattered for the
primary-write question (any chmod on a guarded path was already suspect
there, mode notwithstanding).

**Same escape hatch, deliberately.** `HOOK_BYPASS_ALLOW_ENV` — this is the
SAME category of bypass as `decide_git_bypass`'s (disabling a hook), just
aimed at the file instead of the git invocation; a second, differently-named
env var would only fragment the one human-only override path (see
`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`).
"""

#: Chmod's own recognized flags — never a mode, never a path.
_CHMOD_KNOWN_FLAGS = frozenset({
    "-R", "--recursive", "-v", "--verbose", "-c", "--changes",
    "-f", "--silent", "--quiet",
})


def _resolve_git_common_dir(cwd: str) -> str | None:
    """The repo's shared `.git` dir, resolved THROUGH a linked worktree's
    `gitdir:` indirection. `git rev-parse --git-common-dir` does that
    resolution for us — see the module docstring above for why this must
    not be a manual path join. Returns None when `cwd` is not inside any
    git repo (never blocks on that; the caller treats None as "cannot see").
    """
    out = _run_git(["-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"], None)
    return out or None


def _under_git_hooks_dir(path: str, common: str) -> bool:
    return _within(path, os.path.join(common, "hooks"))


def _is_git_config_file(path: str, common: str) -> bool:
    return os.path.normpath(path) == os.path.normpath(os.path.join(common, "config"))


def _mode_removes_exec(mode: str) -> bool:
    """Does chmod `mode` take the exec bit AWAY (or land on a mode with no
    exec bit anywhere)? `+x` and an explicit `=…x…` clause ADD it — a
    REPAIR, and must not match. A numeric mode is judged by whether ANY of
    its (up to three) permission digits is odd (1/3/5/7 — has the exec bit).
    Ambiguous input (empty, or a symbolic clause naming neither) is treated
    as REMOVING — the safe direction for this gate: there is no legitimate
    reason to chmod anything under `.git/hooks/` except re-adding exec, so an
    unreadable mode is never assumed to be that one legitimate case.
    """
    mode = mode.strip()
    if not mode:
        return True
    if mode.isdigit():
        digits = mode[-3:] if len(mode) >= 3 else mode
        return not any(d in "1357" for d in digits)
    if "+x" in mode or re.search(r"=[^,]*x", mode):
        return False
    return True


def _chmod_targets(command: str, cwd: str) -> tuple[list[str], list[str]]:
    """`(all_targets, disabling_targets)` for every `chmod` in `command`.

    `bash_write_targets` already adds a chmod's target to ITS OWN result
    list, mode-blind (correct for "did work land under a guarded path",
    where any chmod is suspect regardless of mode). That mode-blindness is
    WRONG for this gate — `chmod +x` is a repair — so `decide_hook_integrity`
    must SUBTRACT `all_targets` from the generic scan's chmod contribution
    and add back only `disabling_targets` (mode removes exec, see
    `_mode_removes_exec`). Returning both from one pass keeps the
    tokenizing/positional-extraction logic written exactly once.
    """
    all_targets: list[str] = []
    disabling: list[str] = []
    for segment in _segments(_normalize(command)):
        tokens = _strip_redirections(_tokens(segment))
        idx = next((i for i, t in enumerate(tokens) if os.path.basename(t) == "chmod"), None)
        if idx is None:
            continue
        positional = [t for t in tokens[idx + 1:] if t not in _CHMOD_KNOWN_FLAGS]
        if not positional:
            continue
        mode, paths = positional[0], positional[1:]
        resolved = [r for r in (_resolve(p, cwd) for p in paths) if r]
        all_targets.extend(resolved)
        if resolved and _mode_removes_exec(mode):
            disabling.extend(resolved)
    return all_targets, disabling


def _ln_relink_safe_targets(command: str, cwd: str) -> list[str]:
    """Resolved DESTINATION targets of every `ln` whose SOURCE points at
    `scripts/hooks/` — the sanctioned reinstall pattern (`ln -s scripts/
    hooks/pre-commit .git/hooks/pre-commit`, exactly what `scripts/hooks/
    install-hooks.sh` runs). `bash_write_targets` treats `ln` as dest-only
    (correctly — the source is a READ), but is mode/source-blind the same
    way it is chmod-mode-blind: it cannot tell "pointing a hook symlink at
    the TRACKED source" (a repair) from "pointing it at `/dev/null`" (a
    disable). Anything whose source is NOT under `scripts/hooks/` stays
    caught by the generic scan — this only carves out the one shape that
    is provably always safe.
    """
    safe: list[str] = []
    for segment in _segments(_normalize(command)):
        tokens = _strip_redirections(_tokens(segment))
        idx = next((i for i, t in enumerate(tokens) if os.path.basename(t) == "ln"), None)
        if idx is None:
            continue
        positional = [t for t in tokens[idx + 1:] if not t.startswith("-")]
        if len(positional) < 2:
            continue
        source, dest = positional[0], positional[-1]
        if "scripts/hooks/" not in source and "scripts\\hooks\\" not in source:
            continue
        resolved = _resolve(dest, cwd)
        if resolved:
            safe.append(resolved)
    return safe


def decide_hook_integrity(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = None,
    allow_override: bool | None = None,
) -> dict[str, Any] | None:
    """None to allow; a dict describing the refusal otherwise.

    Covers `Edit`/`Write`/`MultiEdit`/`NotebookEdit` (any write whose target
    resolves under `.git/hooks/` or to `.git/config`) and `Bash` (the same
    two targets, reached via `rm`/`mv`/`cp`/a truncating or any real
    redirect/`tee`/`install`/`ln` — all already computed by
    `bash_write_targets` — plus the mode-aware `chmod` leg above).
    """
    if allow_override is None:
        allow_override = os.environ.get(HOOK_BYPASS_ALLOW_ENV, "") == "1"
    if allow_override:
        return None

    cwd = cwd or os.getcwd()
    common = _resolve_git_common_dir(cwd)
    if common is None:
        return None  # not a git repo, or the probe failed — cannot see, must not block

    def _flagged(paths: Iterable[str]) -> list[str]:
        return sorted({p for p in paths if _under_git_hooks_dir(p, common) or _is_git_config_file(p, common)})

    if tool_name in _FILE_PATH_TOOLS:
        raw = (tool_input or {}).get(_FILE_PATH_TOOLS[tool_name]) or ""
        target = _resolve(raw, cwd) if raw else ""
        hits = _flagged([target]) if target else []
    elif tool_name == "Bash":
        command = (tool_input or {}).get("command") or ""
        if not command:
            return None
        generic_targets, _ = bash_write_targets(command, cwd)
        chmod_all, chmod_disabling = _chmod_targets(command, cwd)
        ln_safe = _ln_relink_safe_targets(command, cwd)
        # Subtract chmod's own (mode-blind) contribution and any `ln`
        # re-linking the tracked source, then add back only the mode-AWARE
        # chmod-disabling subset — see `_chmod_targets`'s and `_ln_relink_
        # safe_targets`'s docstrings for why the generic scan alone would
        # wrongly flag a repairing `chmod +x` or `ln -s scripts/hooks/x
        # .git/hooks/x`.
        non_special_generic = [t for t in generic_targets if t not in chmod_all and t not in ln_safe]
        hits = sorted(set(_flagged(non_special_generic)) | set(_flagged(chmod_disabling)))
    else:
        return None

    if not hits:
        return None

    shown = ", ".join(os.path.relpath(h, common) for h in hits[:4])
    return {
        "tool": tool_name,
        "reason": (
            f"REFUSED — this would touch `{shown}` under the repo's own git "
            f"directory ({common}). Removing, truncating, overwriting, or "
            f"un-executabling a file under `.git/hooks/`, or writing `.git/"
            f"config` directly, disables a hook exactly as effectively as "
            f"`-c core.hooksPath=…` does — and just as silently: git skips a "
            f"missing or non-executable hook with no error at all.\n"
            f"If a hook is genuinely broken, fix the TRACKED source it is "
            f"symlinked from (`scripts/hooks/<name>`) and re-run `bash "
            f"scripts/install-hooks.sh` — never edit anything under `.git/` "
            f"directly.\n"
            f"The only sanctioned mechanism to genuinely bypass hooks is "
            f"`{HOOK_BYPASS_ALLOW_ENV}=1` set in the launching shell's "
            f"environment — never inside the command being refused."
        ),
    }


def findings(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """`decide` in the keeper finding shape, for MCP/compliance consumers."""
    verdict = decide(*args, **kwargs)
    if verdict is None:
        return []
    return [{
        "product": "<repo>",
        "file": ", ".join(verdict["targets"][:4]),
        "issue": verdict["reason"],
        "severity": "high",
    }]


def iter_guarded(paths: Iterable[str], ctx: GuardContext) -> list[str]:
    """Public helper: which of `paths` fall inside the guarded region."""
    return [p for p in paths if is_guarded_path(p, ctx)]
