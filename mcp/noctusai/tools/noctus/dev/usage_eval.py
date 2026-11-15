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

DELIVERIES (``action=sync_deliveries``, project ai-usage-dashboard contract §4): slice-scores + dispatch-budget
(origin/ledgers via ``read_dual``) → ``public.dev_deliveries``; ``dry_run`` works without the table, a real run on a
missing table raises ``DeliveriesSchemaError``. ``dev_telemetry_claude`` rows are stamped ``ambiente``/``origem``.

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
                                "job_workers": _workers_key(d),
                                # hw_admission adb5c4c04: a memory veto reads "memory: reclaimable X MB - expected
                                # peak Y MB (...)"; kept so memory-vetoes count apart from slot waits.
                                "blocked_by": [str(b) for b in (d.get("blocked_by") or [])]},
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
            # jobs whose wait or refusal named memory (expected peaks are a FLOOR: ru_maxrss = largest child only)
            "memory_vetoed": sum(1 for j in jobs if any(b.startswith("memory:") for b in j["metrics"]["blocked_by"])),
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
    ("jobs", "memory_vetoed"),
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
    amb = ambiente()
    claude = [{
        "host": h, "bucket": r.bucket.isoformat(), "session_id": r.session_id, "agent_id": r.agent_id,
        "project": r.project, "model": r.model, **r.counts, "cost_usd": round(r.cost_usd, 6),
        "price_version": r.price_version, "synced_at": datetime.now(timezone.utc).isoformat(),
        "ambiente": amb, "origem": origem_of(),
    } for r in scan_claude(since, until, claude_root)]
    samples, jobs = scan_hw(since, until, hw_log)
    written = {}
    for table, rows, conflict in (
        ("dev_telemetry_claude", claude, "host,bucket,session_id,agent_id,model"),
        ("dev_telemetry_os", samples, "host,ts"),
        ("dev_telemetry_jobs", jobs, "host,ts,job,event"),
    ):
        for chunk in _chunks(rows):
            try:
                client.table(table).upsert(chunk, on_conflict=conflict).execute()
            except Exception as exc:
                if table == "dev_telemetry_claude" and _is_missing_column(exc):
                    raise DeliveriesSchemaError(
                        "dev_telemetry_claude has no ambiente/origem columns yet — apply core migration 111 "
                        "(ai-usage-dashboard §2 expand) before syncing") from exc
                raise
        written[table] = len(rows)
    return {"host": h, "since": since.isoformat(), "until": until.isoformat(), "written": written}


def mark(kind: str, label: str, ts: datetime | None = None, payload: dict | None = None, *, client=None) -> dict:
    client = client or _client()
    row = {"host": host(), "ts": (ts or datetime.now(timezone.utc)).isoformat(), "kind": kind,
           "label": label, "payload": payload or {}}
    client.table("dev_telemetry_marks").upsert(row, on_conflict="host,ts,kind,label").execute()
    return row


# ── ledger → dev_deliveries (ai-usage-dashboard contract §4) ──────────────

DELIVERIES_TABLE = "dev_deliveries"
JOIN_WINDOW = timedelta(minutes=15)
IN_SHARE = 0.9  # the ledger stores one `tokens` total — the seed estimate is priced on a 90/10 in/out split
ORIGEM_VALUES = ("api_key", "assinatura", "desconhecido")
_REPO_ROOT = Path(__file__).resolve().parents[5]
_FLEET_COMPOSE = _REPO_ROOT / "deploy" / "fleet" / "docker-compose.prod.yml"


class DeliveriesSchemaError(RuntimeError):
    """The Supabase schema lacks what the ingest writes (migration 111 not applied). Typed, never skipped."""


def _is_missing_column(exc: BaseException) -> bool:
    code = str(getattr(exc, "code", "") or "")
    msg = str(exc)
    return code in {"PGRST204", "42703"} or "column" in msg and ("does not exist" in msg or "Could not find" in msg)


def _is_missing_table(exc: BaseException) -> bool:
    code = str(getattr(exc, "code", "") or "")
    msg = str(exc)
    return code in {"PGRST205", "42P01"} or ("Could not find the table" in msg) or ("relation" in msg and "does not exist" in msg)


