"""noctus.dev.harness_status / noctus.dev.harness_event — back-ends of the
`noc-harness` Claude Code mod (status line, reminders band, orchestration pane,
friction ledger).

MCP-first: the mod is a thin TS shell that shells out to ``cli.py
--harness-status`` / ``--harness-event``; ALL logic lives here and composes
existing mechanisms (auto_improvement, branch_pointer, refresh_all_caches
detect_stale_caches, memory dir resolver, git worktree porcelain) — nothing is
re-implemented.

``harness_status`` contract: schema ``noc.harness_status/v1``. It NEVER raises
and NEVER fetches: a failing section lands in ``errors`` (no silent errors) and
the section value degrades to ``null`` / empty. Fast mode (after every turn)
reads refs only; full mode adds caches / auto-improvement / pointers /
worktrees / dispatcher.

``harness_event`` records a friction event as an s1 auto-improvement entry via
the EXISTING ``auto_improvement.log_entry`` (same ledger as
``noctus.dev.auto_improvement_log``).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA = "noc.harness_status/v1"
SHARED_BRANCHES = frozenset({"dev", "main", "prod"})
EVENT_KINDS = frozenset({
    "gate_denied", "gate_timeout", "guard_error", "harness_invalid",
    "compaction_capture", "note",
})
_FULL_KEYS = ("caches", "auto_improvement", "branch_pointers", "worktrees", "dispatcher_pending")
_GIT_TIMEOUT = 20


def _git(args: list[str], cwd: str | Path) -> tuple[int, str]:
    r = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )
    return r.returncode, (r.stdout or "").strip()


def _git_ok(args: list[str], cwd: str | Path) -> str:
    rc, out = _git(args, cwd)
    if rc != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (rc={rc})")
    return out


def _primary_root(cwd: str | Path) -> Path:
    """The primary checkout: first entry of `git worktree list` (the common dir's owner)."""
    out = _git_ok(["worktree", "list", "--porcelain"], cwd)
    for line in out.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):]).resolve()
    raise RuntimeError("no worktree entries from git")


def _count(args: list[str], cwd: str | Path) -> int:
    return int(_git_ok(["rev-list", "--count", *args], cwd))


def _dirty(cwd: str | Path, *, untracked: bool = True) -> int:
    """Porcelain line count. ``untracked=False`` (-uno) is ~3x cheaper; the
    worktree pane uses it (tracked/staged changes only) to hold the full-mode
    budget across ~35 worktrees, the session tree keeps untracked files."""
    out = _git_ok(["status", "--porcelain"] + ([] if untracked else ["-uno"]), cwd)
    return len(out.splitlines()) if out else 0


