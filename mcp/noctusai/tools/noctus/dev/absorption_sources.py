"""Absorption SOURCES are frozen — the one derivation every gate shares (Phase 5a, owner rule 2026-11-12).

A product on the absorption list (erp-imobiliario -> social-wiring, igig -> orbity, therapy-platform -> monica,
community -> monica) is an absorption SOURCE only, until it is erased (ladder step A6):

  1. no change / refinement / fix to its code, migrations, docs or data — the only writes allowed are the
     absorption ladder's own steps, on a branch named ``absorb-<source>-*``;
  2. never a reference, pilot or model for new work — new work references the CANON (or the seed);
  3. never a pilot consumer in ``absorptions.ndjson`` capability rows or organ sidecars.

The registry is NOT a constant here. It is DERIVED from the absorptions ledger (``project-history/absorptions.ndjson``,
stored on ``origin/ledgers``): a ``lifecycle`` row with ``stage: absorb_only`` + ``canon`` registers a source; a later
``stage: done`` row (A6, erased) removes it. Other ladder stages for the same slug (cloned/diagnosed/...) never
unfreeze it. Adding a source = ``noctus.dev.absorption_log kind=lifecycle stage=absorb_only canon=<canon>`` — the
owner's decision, one append-only row, picked up by every consumer below on its next read.

Consumers (all call :func:`load_sources` / :func:`derive_sources`; none keeps a slug list):
  F2  ``scripts/hooks/claude-guard-absorption-source.py``  PreToolUse — refuses the WRITE.
  F3  ``compliance.check_absorption_source_frozen``        pre-commit — refuses the COMMIT (deletions pass).
  F4  ``compliance.check_absorption_pilot_is_canon``       pre-commit — refuses a source as ``pilot``;
      ``lint_text_for_source_reference`` — warn-only lint on briefs (engineer_brief_compose) and returns
      (engineer_output_linter).

STDLIB-ONLY and import-free of the toolkit: the F2 hook loads this file BY PATH under a bare ``python3``.
KB § PATTERNS/architect/product-working-scope.md (absorption source state) · gate-methodology-sync.md (build triad).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable, Iterable

LEDGER_NAME = "absorptions.ndjson"
STAGE_SOURCE = "absorb_only"
STAGE_ERASED = "done"
#: A branch may touch a source's tree iff it is ``absorb-<source>-*`` (the optional ``feat/`` is the task_branch prefix).
BRANCH_PREFIX = "absorb-"
_GIT_TIMEOUT_S = 5


# ───────────────────────────── derivation (pure) ─────────────────────────────
def _rows(text: str) -> list[dict]:
    out: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def derive_sources(ledger_text: str) -> dict[str, str]:
    """``{source_slug: canon}`` — latest of {absorb_only, done} per slug wins; ``absorb_only`` means frozen.

    Rows are ordered by ``ts`` (stable, so file order breaks ties): the same ledger text read from the dev copy,
    origin/ledgers and the spool in any concatenation order derives the same set.
    """
    rows = [r for r in _rows(ledger_text) if r.get("kind") == "lifecycle" and r.get("stage") in (STAGE_SOURCE, STAGE_ERASED)]
    rows.sort(key=lambda r: str(r.get("ts") or ""))
    latest: dict[str, dict] = {}
    for r in rows:
        slug = str(r.get("slug") or "")
        if slug:
            latest[slug] = r
    return {s: str(r.get("canon") or "") for s, r in latest.items() if r.get("stage") == STAGE_SOURCE}


def pilot_violations(ledger_text: str, sources: dict[str, str]) -> list[dict]:
    """Latest capability row per (slug, capability) whose ``pilot`` is a source. Each: slug, capability, pilot, canon."""
    latest: dict[tuple[str, str], dict] = {}
    rows = [r for r in _rows(ledger_text) if r.get("kind") == "capability"]
    rows.sort(key=lambda r: str(r.get("ts") or ""))
    for r in rows:
        if r.get("slug") and r.get("capability"):
            latest[(str(r["slug"]), str(r["capability"]))] = r
    return [{"slug": s, "capability": c, "pilot": r["pilot"], "canon": sources[r["pilot"]]}
            for (s, c), r in sorted(latest.items()) if r.get("pilot") in sources]


_PILOT_KEY = re.compile(r"^\s*(pilot(?:_consumer|_product)?)\s*:\s*[\"']?([A-Za-z0-9._/-]+)[\"']?\s*(?:#.*)?$")


def sidecar_pilot_violations(text: str, sources: dict[str, str]) -> list[dict]:
    """``pilot: <slug>`` / ``pilot_consumer:`` keys in an organ sidecar naming a source (line-level, no YAML dep)."""
    hits: list[dict] = []
    for n, line in enumerate((text or "").splitlines(), 1):
        m = _PILOT_KEY.match(line)
        if m and m.group(2) in sources:
            hits.append({"line": n, "key": m.group(1), "pilot": m.group(2), "canon": sources[m.group(2)]})
    return hits


# ───────────────────────────── paths + branches (pure) ─────────────────────────────
def source_of_path(path: str, sources: Iterable[str]) -> str | None:
    """The source whose ``products/<source>/`` tree ``path`` sits in (absolute or repo-relative), else None."""
    parts = Path(path).parts
    for i, part in enumerate(parts[:-1]):
        if part == "products" and parts[i + 1] in set(sources):
            return parts[i + 1]
    return None


def branch_may_touch(branch: str, source: str) -> bool:
    """True for ``absorb-<source>`` / ``absorb-<source>-*`` (also under the task_branch ``feat/`` prefix)."""
    b = branch[5:] if branch.startswith("feat/") else branch
    return b == f"{BRANCH_PREFIX}{source}" or b.startswith(f"{BRANCH_PREFIX}{source}-")


def refusal_reason(source: str, canon: str, branch: str, path: str = "") -> str:
    where = f" ({path})" if path else ""
    return (
        f"products/{source}/ is an ABSORPTION SOURCE{where}: frozen until it is erased (Phase 5a, owner rule 2026-11-12) - "
        f"no changes, refinements or fixes, and never a reference or pilot. Work in the CANON '{canon or '<canon>'}' "
        f"(or the seed) instead. The only allowed writes are the absorption ladder's own steps (A1 salvage, A5 decouple, "
        f"A6 retire) on a branch named 'absorb-{source}-<step>' (you are on '{branch or '?'}'). "
        f"Source findings are carried as absorption input and closed 'accepted (erased)' at A6, not fixed. "
        f"KB § PATTERNS/architect/product-working-scope.md (absorption source)."
    )


# ───────────────────────────── ledger loading (IO, stdlib) ─────────────────────────────
def _git(args: list[str], cwd: str | Path) -> tuple[bool, str]:
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                           timeout=_GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return p.returncode == 0, p.stdout


def read_ledger_text(root: str | Path) -> tuple[str, str | None]:
    """Dev copy ∪ ``origin/ledgers`` ∪ the write-ahead spool (what `_ledger_store.read_ledger_text` merges).

    Returns ``(text, error)``; ``error`` is set only when NO source was readable (blind) — a registry we could not
    read must never read as "no sources"."""
    root = Path(root)
    texts: list[str] = []
    dev = root / "project-history" / LEDGER_NAME
    if dev.is_file():
        try:
            texts.append(dev.read_text(encoding="utf-8"))
        except OSError:
            pass
    ok, out = _git(["show", f"origin/ledgers:{LEDGER_NAME}"], root)
    if ok:
        texts.append(out)
    ok, common = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    if ok:
        spool = Path(common.strip()) / "noctusai" / "ledgers-pending" / LEDGER_NAME
        if spool.is_file():
            try:
                texts.append(spool.read_text(encoding="utf-8"))
            except OSError:
                pass
    if not texts:
        return "", f"absorptions ledger unreadable (no {dev}, no origin/ledgers:{LEDGER_NAME}, no spool)"
    return "\n".join(texts), None


def load_sources(root: str | Path) -> tuple[dict[str, str], str | None]:
    """``(sources, error)`` for the repo at ``root``."""
    text, err = read_ledger_text(root)
    return (derive_sources(text) if not err else {}), err


# ───────────────────────────── F2: write decision (pure given inputs) ─────────────────────────────
_FILE_PATH_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


def branch_of(path: str) -> str | None:
    """Current branch of the git worktree containing ``path`` (walks up to an existing dir). None = unknown."""
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    d = p if p.is_dir() else p.parent
    ok, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], d)
    return out.strip() if ok and out.strip() else None


def decide(
    tool_name: str,
    tool_input: dict | None,
    cwd: str,
    sources: dict[str, str],
    *,
    bash_targets: Callable[[str, str], tuple[list[str], bool]] | None = None,
    resolve: Callable[[str, str], str] | None = None,
    branch_for: Callable[[str], str | None] = branch_of,
) -> dict | None:
    """None = allow; ``{"reason", "source", "canon", "path", "branch"}`` = deny.

    Edit/Write: the file path. Bash: the write targets ``bash_targets`` parses (supplied by the hook from
    primary_write_guard — the one shell parser); an UNCERTAIN parse is not guessed at (measure, don't predict: the
    F3 commit keeper is the backstop for what the parser could not see).
    """
    if not sources:
        return None
    tool_input = tool_input or {}
    raw: list[str] = []
    if tool_name in _FILE_PATH_TOOLS:
        p = tool_input.get(_FILE_PATH_TOOLS[tool_name]) or ""
        raw = [p] if p else []
    elif tool_name == "Bash" and bash_targets is not None:
        raw, _uncertain = bash_targets(str(tool_input.get("command") or ""), cwd)
    else:
        return None
    for t in raw:
        path = resolve(t, cwd) if resolve else (t if Path(t).is_absolute() else str(Path(cwd) / t))
        src = source_of_path(path, sources)
        if not src:
            continue
        branch = branch_for(path)
        if branch is not None and branch_may_touch(branch, src):
            continue
        return {"reason": refusal_reason(src, sources[src], branch or "unknown", path),
                "source": src, "canon": sources[src], "path": path, "branch": branch}
    return None


# ───────────────────────────── F4: reference lint (pure, warn-only) ─────────────────────────────
def in_absorption_slice(text: str, source: str) -> bool:
    """A brief/return is an absorption slice for ``source`` when it names the ``absorb-<source>`` branch or says so."""
    low = text.lower()
    return f"absorb-{source}" in low or "absorption slice" in low or "absorption-slice" in low


def lint_text_for_source_reference(text: str, sources: dict[str, str]) -> list[dict]:
    """Warnings for a brief/return that names a source path or slug outside an absorption slice.

    One per source: ``{source, canon, message}``. Path form is ``products/<source>``; slug form per the rule below."""
    out: list[dict] = []
    for src, canon in sorted(sources.items()):
        # A hyphenated slug (erp-imobiliario, therapy-platform) is unambiguous as a bare token; a one-word slug
        # (igig, community) is also ordinary prose, so it counts only as `slug` in backticks or a products/ path.
        bare = rf"(?<![\w-]){re.escape(src)}(?![\w-])" if "-" in src else rf"`{re.escape(src)}`"
        named = f"products/{src}" in text or re.search(bare, text) is not None
        if named and not in_absorption_slice(text, src):
            out.append({"source": src, "canon": canon, "message": (
                f"names the absorption SOURCE '{src}' outside an absorption slice. A source is frozen: never a reference, "
                f"pilot or model for new work - reference the canon '{canon or '<canon>'}' or the seed instead "
                f"(or run this as an absorption slice on a branch 'absorb-{src}-<step>'). "
                f"KB § PATTERNS/architect/product-working-scope.md (absorption source).")})
    return out


__all__ = [
    "STAGE_SOURCE", "STAGE_ERASED", "derive_sources", "pilot_violations", "sidecar_pilot_violations", "source_of_path",
    "branch_may_touch", "refusal_reason", "read_ledger_text", "load_sources", "decide", "branch_of",
    "lint_text_for_source_reference", "in_absorption_slice",
]