def fleet_hosts(compose: Path = _FLEET_COMPOSE, env: dict[str, str] | None = None) -> set[str]:
    """Hostnames of the prod fleet, DERIVED from the compose file (``container_name`` / ``hostname`` of every
    service) plus ``NOCTUS_VPS_HOST`` (short name). Never a hand-kept list; a missing file yields the empty set."""
    env = os.environ if env is None else env
    names: set[str] = set()
    try:
        import yaml
        doc = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
        for svc in (doc.get("services") or {}).values():
            if isinstance(svc, dict):
                for k in ("container_name", "hostname"):
                    if svc.get(k):
                        names.add(str(svc[k]).split(".")[0].lower())
    except (OSError, ImportError, ValueError):
        pass
    vps = (env.get("NOCTUS_VPS_HOST") or "").strip()
    if vps:
        names.add(vps.split(".")[0].lower())
    return names


def ambiente(env: dict[str, str] | None = None, hostname: str | None = None,
             fleet: set[str] | None = None) -> str:
    """Order (contract §4): NOC_AMBIENTE > CI/GITHUB_ACTIONS=true > host in the fleet inventory > local."""
    env = os.environ if env is None else env
    explicit = (env.get("NOC_AMBIENTE") or "").strip().lower()
    if explicit:
        if explicit not in ("prod", "local", "ci"):
            raise ValueError(f"NOC_AMBIENTE must be prod|local|ci; got {explicit!r}")
        return explicit
    if (env.get("CI") or "").strip().lower() in ("1", "true") or (env.get("GITHUB_ACTIONS") or "").strip().lower() == "true":
        return "ci"
    fleet = fleet_hosts(env=env) if fleet is None else fleet
    return "prod" if (hostname or host()) in fleet else "local"


def origem_of(session: dict | None = None) -> str:
    """``api_key`` | ``assinatura`` only when the session's auth mode is READABLE; else ``desconhecido``.

    FINDING (2026-11-08, ~/.claude/projects transcripts + telemetry + settings): Claude Code transcripts do NOT record
    the auth mode — ``userType`` is always ``external``, ``entrypoint`` ``cli`` and ``usage.service_tier`` ``standard``
    for both API-key and subscription sessions; they carry only account/org uuids. So nothing is readable ⇒ always
    ``desconhecido`` (never guessed). ``session`` is the seam for a future readable signal (``auth_mode``)."""
    mode = (session or {}).get("auth_mode")
    return mode if mode in ("api_key", "assinatura") else "desconhecido"


def canonical_model(model_id: str | None) -> tuple[str | None, bool]:
    """``(canonical_id, known)`` via the seed model registry. A pinned snapshot (``<id>-2026-09-08`` or the
    registry's ``snapshot`` suffix) maps to its catalog id. Unknown ids come back RAW with ``known=False``."""
    if not model_id:
        return None, True  # absent is not unknown
    raw = str(model_id).strip()
    try:
        from noctusai_lib.integrations.llm.models import models_for
        entries = [m for m in models_for("anthropic")]
    except ImportError:
        return raw, False
    ids = {m.id for m in entries}
    if raw in ids:
        return raw, True
    for m in sorted(entries, key=lambda e: -len(e.id)):
        if raw.startswith(m.id + "-") and raw[len(m.id) + 1:len(m.id) + 5].isdigit():
            return m.id, True
        if m.snapshot and raw == m.id + m.snapshot:
            return m.id, True
    return raw, False


def estimate_delivery_cost(model: str | None, tokens: int | None) -> tuple[float | None, str | None]:
    """``(cost_usd, price_version)``; None/None unless tokens exist AND the model is priced. 90/10 split."""
    if not tokens or not model:
        return None, None
    try:
        from noctusai_lib.integrations.llm.usage import price_usage
    except ImportError:
        return None, "unpriced:no-seed-lib"
    cost, version = price_usage(provider="anthropic", model=model, prompt_tokens=round(tokens * IN_SHARE),
                                completion_tokens=tokens - round(tokens * IN_SHARE))
    return (None, version) if version.startswith("unpriced") else (round(cost, 6), version)


