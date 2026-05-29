"""Validation signal derivation for seed organs (reusable components).

Defines the **derived-first** validation semantics used by
``noctus.dev.component_list`` and ``noctus.dev.component_bundle``.

Validation status is DERIVED from observable signals — no manual catalog
entries, no human verdicts that rot over time.

Signal definitions
------------------
``validated``
    ALL of the following must hold:
    1. ``consumers_count >= CONSUMERS_THRESHOLD`` (≥3 wired consumers means
       real cross-product reuse has been proven).
    2. ``has_test is True`` — there is at least one colocated test file.
    3. ``test_passes_ci is True`` — the test passes in CI (if known).
    4. ``has_noc_remediate_markers is False`` — no deferred debt markers in
       the component source.
    5. ``recent_bugfix_commits_14d == 0`` — no bug-fix commits in the last
       ``BUGFIX_WINDOW_DAYS`` days (stable code, not fire-fighting).

``shelfware``
    ``consumers_count == 0`` — built but not wired into any product.
    This is distinct from "broken"; the component may be correct but is
    currently dead code. Naming it "shelfware" surfaces the anti-pattern
    (silent "available") so it can be wired or deleted deliberately.

``emerging``
    Anything else — the component is in use (1-2 consumers) or has one of
    the five ``validated`` gates open (no test, failing CI, debt markers,
    recent bug-fixes). The healthy trajectory: fill the gaps → promote.

``unknown``
    Data is genuinely missing (e.g., graph cache absent, CI signal not
    available). Never used as a lazy fallback — only when data is absent.

Threshold constants
-------------------
These are tunable module-level constants. Do NOT inline them at call-sites.

``CONSUMERS_THRESHOLD``: int = 3
    Minimum wired consumers for ``validated``. Three is the recurrence
    rule (N≥3 → formalize) applied to components: a component consumed
    3+ times has proven cross-product value.

``BUGFIX_WINDOW_DAYS``: int = 14
    Look-back window for recent bugfix commit detection. Two weeks is
    enough to catch fire-fighting that hasn't settled yet.

KB § PATTERNS/architect/component-list-and-validation.md.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass  # only for cross-module type hints if needed

logger = logging.getLogger(__name__)

# ── Tunable thresholds ────────────────────────────────────────────────────────

CONSUMERS_THRESHOLD: int = 3
"""Minimum wired consumers for ``validated`` status.

Three is the recurrence rule applied to components (N≥3 means the pattern
has been proven enough times to be worth formalising / trusting as reusable).
"""

BUGFIX_WINDOW_DAYS: int = 14
"""Look-back window (days) for recent bugfix commit detection.

