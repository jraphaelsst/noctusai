"""``noctus.dev.council_ledger`` — the council ledger (contract v1: project-history/assistant-chatbot/contracts/council-ledger.md).

One council = one ``session``; every councillor point is an ``objection``; the chair writes one ``verdict``;
later state changes (ratified / overruled / outcome) are append-only ``event`` rows. Closed sets are enums, every
metric has exactly ONE derivation (``compute_metrics``) — KB § PATTERNS/architect/measurement-by-design.md.

Storage (contract §4): ndjson in git is the SOURCE OF TRUTH — ``project-history/council/<YYYY-MM>/<session_id>.ndjson``,
one file per session so parallel branches never conflict, append-only (a correction is a new ``event``). A DB mirror
and any UI are deferred (owner decision pending; the parked design lives on branch ``feat/council-db-parked``).

Neutral recorder (owner decision 2026-11-09): the TOOL assigns every ``anon_label`` and withholds seats until a verdict
exists, so the tech-lead never holds the label-to-seat mapping before it has decided.

Everything takes ``root`` (the tree), so tests need neither network nor patching.
"""
from __future__ import annotations

import json
import os
import random
import re
import string
import subprocess
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# ── contract §2: closed enums (adding a value = a contract bump) ─────────────
ENUMS: dict[str, frozenset[str]] = {
    "stage": frozenset({"idealize", "phase0", "verify_seed", "mockup", "contract", "build", "wire", "test_review",
                        "security_pass", "evaluate", "ship", "go_live", "iterate", "owner_question"}),
    "subject_kind": frozenset({"plan", "decision", "agent_definition", "skill", "product", "contract", "refine",
                               "eval_run", "question"}),
    "trigger": frozenset({"stage_map", "new_product", "irreversible", "trust_boundary", "prod_exposure",
                          "money_legal_lgpd", "seed_fanout", "large_estimate", "unrebutted_objection"}),
    "mode": frozenset({"subagents", "api", "single_chat"}),
    "severity": frozenset({"blocker", "major", "minor", "note"}),
    "chair_kind": frozenset({"chair_agent", "tech_lead", "api_chair"}),
    "disposition": frozenset({"accepted", "rejected", "deferred"}),
    "event_kind": frozenset({"ratified", "overruled", "outcome"}),
    "outcome": frozenset({"vindicated", "refuted", "untested"}),
    "evidence_kind": frozenset({"commit", "revert", "incident", "owner_reversal", "eval_run", "test", "review"}),
}
RECORDS = ("session", "objection", "verdict", "event")
PK = {"session": "session_id", "objection": "objection_id", "verdict": "session_id", "event": "event_id"}

COUNCIL_REL = Path("project-history/council")

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SEAT_RE = re.compile(r"^(lens|advisor):[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LABEL_RE = re.compile(r"^[A-Z]{1,2}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")
_SENTENCE_END_RE = re.compile(r"[.!?]+[\"')\]]*\s+(?=[A-Z0-9\"'(\[])")
_UNIQUE_RE = re.compile(r"^\s*unique\s*(?:[:;,\-—].*)?$", re.IGNORECASE | re.DOTALL)

RETUNE_MIN_RESOLVED = 10
RETUNE_DEMOTE_BELOW = 0.2
RETUNE_PROMOTE_ABOVE = 0.6

# the fields each record may carry (anything else is refused: unknown fields are never dropped silently)
FIELDS: dict[str, dict[str, bool]] = {  # name -> required?
    "session": {"session_id": True, "stage": True, "subject_kind": True, "subject_ref": True, "trigger": True,
                "mode": True, "seats": True, "brief_sha256": True, "project": False},
    "objection": {"objection_id": True, "session_id": True, "seat": True, "anon_label": True, "severity": True,
                  "claim": True, "model": True, "tokens": False},
    "verdict": {"session_id": True, "chair_kind": True, "decision": True, "biggest_risk": True, "first_step": True,
                "dispositions": True, "tokens": False},
    "event": {"event_id": True, "event_kind": True, "session_id": True, "objection_id": False, "outcome": False,
              "evidence_kind": False, "evidence_ref": False, "note": False},
}
_COMMON = {"record": True, "recorded_by": True, "recorded_at": True}


def _err(msg: str, **extra: Any) -> dict:
    return {"ok": False, "error": msg, **extra}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str) or not _TS_RE.match(ts):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt


# ── validation (contract §1–§2) ──────────────────────────────────────────────

