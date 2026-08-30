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

#: `git` subcommands that mutate the working tree or the index of the checkout
#: they run in. `pull`, `fetch`, `merge`, `push`, `worktree`, `tag` and `branch`
#: are NOT here: syncing and integrating the primary checkout on `dev` is the
#: orchestrator's actual job, and a guard that fought it would be switched off.
_GIT_WRITE_SUBCOMMANDS = {
    "commit", "add", "apply", "am", "cherry-pick", "revert", "rebase", "reset",
    "checkout", "switch", "restore", "stash", "clean", "mv", "rm",
}

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
        args = tokens[1:]

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
                # Otherwise a git write is scoped to its CHECKOUT, not to the
                # pathspecs: `git checkout .` and `git reset --hard` name no
                # path at all.
                targets.append(sub_cwd)
            continue

        if name in _ALWAYS_WRITE:
            candidates = [a for a in args if _looks_like_path(a)]
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
        if uncertain and not targets:
            targets = [_effective_cwd(command, cwd)]
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
            + ("\nThe command's write target could not be parsed exactly, so it is "
               "judged against its effective working directory — name an absolute "
               "path outside the primary checkout if that is wrong."
               if uncertain else "")
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