def line_hash(row: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _parse_lines(text: str) -> list[dict]:
    out = []
    for ln in text.splitlines():
        if ln.strip():
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                out.append(d)
    return out


def _tok(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def build_deliveries(score_text: str, budget_text: str, *, amb: str, origem: str = "desconhecido",
                     since: datetime | None = None, until: datetime | None = None,
                     now: datetime | None = None) -> tuple[list[dict], dict[str, int]]:
    """Merge the two ledgers into ``dev_deliveries`` rows. Pure: no IO, no clock beyond ``now``."""
    ingested_at = (now or datetime.now(timezone.utc)).isoformat()
    stats = {"scores": 0, "budgets": 0, "matched": 0, "unmatched_budget": 0, "unmatched_score": 0,
             "duplicates": 0, "unknown_model": 0, "out_of_window": 0, "no_key": 0}
    seen_hash: set[str] = set()
    seen_key: set[tuple] = set()

    def fresh(line: dict, kind: str) -> bool:
        h = line_hash(line)
        key = (line.get("slug"), line.get("agent"), line.get("ts"))
        if not all(key) or parse_ts(line.get("ts")) is None:
            stats["no_key"] += 1
            return False
        if h in seen_hash or key in seen_key:
            stats["duplicates"] += 1
            return False
        seen_hash.add(h)
        seen_key.add(key)
        stats[kind] += 1
        return True

    scores = [d for d in _parse_lines(score_text) if fresh(d, "scores")]
    budgets = [d for d in _parse_lines(budget_text) if fresh(d, "budgets")]

    by_pair: dict[tuple, list[int]] = defaultdict(list)
    for i, b in enumerate(budgets):
        by_pair[(b["slug"], b["agent"])].append(i)
    used: set[int] = set()
    pairs: list[tuple[dict | None, dict | None]] = []
    for sc in sorted(scores, key=lambda d: d["ts"]):
        sts = parse_ts(sc["ts"])
        cands = [(abs(parse_ts(budgets[i]["ts"]) - sts), i) for i in by_pair.get((sc["slug"], sc["agent"]), [])
                 if i not in used and abs(parse_ts(budgets[i]["ts"]) - sts) <= JOIN_WINDOW]
        if cands:
            i = min(cands)[1]
            used.add(i)
            stats["matched"] += 1
            pairs.append((sc, budgets[i]))
        else:
            stats["unmatched_score"] += 1
            pairs.append((sc, None))
    for i, b in enumerate(budgets):
        if i not in used:
            stats["unmatched_budget"] += 1
            pairs.append((None, b))

    rows = []
    for sc, bd in pairs:
        primary = sc or bd
        ts = parse_ts(primary["ts"])
        if (since and ts < since) or (until and ts >= until):
            stats["out_of_window"] += 1
            continue
        sc, bd = sc or {}, bd or {}
        model, known = canonical_model(sc.get("model") or bd.get("model"))
        if not known:
            stats["unknown_model"] += 1
        planner, _ = canonical_model(sc.get("planner_model"))
        tokens = _tok(sc.get("tokens"))
        if tokens is None:
            tokens = _tok(bd.get("total_tokens"))
        if tokens is None:
            tokens = _tok(bd.get("estimated_tokens"))
        cost, version = estimate_delivery_cost(model, tokens)
        rows.append({
            "line_hash": line_hash(primary), "slug": primary["slug"], "agent": primary["agent"], "ts": ts.isoformat(),
            "branch": sc.get("branch"), "sha": sc.get("sha"), "model": model, "planner_model": planner,
            "q": sc.get("q"), "q_weighted": sc.get("q_weighted"), "first_pass": sc.get("first_pass"),
            "rework_commits": sc.get("rework_commits"), "tokens": tokens, "tool_uses": sc.get("tool_uses"),
            "wall_s_measured": sc.get("wall_s_measured"), "wall_s_self_reported": sc.get("wall_s_self_reported"),
            "duration_minutes": bd.get("duration_minutes"), "outcome": bd.get("outcome"),
            "cost_usd": cost, "cost_is_estimate": True if cost is not None else None, "price_version": version,
            "ambiente": amb, "origem": origem, "ingested_at": ingested_at,
        })
    rows.sort(key=lambda r: (r["ts"], r["slug"], r["agent"]))
    return rows, stats


def _read_ledgers() -> tuple[str, str, list[str]]:
    """``(scores, budgets, store_errors)`` — origin/ledgers ∪ the legacy dev copy (``read_dual``)."""
    from settings import LEDGER_ROOT
    from tools.noctus.dev._ledger_store import read_ledger_text
    errors = []
    texts = []
    for name in ("slice-scores.ndjson", "dispatch-budget.ndjson"):
        text, err = read_ledger_text(name, LEDGER_ROOT / "project-history" / name, fetch=True)
        texts.append(text)
        if err:
            errors.append(f"{name}: {err}")
    return texts[0], texts[1], errors


def sync_deliveries(since: datetime | None = None, until: datetime | None = None, *, dry_run: bool = False,
                    client=None, ledgers: tuple[str, str, list[str]] | None = None,
                    env: dict[str, str] | None = None, hostname: str | None = None,
                    fleet: set[str] | None = None) -> dict[str, Any]:
    """Idempotent ledger → ``public.dev_deliveries`` upsert. ``dry_run`` needs neither the table nor credentials.
    A real run on a missing table raises :class:`DeliveriesSchemaError` (never a silent skip)."""
    score_text, budget_text, store_errors = ledgers if ledgers is not None else _read_ledgers()
    amb = ambiente(env, hostname, fleet)
    rows, stats = build_deliveries(score_text, budget_text, amb=amb, origem=origem_of(), since=since, until=until)
    result: dict[str, Any] = {"dry_run": dry_run, "ambiente": amb, "origem": origem_of(), "stats": stats,
                              "rows": len(rows), "unknown_model": stats["unknown_model"],
                              "ledger_errors": store_errors,
                              "since": since.isoformat() if since else None, "until": until.isoformat() if until else None}
    if dry_run:
        result["sample"] = rows[:3]
        result["written"] = 0
        return result
    client = client or _client()
    try:
        client.table(DELIVERIES_TABLE).select("line_hash").limit(1).execute()
    except Exception as exc:
        if _is_missing_table(exc):
            raise DeliveriesSchemaError(
                f"public.{DELIVERIES_TABLE} does not exist — apply core migration 111 (feat/ai-usage-be) first; "
                "nothing was written. Use dry_run=true to preview.") from exc
        raise
    for chunk in _chunks(rows):
        client.table(DELIVERIES_TABLE).upsert(chunk, on_conflict="slug,agent,ts").execute()
    result["written"] = len(rows)
    return result


# ── entry points ──────────────────────────────────────────────────────────

def _window(since: str | None, until: str | None, default_hours: float = 2.0) -> tuple[datetime, datetime]:
    end = parse_ts(until) or datetime.now(timezone.utc)
    start = parse_ts(since) or end - timedelta(hours=default_hours)
    if start >= end:
        raise ValueError(f"since ({start.isoformat()}) must be before until ({end.isoformat()})")
    return start, end


def usage_eval(action: str = "report", since: str | None = None, until: str | None = None,
               b_since: str | None = None, b_until: str | None = None, kind: str | None = None,
               label: str | None = None, payload: dict | None = None, dry_run: bool = False) -> dict[str, Any]:
    if action == "sync_deliveries":
        return sync_deliveries(parse_ts(since), parse_ts(until), dry_run=dry_run)
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
    raise ValueError(f"unknown action {action!r}: report | compare | sync | sync_deliveries | mark")


def register(server) -> None:
    @server.tool(
        name="noctus.dev.usage_eval",
        description=(
            "Measure how dev work uses Claude and this machine, per window. action=report since/until (ISO) -> "
            "Claude tokens (input/output/thinking/cache), API-equivalent cost, chars, tool calls, top sessions + "
            "heavy jobs (ran/wait/peak RSS/not-admitted) + OS samples (CPU idle, reclaimable MB, swap-out, load, "
            "overloaded %). action=compare since/until + b_since/b_until -> A vs B deltas. action=sync -> upsert "
            "the window into Supabase public.dev_telemetry_* (the dashboard's data). action=mark kind/label -> "
            "record a phase change / experiment window. action=sync_deliveries since/until/dry_run -> ingest "
            "slice-scores + dispatch-budget (origin/ledgers) into public.dev_deliveries (dry_run previews; a missing "
            "table fails loudly). Counts only, never text. KB § PATTERNS/devops/usage-evaluation.md"
        ),
    )
    def _usage_eval(action: str = "report", since: str | None = None, until: str | None = None,
                    b_since: str | None = None, b_until: str | None = None, kind: str | None = None,
                    label: str | None = None, payload: dict | None = None, dry_run: bool = False) -> dict:
        return usage_eval(action, since, until, b_since, b_until, kind, label, payload, dry_run)


if __name__ == "__main__":  # `python usage_eval.py sync [since] [until]` — the scheduled syncer's entry
    import sys

    args = sys.argv[1:] or ["report"]
    print(json.dumps(usage_eval(args[0], *(args[1:3] + [None] * (2 - len(args[1:3])))), indent=1, default=str))