# ── sections ──────────────────────────────────────────────────────────────────
def _section_session(cwd: Path, primary: Path) -> dict:
    cwd = cwd.resolve()
    s: dict[str, Any] = {"cwd": str(cwd), "tree": "outside", "worktree_slug": None,
                         "branch": None, "is_shared_branch": False, "dirty": 0}
    rc, top = _git(["rev-parse", "--show-toplevel"], cwd)
    if rc != 0 or not top:
        return s
    top_p = Path(top).resolve()
    if top_p == primary:
        s["tree"] = "primary"
    else:
        s["tree"] = "worktree"
        s["worktree_slug"] = top_p.name
    rc, br = _git(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
    s["branch"] = br if rc == 0 and br else None
    s["is_shared_branch"] = s["branch"] in SHARED_BRANCHES
    s["dirty"] = _dirty(cwd)
    return s


def _section_dev(primary: Path) -> dict:
    left, right = _git_ok(["rev-list", "--left-right", "--count", "dev...origin/dev"], primary).split()
    return {
        "local_ahead": int(left),
        "local_behind": int(right),
        "dev_ahead_of_main": _count(["origin/main..origin/dev"], primary),
    }


_REMINDER_RE = re.compile(r"^\s*-\s*\[(?P<title>[^\]]+)\]\((?P<file>[^)]+)\)")


def parse_reminders(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = _REMINDER_RE.match(line)
        if m:
            out.append({"title": m.group("title").strip(), "file": m.group("file").strip()})
    return out


def _section_reminders(memory_dir: Path | None) -> list[dict]:
    if memory_dir is None:
        from tools.noctus.dev.memory_embeddings import _resolve_memory_dir
        memory_dir = _resolve_memory_dir()
    if memory_dir is None:
        raise RuntimeError("agent memory dir not found (set NOCTUS_AGENT_MEMORY_DIR)")
    f = Path(memory_dir) / "MEMORY-reminders.md"
    if not f.is_file():
        raise RuntimeError(f"{f} not found")
    return parse_reminders(f.read_text(encoding="utf-8"))


# noc-graph's freshness keeper walks every file of the tree incl. nested
# .claude/worktrees (~40 s on a primary with many worktrees) — far past the
# full-mode budget. Skipped LOUDLY (errors[] entry), never silently.
_SLOW_CACHES = frozenset({"noc-graph"})


def _section_caches(root: Path, errors: list[dict]) -> dict:
    from tools.noctus.dev import refresh_all_caches as rac
    stale = rac.detect_stale_caches(repo_root=root, skip=_SLOW_CACHES)
    errors.append({"section": "caches.noc-graph",
                   "error": "skipped: freshness keeper too slow for the poll budget (run noctus.dev.detect_stale_caches)"})
    return {"stale": list(stale), "total": len(rac._ALL_CACHES) - len(_SLOW_CACHES)}


def _section_auto_improvement() -> dict:
    from tools.noctus.dev import auto_improvement as ai
    rows = ai.query(open_only=True, limit=500)
    top = [{"target": r.get("target"), "stage": r.get("status"),
            "summary": (r.get("description") or "")[:160]} for r in rows[:5]]
    return {
        "open_s1": sum(1 for r in rows if r.get("status") == "s1-emergent"),
        "open_s2": sum(1 for r in rows if r.get("status") == "s2-memory"),
        "top": top,
    }


def _section_pointers() -> list[dict]:
    from tools.noctus.dev import branch_pointer as bp
    out = []
    for r in bp.list_pointers(from_dev=True):
        out.append({
            "branch": r.get("branch"), "agent": r.get("agent"), "role": r.get("role"),
            "status": r.get("status"), "brief": r.get("brief"), "worktree": r.get("worktree"),
            "paths": r.get("paths", []), "updated_at": r.get("ts"),
        })
    return out


def _worktree_row(wt: dict, primary: Path) -> dict:
    path = wt["path"]
    rc, ahead = _git(["rev-list", "--count", "origin/dev..HEAD"], path)
    return {
        "slug": Path(path).name, "path": path, "branch": wt.get("branch"),
        "head": wt.get("head", "")[:9], "dirty": _dirty(path, untracked=False),
        "ahead_of_dev": int(ahead) if rc == 0 and ahead.isdigit() else 0,
    }


def _section_worktrees(primary: Path) -> list[dict]:
    out = _git_ok(["worktree", "list", "--porcelain"], primary)
    wts: list[dict] = []
    cur: dict = {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                wts.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[9:]
        elif line.startswith("HEAD "):
            cur["head"] = line[5:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].removeprefix("refs/heads/")
    wt_root = str(primary / ".claude" / "worktrees")
    mine = [w for w in wts if w.get("path", "").startswith(wt_root + "/")]
    with ThreadPoolExecutor(max_workers=16) as ex:
        return list(ex.map(lambda w: _worktree_row(w, primary), mine))


def _section_dispatcher(primary: Path) -> int:
    f = primary / ".claude" / "dispatcher.md"
    if not f.is_file():
        return 0
    n, in_pending = 0, False
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_pending = line[3:].strip().lower() == "pending"
            continue
        if in_pending and re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line):
            n += 1
    return n


# ── public API ────────────────────────────────────────────────────────────────
def harness_status(
    *, full: bool = False, cwd: str | None = None, repo_root: str | Path | None = None,
    memory_dir: Path | None = None,
    section_overrides: dict[str, Callable[[], Any]] | None = None,
) -> dict:
    """Build the ``noc.harness_status/v1`` object. Never raises.

    ``section_overrides`` is a DI seam (name -> zero-arg callable) so tests and
    callers can substitute a section provider; production passes nothing.
    """
    ov = section_overrides or {}
    errors: list[dict] = []
    cwd_p = Path(cwd or ".").expanduser().resolve()
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "full" if full else "fast",
        "repo_root": None,
        "session": {"cwd": str(cwd_p), "tree": "outside", "worktree_slug": None,
                    "branch": None, "is_shared_branch": False, "dirty": 0},
        "dev": {"local_ahead": 0, "local_behind": 0, "dev_ahead_of_main": 0},
        "reminders": [],
    }
    for k in _FULL_KEYS:
        out[k] = None

    def run(name: str, fn: Callable[[], Any], default: Any = None) -> Any:
        try:
            return ov[name]() if name in ov else fn()
        except Exception as exc:  # noqa: BLE001 — surfaced in errors[], never dropped
            errors.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
            return default

    start = Path(repo_root) if repo_root else cwd_p
    primary: Path | None = run("repo_root", lambda: _primary_root(start))
    out["repo_root"] = str(primary) if primary else None
    if primary is not None:
        out["session"] = run("session", lambda: _section_session(cwd_p, primary), out["session"])
        out["dev"] = run("dev", lambda: _section_dev(primary), out["dev"])
    out["reminders"] = run("reminders", lambda: _section_reminders(memory_dir), [])
    tree_root = Path(out["session"].get("cwd") or primary or ".")
    rc, top = _git(["rev-parse", "--show-toplevel"], tree_root) if primary else (1, "")
    tree_root = Path(top) if rc == 0 and top else (primary or tree_root)
    if full and primary is not None:
        out["caches"] = run("caches", lambda: _section_caches(tree_root, errors))
        out["auto_improvement"] = run("auto_improvement", _section_auto_improvement)
        out["branch_pointers"] = run("branch_pointers", _section_pointers)
        out["worktrees"] = run("worktrees", lambda: _section_worktrees(primary))
        out["dispatcher_pending"] = run("dispatcher_pending", lambda: _section_dispatcher(primary))
    out["errors"] = errors
    return out


def harness_event(payload: Any) -> dict:
    """Record one friction event as an s1 auto-improvement entry."""
    if not isinstance(payload, dict):
        return {"status": "error", "error": "payload must be a JSON object"}
    kind = payload.get("kind")
    if kind not in EVENT_KINDS:
        return {"status": "error",
                "error": f"kind must be one of {sorted(EVENT_KINDS)}; got {kind!r}"}
    for req in ("target", "summary"):
        if not isinstance(payload.get(req), str) or not payload[req].strip():
            return {"status": "error", "error": f"{req} is required (non-empty string)"}
    source = payload.get("source") or "noc-harness-mod"
    desc = f"[{kind}] {payload['summary'].strip()}"
    if payload.get("detail"):
        desc += f"\n\n{payload['detail']}"
    from tools.noctus.dev import auto_improvement as ai
    try:
        r = ai.log_entry(
            scope="scoped",
            kind="improvement" if kind in ("note", "compaction_capture") else "drift",
            target=payload["target"], description=desc, agent=source,
            status="s1-emergent",
            source_ref=(f"session:{payload['session_id']}" if payload.get("session_id") else source),
        )
    except Exception as exc:  # noqa: BLE001 — reported, exit 1 by the CLI
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    if not r.get("ok"):
        return {"status": "error", "error": r.get("error", "auto_improvement.log_entry refused")}
    e = r["entry"]
    eid = hashlib.sha1(f"{e['ts']}|{e['target']}|{desc}".encode()).hexdigest()[:12]
    # log_entry publishes to the orphan origin/ledgers branch (or spools on
    # failure) — report what actually happened, not the legacy dev-copy path.
    pub = r.get("publish") or {}
    published = bool(pub.get("ok"))
    return {"status": "logged", "id": eid, "ts": e["ts"],
            "published_to": "origin/ledgers" if published else None,
            "spooled": not published}


# ── panels (noc.harness_panel/v1) ────────────────────────────────────────────
PANEL_SCHEMA = "noc.harness_panel/v1"
PANELS = ("vectors", "baselines", "codify", "gates")
_TONES = frozenset({"ok", "warn", "bad", "info"})


def _row(label: str, value: Any, tone: str = "info") -> dict:
    return {"label": label, "value": str(value), "tone": tone if tone in _TONES else "info"}


def _panel_vectors() -> list[dict]:
    from tools.noctus.dev import vector_costs, vectorize
    st = vectorize.vector_status()
    emb, sto = st.get("embedding") or {}, st.get("storage") or {}
    cost = vector_costs.total()
    stack = [
        _row("provider", emb.get("provider") or "unconfigured", "info" if emb.get("provider") else "warn"),
        _row("model", emb.get("model") or "-"),
        _row("engine", sto.get("engine_active", "?"), "ok" if sto.get("sqlite_vec_available") else "warn"),
    ]
    caches = [_row(c.get("name", "?"), f"{c.get('rows')} rows", "ok" if c.get("rows") else "warn")
              for c in st.get("caches", [])]
    costs = [
        _row("batches", cost.get("batch_count", 0)),
        _row("chunks", cost.get("chunk_count", 0)),
        _row("lifetime est. USD", f"{cost.get('estimated_cost_usd', 0):.4f}"),
        _row("lifetime actual USD", f"{cost.get('actual_cost_usd', 0):.4f}"),
        _row("last refresh", cost.get("last_ts") or "never"),
    ]
    return [{"heading": "Embedding stack", "rows": stack},
            {"heading": "Caches", "rows": caches}, {"heading": "Cost ledger", "rows": costs}]


_PANEL_BUDGET_S = 8.0


def _within_budget(fn: Callable[[], Any], budget: float = _PANEL_BUDGET_S) -> Any:
    """Run ``fn`` on a daemon thread; raise TimeoutError past ``budget`` seconds
    (the slow call is abandoned, the CLI exits via os._exit - see cli.py)."""
    import threading
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["v"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            box["e"] = exc
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(budget)
    if t.is_alive():
        raise TimeoutError(f"exceeded the {budget:.0f}s panel budget (run the underlying MCP tool directly)")
    if "e" in box:
        raise box["e"]
    return box["v"]


def _baseline_rows(d: dict, new_key: str, res_key: str, drift_key: str) -> list[dict]:
    if not d.get("ok", True):
        raise RuntimeError(d.get("error", "baseline diff failed"))
    new = len(d.get(new_key, []))
    rows = [_row("baseline", d.get("baseline_id") or "none ratified", "info" if d.get("baseline_id") else "warn"),
            _row("new (review)", new, "warn" if new else "ok"),
            _row("resolved", len(d.get(res_key, []))),
            _row("unchanged", d.get("unchanged_count", 0))]
    if d.get(drift_key):
        rows.append(_row("corpus drifted", "yes - resolved may be artifacts", "warn"))
    return rows


def _panel_baselines(errors: list[dict]) -> list[dict]:
    from tools.noctus.dev import code_baseline, kb_baseline
    specs = (
        ("KB baseline", kb_baseline.diff, ("new_findings", "resolved_findings", "kb_corpus_drifted")),
        ("Code recurrence baseline", code_baseline.diff, ("new_matches", "resolved_matches", "code_corpus_drifted")),
    )
    # Run concurrently so the panel stays inside ONE budget, not one per section.
    with ThreadPoolExecutor(max_workers=len(specs), thread_name_prefix="panel") as ex:
        futs = [(h, ex.submit(_within_budget, fn), k) for h, fn, k in specs]
        secs = []
        for heading, fut, keys in futs:
            try:
                secs.append({"heading": heading, "rows": _baseline_rows(fut.result(), *keys)})
            except Exception as exc:  # noqa: BLE001
                errors.append({"section": heading, "error": f"{type(exc).__name__}: {exc}"})
    return secs


def _panel_codify() -> list[dict]:
    from tools.noctus.dev import codification_radar
    r = _within_budget(lambda: codification_radar.cluster(threshold=0.75, limit=50))
    if not r.get("ok"):
        raise RuntimeError(r.get("error", "radar failed"))
    rows = []
    for c in r.get("clusters", [])[:8]:
        tgt = (c.get("entries") or [{}])[0].get("target", "?")
        rows.append(_row(f"{c.get('suggested_status_next')} x{c.get('size')}",
                         f"{tgt} (cohesion {c.get('avg_score', 0):.2f})", "warn"))
    if not rows:
        rows = [_row("candidates", f"none among {r.get('total_entries', 0)} open entries", "ok")]
    return [{"heading": "Promotion candidates", "rows": rows}]


_PROBE_TIMEOUT = 8


def declared_guards(settings_path: Path) -> list[dict]:
    """PreToolUse/PostToolUse hook commands wired in settings.json (derived)."""
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    out = []
    for event in ("PreToolUse", "PostToolUse"):
        for grp in (data.get("hooks") or {}).get(event, []):
            for h in grp.get("hooks", []):
                m = re.search(r'(scripts/hooks/[\w.\-]+\.py)', h.get("command", ""))
                if m:
                    out.append({"event": event, "matcher": grp.get("matcher", ""), "script": m.group(1),
                                "name": Path(m.group(1)).stem})
    return out


def probe_guard(root: Path, script: str, *, timeout: int = _PROBE_TIMEOUT) -> dict:
    """Run one hook once with a harmless synthetic Read payload."""
    import time
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/dev/null"},
                          "cwd": str(root), "session_id": "harness-probe", "hook_event_name": "PreToolUse"})
    env_extra = {"CLAUDE_PROJECT_DIR": str(root)}
    import os
    t0 = time.monotonic()
    try:
        r = subprocess.run(["python3", str(root / script)], input=payload, capture_output=True,
                           text=True, timeout=timeout, cwd=str(root), env={**os.environ, **env_extra})
    except subprocess.TimeoutExpired:
        return {"verdict": "crash", "detail": f"timeout>{timeout}s", "ms": int((time.monotonic() - t0) * 1000)}
    ms = int((time.monotonic() - t0) * 1000)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 2 or '"permissionDecision": "deny"' in out or '"permissionDecision":"deny"' in out:
        return {"verdict": "deny", "detail": "denied the synthetic Read", "ms": ms}
    if r.returncode != 0 or "Traceback" in out:
        return {"verdict": "crash", "detail": (out.strip().splitlines() or [f"rc={r.returncode}"])[-1][:120], "ms": ms}
    return {"verdict": "allow", "detail": "", "ms": ms}


