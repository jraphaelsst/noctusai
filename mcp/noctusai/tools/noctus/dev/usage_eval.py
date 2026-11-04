"""noctus.dev.usage_eval — measure how our development work uses Claude and the machine.

WHY (owner, 2026-11-04): "measure work now until then and from then on … seed this as a frequent
workflow/pattern/evaluation so we keep track as how our usage is going, say it per cost, machine usage,
tokens, chars and everything that's essential for a job" + "keep track of os data so we can keep track
and measure and decide on usage". First use: the hardware-admission slot trial (window A = build phase,
window B = loosened slot) — but the evaluation is general: any two windows, any time.

SOURCES (read-only, machine-local)
- Claude Code transcripts ``~/.claude/projects/<project>/<session>.jsonl`` and
  ``<session>/subagents/agent-<id>.jsonl``. One API request appears as several JSONL entries (one per
  content block) carrying the SAME ``message.id`` and the same ``usage`` — usage is counted ONCE per
  message id; chars and tool calls are summed over its blocks.
- The hardware-admission log ``~/.noctus/hw-admission.ndjson`` (owned by ``noctus.dev.hw_admission``):
  ``sample`` rows (OS: CPU idle, reclaimable MB, swap-out, load, claude sessions, overloaded) and
  ``ran`` / ``not_admitted`` rows (heavy jobs, ``<kind>:<target>``).

COST = API-list-price equivalent from the seed rate card (``noctusai_lib.integrations.llm.usage.price_usage``).
Claude Code runs on a subscription, so this is the comparable unit, not an invoice.
NOC-REMEDIATE[anthropic-cache-ttl-pricing]: the seed prices every cache write at one multiplier; 1-hour
cache writes cost more than 5-minute ones, so cache-write cost here is a lower bound.

SINK: Supabase ``public.dev_telemetry_{claude,os,jobs,marks}`` (core migration 097), idempotent upserts,
read directly by the usage dashboard. Never ``public.ai_usage`` (product ledger, credit-charged).
No prompt/response text leaves the machine — counts only.

KB § PATTERNS/devops/usage-evaluation.md
"""
from __future__ import annotations

import json
import os
import socket
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

BUCKET_MIN = 5
_CLAUDE_ROOT = Path.home() / ".claude" / "projects"
_HW_LOG = Path(os.environ.get("NOCTUS_HW_LOG") or Path.home() / ".noctus" / "hw-admission.ndjson")


# ── time helpers ──────────────────────────────────────────────────────────

def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def bucket_of(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return dt.replace(minute=dt.minute - dt.minute % BUCKET_MIN, second=0, microsecond=0)


def host() -> str:
    return socket.gethostname().split(".")[0].lower()


def _in(dt: datetime | None, since: datetime, until: datetime) -> bool:
    return dt is not None and since <= dt < until


# ── Claude transcripts ────────────────────────────────────────────────────

_COUNTERS = ("requests", "input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens",
             "cache_write_tokens", "prompt_chars", "output_chars", "tool_result_chars", "tool_calls")


@dataclass
class ClaudeRow:
    """One (bucket, session, agent, model) aggregate — the ``dev_telemetry_claude`` row shape."""
    bucket: datetime
    session_id: str
    agent_id: str
    project: str
    model: str
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_COUNTERS, 0))
    cost_usd: float = 0.0
    price_version: str = "unpriced"


def _block_chars(block: Any) -> int:
    if isinstance(block, str):
        return len(block)
    if not isinstance(block, dict):
        return 0
    kind = block.get("type")
    if kind == "text":
        return len(block.get("text") or "")
    if kind == "thinking":
        return len(block.get("thinking") or "")
    if kind == "tool_use":
        return len(json.dumps(block.get("input") or {}, ensure_ascii=False))
    if kind == "tool_result":
        content = block.get("content")
        if isinstance(content, list):
            return sum(_block_chars(c) for c in content)
        return len(content or "") if isinstance(content, str) else 0
    return 0


def transcript_files(root: Path, since: datetime) -> Iterator[tuple[Path, str]]:
    """Every transcript modified at/after ``since`` (older files cannot hold in-window rows)."""
    cutoff = since.timestamp()
    if not root.exists():
        return
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in project.glob("*.jsonl"):
            if f.stat().st_mtime >= cutoff:
                yield f, project.name
        for f in project.glob("*/subagents/agent-*.jsonl"):
            if f.stat().st_mtime >= cutoff:
                yield f, project.name