def _nonempty(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_row(row: Any) -> list[str]:
    """Return every contract violation of ONE row ([] = valid). Refuses unknown fields; never coerces."""
    if not isinstance(row, dict):
        return ["row must be a JSON object"]
    kind = row.get("record")
    if kind not in RECORDS:
        return [f"record must be one of {'|'.join(RECORDS)}; got {kind!r}"]
    errs: list[str] = []
    spec = {**_COMMON, **FIELDS[kind]}
    for k in row:
        if k not in spec:
            errs.append(f"{kind}: unknown field {k!r} (allowed: {', '.join(sorted(spec))})")
    for k, required in spec.items():
        if required and k not in row:
            errs.append(f"{kind}: missing required field {k!r}")
    if errs:
        return errs

    if not _nonempty(row["recorded_by"]):
        errs.append("recorded_by must be a non-empty string (Claude session id or 'owner')")
    if _parse_ts(row["recorded_at"]) is None:
        errs.append(f"recorded_at must be ISO-8601 UTC (e.g. 2026-11-09T12:00:00Z); got {row['recorded_at']!r}")

    def uuid_field(name: str, nullable: bool = False) -> None:
        v = row.get(name)
        if v is None and nullable:
            return
        if not isinstance(v, str) or not _UUID_RE.match(v):
            errs.append(f"{kind}.{name} must be a UUIDv4 string; got {v!r}")

    def enum_field(name: str, enum: str | None = None, nullable: bool = False) -> None:
        v = row.get(name)
        if v is None and nullable:
            return
        allowed = ENUMS[enum or name]
        if v not in allowed:
            errs.append(f"{kind}.{name} must be one of {'|'.join(sorted(allowed))}; got {v!r}")

    def text_field(name: str) -> None:
        if not _nonempty(row.get(name)):
            errs.append(f"{kind}.{name} must be a non-empty string")

    def tokens_field() -> None:
        v = row.get("tokens")
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            errs.append(f"{kind}.tokens must be a non-negative integer or null; got {v!r}")

    if kind == "session":
        uuid_field("session_id")
        for f in ("stage", "subject_kind", "trigger", "mode"):
            enum_field(f)
        text_field("subject_ref")
        seats = row["seats"]
        if not isinstance(seats, list) or not seats:
            errs.append("session.seats must be a non-empty list of 'lens:<lens>' | 'advisor:<agent-name>'")
        else:
            for s in seats:
                if not isinstance(s, str) or not _SEAT_RE.match(s):
                    errs.append(f"session.seats entry {s!r} must look like 'lens:<lens>' or 'advisor:<agent-name>'")
            if len(set(seats)) != len(seats):
                errs.append("session.seats must not repeat a seat")
        if not isinstance(row["brief_sha256"], str) or not _SHA_RE.match(row["brief_sha256"]):
            errs.append("session.brief_sha256 must be a 64-char lowercase hex sha256")
        if row.get("project") is not None and not _nonempty(row["project"]):
            errs.append("session.project must be a non-empty string or null")
    elif kind == "objection":
        uuid_field("objection_id")
        uuid_field("session_id")
        enum_field("severity")
        if not isinstance(row["seat"], str) or not _SEAT_RE.match(row["seat"]):
            errs.append(f"objection.seat {row['seat']!r} must look like 'lens:<lens>' or 'advisor:<agent-name>'")
        if not isinstance(row["anon_label"], str) or not _LABEL_RE.match(row["anon_label"]):
            errs.append("objection.anon_label must be 1-2 capital letters (A, B, ...)")
        text_field("claim")
        text_field("model")
        if _nonempty(row["claim"]) and len(_SENTENCE_END_RE.findall(row["claim"].strip())) + 1 > 3:
            errs.append("objection.claim must be at most 3 sentences (contract §1)")
        tokens_field()
    elif kind == "verdict":
        uuid_field("session_id")
        enum_field("chair_kind")
        for f in ("decision", "biggest_risk", "first_step"):
            text_field(f)
        tokens_field()
        disp = row["dispositions"]
        if not isinstance(disp, list):
            errs.append("verdict.dispositions must be a list of {objection_id, disposition, reason}")
        else:
            seen: set[str] = set()
            for i, d in enumerate(disp):
                if not isinstance(d, dict) or set(d) != {"objection_id", "disposition", "reason"}:
                    errs.append(f"verdict.dispositions[{i}] must be exactly {{objection_id, disposition, reason}}")
                    continue
                if not isinstance(d["objection_id"], str) or not _UUID_RE.match(d["objection_id"]):
                    errs.append(f"verdict.dispositions[{i}].objection_id must be a UUIDv4 string")
                elif d["objection_id"] in seen:
                    errs.append(f"verdict.dispositions[{i}]: objection {d['objection_id']} has two dispositions")
                else:
                    seen.add(d["objection_id"])
                if d["disposition"] not in ENUMS["disposition"]:
                    errs.append(f"verdict.dispositions[{i}].disposition must be one of "
                                f"{'|'.join(sorted(ENUMS['disposition']))}; got {d['disposition']!r}")
                if not _nonempty(d["reason"]):
                    errs.append(f"verdict.dispositions[{i}].reason must be a non-empty string")
    else:  # event
        uuid_field("event_id")
        uuid_field("session_id")
        enum_field("event_kind")
        ek = row["event_kind"]
        outcome_fields = ("objection_id", "outcome", "evidence_kind")
        if ek == "outcome":
            for f in outcome_fields:
                if row.get(f) is None:
                    errs.append(f"event.{f} is required when event_kind=outcome")
            uuid_field("objection_id", nullable=True)
            enum_field("outcome", nullable=True)
            enum_field("evidence_kind", nullable=True)
        elif ek in ENUMS["event_kind"]:
            for f in outcome_fields:
                if row.get(f) is not None:
                    errs.append(f"event.{f} is only allowed when event_kind=outcome (got event_kind={ek})")
        for f in ("evidence_ref", "note"):
            if row.get(f) is not None and not _nonempty(row[f]):
                errs.append(f"event.{f} must be a non-empty string or null")
    return errs


def validate_file_rows(rows: list[dict], *, file_session_id: str | None = None,
                       file_month: str | None = None) -> list[str]:
    """Per-file consistency (one session's ndjson): row validity + the references between its rows."""
    errs: list[str] = []
    for i, r in enumerate(rows, 1):
        errs += [f"line {i}: {e}" for e in validate_row(r)]
    if errs:
        return errs
    if not rows:
        return ["file is empty (a session file starts with its session row)"]
    if rows[0]["record"] != "session":
        errs.append("line 1: the first row must be the session row")
    sessions = [r for r in rows if r["record"] == "session"]
    if len(sessions) != 1:
        errs.append(f"file must hold exactly one session row; found {len(sessions)}")
        return errs
    s = sessions[0]
    sid = s["session_id"]
    if file_session_id is not None and sid != file_session_id:
        errs.append(f"file name {file_session_id}.ndjson does not match its session_id {sid}")
    if file_month is not None and s["recorded_at"][:7] != file_month:
        errs.append(f"file lives in {file_month}/ but the session was recorded {s['recorded_at'][:7]}")
    seen_ids: set[str] = set()
    objections: dict[str, dict] = {}
    labels: set[str] = set()
    verdicts = 0
    for i, r in enumerate(rows, 1):
        k = r["record"]
        if k != "session" and r["session_id"] != sid:
            errs.append(f"line {i}: {k} belongs to session {r['session_id']}, not this file's {sid}")
        pk = f"{k}:{r[PK[k]]}"
        if pk in seen_ids:
            errs.append(f"line {i}: duplicate {PK[k]} {r[PK[k]]}")
        seen_ids.add(pk)
        if k == "objection":
            if verdicts:
                errs.append(f"line {i}: objection recorded after the verdict (objections come before the chair sees them)")
            if r["seat"] not in s["seats"]:
                errs.append(f"line {i}: seat {r['seat']!r} is not one of the session's seats")
            if r["anon_label"] in labels:
                errs.append(f"line {i}: anon_label {r['anon_label']} is used twice in this session")
            labels.add(r["anon_label"])
            objections[r["objection_id"]] = r
        elif k == "verdict":
            verdicts += 1
            if verdicts > 1:
                errs.append(f"line {i}: a session has one verdict")
            ids = {d["objection_id"] for d in r["dispositions"]}
            for oid in sorted(set(objections) - ids):
                errs.append(f"line {i}: verdict gives no disposition to objection {oid}")
            for oid in sorted(ids - set(objections)):
                errs.append(f"line {i}: verdict disposes unknown objection {oid}")
        elif k == "event":
            if r["event_kind"] == "outcome" and r["objection_id"] not in objections:
                errs.append(f"line {i}: outcome refers to unknown objection {r['objection_id']}")
            if r["event_kind"] in ("ratified", "overruled") and verdicts == 0:
                errs.append(f"line {i}: {r['event_kind']} needs a verdict first")
    return errs


# ── storage ──────────────────────────────────────────────────────────────────

def session_file(root: Path, session_id: str, month: str | None = None) -> Path | None:
    """Existing file of a session, else None (``month`` = YYYY-MM creates the path for a new one)."""
    base = root / COUNCIL_REL
    hits = sorted(base.glob(f"*/{session_id}.ndjson")) if base.is_dir() else []
    if hits:
        return hits[0]
    return base / month / f"{session_id}.ndjson" if month else None


def read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {n} is not valid JSON ({exc.msg})") from exc
    return rows


def all_session_files(root: Path) -> list[Path]:
    base = root / COUNCIL_REL
    return sorted(base.glob("*/*.ndjson")) if base.is_dir() else []


def load_sessions(root: Path) -> list[list[dict]]:
    return [read_rows(p) for p in all_session_files(root)]


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def _stamp(row: dict, recorded_by: str | None, recorded_at: str | None) -> dict:
    by = recorded_by or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not by:
        return _err("recorded_by is required (Claude session id or 'owner'); CLAUDE_CODE_SESSION_ID is not set")
    return {**row, "recorded_by": by, "recorded_at": recorded_at or now_iso()}


def _write(root: Path, row: dict, *, create_month: str | None = None) -> dict:
    sid = row["session_id"]
    path = session_file(root, sid, month=create_month)
    if path is None:
        return _err(f"unknown session {sid}: open_session first")
    existing = read_rows(path) if path.exists() else []
    errs = validate_file_rows(existing + [row])
    if errs:
        return _err("; ".join(errs[:6]) + (f" (+{len(errs) - 6} more)" if len(errs) > 6 else ""), refused=True)
    _append(path, row)
    return {"ok": True, "file": str(path.relative_to(root))}


# ── actions ──────────────────────────────────────────────────────────────────

def open_session(root: Path, *, stage, subject_kind, subject_ref, trigger, mode, seats, brief_sha256,
                 project=None, session_id=None, recorded_by=None, recorded_at=None) -> dict:
    row = _stamp({"record": "session", "session_id": session_id or str(uuid.uuid4()), "stage": stage,
                  "subject_kind": subject_kind, "subject_ref": subject_ref, "trigger": trigger, "mode": mode,
                  "seats": seats, "brief_sha256": brief_sha256, "project": project}, recorded_by, recorded_at)
    if row.get("ok") is False:
        return row
    errs = validate_row(row)
    if errs:
        return _err("; ".join(errs), refused=True)
    if session_file(root, row["session_id"]) is not None:
        return _err(f"session {row['session_id']} already exists (append-only: record objections/events instead)")
    out = _write(root, row, create_month=row["recorded_at"][:7])
    return {**out, "session_id": row["session_id"]} if out.get("ok") else out


def _free_label(used: set[str]) -> str:
    """Random label unused in this session: single letters first, then two-letter ones (the tool assigns, never the caller)."""
    rng = random.SystemRandom()
    singles = [c for c in string.ascii_uppercase if c not in used]
    if singles:
        return rng.choice(singles)
    pairs = [a + b for a in string.ascii_uppercase for b in string.ascii_uppercase if a + b not in used]
    if not pairs:
        raise ValueError("no free anon_label left in this session")
    return rng.choice(pairs)


def record_objection(root: Path, *, session_id, seat, severity, claim, model, tokens=None,
                     objection_id=None, recorded_by=None, recorded_at=None) -> dict:
    """Neutral recorder: the TOOL assigns ``anon_label``; the result never carries the label or the seat mapping."""
    path = session_file(root, session_id) if isinstance(session_id, str) else None
    used = {r["anon_label"] for r in read_rows(path) if r["record"] == "objection"} if path and path.exists() else set()
    try:
        label = _free_label(used)
    except ValueError as exc:
        return _err(str(exc))
    row = _stamp({"record": "objection", "objection_id": objection_id or str(uuid.uuid4()), "session_id": session_id,
                  "seat": seat, "anon_label": label, "severity": severity, "claim": claim, "model": model,
                  "tokens": tokens}, recorded_by, recorded_at)
    if row.get("ok") is False:
        return row
    errs = validate_row(row)
    if errs:
        return _err("; ".join(errs), refused=True)
    out = _write(root, row)
    return {"ok": True, "objection_id": row["objection_id"], "status": "submitted"} if out.get("ok") else out


def _translate_dispositions(root: Path, session_id: Any, dispositions: Any) -> Any:
    """Accept dispositions keyed by ``anon_label`` (the chair's blind view) and translate them to objection ids."""
    if not isinstance(dispositions, list) or not any(isinstance(d, dict) and "anon_label" in d for d in dispositions):
        return dispositions
    path = session_file(root, session_id) if isinstance(session_id, str) else None
    by_label = ({r["anon_label"]: r["objection_id"] for r in read_rows(path) if r["record"] == "objection"}
                if path and path.exists() else {})
    out = []
    for d in dispositions:
        if isinstance(d, dict) and "anon_label" in d:
            if "objection_id" in d:
                return _err("a disposition carries objection_id OR anon_label, not both")
            if d["anon_label"] not in by_label:
                return _err(f"disposition refers to unknown anon_label {d['anon_label']!r}")
            d = {"objection_id": by_label[d["anon_label"]], **{k: v for k, v in d.items() if k != "anon_label"}}
        out.append(d)
    return out


def blind_view(root: Path, session_id: Any) -> dict:
    """The chair's view: {anon_label, severity, claim} per objection — no seat, no model, no ids."""
    path = session_file(root, session_id) if isinstance(session_id, str) else None
    if path is None or not path.exists():
        return _err(f"unknown session {session_id}")
    try:
        rows = read_rows(path)
    except ValueError as exc:
        return _err(str(exc))
    objs = sorted((r for r in rows if r["record"] == "objection"), key=lambda r: r["anon_label"])
    return {"ok": True, "action": "blind_view", "session_id": session_id,
            "objections": [{"anon_label": o["anon_label"], "severity": o["severity"], "claim": o["claim"]} for o in objs]}


def full_view(root: Path, session_id: Any) -> dict:
    """Seats revealed — refused until a verdict row exists for the session."""
    path = session_file(root, session_id) if isinstance(session_id, str) else None
    if path is None or not path.exists():
        return _err(f"unknown session {session_id}")
    try:
        rows = read_rows(path)
    except ValueError as exc:
        return _err(str(exc))
    if not _has_verdict(rows):
        return _err("blind recorder: seats are hidden until the verdict is recorded (use blind_view)", refused=True)
    return {"ok": True, "action": "full_view", "session_id": session_id, "rows": rows}


def _has_verdict(rows: list[dict]) -> bool:
    return any(r["record"] == "verdict" for r in rows)


def record_verdict(root: Path, *, session_id, chair_kind, decision, biggest_risk, first_step, dispositions,
                   tokens=None, recorded_by=None, recorded_at=None) -> dict:
    dispositions = _translate_dispositions(root, session_id, dispositions)
    if isinstance(dispositions, dict) and dispositions.get("ok") is False:
        return dispositions
    row = _stamp({"record": "verdict", "session_id": session_id, "chair_kind": chair_kind, "decision": decision,
                  "biggest_risk": biggest_risk, "first_step": first_step, "dispositions": dispositions,
                  "tokens": tokens}, recorded_by, recorded_at)
    if row.get("ok") is False:
        return row
    errs = validate_row(row)
    if errs:
        return _err("; ".join(errs), refused=True)
    return _write(root, row)


def record_event(root: Path, *, session_id, event_kind, objection_id=None, outcome=None, evidence_kind=None,
                 evidence_ref=None, note=None, event_id=None, recorded_by=None, recorded_at=None) -> dict:
    row = _stamp({"record": "event", "event_id": event_id or str(uuid.uuid4()), "event_kind": event_kind,
                  "session_id": session_id, "objection_id": objection_id, "outcome": outcome,
                  "evidence_kind": evidence_kind, "evidence_ref": evidence_ref, "note": note},
                 recorded_by, recorded_at)
    if row.get("ok") is False:
        return row
    errs = validate_row(row)
    if errs:
        return _err("; ".join(errs), refused=True)
    out = _write(root, row)
    return {**out, "event_id": row["event_id"]} if out.get("ok") else out


# ── metrics (contract §3: ONE derivation each) ───────────────────────────────

def _ratio(n: float, d: float) -> float | None:
    return round(n / d, 4) if d else None


def _is_unique_mark(reason: str) -> bool:
    return bool(_UNIQUE_RE.match(reason or ""))


def compute_metrics(sessions: list[list[dict]], *, stage: str | None = None, project: str | None = None,
                    since: str | None = None, stage_map: dict[str, dict[str, str]] | None = None) -> dict:
    """Per-seat metrics over the given sessions WITH a verdict (each a list of rows, file order) + retune proposals.

    ``since`` filters by the session's ``recorded_at``. ``stage_map`` ({stage: {seat: 'M'|'O'}}) is optional:
    with it the retune proposals apply the contract's M->O / O->M condition exactly; without it each proposal
    carries ``applies_if`` so the owner reads the condition instead of the tool guessing the map.
    """
    since_dt = _parse_ts(since) if since and _TS_RE.match(since) else (
        datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None)
    seat_total: dict[str, dict[str, Any]] = {}
    by_seat_stage: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"vindicated": 0, "refuted": 0})
    kept = 0
    for rows in sessions:
        s = next((r for r in rows if r["record"] == "session"), None)
        if s is None or not _has_verdict(rows):  # blind recorder: only sessions with a verdict are aggregated
            continue
        if stage and s["stage"] != stage:
            continue
        if project and s.get("project") != project:
            continue
        if since_dt and _parse_ts(s["recorded_at"]) < since_dt:
            continue
        kept += 1
        objs = {r["objection_id"]: r for r in rows if r["record"] == "objection"}
        latest: dict[str, str] = {}
        for r in sorted((r for r in rows if r["record"] == "event" and r["event_kind"] == "outcome"),
                        key=lambda r: r["recorded_at"]):  # stable: ties keep file order
            latest[r["objection_id"]] = r["outcome"]
        disp: dict[str, dict] = {}
        for v in (r for r in rows if r["record"] == "verdict"):
            disp = {d["objection_id"]: d for d in v["dispositions"]}
        for oid, o in objs.items():
            t = seat_total.setdefault(o["seat"], {"objections": 0, "tokens": 0, "vindicated": 0, "refuted": 0,
                                                  "with_outcome": 0, "unique_vindicated": 0, "dispositions": 0,
                                                  "accepted": 0})
            t["objections"] += 1
            t["tokens"] += o.get("tokens") or 0
            out = latest.get(oid)
            if out is not None:
                t["with_outcome"] += 1
            if out == "vindicated":
                t["vindicated"] += 1
                by_seat_stage[(o["seat"], s["stage"])]["vindicated"] += 1
                if oid in disp and _is_unique_mark(disp[oid]["reason"]):
                    t["unique_vindicated"] += 1
            elif out == "refuted":
                t["refuted"] += 1
                by_seat_stage[(o["seat"], s["stage"])]["refuted"] += 1
            if oid in disp:
                t["dispositions"] += 1
                t["accepted"] += disp[oid]["disposition"] == "accepted"
    seats = {}
    for seat, t in sorted(seat_total.items()):
        seats[seat] = {
            "objections": t["objections"], "vindicated": t["vindicated"], "refuted": t["refuted"],
            "with_outcome": t["with_outcome"],
            "hit_rate": _ratio(t["vindicated"], t["vindicated"] + t["refuted"]),
            "unique_hit_rate": _ratio(t["unique_vindicated"], t["vindicated"]),
            "false_alarm_rate": _ratio(t["refuted"], t["with_outcome"]),
            "acceptance_rate": _ratio(t["accepted"], t["dispositions"]),
            "cost_per_hit": _ratio(t["tokens"], t["vindicated"]) if t["vindicated"] else None,
            "tokens": t["tokens"],
        }
    proposals = []
    for (seat, stg), c in sorted(by_seat_stage.items()):
        resolved = c["vindicated"] + c["refuted"]
        if resolved < RETUNE_MIN_RESOLVED:
            continue
        hit = c["vindicated"] / resolved
        mapped = (stage_map or {}).get(stg, {}).get(seat)
        if hit < RETUNE_DEMOTE_BELOW and mapped in (None, "M"):
            proposals.append({"seat": seat, "stage": stg, "proposal": "demote M->O", "hit_rate": round(hit, 4),
                              "resolved": resolved, "applies_if": None if mapped else "seat is currently M on the stage map",
                              "auto_apply": False})
        elif hit > RETUNE_PROMOTE_ABOVE and mapped in (None, "O"):
            proposals.append({"seat": seat, "stage": stg, "proposal": "promote O->M", "hit_rate": round(hit, 4),
                              "resolved": resolved, "applies_if": None if mapped else "seat is currently O on the stage map",
                              "auto_apply": False})
    return {"sessions": kept, "filters": {"stage": stage, "project": project, "since": since}, "seats": seats,
            "retune_proposals": proposals, "note": "the owner ratifies a retune; the skill never edits the stage map"}