def count_guard_refusals(rows: list[dict]) -> dict[str, int]:
    """Count `[noc-guard:<name>]` / gate_denied refusals in harness-sourced entries."""
    counts: dict[str, int] = {}
    for r in rows:
        if r.get("agent") != "noc-harness-mod":
            continue
        desc = r.get("description") or ""
        m = re.search(r"\[noc-guard:([\w\-]+)\]", desc)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        elif desc.startswith("[gate_denied]"):
            counts["(unattributed)"] = counts.get("(unattributed)", 0) + 1
    return counts


def _panel_gates(root: Path, errors: list[dict]) -> list[dict]:
    guards = declared_guards(root / ".claude" / "settings.json")
    uniq = list({g["script"]: g for g in guards}.values())
    with ThreadPoolExecutor(max_workers=6) as ex:
        probes = list(ex.map(lambda g: probe_guard(root, g["script"]), uniq))
    rows = []
    for g, p in zip(uniq, probes):
        tone = {"allow": "ok", "deny": "warn", "crash": "bad"}[p["verdict"]]
        rows.append(_row(f"{g['name']} [{g['event']} {g['matcher']}]",
                         f"{p['verdict']} {p['ms']}ms" + (f" - {p['detail']}" if p["detail"] else ""), tone))
    secs = [{"heading": "Wired guards (probe: synthetic Read)", "rows": rows or [_row("guards", "none wired", "warn")]}]
    try:
        from tools.noctus.dev import auto_improvement as ai
        counts = count_guard_refusals(ai.query(agent="noc-harness-mod", limit=500))
        secs.append({"heading": "Recent refusals (auto-improvement ledger)",
                     "rows": [_row(k, v, "warn") for k, v in sorted(counts.items())]
                     or [_row("refusals", "none recorded", "ok")]})
    except Exception as exc:  # noqa: BLE001
        errors.append({"section": "refusals", "error": f"{type(exc).__name__}: {exc}"})
    return secs