def _price(model: str, u: dict[str, int]) -> tuple[float, str]:
    try:
        from noctusai_lib.integrations.llm.usage import price_usage
    except ImportError as exc:  # never silent: the row is kept, priced as unpriced, and the reason surfaces
        return 0.0, f"unpriced:no-seed-lib:{type(exc).__name__}"
    return price_usage(
        provider="anthropic", model=model, prompt_tokens=u["input_tokens"],
        completion_tokens=u["output_tokens"], cache_read_input_tokens=u["cache_read_tokens"],
        cache_creation_input_tokens=u["cache_write_tokens"],
    )


def _model_of(line: str) -> str | None:
    """The answering model of an assistant entry with usage (cheap pre-check before a full parse)."""
    if '"usage"' not in line or '"assistant"' not in line:
        return None
    try:
        msg = json.loads(line).get("message") or {}
    except json.JSONDecodeError:
        return None
    model = msg.get("model") if isinstance(msg, dict) else None
    return model if model and model != "<synthetic>" else None


def scan_claude(since: datetime, until: datetime, root: Path = _CLAUDE_ROOT) -> list[ClaudeRow]:
    rows: dict[tuple, ClaudeRow] = {}
    last_model: dict[tuple[str, str], str] = {}
    for path, project in transcript_files(root, since):
        agent_id = path.stem.removeprefix("agent-") if path.parent.name == "subagents" else ""
        seen: set[str] = set()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:  # unreadable transcript: surfaced, never silently dropped
            import logging
            logging.getLogger(__name__).warning("usage_eval: cannot read %s (%s)", path, type(exc).__name__)
            continue
        # A prompt typed before the session's first answer belongs to the model that answers it.
        first_model = next((m for m in (_model_of(ln) for ln in lines) if m), "unknown")
        for line in lines:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(d.get("timestamp"))
            if not _in(ts, since, until):
                continue
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}
            session = d.get("sessionId") or path.stem
            kind = d.get("type")
            if kind == "assistant" and msg.get("usage"):
                model = msg.get("model") or "unknown"
                if model == "<synthetic>":
                    continue
                last_model[(session, agent_id)] = model
                key = (bucket_of(ts), session, agent_id, model)
                row = rows.get(key) or rows.setdefault(key, ClaudeRow(key[0], session, agent_id, project, model))
                c = row.counts
                for block in msg.get("content") or []:
                    c["output_chars"] += _block_chars(block)
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        c["tool_calls"] += 1
                mid = msg.get("id") or d.get("uuid")
                if mid in seen:
                    continue
                seen.add(mid)
                u = msg["usage"]
                c["requests"] += 1
                c["input_tokens"] += int(u.get("input_tokens") or 0)
                c["output_tokens"] += int(u.get("output_tokens") or 0)
                c["thinking_tokens"] += int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
                c["cache_read_tokens"] += int(u.get("cache_read_input_tokens") or 0)
                c["cache_write_tokens"] += int(u.get("cache_creation_input_tokens") or 0)
            elif kind == "user" and not d.get("isMeta"):
                content = msg.get("content")
                if content is None:
                    continue
                # attribute user-side chars to the model the session last answered with
                model = last_model.get((session, agent_id), first_model)
                key = (bucket_of(ts), session, agent_id, model)
                row = rows.get(key) or rows.setdefault(key, ClaudeRow(key[0], session, agent_id, project, model))
                if isinstance(content, str):
                    row.counts["prompt_chars"] += len(content)
                else:
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            row.counts["tool_result_chars"] += _block_chars(block)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            row.counts["prompt_chars"] += _block_chars(block)
    for row in rows.values():
        if row.model != "unknown":
            row.cost_usd, row.price_version = _price(row.model, row.counts)
    return sorted(rows.values(), key=lambda r: (r.bucket, r.session_id, r.agent_id, r.model))


# ── hardware-admission log (OS samples + heavy jobs) ─────────────────────