def report(root: Path, **filters: Any) -> dict:
    try:
        sessions = load_sessions(root)
    except ValueError as exc:
        return _err(str(exc))
    return {"ok": True, "action": "report", **compute_metrics(sessions, **filters)}


# ── status ───────────────────────────────────────────────────────────────────


def status(root: Path, *, outcome_after_days: int = 14, now: datetime | None = None) -> dict:
    """Sessions with no verdict, objections with no outcome older than N days (seats only for verdicted sessions)."""
    now = now or datetime.now(timezone.utc)
    try:
        sessions = load_sessions(root)
    except ValueError as exc:
        return _err(str(exc))
    no_verdict: list[str] = []
    stale: list[dict] = []
    for rows in sessions:
        s = rows[0]
        sid = s["session_id"]
        revealed = _has_verdict(rows)
        if not revealed:
            no_verdict.append(sid)
        decided = {r["objection_id"] for r in rows if r["record"] == "event" and r["event_kind"] == "outcome"
                   and r["outcome"] != "untested"}
        for o in (r for r in rows if r["record"] == "objection"):
            ts = _parse_ts(o["recorded_at"])
            if o["objection_id"] not in decided and ts and now - ts > timedelta(days=outcome_after_days):
                item = {"objection_id": o["objection_id"], "session_id": sid, "age_days": (now - ts).days}
                if revealed:  # seats stay hidden until the verdict exists
                    item["seat"] = o["seat"]
                stale.append(item)
    return {"ok": True, "action": "status", "sessions": len(sessions), "sessions_without_verdict": no_verdict,
            "objections_without_outcome": stale, "outcome_after_days": outcome_after_days}