_PANEL_TITLES = {"vectors": "Vector platform", "baselines": "Baselines",
                 "codify": "Codification radar", "gates": "Guards"}


def harness_panel(name: str, *, repo_root: str | Path | None = None,
                  section_overrides: dict[str, Callable[[], Any]] | None = None) -> dict:
    """Build a ``noc.harness_panel/v1`` object. Never raises; unknown panel ⇒ status error."""
    ov = section_overrides or {}
    out: dict[str, Any] = {"schema": PANEL_SCHEMA, "panel": name,
                           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "title": _PANEL_TITLES.get(name, name), "sections": [], "errors": []}
    if name not in PANELS:
        out["status"] = "error"
        out["errors"].append({"section": "panel", "error": f"unknown panel {name!r}; one of {list(PANELS)}"})
        return out
    errors = out["errors"]
    try:
        if name in ov:
            out["sections"] = ov[name]()
        else:
            root = Path(repo_root) if repo_root else _primary_root(Path.cwd())
            if name == "vectors":
                out["sections"] = _panel_vectors()
            elif name == "baselines":
                out["sections"] = _panel_baselines(errors)
            elif name == "codify":
                out["sections"] = _panel_codify()
            else:
                out["sections"] = _panel_gates(root, errors)
    except Exception as exc:  # noqa: BLE001 — surfaced, never silent
        errors.append({"section": name, "error": f"{type(exc).__name__}: {exc}"})
    out["status"] = "ok"
    return out