def scan_hw(since: datetime, until: datetime, path: Path = _HW_LOG) -> tuple[list[dict], list[dict]]:
    """``(os_samples, jobs)`` from the admission log; a missing log returns empty lists (the report says so)."""
    samples: list[dict] = []
    jobs: list[dict] = []
    if not path.exists():
        return samples, jobs
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(d.get("ts"))
            if not _in(ts, since, until):
                continue
            m = d.get("metrics") or {}
            if d.get("event") == "sample":
                samples.append({
                    "host": d.get("host") or host(), "ts": ts.isoformat(), "phase": d.get("phase"),
                    "overloaded": d.get("overloaded"), "busy_slots": d.get("busy_slots"),
                    "cpu_idle_pct": m.get("cpu_idle_pct"), "reclaimable_mb": m.get("reclaimable_mb"),
                    "swapout_per_s": m.get("swapout_per_s"), "load_1m": m.get("load_1m"),
                    "cpu_cores": m.get("cpu_cores"), "claude_sessions": m.get("claude_sessions"),
                    # probe_version (hw_admission sampler): v2 divides swap-out by the MEASURED interval
                    # (metrics.elapsed_s) and adds swapout_mb_per_s; v1 (absent) divided by the nominal sample_s, so its
                    # swap-out is an inflated UPPER BOUND under load. Kept in extra so 097 needs no column.
                    "extra": {"probe_version": int(d.get("probe_version") or 1),
                              **{k: v for k, v in m.items() if k not in {
                                  "cpu_idle_pct", "reclaimable_mb", "swapout_per_s", "load_1m", "cpu_cores",
                                  "claude_sessions"}}},
                })
            elif d.get("event") in ("ran", "not_admitted"):
                job = str(d.get("job") or "unknown")
                kind, _, target = job.partition(":")
                # hw_admission nests the result: outcome.{exit_code, timed_out, harness_suspect}. A timeout or a
                # harness-suspect red under load is the false-red signal, so it is kept apart from exit_code.
                out = d.get("outcome") or {}
                jobs.append({
                    "host": d.get("host") or host(), "ts": ts.isoformat(), "job": job, "kind": kind,
                    "target": target or "", "event": d["event"], "phase": d.get("phase"),
                    "admitted": d.get("admitted"), "waited_s": d.get("waited_s"),
                    "duration_s": d.get("duration_s"), "children_peak_rss_mb": d.get("children_peak_rss_mb"),
                    "exit_code": out.get("exit_code"),
                    # job_workers (hw_admission a58b88666): the per-job fan-out cap. Absent = the writing process
                    # predates the field → "unknown"; null = the job has no fan-out cap → "none". Never conflated.
                    "metrics": {**m, "outcome": {"timed_out": bool(out.get("timed_out")),
                                                 "harness_suspect": bool(out.get("harness_suspect"))},
                                "job_workers": _workers_key(d)},
                })
    return samples, jobs


# ── window report + comparison ───────────────────────────────────────────

