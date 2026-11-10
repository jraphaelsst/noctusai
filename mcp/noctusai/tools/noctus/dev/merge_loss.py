"""`noctus.dev.merge_loss_check` — did a merge silently DROP a line one side added?

Backstop leg of the merge-driver triad (construction = tests/test_merge_driver_contract.py,
telemetry = project-history/merge-loss-detector.ndjson + an auto-improvement ``finding``).
Born 2026-11-10: a custom merge driver left %A as "ours" on a real conflict, so
`git merge origin/dev` dropped dev's `agent-creator` row from 06-AGENTS.md with NO conflict
markers anywhere. Only a manual diff against origin/dev caught it. The class is "a driver
(or hand resolution) whose output is silently wrong"; this check judges the RESULT, not the
driver, so it also catches a future driver nobody has written yet.

Given a merge (MERGE_HEAD at pre-commit time — the result is the INDEX — or a merge commit
SHA), for every file changed on BOTH sides relative to the merge-base it computes the lines
each side ADDED, and reports any non-trivial added line absent from the result, unless the
other side removed the base region that hunk replaced (a legitimate either/or resolution).

SHADOW mode (the only mode wired today): findings are logged and printed, never blocking.
Promotion to blocking is gated on measured false-alarm data — KB § PATTERNS/common/
auto-generated-merge-drivers.md § Merge-loss detector.

Known blind spots (documented, not hidden): a line present elsewhere in the result counts as
kept (presence, not position); a duplicated-line count drop is not seen; renames are not
followed (files are compared by path); binary files are skipped and listed. Lines inside
`kb-counts` generated blocks are exempt (the driver re-derives them by design).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("noctus.dev.merge_loss")

LEDGER_NAME = "merge-loss-detector.ndjson"
MODE_SHADOW = "shadow"
MAX_LINE_CHARS = 200
MAX_DROPPED_REPORTED = 200
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_TRIVIAL_RE = re.compile(r"^[\s|:\-=_*#`>+.]*$")  # blank / table rules / punctuation-only
_MARKER_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)")
# Derived / rewritten artifacts: ledgers (rows are UPDATED in place, not appended) and the findings
# tables regenerated from them. Measured false-alarm class (2026-11-10 sample: every false alarm in
# 25 historical merges was project-history/access-tiers/*). Reported under `skipped`, never silent.
_DERIVED_PREFIXES = ("project-history/",)
_GEN_START_RE = re.compile(r"kb-counts:start:")
_GEN_END_RE = re.compile(r"kb-counts:end:")
# A WHOLE file rendered from a source (`> Generated from `<src>` by `<cmd>``) is re-derived on
# every merge, and positional ids (e.g. the D-numbers of gate-alignment-inventory.md) shift when
# a row lands upstream — every shifted row reads as "dropped" although its content is intact
# (benign class, 2026-11-10 D2b merge). A loss there is judged at its SOURCE file, which this
# detector checks like any other. Declared in ours, theirs AND the result, so a hand-written
# file cannot exempt itself by adding the header in the merge. Reported under `skipped`.
_RENDERED_HEADER_RE = re.compile(r"^>\s*Generated from `([^`]+)` by `", re.MULTILINE)
_RENDERED_HEADER_LINES = 6


def _rendered_source(text: str) -> str | None:
    m = _RENDERED_HEADER_RE.search("\n".join(text.splitlines()[:_RENDERED_HEADER_LINES]))
    return m.group(1) if m else None


def _git(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=text)


def _out(root: Path, *args: str) -> str | None:
    r = _git(root, *args)
    return r.stdout if r.returncode == 0 else None


def _show(root: Path, spec: str) -> str | None:
    """Text of a blob spec (`<rev>:<path>` / `:0:<path>`); None when absent or binary."""
    r = _git(root, "show", spec, text=False)
    if r.returncode != 0:
        return None
    if b"\x00" in r.stdout[:8192]:
        raise ValueError("binary")
    return r.stdout.decode("utf-8", errors="replace")


def _hunks(base: str, side: str, root: Path) -> list[dict]:
    """Zero-context hunks of base -> side as {start, removed:n, added:[lines]} (0-based start;
    for a pure insertion `start` is the index of the base line it goes BEFORE)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "a", Path(td) / "b"
        a.write_text(base, encoding="utf-8")
        b.write_text(side, encoding="utf-8")
        r = _git(root, "diff", "--no-index", "--no-color", "-U0", "--", str(a), str(b))
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git diff failed: {r.stderr.strip()[:200]}")
    hunks: list[dict] = []
    cur: dict | None = None
    for ln in r.stdout.splitlines():
        m = _HUNK_RE.match(ln)
        if m:
            a_start, a_len = int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1
            cur = {"start": a_start if a_len == 0 else a_start - 1, "removed": a_len, "added": [],
                   "new_start": int(m.group(3)) - 1}
            hunks.append(cur)
        elif cur is not None and ln.startswith("+") and not ln.startswith("+++"):
            cur["added"].append(ln[1:])
        elif cur is not None and ln.startswith("\\"):
            continue
    return hunks