# ── route (noc.harness_route/v1) ─────────────────────────────────────────────
ROUTE_SCHEMA = "noc.harness_route/v1"
_PTR_RE = re.compile(r"\(([^)\s]+\.md)\)")
_TOPIC_TITLE_RE = re.compile(r"^#\s*(.+)$", re.M)


def _topic_index(memory_dir: Path) -> dict[str, tuple[str, str]]:
    """memory file basename -> (MEMORY-<topic>.md, title), derived from pointer lines."""
    idx: dict[str, tuple[str, str]] = {}
    for tf in sorted(memory_dir.glob("MEMORY-*.md")):
        text = tf.read_text(encoding="utf-8")
        m = _TOPIC_TITLE_RE.search(text)
        title = m.group(1).strip() if m else tf.stem
        for ptr in _PTR_RE.findall(text):
            idx.setdefault(Path(ptr).name, (tf.name, title))
    return idx


def harness_route(payload: Any, *, memory_dir: Path | None = None,
                  search_fn: Callable[..., list[dict]] | None = None, top_k: int = 12) -> dict:
    """Map a prompt to the MEMORY-<topic>.md files most likely relevant (semantic)."""
    out: dict[str, Any] = {"schema": ROUTE_SCHEMA, "topics": [], "errors": []}
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        out["errors"].append({"section": "input", "error": "prompt is required (non-empty string)"})
        return out
    try:
        if memory_dir is None:
            from tools.noctus.dev.memory_embeddings import _resolve_memory_dir
            memory_dir = _resolve_memory_dir()
        if memory_dir is None:
            raise RuntimeError("agent memory dir not found (set NOCTUS_AGENT_MEMORY_DIR)")
        if search_fn is None:
            from tools.noctus.dev.memory_embeddings import search as search_fn
        hits = search_fn(prompt, top_k=top_k)
        if not hits:
            out["errors"].append({"section": "semantic",
                                  "error": "no hits (embedding provider unavailable, e.g. 429, or nothing relevant)"})
            return out
        idx = _topic_index(Path(memory_dir))
        best: dict[str, dict] = {}
        for h in hits:
            hit = idx.get(Path(str(h.get("path", ""))).name)
            if not hit:
                continue
            file, title = hit
            sc = float(h.get("score", 0))
            if file not in best or sc > best[file]["score"]:
                best[file] = {"file": file, "title": title, "score": round(sc, 4), "via": "semantic"}
        out["topics"] = sorted(best.values(), key=lambda t: -t["score"])
    except Exception as exc:  # noqa: BLE001
        out["errors"].append({"section": "semantic", "error": f"{type(exc).__name__}: {exc}"})
    return out