def _workers_key(row: dict) -> str:
    if "job_workers" not in row:
        return "unknown"
    return "none" if row["job_workers"] is None else str(int(row["job_workers"]))


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def window_report(since: datetime, until: datetime, *, claude_root: Path = _CLAUDE_ROOT,
                  hw_log: Path = _HW_LOG) -> dict[str, Any]:
    hours = max((until - since).total_seconds() / 3600.0, 1e-9)
    claude = scan_claude(since, until, claude_root)
    samples, jobs = scan_hw(since, until, hw_log)
    tot = dict.fromkeys(_COUNTERS, 0)
    cost = 0.0
    sessions: dict[str, dict[str, Any]] = defaultdict(lambda: {"cost_usd": 0.0, "requests": 0, "output_tokens": 0})
    unpriced = set()
    for r in claude:
        for k in _COUNTERS:
            tot[k] += r.counts[k]
        cost += r.cost_usd
        s = sessions[r.session_id[:8] + (f"/{r.agent_id[:8]}" if r.agent_id else "")]
        s["cost_usd"] += r.cost_usd
        s["requests"] += r.counts["requests"]
        s["output_tokens"] += r.counts["output_tokens"]
        if r.price_version.startswith("unpriced") and r.counts["requests"]:
            unpriced.add(r.model)
    ran = [j for j in jobs if j["event"] == "ran"]
    num = lambda rows, k: [float(x[k]) for x in rows if x.get(k) is not None]  # noqa: E731
    top = sorted(sessions.items(), key=lambda kv: -kv[1]["cost_usd"])[:10]
    v1 = [s for s in samples if s["extra"]["probe_version"] < 2]
    v2 = [s for s in samples if s["extra"]["probe_version"] >= 2]
    return {
        "window": {"since": since.isoformat(), "until": until.isoformat(), "hours": round(hours, 3)},
        "claude": {
            **tot, "cost_usd": round(cost, 4), "cost_usd_per_h": round(cost / hours, 4),
            "output_tokens_per_h": round(tot["output_tokens"] / hours), "requests_per_h": round(tot["requests"] / hours, 1),
            "sessions_active": len({r.session_id for r in claude if r.counts["requests"]}),
            "agents_active": len({(r.session_id, r.agent_id) for r in claude if r.agent_id and r.counts["requests"]}),
            "unpriced_models": sorted(unpriced),
            "top_sessions": [{"id": k, **{kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()}} for k, v in top],
        },
        "jobs": {
            "ran": len(ran), "not_admitted": sum(1 for j in jobs if j["event"] == "not_admitted"),
            "ran_per_h": round(len(ran) / hours, 2),
            # failed mixes real product reds with load reds; timed_out / harness_suspect split the gate rows
            # (predeploy rows carry neither, so their reds stay unsplit).
            "failed": sum(1 for j in ran if j.get("exit_code") not in (None, 0)),
            "timed_out": sum(1 for j in ran if j["metrics"]["outcome"]["timed_out"]),
            "harness_suspect": sum(1 for j in ran if j["metrics"]["outcome"]["harness_suspect"]),
            "wait_s_max": max(num(ran, "waited_s"), default=None), "wait_s_avg": _avg(num(ran, "waited_s")),
            "duration_s_sum": round(sum(num(ran, "duration_s")), 1),
            "peak_rss_mb_max": max(num(ran, "children_peak_rss_mb"), default=None),
            "by_kind": dict(sorted(_count(j["kind"] for j in ran).items())),
            "by_job_workers": dict(sorted(_count(j["metrics"]["job_workers"] for j in ran).items())),
        },
        "os": {
            "samples": len(samples),
            "overloaded_pct": round(100.0 * sum(1 for s in samples if s.get("overloaded")) / len(samples), 1) if samples else None,
            "cpu_idle_pct_avg": _avg(num(samples, "cpu_idle_pct")),
            "cpu_idle_pct_min": min(num(samples, "cpu_idle_pct"), default=None),
            "reclaimable_mb_min": min(num(samples, "reclaimable_mb"), default=None),
            "reclaimable_mb_avg": _avg(num(samples, "reclaimable_mb")),
            # swap-out (PAGES/s) only from v2 samples; v1 maxima reported apart as an upper bound, never mixed in.
            "swapout_per_s_max": max(num(v2, "swapout_per_s"), default=None),
            "swapout_mb_per_s_max": max((float(s["extra"]["swapout_mb_per_s"]) for s in v2
                                         if s["extra"].get("swapout_mb_per_s") is not None), default=None),
            "swapout_per_s_max_v1_upper_bound": max(num(v1, "swapout_per_s"), default=None),
            "probe_versions": {"v1": len(v1), "v2": len(v2)},
            "load_1m_max": max(num(samples, "load_1m"), default=None),
            "claude_sessions_max": max(num(samples, "claude_sessions"), default=None),
            "source": str(hw_log) if hw_log.exists() else f"missing: {hw_log}",
        },
    }