def _generated_lines(text: str) -> set[int]:
    """0-based indices of lines inside `<!-- kb-counts:start:X -->…:end:X -->` blocks: machine-derived
    inventory the merge driver deliberately RE-DERIVES from the merged tree, so a side's count line
    differing from the result is the design, not a loss."""
    out: set[int] = set()
    inside = False
    for i, ln in enumerate(text.splitlines()):
        if _GEN_START_RE.search(ln):
            inside = True
        if inside:
            out.add(i)
        if _GEN_END_RE.search(ln):
            inside = False
    return out


def _exempt(h: dict, other: list[dict]) -> bool:
    """The other side removed the base region this hunk replaced (replace), or removed the
    base lines on BOTH sides of this insertion point (its context is gone)."""
    s, n = h["start"], h["removed"]
    for o in other:
        if o["removed"] <= 0:
            continue
        o_s, o_e = o["start"], o["start"] + o["removed"]
        if n > 0 and o_s < s + n and s < o_e:
            return True
        if n == 0 and o_s < s < o_e:
            return True
    return False


def _norm(line: str) -> str:
    return line.rstrip()


def _significant(line: str) -> bool:
    return not _TRIVIAL_RE.match(line) and not _MARKER_RE.match(line)


def _changed(root: Path, base: str, rev: str) -> set[str]:
    out = _out(root, "diff", "--name-only", "--no-renames", "-z", base, rev)
    return {p for p in (out or "").split("\0") if p}


def _resolve_merge(root: Path, merge_sha: str | None) -> dict:
    """{ours, theirs, label, result_spec(path)->spec} or {error}."""
    if merge_sha:
        parents = (_out(root, "rev-list", "--parents", "-n", "1", merge_sha) or "").split()
        if len(parents) < 3:
            return {"error": f"{merge_sha} is not a merge commit (parents: {len(parents) - 1})"}
        return {"ours": parents[1], "theirs": parents[2], "label": parents[0],
                "result": lambda p, c=parents[0]: f"{c}:{p}"}
    git_dir = _out(root, "rev-parse", "--git-dir")
    if git_dir is None:
        return {"error": "not a git repository"}
    gd = Path(git_dir.strip())
    gd = gd if gd.is_absolute() else root / gd
    mh = gd / "MERGE_HEAD"
    if not mh.is_file():
        return {"error": "no merge in progress (no MERGE_HEAD) and no merge_sha given"}
    theirs = mh.read_text().split()[0]
    ours = (_out(root, "rev-parse", "HEAD") or "").strip()
    if not ours:
        return {"error": "cannot resolve HEAD"}
    return {"ours": ours, "theirs": theirs, "label": "MERGE_HEAD", "result": lambda p: f":0:{p}"}