# ── keeper legs (offline; compliance.py wraps them) ──────────────────────────

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def append_only_violations(rel: str, status_letter: str, diff_text: str, old_line_count: int) -> list[str]:
    """A staged change to a ledger file must ADD lines at EOF and nothing else (contract §4)."""
    if status_letter == "A":
        return []
    if status_letter != "M":
        return [f"{rel}: ledger files are append-only (staged status {status_letter}: deleted/renamed/copied)"]
    errs: list[str] = []
    for line in diff_text.splitlines():
        m = _HUNK_RE.match(line)
        if m:
            old_start, old_cnt = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if old_cnt == 0 and old_start != old_line_count:
                errs.append(f"{rel}: lines inserted after line {old_start} but the file has {old_line_count}: "
                            "only appending at the end is allowed")
        elif line.startswith("-") and not line.startswith("---"):
            errs.append(f"{rel}: an existing line was modified or deleted (a correction is a new event row)")
            break
    return errs


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False).stdout


def check_schema(root: Path, paths: Iterable[str] | None = None, *, staged: bool = False,
                 name_status: dict[str, str] | None = None, diffs: dict[str, str] | None = None,
                 old_counts: dict[str, int] | None = None) -> list[dict]:
    """Keeper issues for ledger files. ``paths`` None = every ledger file. ``staged`` also enforces append-only
    against the index (the git facts can be injected: ``name_status`` / ``diffs`` / ``old_counts``)."""
    files = ([p for p in paths if re.match(rf"^{re.escape(str(COUNCIL_REL))}/[^/]+/[^/]+\.ndjson$", p)]
             if paths is not None else [str(p.relative_to(root)) for p in all_session_files(root)])
    issues: list[dict] = []

    def add(rel: str, msg: str) -> None:
        issues.append({"file": rel, "issue": msg, "severity": "high", "line": 0})

    if staged and name_status is None:
        name_status = {}
        for ln in _git(root, "diff", "--cached", "--name-status", "--", str(COUNCIL_REL)).splitlines():
            parts = ln.split("\t")
            for p in parts[1:]:
                name_status[p] = parts[0][0]
    for rel in files:
        f = root / rel
        st = (name_status or {}).get(rel)
        if staged and st:
            d = (diffs or {}).get(rel)
            if d is None:
                d = _git(root, "diff", "--cached", "-U0", "--", rel)
            n = (old_counts or {}).get(rel)
            if n is None:
                n = len(_git(root, "show", f"HEAD:{rel}").splitlines()) if st == "M" else 0
            for e in append_only_violations(rel, st, d, n):
                add(rel, e)
        if not f.exists():
            if not (staged and st == "D"):
                add(rel, "file is listed but does not exist")
            continue
        try:
            rows = read_rows(f)
        except ValueError as exc:
            add(rel, str(exc))
            continue
        for e in validate_file_rows(rows, file_session_id=f.stem, file_month=f.parent.name):
            add(rel, e)
    if staged:  # a deleted ledger file is not in `files` (it is gone): report it from the index
        for rel, st in (name_status or {}).items():
            if st == "D" and rel not in files and rel.endswith(".ndjson") and rel.startswith(str(COUNCIL_REL)):
                add(rel, "ledger files are append-only (staged status D: deleted)")
    return issues