def register(server) -> None:
    @server.tool(
        name="noctus.dev.harness_status",
        description=(
            "Status snapshot for the noc-harness Claude Code mod (schema noc.harness_status/v1): "
            "session tree/branch/dirty, local-dev vs origin/dev vs origin/main drift (refs only, "
            "no fetch), open owner reminders; full=True adds stale caches, open auto-improvement, "
            "live branch pointers, worktrees, dispatcher pending. Never raises — section failures "
            "go in `errors`. Read-only."
        ),
    )
    def _status(full: bool = False, cwd: str | None = None) -> dict:
        return harness_status(full=full, cwd=cwd)

    @server.tool(
        name="noctus.dev.harness_event",
        description=(
            "Record a noc-harness friction event (kind ∈ gate_denied|gate_timeout|guard_error|"
            "harness_invalid|compaction_capture|note; target; summary; detail?; session_id?) as an "
            "s1 auto-improvement entry via the existing auto_improvement ledger."
        ),
    )
    def _event(kind: str, target: str, summary: str, detail: str | None = None,
               session_id: str | None = None, source: str = "noc-harness-mod") -> dict:
        return harness_event({"kind": kind, "target": target, "summary": summary,
                              "detail": detail, "session_id": session_id, "source": source})

    @server.tool(
        name="noctus.dev.harness_panel",
        description=(
            "Generic render panel for the noc-harness mod (schema noc.harness_panel/v1). "
            "name ∈ vectors|baselines|codify|gates: vector platform status+cost, KB/code baseline "
            "diffs, codification-radar candidates, wired PreToolUse guards with a per-guard probe. "
            "Never raises; failures land in `errors`. Read-only."
        ),
    )
    def _panel(name: str) -> dict:
        return harness_panel(name)

    @server.tool(
        name="noctus.dev.harness_route",
        description=(
            "Route a prompt to the MEMORY-<topic>.md files most relevant to it (schema "
            "noc.harness_route/v1) via the existing semantic memory_search. Provider failures "
            "go in `errors`. Read-only."
        ),
    )
    def _route(prompt: str) -> dict:
        return harness_route({"prompt": prompt})
