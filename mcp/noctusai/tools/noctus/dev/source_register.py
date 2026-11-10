"""noctus.dev.source_register - the source-reliability register that research learns from.

One row per source (a domain, or a domain/path when one site hosts sources of
different weight), FOLDED from an append-only event log:

- the committed, reviewed seed: ``KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/source-register-seed.ndjson``
  (sources already graded in past research, mined 2026-11-10);
- the live events on the ledgers store (``source-register.ndjson`` on the orphan
  ``ledgers`` branch, ``KB § PATTERNS/common/ledger-store.md``), appended by every
  research run (skill ``noc-research``) - never a commit on ``dev``.

``action='read'`` returns the folded view (tier, track record, standing, last seen);
``action='log'`` appends one event (dry-run unless ``confirm=True``). Reliability
"learns" because the standing is recomputed from the whole track record on every
read: a source whose claims get refuted is flagged for demotion, a source that is
unreachable keeps being reported as such, a source not seen for 180 days is stale.

The core is pure (``fold``/``build_event``) with DI seams (``reader``/``writer``)
so tests drive it without patching anything. Depth: ``KB § PATTERNS/common/research-method.md``.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import toolkit_freshness as _toolkit_freshness

LEDGER_NAME = "source-register.ndjson"
SEED_RELPATH = Path("KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/source-register-seed.ndjson")

TIERS = ("T1", "T2", "T3", "T4")
OUTCOMES = ("graded", "confirmed", "refuted", "contested", "unverified", "unreachable")
STALE_DAYS = 180
# Sub-authorities: a path on a shared host that is its own authority keeps ``host/path``
# as the key (a regulator on gov.br, the legal pages of a product site). Everything else
# reduces to the host. Extend this list in the same change as the first event that needs it.
SUB_AUTHORITIES = (
    "gov.br/anpd", "gov.br/receitafederal",
    "whatsapp.com/legal", "facebook.com/legal",
)
EVENT_FIELDS = ("source", "outcome", "tier", "label", "claim", "evidence", "question", "note", "by")

Reader = Callable[[], tuple[str, str | None]]
Writer = Callable[[list[dict[str, Any]]], dict[str, Any]]


# ── pure core ────────────────────────────────────────────────────────────────
def normalize_source(source: str) -> str:
    """URL -> host (lower, no ``www.``); a bare ``host[/path]`` key is kept,
    lower-cased, without a trailing slash."""
    s = (source or "").strip()
    if "://" in s:
        u = urlparse(s)
        key = (u.hostname or "").lower() + (u.path or "").lower().rstrip("/")
    else:
        key = s.lower().rstrip("/")
    key = key[4:] if key.startswith("www.") else key
    if key.startswith("web.facebook.com/"):
        key = key[4:]
    for sub in SUB_AUTHORITIES:
        if key == sub or key.startswith(sub + "/"):
            return sub
    return key.split("/", 1)[0]


def build_event(*, source: str, outcome: str, tier: str = "", label: str = "",
                claim: str = "", evidence: str = "", question: str = "",
                note: str = "", by: str = "", ts: str | None = None) -> dict[str, Any]:
    """Validate and shape one event row. Raises ``ValueError`` on a bad row."""
    key = normalize_source(source)
    if not key:
        raise ValueError("source is required (a URL or a host such as 'planalto.gov.br')")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
    if tier and tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    if outcome == "graded" and not tier:
        raise ValueError("outcome='graded' needs a tier")
    if outcome in ("confirmed", "refuted", "contested") and not (claim and evidence):
        raise ValueError(f"outcome={outcome!r} needs the claim AND the evidence (the independent source that judged it)")
    row: dict[str, Any] = {
        "ts": ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": key, "outcome": outcome,
    }
    for k, v in (("tier", tier), ("label", label), ("claim", claim), ("evidence", evidence),
                 ("question", question), ("note", note), ("by", by)):
        if v:
            row[k] = v
    return row


def _standing(c: dict[str, int]) -> str:
    judged = c["confirmed"] + c["refuted"]
    if c["refuted"] >= 2 and c["refuted"] * 3 >= judged:
        return "demote"
    if c["refuted"] >= 1 or c["contested"] >= 2:
        return "watch"
    if c["unreachable"] >= 2 and c["confirmed"] == 0:
        return "hard-to-reach"
    if c["confirmed"] >= 3:
        return "proven"
    return "new"


def fold(text: str, *, today: date | None = None) -> dict[str, dict[str, Any]]:
    """Fold event rows (ndjson text) into one row per source. Malformed lines
    are counted under ``"_malformed"`` by the caller, never dropped silently."""
    today = today or datetime.now(timezone.utc).date()
    out: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        r = json.loads(line)
        key = normalize_source(r.get("source", ""))
        row = out.setdefault(key, {
            "source": key, "tier": "", "label": "",
            "counts": {o: 0 for o in OUTCOMES}, "first_seen": r.get("ts", ""),
            "last_seen": "", "notes": [], "refuted_claims": [],
        })
        row["counts"][r["outcome"]] += 1
        if r.get("tier"):
            row["tier"] = r["tier"]
        if r.get("label"):
            row["label"] = r["label"]
        ts = r.get("ts", "")
        row["first_seen"] = min(row["first_seen"] or ts, ts)
        row["last_seen"] = max(row["last_seen"], ts)
        if r.get("note"):
            row["notes"] = (row["notes"] + [f"{ts[:10]} {r['note']}"])[-3:]
        if r["outcome"] == "refuted":
            row["refuted_claims"] = (row["refuted_claims"] + [
                {"claim": r.get("claim", ""), "evidence": r.get("evidence", ""), "ts": ts[:10]}])[-5:]
    for row in out.values():
        row["standing"] = _standing(row["counts"])
        try:
            last = datetime.fromisoformat(row["last_seen"]).date()
            row["stale"] = (today - last).days > STALE_DAYS
        except ValueError:
            row["stale"] = True
    return out


def _parse_lines(text: str) -> tuple[str, int]:
    good, bad = [], 0
    for ln in text.splitlines():
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
            if r.get("outcome") in OUTCOMES and r.get("source"):
                good.append(ln.strip())
                continue
        except json.JSONDecodeError:
            pass
        bad += 1
    return "\n".join(good), bad


# ── IO seams ─────────────────────────────────────────────────────────────────
def _default_reader() -> tuple[str, str | None]:
    from settings import LEDGER_ROOT, REPO_ROOT

    from ._ledger_store import read_ledger_text

    seed_path = Path(REPO_ROOT) / SEED_RELPATH
    seed = seed_path.read_text(encoding="utf-8") if seed_path.exists() else ""
    err = None if seed else f"seed file missing: {SEED_RELPATH}"
    live, store_err = read_ledger_text(LEDGER_NAME, Path(LEDGER_ROOT) / "project-history" / LEDGER_NAME)
    errs = "; ".join(e for e in (err, store_err) if e) or None
    return seed + "\n" + live, errs


def _default_writer(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from settings import LEDGER_ROOT

    from ._ledger_store import append_rows

    return append_rows(LEDGER_NAME, Path(LEDGER_ROOT) / "project-history" / LEDGER_NAME, rows,
                       message=f"source-register: {len(rows)} event(s)")


def _is_write(bound: dict[str, Any]) -> bool:
    return bound.get("action") == "log" and bool(bound.get("confirm"))


@_toolkit_freshness.refuse_gate("source_register", write_predicate=_is_write)
def source_register(
    action: str = "read",
    *,
    query: str = "",
    tier_filter: str = "",
    limit: int = 50,
    source: str = "",
    outcome: str = "",
    tier: str = "",
    label: str = "",
    claim: str = "",
    evidence: str = "",
    question: str = "",
    note: str = "",
    by: str = "",
    events: list[dict[str, Any]] | str | None = None,
    confirm: bool = False,
    reader: Reader | None = None,
    writer: Writer | None = None,
) -> dict[str, Any]:
    """``read``: folded rows matching ``query`` (substring of source/label/notes) and
    ``tier_filter``. ``log``: append one event; ``confirm=False`` plans only."""
    if action == "log":
        if isinstance(events, str):
            try:
                events = json.loads(events) if events.strip() else None
            except json.JSONDecodeError as exc:
                return {"ok": False, "status": "invalid", "error": f"events is not JSON: {exc}"}
        specs = list(events) if events else [dict(source=source, outcome=outcome, tier=tier, label=label,
                                                  claim=claim, evidence=evidence, question=question,
                                                  note=note, by=by)]
        rows, errors = [], []
        for i, spec in enumerate(specs):
            try:
                kw = {k: str(spec.get(k, "") or "") for k in EVENT_FIELDS}
                kw["by"] = kw["by"] or by
                rows.append(build_event(**kw))
            except (ValueError, AttributeError) as exc:
                errors.append(f"event {i}: {exc}")
        if errors:  # all-or-nothing: a batch with one bad row writes nothing
            return {"ok": False, "status": "invalid", "error": "; ".join(errors)}
        brief = [f"{r['outcome']} {r['source']}" + (f" {r['tier']}" if r.get("tier") else "") for r in rows]
        if not confirm:
            return {"ok": True, "status": "planned", "count": len(rows), "events": brief, "rows": rows}
        result = (writer or _default_writer)(rows)
        pending = result.get("status") == "pending"
        return {"ok": True, "status": "spooled" if pending else "applied", "count": len(rows),
                "events": brief, "store_status": result.get("status", "")}
    if action != "read":
        return {"ok": False, "status": "invalid", "error": f"action must be 'read' or 'log', got {action!r}"}
    text, err = (reader or _default_reader)()
    clean, malformed = _parse_lines(text)
    rows = list(fold(clean).values())
    q = query.lower().strip()
    if q:
        rows = [r for r in rows if q in r["source"] or q in r["label"].lower()
                or any(q in n.lower() for n in r["notes"])]
    if tier_filter:
        rows = [r for r in rows if r["tier"] == tier_filter]
    rows.sort(key=lambda r: (r["tier"] or "T9", r["source"]))
    out: dict[str, Any] = {"ok": True, "status": "read", "total": len(rows), "rows": rows[:max(limit, 0)]}
    if malformed:
        out["malformed_lines"] = malformed
    if err:
        out["degraded"] = err
    return out


def register(server) -> None:
    @server.tool(
        name="noctus.dev.source_register",
        description=(
            "Source-reliability register for research (skill noc-research): action='read' returns one folded "
            "row per source (tier T1-T4, counts of confirmed/refuted/contested/unverified/unreachable, standing "
            "new|proven|watch|demote|hard-to-reach, last_seen, stale) filtered by query/tier_filter; "
            "action='log' appends one event (source, outcome, tier, claim, evidence, question, note) or a batch "
            "via events=[{...}, ...] (all-or-nothing) to the ledgers store - WRITE, confirm=False returns the "
            "planned rows. Read it before researching, log after. CLI: --source-register-<arg>. "
            "KB § PATTERNS/common/research-method.md"
        ),
    )
    def _source_register(
        action: str = "read",
        query: str = "",
        tier_filter: str = "",
        limit: int = 50,
        source: str = "",
        outcome: str = "",
        tier: str = "",
        label: str = "",
        claim: str = "",
        evidence: str = "",
        question: str = "",
        note: str = "",
        by: str = "",
        events: list[dict] | None = None,
        confirm: bool = False,
        allow_stale_toolkit: bool = False,
    ) -> dict:
        return source_register(
            action, query=query, tier_filter=tier_filter, limit=limit, source=source, outcome=outcome,
            tier=tier, label=label, claim=claim, evidence=evidence, question=question, note=note, by=by,
            events=events, confirm=confirm, allow_stale_toolkit=allow_stale_toolkit,
        )


__all__ = ["source_register", "register", "fold", "build_event", "normalize_source", "TIERS", "OUTCOMES"]