# ── dispatch (MCP tool + CLI) ────────────────────────────────────────────────

def _req(kw: dict, *names: str) -> str | None:
    miss = [n for n in names if kw.get(n) is None]
    return f"missing required argument(s): {', '.join(miss)}" if miss else None


def run(action: str, *, root: Path | None = None, **kw: Any) -> dict:
    if root is None:
        wt = kw.pop("worktree_path", None)
        if wt:
            root = Path(wt)
        else:
            from settings import REPO_ROOT
            root = Path(REPO_ROOT)
    else:
        kw.pop("worktree_path", None)
    common = {"recorded_by": kw.get("recorded_by"), "recorded_at": kw.get("recorded_at")}
    if action == "open_session":
        e = _req(kw, "stage", "subject_kind", "subject_ref", "trigger", "mode", "seats", "brief_sha256")
        return _err(e) if e else open_session(
            root, stage=kw["stage"], subject_kind=kw["subject_kind"], subject_ref=kw["subject_ref"],
            trigger=kw["trigger"], mode=kw["mode"], seats=kw["seats"], brief_sha256=kw["brief_sha256"],
            project=kw.get("project"), session_id=kw.get("session_id"), **common)
    if action == "record_objection":
        if kw.get("anon_label") is not None:
            return _err("anon_label is assigned by the tool (neutral recorder); the caller cannot pass one", refused=True)
        e = _req(kw, "session_id", "seat", "severity", "claim", "model")
        return _err(e) if e else record_objection(
            root, session_id=kw["session_id"], seat=kw["seat"],
            severity=kw["severity"], claim=kw["claim"], model=kw["model"], tokens=kw.get("tokens"),
            objection_id=kw.get("objection_id"), **common)
    if action == "record_verdict":
        e = _req(kw, "session_id", "chair_kind", "decision", "biggest_risk", "first_step", "dispositions")
        return _err(e) if e else record_verdict(
            root, session_id=kw["session_id"], chair_kind=kw["chair_kind"], decision=kw["decision"],
            biggest_risk=kw["biggest_risk"], first_step=kw["first_step"], dispositions=kw["dispositions"],
            tokens=kw.get("tokens"), **common)
    if action == "record_event":
        e = _req(kw, "session_id", "event_kind")
        return _err(e) if e else record_event(
            root, session_id=kw["session_id"], event_kind=kw["event_kind"], objection_id=kw.get("objection_id"),
            outcome=kw.get("outcome"), evidence_kind=kw.get("evidence_kind"), evidence_ref=kw.get("evidence_ref"),
            note=kw.get("note"), event_id=kw.get("event_id"), **common)
    if action in ("blind_view", "full_view"):
        e = _req(kw, "session_id")
        return _err(e) if e else (blind_view if action == "blind_view" else full_view)(root, kw["session_id"])
    if action == "report":
        return report(root, stage=kw.get("stage"), project=kw.get("project"), since=kw.get("since"),
                      stage_map=kw.get("stage_map"))
    if action == "status":
        return status(root, outcome_after_days=int(kw.get("outcome_after_days") or 14))
    return _err("action must be one of open_session|record_objection|record_verdict|record_event|blind_view|full_view|report|status; "
                f"got {action!r}")