def _count(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for i in items:
        out[i] += 1
    return dict(out)


_COMPARE_KEYS = (
    ("claude", "cost_usd_per_h"), ("claude", "output_tokens_per_h"), ("claude", "requests_per_h"),
    ("claude", "sessions_active"), ("jobs", "ran_per_h"), ("jobs", "failed"), ("jobs", "timed_out"), ("jobs", "not_admitted"),
    ("jobs", "wait_s_max"), ("jobs", "peak_rss_mb_max"), ("os", "overloaded_pct"), ("os", "cpu_idle_pct_avg"),
    ("os", "reclaimable_mb_min"), ("os", "swapout_per_s_max"), ("os", "swapout_mb_per_s_max"),
    ("os", "claude_sessions_max"),
)


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Per-metric A → B with absolute and relative deltas (None when either side is unmeasured)."""
    rows = []
    for sec, key in _COMPARE_KEYS:
        va, vb = a[sec].get(key), b[sec].get(key)
        delta = None if va is None or vb is None else round(vb - va, 4)
        rel = None if delta is None or not va else round(100.0 * delta / va, 1)
        rows.append({"metric": f"{sec}.{key}", "a": va, "b": vb, "delta": delta, "delta_pct": rel})
    return {"a": a["window"], "b": b["window"], "metrics": rows}


# ── DB sync ───────────────────────────────────────────────────────────────

def _client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set — cannot write dev telemetry. "
                           "Source the repo-root .env and re-run.")
    from supabase import create_client
    return create_client(url, key)


def _chunks(rows: list[dict], n: int = 500) -> Iterator[list[dict]]:
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def sync(since: datetime, until: datetime, *, client=None, claude_root: Path = _CLAUDE_ROOT,
         hw_log: Path = _HW_LOG) -> dict[str, Any]:
    """Upsert the window's rows (idempotent: same input ⇒ same rows). Re-scanning a bucket REPLACES it,
    so a bucket that was still filling at the last sync is completed by the next one."""
    client = client or _client()
    h = host()
    claude = [{
        "host": h, "bucket": r.bucket.isoformat(), "session_id": r.session_id, "agent_id": r.agent_id,
        "project": r.project, "model": r.model, **r.counts, "cost_usd": round(r.cost_usd, 6),
        "price_version": r.price_version, "synced_at": datetime.now(timezone.utc).isoformat(),
    } for r in scan_claude(since, until, claude_root)]
    samples, jobs = scan_hw(since, until, hw_log)
    written = {}
    for table, rows, conflict in (
        ("dev_telemetry_claude", claude, "host,bucket,session_id,agent_id,model"),
        ("dev_telemetry_os", samples, "host,ts"),
        ("dev_telemetry_jobs", jobs, "host,ts,job,event"),
    ):
        for chunk in _chunks(rows):
            client.table(table).upsert(chunk, on_conflict=conflict).execute()
        written[table] = len(rows)
    return {"host": h, "since": since.isoformat(), "until": until.isoformat(), "written": written}


def mark(kind: str, label: str, ts: datetime | None = None, payload: dict | None = None, *, client=None) -> dict:
    client = client or _client()
    row = {"host": host(), "ts": (ts or datetime.now(timezone.utc)).isoformat(), "kind": kind,
           "label": label, "payload": payload or {}}
    client.table("dev_telemetry_marks").upsert(row, on_conflict="host,ts,kind,label").execute()
    return row


# ── entry points ──────────────────────────────────────────────────────────

def _window(since: str | None, until: str | None, default_hours: float = 2.0) -> tuple[datetime, datetime]:
    end = parse_ts(until) or datetime.now(timezone.utc)
    start = parse_ts(since) or end - timedelta(hours=default_hours)
    if start >= end:
        raise ValueError(f"since ({start.isoformat()}) must be before until ({end.isoformat()})")
    return start, end


def usage_eval(action: str = "report", since: str | None = None, until: str | None = None,
               b_since: str | None = None, b_until: str | None = None, kind: str | None = None,
               label: str | None = None, payload: dict | None = None) -> dict[str, Any]:
    if action == "report":
        return window_report(*_window(since, until))
    if action == "compare":
        if not (b_since and b_until):
            raise ValueError("compare needs since/until (window A) and b_since/b_until (window B)")
        return compare(window_report(*_window(since, until)), window_report(*_window(b_since, b_until)))
    if action == "sync":
        return sync(*_window(since, until, default_hours=0.5))
    if action == "mark":
        if not (kind and label):
            raise ValueError("mark needs kind and label")
        return mark(kind, label, parse_ts(since), payload)
    raise ValueError(f"unknown action {action!r}: report | compare | sync | mark")


def register(server) -> None:
    @server.tool(
        name="noctus.dev.usage_eval",
        description=(
            "Measure how dev work uses Claude and this machine, per window. action=report since/until (ISO) -> "
            "Claude tokens (input/output/thinking/cache), API-equivalent cost, chars, tool calls, top sessions + "
            "heavy jobs (ran/wait/peak RSS/not-admitted) + OS samples (CPU idle, reclaimable MB, swap-out, load, "
            "overloaded %). action=compare since/until + b_since/b_until -> A vs B deltas. action=sync -> upsert "
            "the window into Supabase public.dev_telemetry_* (the dashboard's data). action=mark kind/label -> "
            "record a phase change / experiment window. Counts only, never text. KB § PATTERNS/devops/usage-evaluation.md"
        ),
    )
    def _usage_eval(action: str = "report", since: str | None = None, until: str | None = None,
                    b_since: str | None = None, b_until: str | None = None, kind: str | None = None,
                    label: str | None = None, payload: dict | None = None) -> dict:
        return usage_eval(action, since, until, b_since, b_until, kind, label, payload)


if __name__ == "__main__":  # `python usage_eval.py sync [since] [until]` — the scheduled syncer's entry
    import sys

    args = sys.argv[1:] or ["report"]
    print(json.dumps(usage_eval(args[0], *(args[1:3] + [None] * (2 - len(args[1:3])))), indent=1, default=str))