def merge_loss_check(
    *,
    merge_sha: str | None = None,
    worktree_path: str | Path | None = None,
    log: bool = True,
    publish: bool = False,
    mode: str = MODE_SHADOW,
    ledger_append: Callable[..., Any] | None = None,
    finding_log: Callable[..., Any] | None = None,
) -> dict:
    """Detect lines added by one side of a merge that are missing from the result.

    Returns ``{ok, verdict, dropped:[{path, side, line, base_region}], checked_files, ...}``.
    ``verdict``: ``clean`` | ``dropped`` | ``unmeasurable`` (the merge or base could not be
    read — never green, never red). ``ok`` is True only for ``clean``. Shadow mode never
    changes an exit code; the telemetry row + (when dropped) an auto-improvement ``finding``
    are written when ``log`` is True. ``ledger_append`` / ``finding_log`` are DI seams.
    """
    from workspace import resolve_caller_root
    from settings import REPO_ROOT

    root = Path(resolve_caller_root(worktree_path)) if worktree_path is not None else Path(REPO_ROOT)
    res = _result(root, merge_sha)
    res["mode"] = mode
    if log:
        _telemetry(res, root=root, publish=publish, ledger_append=ledger_append, finding_log=finding_log)
    return res


def _result(root: Path, merge_sha: str | None) -> dict:
    ctx = _resolve_merge(root, merge_sha)
    base_out = {"ok": False, "verdict": "unmeasurable", "dropped": [], "checked_files": 0,
                "merge_ref": merge_sha or "MERGE_HEAD", "files": [], "skipped": []}
    if "error" in ctx:
        return {**base_out, "error": ctx["error"]}
    bases = (_out(root, "merge-base", "--all", ctx["ours"], ctx["theirs"]) or "").split()
    if not bases:
        return {**base_out, "error": "no merge-base between the parents"}
    base = bases[0]
    both = sorted(_changed(root, base, ctx["ours"]) & _changed(root, base, ctx["theirs"]))
    dropped: list[dict] = []
    skipped: list[dict] = []
    checked: list[str] = []
    for path in both:
        if path.startswith(_DERIVED_PREFIXES):
            skipped.append({"path": path, "reason": "derived/rewritten artifact (project-history/)"})
            continue
        try:
            b = _show(root, f"{base}:{path}") or ""
            o = _show(root, f"{ctx['ours']}:{path}")
            t = _show(root, f"{ctx['theirs']}:{path}")
            if o is None or t is None:
                skipped.append({"path": path, "reason": "deleted on one side"})
                continue
            stages = _out(root, "ls-files", "-u", "--", path) if ctx["label"] == "MERGE_HEAD" else ""
            if stages:
                skipped.append({"path": path, "reason": "still conflicted (unmerged index entry)"})
                continue
            r = _show(root, ctx["result"](path))
            if r is None:
                dropped.append({"path": path, "side": "both", "line": "<file absent from the merge result>",
                                "base_region": None})
                checked.append(path)
                continue
            src = _rendered_source(r)
            if src and _rendered_source(o) == src and _rendered_source(t) == src:
                skipped.append({"path": path, "reason": f"rendered from {src} (judged at its source)"})
                continue
            kept = {_norm(x) for x in r.splitlines()}
            hs = {"ours": _hunks(b, o, root), "theirs": _hunks(b, t, root)}
            gen = {"ours": _generated_lines(o), "theirs": _generated_lines(t)}
            for side, other in (("ours", "theirs"), ("theirs", "ours")):
                for h in hs[side]:
                    if _exempt(h, hs[other]):
                        continue
                    for k, line in enumerate(h["added"]):
                        if h["new_start"] + k in gen[side]:
                            continue
                        if _significant(line) and _norm(line) not in kept:
                            dropped.append({
                                "path": path, "side": side, "line": line[:MAX_LINE_CHARS],
                                "base_region": [h["start"] + 1, h["start"] + max(h["removed"], 1)],
                            })
            checked.append(path)
        except ValueError:
            skipped.append({"path": path, "reason": "binary"})
        except (RuntimeError, OSError) as exc:
            return {**base_out, "error": f"{path}: {exc}"}
    return {
        "ok": not dropped, "verdict": "dropped" if dropped else "clean",
        "dropped": dropped[:MAX_DROPPED_REPORTED], "dropped_count": len(dropped),
        "checked_files": len(checked), "files": checked, "skipped": skipped,
        "merge_ref": ctx["label"], "base": base,
    }