def register(server) -> None:  # noqa: ANN001
    @server.tool(
        name="noctus.dev.council_ledger",
        description=(
            "The council ledger (contract: project-history/assistant-chatbot/contracts/council-ledger.md). ndjson per "
            "session under project-history/council/<YYYY-MM>/, append-only, every enum validated (invalid row = "
            "refused with the exact clause). The ndjson in git is the source of truth (DB mirror deferred).\n\n"
            "ACTIONS\n"
            "  open_session     — stage, subject_kind, subject_ref, trigger, mode, seats[], brief_sha256; optional project.\n"
            "  record_objection — session_id, seat, severity, claim (<=3 sentences), model; optional tokens. The TOOL assigns "
            "anon_label (callers cannot pass one); returns only {objection_id, status:'submitted'} (neutral recorder).\n"
            "  blind_view       — session_id: the chair's view, {anon_label, severity, claim} only (no seat/model/id).\n"
            "  full_view        — session_id: every row incl. seats; refused until a verdict exists.\n"
            "  record_verdict   — session_id, chair_kind, decision, biggest_risk, first_step, dispositions"
            "[{objection_id|anon_label, disposition, reason}] (one per objection; labels are translated; reason 'unique' marks a unique hit); optional tokens.\n"
            "  record_event     — session_id, event_kind in {ratified,overruled,outcome}; outcome needs objection_id, "
            "outcome {vindicated,refuted,untested}, evidence_kind; optional evidence_ref, note.\n"
            "  report           — (sessions with a verdict only) per-seat hit/unique-hit/false-alarm/acceptance/cost_per_hit + retune proposals; "
            "filters stage, project, since; optional stage_map {stage:{seat:M|O}}.\n"
            "  status           — sessions without a verdict, objections without an outcome "
            "older than outcome_after_days (default 14); seats shown only for sessions with a verdict.\n"
            "recorded_by defaults to CLAUDE_CODE_SESSION_ID; ids are generated when omitted; worktree_path pins the tree."
        ),
    )
    def _council_ledger(
        action: str,
        session_id: str | None = None,
        stage: str | None = None,
        subject_kind: str | None = None,
        subject_ref: str | None = None,
        trigger: str | None = None,
        mode: str | None = None,
        seats: list[str] | None = None,
        brief_sha256: str | None = None,
        project: str | None = None,
        seat: str | None = None,
        severity: str | None = None,
        claim: str | None = None,
        model: str | None = None,
        tokens: int | None = None,
        objection_id: str | None = None,
        chair_kind: str | None = None,
        decision: str | None = None,
        biggest_risk: str | None = None,
        first_step: str | None = None,
        dispositions: list[dict] | None = None,
        event_kind: str | None = None,
        outcome: str | None = None,
        evidence_kind: str | None = None,
        evidence_ref: str | None = None,
        note: str | None = None,
        since: str | None = None,
        stage_map: dict | None = None,
        outcome_after_days: int = 14,
        recorded_by: str | None = None,
        worktree_path: str | None = None,
    ) -> dict:
        return run(action, worktree_path=worktree_path, session_id=session_id, stage=stage,
                   subject_kind=subject_kind, subject_ref=subject_ref, trigger=trigger, mode=mode, seats=seats,
                   brief_sha256=brief_sha256, project=project, seat=seat, severity=severity,
                   claim=claim, model=model, tokens=tokens, objection_id=objection_id, chair_kind=chair_kind,
                   decision=decision, biggest_risk=biggest_risk, first_step=first_step, dispositions=dispositions,
                   event_kind=event_kind, outcome=outcome, evidence_kind=evidence_kind, evidence_ref=evidence_ref,
                   note=note, since=since, stage_map=stage_map,
                   outcome_after_days=outcome_after_days, recorded_by=recorded_by)


__all__ = ["run", "validate_row", "validate_file_rows", "compute_metrics", "check_schema", "append_only_violations", "register", "blind_view", "full_view", "ENUMS"]