Two weeks is long enough to catch a settling fire-fight while keeping
components that had an old one-off fix in the ``emerging`` bucket.
"""


# ── Public derivation ─────────────────────────────────────────────────────────


def derive_validation_status(
    component_name: str,
    consumers_count: int,
    has_test: bool,
    test_passes_ci: bool | None,  # None = unknown
    has_noc_remediate_markers: bool,
    recent_bugfix_commits_14d: int,
) -> Literal["validated", "emerging", "shelfware", "unknown"]:
    """Derive the validation status of a component from its observable signals.

    Parameters
    ----------
    component_name:
        Human-readable name (used for log messages only; not load-bearing).
    consumers_count:
        Number of wired consumers found via ``consumes_component`` edges
        (or ``imports`` edges as fallback). 0 → ``shelfware`` immediately.
    has_test:
        True when a colocated test file for this component is present on disk.
    test_passes_ci:
        True = green, False = red, None = not known (no CI data, no test run).
        ``None`` is treated as a missing signal — not as "passes".
    has_noc_remediate_markers:
        True when any ``NOC-REMEDIATE[...]`` marker appears in the component
        source file(s).  Even one marker means unresolved deferred debt.
    recent_bugfix_commits_14d:
        Number of ``fix:``-prefixed commits touching the component in the last
        ``BUGFIX_WINDOW_DAYS`` days.  Any > 0 blocks ``validated``.

    Returns
    -------
    Literal["validated", "emerging", "shelfware", "unknown"]
        Derived status.  ``unknown`` only when ``consumers_count < 0``
        (caller signals missing data).
    """
    # ``unknown`` sentinel: caller passes -1 to indicate missing graph data.
    if consumers_count < 0:
        logger.debug("derive_validation_status: %s → unknown (missing data)", component_name)
        return "unknown"

    # ``shelfware`` — zero consumers, built but not wired.
    if consumers_count == 0:
        logger.debug("derive_validation_status: %s → shelfware", component_name)
        return "shelfware"

    # Check all five ``validated`` gates.
    gates = {
        "consumers_threshold": consumers_count >= CONSUMERS_THRESHOLD,
        "has_test": has_test,
        "test_passes_ci": test_passes_ci is True,
        "no_remediate_markers": not has_noc_remediate_markers,
        "no_recent_bugfixes": recent_bugfix_commits_14d == 0,
    }
    if all(gates.values()):
        logger.debug("derive_validation_status: %s → validated (all gates pass)", component_name)
        return "validated"

    failing = [k for k, v in gates.items() if not v]
    logger.debug(
        "derive_validation_status: %s → emerging (failing gates: %s)",
        component_name, failing,
    )
    return "emerging"


# ── Signal input collector ────────────────────────────────────────────────────

_NOC_REMEDIATE_RE = re.compile(r"NOC-REMEDIATE\[(?P<cls>[^\]<>\s][^\]<>]*)\]")
# Conventional-commits fix pattern: "fix:" or "fix(scope):" at line start.
_FIX_COMMIT_RE = re.compile(r"^fix(\([^)]+\))?:", re.IGNORECASE | re.MULTILINE)


def compute_signal_inputs(
    component_path: Path,
    graph_neighbors_result: dict,
    repo_root: Path,
) -> dict:
    """Compute the raw signal inputs for :func:`derive_validation_status`.

    This is the "heavy lifting" half — it reads disk + git to populate the
    five signal fields.  The pure derivation function stays thin and testable
    with plain arguments.

    Parameters
    ----------
    component_path:
        Absolute path to the component source file (e.g. a ``.tsx`` or
        ``.py`` file).
    graph_neighbors_result:
        The ``dict`` returned by ``noctus.graph.neighbors`` (or
        ``GraphIndex.neighbors``) for the component node.  Used to count
        ``consumes_component`` edges.  If ``W1`` hasn't landed yet (no such
        edge kind), falls back to counting ``imports`` edges with a warning.
    repo_root:
        Absolute path to the repo root — needed for ``git log``.

    Returns
    -------
    dict with keys: ``consumers_count``, ``has_test``, ``test_passes_ci``,
    ``has_noc_remediate_markers``, ``recent_bugfix_commits_14d``.
    """
    consumers_count = _count_consumers(component_path, graph_neighbors_result)
    has_test = _find_test_file(component_path)
    has_noc_remediate_markers = _has_remediate_markers(component_path)
    recent_bugfixes = _count_recent_bugfix_commits(component_path, repo_root)

    # test_passes_ci: we don't have a live CI signal at this layer —
    # mark as None (unknown).  W4 organ.yaml sidecars can override this.
    return {
        "consumers_count": consumers_count,
        "has_test": has_test,
        "test_passes_ci": None,
        "has_noc_remediate_markers": has_noc_remediate_markers,
        "recent_bugfix_commits_14d": recent_bugfixes,
    }


# ── Private helpers ───────────────────────────────────────────────────────────


def _count_consumers(component_path: Path, neighbors: dict) -> int:
    """Extract consumer count from graph neighbors.

    Prefers ``consumes_component`` edges (W1); falls back to inbound
    ``imports`` edges if W1 hasn't landed yet (warning emitted once per
    component — not a silent-ok).
    """
    sub_edges: list[dict] = neighbors.get("edges", [])
    component_label = component_path.stem

    consumes_edges = [
        e for e in sub_edges
        if e.get("kind") == "consumes_component"
        and e.get("target", "").split(":")[-1] == component_label
    ]
    if consumes_edges:
        return len(consumes_edges)

    # W1 fallback — count inbound ``imports`` edges pointing at this component.
    import_edges = [
        e for e in sub_edges
        if e.get("kind") == "imports"
        and e.get("target", "") == component_label
    ]
    if import_edges:
        logger.warning(
            "compute_signal_inputs: no 'consumes_component' edges for %s — "
            "falling back to 'imports' edges (count=%d). W1 may not have landed.",
            component_label, len(import_edges),
        )
        return len(import_edges)

    # Empty neighbors is data-present but zero consumers (not unknown).
    return 0


def _find_test_file(component_path: Path) -> bool:
    """True when a colocated test file exists for the component.

    Colocated = same directory OR a ``__tests__/`` / ``tests/`` sibling.
    The check is name-based:
      - ``<Name>.test.tsx`` / ``<Name>.test.ts`` (TS/TSX components)
      - ``test_<name>.py`` (Python components)
    """
    stem = component_path.stem
    parent = component_path.parent

    # TS/TSX flavours
    ts_names = [
        f"{stem}.test.tsx",
        f"{stem}.test.ts",
        f"{stem}.spec.tsx",
        f"{stem}.spec.ts",
    ]
    # Python flavour
    py_names = [f"test_{stem.lower()}.py"]

    # Check sibling dir and __tests__ subdir
    check_dirs = [parent, parent / "__tests__", parent / "tests"]
    for d in check_dirs:
        for name in ts_names + py_names:
            if (d / name).exists():
                return True
    return False


def _has_remediate_markers(component_path: Path) -> bool:
    """True when the component source contains at least one NOC-REMEDIATE marker."""
    try:
        text = component_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("_has_remediate_markers: cannot read %s — %s", component_path, exc)
        return False
    return bool(_NOC_REMEDIATE_RE.search(text))


def _count_recent_bugfix_commits(component_path: Path, repo_root: Path) -> int:
    """Count fix-commits touching this file in the last BUGFIX_WINDOW_DAYS days.

    Uses ``git log --oneline --since=<N>.days.ago --grep=^fix -- <rel_path>``
    (conventional-commits fix prefix).  Returns 0 on any git failure (not an
    error — the component may be untracked or in a detached worktree).
    """
    try:
        rel_path = component_path.relative_to(repo_root).as_posix()
    except ValueError:
        logger.debug(
            "_count_recent_bugfix_commits: %s is not under %s — returning 0",
            component_path, repo_root,
        )
        return 0

    try:
        result = subprocess.run(
            [
                "git", "log", "--oneline",
                f"--since={BUGFIX_WINDOW_DAYS}.days.ago",
                "--grep=^fix",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        if result.returncode != 0:
            logger.debug(
                "_count_recent_bugfix_commits: git log non-zero exit for %s — %s",
                rel_path, result.stderr.strip(),
            )
            return 0
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return len(lines)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "_count_recent_bugfix_commits: git log failed for %s — %s", rel_path, exc
        )
        return 0
