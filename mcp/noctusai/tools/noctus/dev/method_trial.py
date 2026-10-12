"""``noctus.dev.method_trial`` — record a METHODOLOGY TRIAL.

"I'm using a method / skill / tool / code pattern I cannot fully trust yet": state
a hypothesis + metrics (``open``), log observations while working (``observe``),
then close with a verdict (``verdict``). ``status`` / ``report`` aggregate.

Storage — extend before spawn: trials live in the EXISTING auto-improvement
ledger (``auto_improvement.py``) as three row kinds carrying an optional
``trial`` dict: ``trial`` (head, status ``s1-emergent``), ``trial-obs`` and
``trial-verdict`` (both ``closed`` so they never pollute open/radar views).
Rows of one trial share ``source_ref == "trial:<slug>"``. A trial is OPEN until a
``trial-verdict`` row exists for its slug. Radar and ``reconcile`` ignore trials.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import auto_improvement as ai

SIGNALS = frozenset({"measure", "friction", "surprise", "failure", "success", "note"})
VERDICTS = frozenset({"adopt", "refine", "discard", "extend"})
STALE_OPEN_DAYS = 14
STALE_QUIET_DAYS = 7
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MIN_TEXT = 20


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}


def _ref(slug: str) -> str:
    return f"trial:{slug}"


def _parse_ts(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load() -> dict[str, dict]:
    """Group every trial row by slug -> {head, obs[], verdict}. Latest verdict wins."""
    rows = ai.query(limit=1_000_000, skip_reconcile=True)
    rows = [r for r in rows if r.get("kind") in ai.TRIAL_KINDS and isinstance(r.get("trial"), dict)]
    rows.sort(key=lambda r: r.get("ts", ""))
    trials: dict[str, dict] = {}
    for r in rows:
        slug = r["trial"].get("slug")
        if not slug:
            continue
        t = trials.setdefault(slug, {"head": None, "obs": [], "verdict": None})
        if r["kind"] == "trial":
            t["head"] = t["head"] or r
        elif r["kind"] == "trial-obs":
            t["obs"].append(r)
        else:
            t["verdict"] = r
    return {s: t for s, t in trials.items() if t["head"] is not None}


def _validate_metrics(metrics) -> tuple[list[dict] | None, str | None]:
    if not isinstance(metrics, list) or not metrics:
        return None, "metrics must be a non-empty list of {name, how, target?}"
    out: list[dict] = []
    seen: set[str] = set()
    for m in metrics:
        if not isinstance(m, dict):
            return None, "each metric must be an object {name, how, target?}"
        name, how = m.get("name"), m.get("how")
        if not isinstance(name, str) or not name.strip() or not isinstance(how, str) or not how.strip():
            return None, "each metric needs a non-empty string `name` and `how`"
        if name in seen:
            return None, f"duplicate metric name {name!r}"
        seen.add(name)
        out.append({"name": name, "how": how, "target": m.get("target")})
    return out, None


def open_trial(*, slug: str, target: str, hypothesis: str, metrics: list[dict],
               project: str | None = None, agent: str = "tech-lead") -> dict:
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        return _err(f"slug must be kebab-case (a-z0-9 and '-'); got {slug!r}")
    if not isinstance(target, str) or not target.strip():
        return _err("target is required (skill / tool / KB path / code area under evaluation)")
    if not isinstance(hypothesis, str) or len(hypothesis.strip()) < _MIN_TEXT:
        return _err(f"hypothesis must be at least {_MIN_TEXT} characters")
    clean, merr = _validate_metrics(metrics)
    if merr:
        return _err(merr)
    # Stricter than "duplicate OPEN slug": a verdicted slug is refused too, because
    # observations/verdicts key on the slug alone and a reused slug would be
    # closed by the earlier trial's verdict. Follow-ups take a new slug.
    existing = _load().get(slug)
    if existing is not None:
        state = "already has a verdict" if existing["verdict"] else "is already open"
        return _err(f"trial slug {slug!r} {state}; use a new slug (follow-ups get their own)")
    res = ai.log_entry(
        scope="broad", kind="trial", target=target, description=hypothesis,
        agent=agent, status="s1-emergent", source_ref=_ref(slug),
        trial={"slug": slug, "hypothesis": hypothesis, "metrics": clean,
               "project": project, "verdict": "pending"},
    )
    if not res.get("ok"):
        return res
    return {"ok": True, "action": "open", "slug": slug, "entry": res["entry"]}


def _live(slug: str) -> tuple[dict | None, dict | None]:
    t = _load().get(slug)
    if t is None:
        return None, _err(f"unknown trial slug {slug!r}")
    if t["verdict"] is not None:
        return None, _err(f"trial {slug!r} already has a verdict "
                          f"({t['verdict']['trial'].get('verdict')}); it is closed")
    return t, None


def observe(*, slug: str, signal: str, text: str, metric: str | None = None,
            value: float | int | str | None = None, evidence: str | None = None,
            agent: str = "tech-lead") -> dict:
    if signal not in SIGNALS:
        return _err(f"signal must be one of {sorted(SIGNALS)}; got {signal!r}")
    if not isinstance(text, str) or not text.strip():
        return _err("text is required")
    t, err = _live(slug)
    if err:
        return err
    names = [m["name"] for m in t["head"]["trial"]["metrics"]]
    if metric is not None and metric not in names:
        return _err(f"metric {metric!r} is not one of this trial's metrics {names}")
    res = ai.log_entry(
        scope="broad", kind="trial-obs", target=t["head"]["target"],
        description=f"[{signal}] {text}", agent=agent, status="closed",
        source_ref=_ref(slug),
        trial={"slug": slug, "signal": signal, "metric": metric,
               "value": value, "evidence": evidence},
    )
    if not res.get("ok"):
        return res
    return {"ok": True, "action": "observe", "slug": slug, "entry": res["entry"]}


def _next_steps(verdict: str, target: str, followup: str | None) -> str:
    nxt = followup or "<followup-slug>"
    return {
        "adopt": (f"codify_log stage s3 for {target} (s4 keeper only after N>=5 confirming "
                  "trials, per methodology-codification-pipeline TEMP rule)"),
        "refine": f"apply the edits now, then open {nxt}",
        "discard": f"remove/rewrite {target} and record why in KB",
        "extend": f"open {nxt} with the widened hypothesis",
    }[verdict]


def verdict(*, slug: str, verdict: str, reasoning: str, changes: list[str] | None = None,
            followup_slug: str | None = None, agent: str = "tech-lead") -> dict:
    if verdict not in VERDICTS:
        return _err(f"verdict must be one of {sorted(VERDICTS)}; got {verdict!r}")
    if not isinstance(reasoning, str) or len(reasoning.strip()) < _MIN_TEXT:
        return _err(f"reasoning must be at least {_MIN_TEXT} characters")
    changes = list(changes or [])
    if not all(isinstance(c, str) for c in changes):
        return _err("changes must be a list of strings (paths/commits)")
    t, err = _live(slug)
    if err:
        return err
    target = t["head"]["target"]
    res = ai.log_entry(
        scope="broad", kind="trial-verdict", target=target, description=reasoning,
        agent=agent, status="closed", source_ref=_ref(slug),
        trial={"slug": slug, "verdict": verdict, "changes": changes,
               "followup_slug": followup_slug},
    )
    if not res.get("ok"):
        return res
    return {"ok": True, "action": "verdict", "slug": slug, "verdict": verdict,
            "entry": res["entry"], "next_steps": _next_steps(verdict, target, followup_slug)}


def _view(slug: str, t: dict, now: datetime) -> dict:
    head = t["head"]
    tr = head["trial"]
    opened = _parse_ts(head["ts"])
    age = (now - opened).days if opened else None
    by_signal: dict[str, dict] = {}
    per_metric: dict[str, list] = {m["name"]: [] for m in tr["metrics"]}
    last_obs: datetime | None = None
    for o in t["obs"]:
        ot = o["trial"]
        g = by_signal.setdefault(ot.get("signal", "note"), {"count": 0, "items": []})
        g["count"] += 1
        g["items"].append({"ts": o["ts"], "text": o["description"].split("] ", 1)[-1],
                           "metric": ot.get("metric"), "value": ot.get("value"),
                           "evidence": ot.get("evidence")})
        if ot.get("metric") in per_metric:
            per_metric[ot["metric"]].append(ot.get("value"))
        ts = _parse_ts(o["ts"])
        if ts and (last_obs is None or ts > last_obs):
            last_obs = ts
    v = t["verdict"]
    stale = False
    if v is None and age is not None and age > STALE_OPEN_DAYS:
        stale = last_obs is None or (now - last_obs).days >= STALE_QUIET_DAYS
    return {
        "slug": slug, "target": head["target"], "hypothesis": tr["hypothesis"],
        "metrics": tr["metrics"], "project": tr.get("project"),
        "opened_at": head["ts"], "age_days": age,
        "observation_count": len(t["obs"]),
        "observations": by_signal, "metric_values": per_metric,
        "verdict": v["trial"]["verdict"] if v else "pending",
        "verdict_reasoning": v["description"] if v else None,
        "verdict_changes": v["trial"].get("changes", []) if v else [],
        "verdict_ts": v["ts"] if v else None,
        "stale": stale,
    }


def status(*, slug: str | None = None, open_only: bool = True,
           now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    trials = _load()
    if slug is not None:
        if slug not in trials:
            return _err(f"unknown trial slug {slug!r}")
        views = [_view(slug, trials[slug], now)]
    else:
        views = [_view(s, t, now) for s, t in trials.items()
                 if not (open_only and t["verdict"] is not None)]
        views.sort(key=lambda x: x["opened_at"])
    return {"ok": True, "action": "status", "count": len(views), "trials": views}


def report(*, since: str | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = None
    if since:
        cutoff = _parse_ts(since)
        if cutoff is None:
            return _err(f"since must be an ISO date; got {since!r}")
    views = []
    for s, t in _load().items():
        v = _view(s, t, now)
        ref = t["verdict"]["ts"] if t["verdict"] else t["head"]["ts"]
        ref_dt = _parse_ts(ref)
        if cutoff and ref_dt and ref_dt < cutoff:
            continue
        views.append(v)
    counts = {"open": 0, "adopt": 0, "refine": 0, "discard": 0, "extend": 0}
    for v in views:
        counts["open" if v["verdict"] == "pending" else v["verdict"]] += 1
    open_trials = [{"slug": v["slug"], "target": v["target"], "age_days": v["age_days"],
                    "observation_count": v["observation_count"], "stale": v["stale"]}
                   for v in views if v["verdict"] == "pending"]
    closed = sorted((v for v in views if v["verdict"] != "pending"),
                    key=lambda v: v["verdict_ts"] or "", reverse=True)[:10]
    last = [{"slug": v["slug"], "target": v["target"], "verdict": v["verdict"],
             "ts": v["verdict_ts"], "reasoning": v["verdict_reasoning"],
             "changes": v["verdict_changes"]} for v in closed]
    return {"ok": True, "action": "report", "since": since, "counts": counts,
            "open_trials": open_trials, "last_verdicts": last}


def run(action: str, **kw) -> dict:
    """Single dispatch used by the MCP tool and the CLI."""
    if action == "open":
        need = [k for k in ("slug", "target", "hypothesis", "metrics") if kw.get(k) is None]
        if need:
            return _err(f"open requires: {', '.join(need)}")
        return open_trial(slug=kw["slug"], target=kw["target"], hypothesis=kw["hypothesis"],
                          metrics=kw["metrics"], project=kw.get("project"),
                          agent=kw.get("agent") or "tech-lead")
    if action == "observe":
        need = [k for k in ("slug", "signal", "text") if kw.get(k) is None]
        if need:
            return _err(f"observe requires: {', '.join(need)}")
        return observe(slug=kw["slug"], signal=kw["signal"], text=kw["text"],
                       metric=kw.get("metric"), value=kw.get("value"),
                       evidence=kw.get("evidence"), agent=kw.get("agent") or "tech-lead")
    if action == "verdict":
        need = [k for k in ("slug", "verdict", "reasoning") if kw.get(k) is None]
        if need:
            return _err(f"verdict requires: {', '.join(need)}")
        return verdict(slug=kw["slug"], verdict=kw["verdict"], reasoning=kw["reasoning"],
                       changes=kw.get("changes"), followup_slug=kw.get("followup_slug"),
                       agent=kw.get("agent") or "tech-lead")
    if action == "status":
        return status(slug=kw.get("slug"),
                      open_only=True if kw.get("open_only") is None else bool(kw["open_only"]))
    if action == "report":
        return report(since=kw.get("since"))
    return _err(f"action must be one of open|observe|verdict|status|report; got {action!r}")


def register(server) -> None:  # noqa: ANN001
    @server.tool(
        name="noctus.dev.method_trial",
        description=(
            "Record a METHODOLOGY TRIAL — using a method/skill/tool/code pattern you cannot "
            "fully trust yet: state a hypothesis + metrics, log observations while working, "
            "then give a verdict. Stored in the auto-improvement ledger (kinds trial / "
            "trial-obs / trial-verdict).\n\n"
            "ACTIONS\n"
            "  open    — slug (kebab, unique), target, hypothesis (>=20 chars), metrics "
            "[{name, how, target?}] (>=1); optional project, agent.\n"
            "  observe — slug, signal in {measure,friction,surprise,failure,success,note}, "
            "text; optional metric (must be a trial metric), value, evidence.\n"
            "  verdict — slug, verdict in {adopt,refine,discard,extend}, reasoning (>=20 chars); "
            "optional changes [paths/commits], followup_slug. Returns next_steps routing.\n"
            "  status  — optional slug; open_only (default True). Per-trial aggregate incl. "
            "stale flag (open >14d with no observation in 7d).\n"
            "  report  — optional since (ISO date). Counts + open trials + last 10 verdicts "
            "(for wrap-up).\n"
            "KB § PATTERNS/common/method-trials.md."
        ),
    )
    def _method_trial(
        action: str,
        slug: str | None = None,
        target: str | None = None,
        hypothesis: str | None = None,
        metrics: list[dict] | None = None,
        project: str | None = None,
        agent: str = "tech-lead",
        signal: str | None = None,
        text: str | None = None,
        metric: str | None = None,
        value: float | int | str | None = None,
        evidence: str | None = None,
        verdict: str | None = None,  # noqa: F811 — public arg name per contract
        reasoning: str | None = None,
        changes: list[str] | None = None,
        followup_slug: str | None = None,
        open_only: bool = True,
        since: str | None = None,
    ) -> dict:
        return run(action, slug=slug, target=target, hypothesis=hypothesis, metrics=metrics,
                   project=project, agent=agent, signal=signal, text=text, metric=metric,
                   value=value, evidence=evidence, verdict=verdict, reasoning=reasoning,
                   changes=changes, followup_slug=followup_slug, open_only=open_only,
                   since=since)


__all__ = ["run", "open_trial", "observe", "verdict", "status", "report", "register"]
