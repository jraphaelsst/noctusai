"""R2 (2026-09-24, the dev-freeze fix): `.github/workflows/test.yml`'s push
trigger's `paths-ignore` must classify EXACTLY the same paths as
"ledger-only" that the `changes` job's own in-script `NON_LEDGER=... grep
-vE '<pattern>'` predicate does — two hand-authored definitions of the same
concept WILL drift (`KB § …` "hand-maintained lists drift"). This is the
"keeper/test asserting the two sets are equal" leg (the workflow `on:` block
cannot itself run a generator at parse time, so cross-validation is the
sanctioned alternative — CLAUDE.md §1 "Hand-maintained lists drift").

Both sides are extracted from the LIVE file text (never hand-copied into
this test), then run against the same battery of representative repo-
relative paths and asserted to classify identically.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github" / "workflows" / "test.yml"


def _text() -> str:
    return WF.read_text(encoding="utf-8")


def _paths_ignore() -> list[str]:
    on = yaml.safe_load(_text()).get(True) or yaml.safe_load(_text()).get("on")
    patterns = (on or {}).get("push", {}).get("paths-ignore")
    assert patterns, "test.yml push trigger has no paths-ignore — R2 regressed"
    return patterns


def _ledger_only_grep_pattern() -> str:
    """Extract the exact `grep -vE '<pattern>'` regex the `changes` job uses
    to decide `NON_LEDGER` — never hand-copied, always read from the live
    script text."""
    t = _text()
    m = re.search(r"NON_LEDGER=.*?grep -vE '([^']+)'", t)
    assert m, "changes job's NON_LEDGER grep predicate not found in test.yml"
    return m.group(1)


def _gha_glob_to_regex(pattern: str) -> re.Pattern:
    """Translate ONE GitHub Actions path-filter glob to a `re.Pattern`, per
    the documented semantics this repo relies on (GitHub "path filter cheat
    sheet"): `*` matches zero-or-more characters EXCLUDING `/` (stays inside
    one path segment); `**` as its own path segment matches zero-or-more
    FULL segments (including none — `project-history/**/*.ndjson` matches
    `project-history/x.ndjson` with zero intermediate directories). Patterns
    are matched against the FULL repo-relative path, anchored at the start
    (no implicit leading `**/`) — mirrors this repo's one actual use case;
    not a general-purpose minimatch port."""
    segments = pattern.split("/")
    regex_segments: list[str] = []
    for seg in segments:
        if seg == "**":
            regex_segments.append(r"(?:[^/]+/)*")
        else:
            escaped = re.escape(seg).replace(r"\*", "[^/]*")
            regex_segments.append(escaped)
    # `**` segments already carry their own trailing "/" in the regex above
    # (or match zero of them) — join the REMAINING literal segments with "/".
    body = ""
    for i, (seg, rx) in enumerate(zip(segments, regex_segments)):
        if seg == "**":
            body += rx
        else:
            body += rx + ("/" if i < len(segments) - 1 else "")
    return re.compile("^" + body + "$")


def _matches_paths_ignore(path: str, patterns: list[str]) -> bool:
    return any(_gha_glob_to_regex(p).match(path) for p in patterns)


_BATTERY = [
    "project-history/branch-tree.ndjson",
    "project-history/branch-tree.mirror.ndjson",
    "project-history/vector-costs.ndjson",
    "project-history/ledger.ndjson",
    "project-history/code-baselines/foo.ndjson",           # nested — the `**` case
    "project-history/PROJECT-HISTORY.md",                   # ledger dir, wrong ext
    "project-history/absorptions.ndjson.bak",                # wrong suffix (not .ndjson)
    "mcp/noctusai/tools/noctus/dev/release.py",              # real code
    "products/core/backend/app/main.py",                     # real code
    "products/project-history/backend/app/main.py",          # decoy: contains the substring, wrong position
    "KNOWLEDGE-BASE/PATTERNS/devops/dev-main-ci-gates.md",    # docs, but NOT under project-history/
]


def test_paths_ignore_matches_the_ledger_only_scope_predicate():
    patterns = _paths_ignore()
    grep_re = re.compile(_ledger_only_grep_pattern())
    for path in _BATTERY:
        via_grep = bool(grep_re.match(path))          # True ⇒ counted as NON_LEDGER (code)
        via_paths_ignore = _matches_paths_ignore(path, patterns)
        # `NON_LEDGER` keeps a path when the grep pattern does NOT match it
        # (grep -v); `paths-ignore` SKIPS the run when a path DOES match one
        # of its globs. "ledger-only" (skip CI) ⇔ every changed path fails
        # NON_LEDGER's keep-test ⇔ every changed path matches the glob — i.e.
        # the two predicates must agree on EVERY individual path: matches
        # the grep pattern ⇔ matches a paths-ignore glob.
        assert via_grep == via_paths_ignore, (
            f"{path!r}: grep pattern match={via_grep} but paths-ignore "
            f"match={via_paths_ignore} — the two ledger-only definitions "
            "have drifted apart (test.yml's push.paths-ignore vs. the "
            "changes job's NON_LEDGER grep predicate)."
        )


def test_paths_ignore_is_scoped_to_the_push_trigger_only():
    """pull_request stays fully covered — a docs-vs-code judgment on an
    open PR is exactly what review wants visible, unaffected by R2."""
    on = yaml.safe_load(_text()).get(True) or yaml.safe_load(_text()).get("on")
    pr = (on or {}).get("pull_request", {})
    assert "paths-ignore" not in pr and "paths" not in pr