def _telemetry(res: dict, *, root: Path, publish: bool, ledger_append, finding_log) -> None:
    """One ledger row per run (always) + an auto-improvement finding when lines were dropped."""
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "merge_sha": res.get("merge_ref"), "files": res.get("files", []),
        "dropped_count": res.get("dropped_count", 0), "mode": res.get("mode", MODE_SHADOW),
        "verdict": res.get("verdict"),
    }
    if res.get("dropped_count"):
        row["dropped_paths"] = sorted({d["path"] for d in res["dropped"]})
    try:
        if ledger_append is None:
            from settings import LEDGER_ROOT
            from ._ledger_store import append_rows
            path = Path(LEDGER_ROOT) / "project-history" / LEDGER_NAME
            append_rows(LEDGER_NAME, path, [row], message=f"merge-loss-detector: {row['verdict']}", publish=publish)
        else:
            ledger_append(LEDGER_NAME, [row], publish=publish)
        res["telemetry"] = "logged"
    except (OSError, ValueError, RuntimeError) as exc:  # telemetry must never fail a commit
        logger.warning("merge_loss: ledger append failed: %s", exc)
        res["telemetry"] = f"failed: {exc}"
    if res.get("dropped_count"):
        first = res["dropped"][0]
        desc = (f"merge-loss detector (shadow): {res['dropped_count']} line(s) added by one side are missing "
                f"from the merge result of {res.get('merge_ref')} — e.g. {first['side']} line "
                f"{first['line'][:80]!r} in {first['path']}. Triage: real loss (fix the driver/resolution, "
                f"add a SPECS fixture) or false alarm (record why in the KB Learnings section).")
        try:
            if finding_log is None:
                from .auto_improvement import log_entry as finding_log
            finding_log(scope="broad", kind="finding", target=first["path"], description=desc,
                        agent="tooling-engineer", source={"tool": "noctus.dev.merge_loss_check",
                                                          "ref": str(res.get("merge_ref"))})
            res["finding"] = "logged"
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("merge_loss: finding log failed: %s", exc)
            res["finding"] = f"failed: {exc}"


def register(server) -> None:
    @server.tool(
        name="noctus.dev.merge_loss_check",
        description=(
            "Merge-loss detector (SHADOW, never blocks): for a merge in progress (MERGE_HEAD; the result is "
            "the index) or a merge commit sha, list every non-trivial line one side ADDED relative to the "
            "merge-base that is MISSING from the result, unless the other side removed that base region. "
            "Catches a merge driver / hand resolution that silently drops the other side's lines "
            "(2026-11-10: dev's agent-creator row vanished from 06-AGENTS.md with no markers). Returns "
            "{ok, verdict: clean|dropped|unmeasurable, dropped:[{path, side, line, base_region}], "
            "checked_files}. log=True (default) appends a telemetry row to merge-loss-detector.ndjson and "
            "files an auto-improvement finding when lines were dropped; log=False is a pure read. "
            "Pass worktree_path from inside a worktree. KB § PATTERNS/common/auto-generated-merge-drivers.md."
        ),
    )
    def _merge_loss_check(merge_sha: str | None = None, worktree_path: str | None = None,
                          log: bool = True) -> dict:
        return merge_loss_check(merge_sha=merge_sha, worktree_path=worktree_path, log=log)


__all__ = ["merge_loss_check", "register"]
