"""``noctus.dev.decision_log`` — the executor decision log (any executor agent; contract v1.1:
project-history/assistant-chatbot/contracts/decision-log.md).

A decision is one append-only ndjson row: ``project-history/decisions/<YYYY-MM>/<slice_id>.ndjson`` (decision rows +
review rows). Closed sets are enums; the tier is never trusted: ``tier_floor`` derives the MINIMUM tier from
``criteria_hit`` + ``reversibility`` + ``blast_radius`` + ``surprise_test`` and a row below it is refused (contract §2).
Caps / 3-in-a-row (§5) are enforced at ``record``; ``audit`` (§6) judges the whole slice diff vs its base.

Storage choice (contract §8 says "through ledger_store"): ``ledger_store`` is the orphan-``ledgers``-branch store of FIXED
flat ledger names (``project-history/<name>.ndjson``); it has no per-slice / per-month files and the owner wants the rows
in the branch's own git (offline keeper validates the staged file, the audit reads the worktree). So this tool follows the
``council_ledger`` pattern (in-tree ndjson, reusing its append-only + read helpers); NO DB leg (ledger-first).
Everything takes ``root`` so tests need no network.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .council_ledger import _append as append_row
from .council_ledger import _git, _parse_ts, append_only_violations, now_iso, read_rows

# ── contract §3: closed enums ────────────────────────────────────────────────
TIERS = ("autonomous", "notify", "escalate")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}
ENUMS: dict[str, frozenset[str]] = {
    "tier": frozenset(TIERS),
    "class": frozenset({"edge_case", "internal_error_text", "internal_naming", "test_added", "in_file_refactor",
                        "log_line", "validation_tightened", "null_handling", "typo", "other"}),
    "criteria": frozenset(f"C{i}" for i in range(1, 10)),
    "reversibility": frozenset({"one_commit", "shared_code", "needs_migration", "external_effect"}),
    "blast_radius": frozenset({"slice_paths", "same_product", "seed_internal", "cross_product", "seed_api",
                               "ci_keepers"}),
    "surprise_test": frozenset({"all_no", "escalated_by_test"}),
    "outcome": frozenset({"pending_review", "accepted", "vetoed", "reclassified", "superseded"}),
    "reviewer_kind": frozenset({"compliance_reviewer", "tech_lead", "owner", "product_analyst"}),
}
RECORDS = ("decision", "review")
CLASSES = tuple(sorted(ENUMS["class"] - {"other"}))

# contract §5 starting values (data retunes them; the owner ratifies)
CAP_AUTONOMOUS = 5
CAP_NOTIFY = 3
SAME_CLASS_FILE_LIMIT = 3
SAMPLE_ONE_IN = 5
CLEAN_USES_TO_PROMOTE = 10

# contract §2 → minimum tier per criterion hit / per level-carrying enum value. `criteria_hit` lists the criteria whose
# autonomous column is EXCEEDED (a C1 hit = "not implementing a criterion as written"); the level inside a row is
# carried by reversibility / blast_radius / surprise_test, so the floor is the max over all of them.
CRITERION_FLOOR = {"C1": "notify", "C2": "notify", "C3": "notify", "C4": "escalate", "C5": "notify", "C6": "notify",
                   "C7": "escalate", "C8": "escalate", "C9": "escalate"}
REVERSIBILITY_FLOOR = {"one_commit": "autonomous", "shared_code": "notify", "needs_migration": "escalate",
                       "external_effect": "escalate"}
BLAST_FLOOR = {"slice_paths": "autonomous", "same_product": "notify", "seed_internal": "notify",
               "cross_product": "escalate", "seed_api": "escalate", "ci_keepers": "escalate"}

DECISIONS_REL = Path("project-history/decisions")
_SLICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_ID_RE = re.compile(r"^D-([a-z0-9][a-z0-9-]*)-(\d{3,})$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
DECISION_MAX = 200

FIELDS: dict[str, dict[str, bool]] = {  # name -> required?
    "decision": {"id": True, "ts": True, "agent": True, "slice_id": True, "branch": True, "commit_sha": False,
                 "ac_ref": False, "product": False, "tier": True, "class": True, "criteria_hit": True, "reversibility": True,
                 "blast_radius": True, "surprise_test": True, "paths": True, "decision": True,
                 "options_considered": False, "revert_hint": False, "supersedes": False},
    "review": {"ts": True, "id_ref": True, "outcome": True, "reviewer_kind": True, "reviewer": True, "note": False},
}
_COMMON = {"record": True}


def _err(msg: str, **extra: Any) -> dict:
    return {"ok": False, "error": msg, **extra}


def _nonempty(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def tier_floor(criteria_hit: Iterable[str], reversibility: str, blast_radius: str, surprise_test: str,
               cls: str) -> tuple[str, list[str]]:
    """Minimum tier a decision may carry (contract §2: the HIGHEST tier any criterion gives it) + the reasons."""
    floor, why = "autonomous", []

    def bump(tier: str, reason: str) -> None:
        nonlocal floor
        if TIER_RANK[tier] > TIER_RANK[floor]:
            floor = tier
        if tier != "autonomous":
            why.append(f"{reason} -> {tier}")

    for c in criteria_hit:
        bump(CRITERION_FLOOR[c], c)
    bump(REVERSIBILITY_FLOOR[reversibility], f"reversibility={reversibility}")
    bump(BLAST_FLOOR[blast_radius], f"blast_radius={blast_radius}")
    if cls == "other":
        bump("notify", "class=other is never autonomous")
    if surprise_test == "escalated_by_test":  # the surprise test moves the decision up one tier
        bump(TIERS[min(TIER_RANK[floor] + 1, 2)], "surprise_test=escalated_by_test (+1 tier)")
    return floor, why


# ── validation (contract §3–§4) ──────────────────────────────────────────────

def validate_row(row: Any) -> list[str]:
    """Every contract violation of ONE row ([] = valid). Unknown fields are refused, never dropped; never coerces."""
    if not isinstance(row, dict):
        return ["row must be a JSON object"]
    kind = row.get("record")
    if kind not in RECORDS:
        return [f"record must be one of {'|'.join(RECORDS)}; got {kind!r}"]
    spec = {**_COMMON, **FIELDS[kind]}
    errs = [f"{kind}: unknown field {k!r} (allowed: {', '.join(sorted(spec))})" for k in row if k not in spec]
    errs += [f"{kind}: missing required field {k!r}" for k, req in spec.items() if req and k not in row]
    if errs:
        return errs
    if _parse_ts(row["ts"]) is None:
        errs.append(f"ts must be ISO-8601 UTC (e.g. 2026-11-09T12:00:00Z); got {row['ts']!r}")

    def enum_field(name: str, enum: str | None = None) -> None:
        if row[name] not in ENUMS[enum or name]:
            errs.append(f"{kind}.{name} must be one of {sorted(ENUMS[enum or name])}; got {row[name]!r}")

    if kind == "review":
        if not isinstance(row["id_ref"], str) or not _ID_RE.match(row["id_ref"]):
            errs.append(f"review.id_ref must look like D-<slice>-<NNN>; got {row['id_ref']!r}")
        enum_field("outcome")
        enum_field("reviewer_kind")
        if not _nonempty(row["reviewer"]):
            errs.append("review.reviewer must be a non-empty string")
        if "note" in row and not isinstance(row["note"], str):
            errs.append("review.note must be a string")
        return errs

    if not isinstance(row["id"], str) or not _ID_RE.match(row["id"]):
        errs.append(f"decision.id must look like D-<slice>-<NNN>; got {row['id']!r}")
    elif _ID_RE.match(row["id"]).group(1) != row["slice_id"]:
        errs.append(f"decision.id {row['id']} does not carry slice_id {row['slice_id']!r}")
    if not isinstance(row["slice_id"], str) or not _SLICE_RE.match(row["slice_id"]):
        errs.append(f"decision.slice_id must match {_SLICE_RE.pattern}; got {row['slice_id']!r}")
    for k in ("agent", "branch"):
        if not _nonempty(row[k]):
            errs.append(f"decision.{k} must be a non-empty string")
    for k in ("ac_ref", "options_considered", "revert_hint", "supersedes"):
        if k in row and not _nonempty(row[k]):
            errs.append(f"decision.{k}, when present, must be a non-empty string")
    if "product" in row and not (isinstance(row["product"], str) and _SLICE_RE.match(row["product"])):
        errs.append(f"decision.product, when present, must be a product slug matching {_SLICE_RE.pattern}; "
                    f"got {row['product']!r}")
    if "supersedes" in row and _nonempty(row["supersedes"]) and not _ID_RE.match(row["supersedes"]):
        errs.append(f"decision.supersedes must look like D-<slice>-<NNN>; got {row['supersedes']!r}")
    if "commit_sha" in row and not (isinstance(row["commit_sha"], str) and _SHA_RE.match(row["commit_sha"])):
        errs.append(f"decision.commit_sha must be 7-40 lowercase hex; got {row['commit_sha']!r}")
    enum_field("tier")
    enum_field("class")
    enum_field("reversibility")
    enum_field("blast_radius")
    enum_field("surprise_test")
    ch = row["criteria_hit"]
    if not isinstance(ch, list) or any(c not in ENUMS["criteria"] for c in ch) or len(set(ch)) != len(ch):
        errs.append(f"decision.criteria_hit must be a list of distinct C1..C9; got {ch!r}")
    p = row["paths"]
    if (not isinstance(p, list) or not p or any(not _nonempty(x) or x.startswith("/") or ".." in Path(x).parts
                                                for x in p)):
        errs.append("decision.paths must be a non-empty list of repo-relative paths (no absolute, no '..')")
    d = row["decision"]
    if not _nonempty(d) or len(d) > DECISION_MAX:
        errs.append(f"decision.decision must be 1..{DECISION_MAX} characters; got {len(d) if isinstance(d, str) else d!r}")
    elif not d.startswith("We will "):
        errs.append("decision.decision must be phrased 'We will …'")
    if errs:
        return errs
    floor, why = tier_floor(ch, row["reversibility"], row["blast_radius"], row["surprise_test"], row["class"])
    if TIER_RANK[row["tier"]] < TIER_RANK[floor]:
        errs.append(f"decision.tier {row['tier']!r} is below the floor {floor!r} the row's own fields imply "
                    f"({'; '.join(why)})")
    return errs


def validate_file_rows(rows: list[dict], *, file_slice: str | None = None, file_month: str | None = None) -> list[str]:
    """Per-file consistency: row validity + sequential ids + references between rows."""
    errs: list[str] = []
    for i, r in enumerate(rows, 1):
        errs += [f"line {i}: {e}" for e in validate_row(r)]
    if errs:
        return errs
    if not rows:
        return ["file is empty (a slice file starts with its first decision row)"]
    if rows[0]["record"] != "decision":
        return ["line 1: the first row must be a decision row"]
    sid = rows[0]["slice_id"]
    if file_slice is not None and sid != file_slice:
        errs.append(f"file name {file_slice}.ndjson does not match its slice_id {sid}")
    if file_month is not None and rows[0]["ts"][:7] != file_month:
        errs.append(f"file lives in {file_month}/ but the first decision was recorded {rows[0]['ts'][:7]}")
    known: set[str] = set()
    n = 0
    for i, r in enumerate(rows, 1):
        if r["record"] == "decision":
            n += 1
            if r["slice_id"] != sid:
                errs.append(f"line {i}: slice_id {r['slice_id']!r} is not this file's {sid!r}")
            want = f"D-{sid}-{n:03d}"
            if r["id"] != want:
                errs.append(f"line {i}: id {r['id']} must be {want} (sequential, never reused)")
            if r.get("supersedes") and r["supersedes"] not in known:
                errs.append(f"line {i}: supersedes unknown/later decision {r['supersedes']}")
            known.add(r["id"])
        elif r["id_ref"] not in known:
            errs.append(f"line {i}: review refers to unknown decision {r['id_ref']}")
    return errs


# ── storage ──────────────────────────────────────────────────────────────────

def all_files(root: Path) -> list[Path]:
    base = root / DECISIONS_REL
    return sorted(base.glob("*/*.ndjson")) if base.is_dir() else []


def slice_file(root: Path, slice_id: str, month: str | None = None) -> Path | None:
    base = root / DECISIONS_REL
    hits = sorted(base.glob(f"*/{slice_id}.ndjson")) if base.is_dir() else []
    if hits:
        return hits[0]
    return base / month / f"{slice_id}.ndjson" if month else None


def effective_outcomes(rows: list[dict]) -> dict[str, str]:
    """{decision id: latest review outcome (file order), default pending_review}; a `supersedes` link also
    marks the superseded decision `superseded` unless a later review says otherwise."""
    out = {r["id"]: "pending_review" for r in rows if r["record"] == "decision"}
    for r in rows:
        if r["record"] == "decision" and r.get("supersedes") in out:
            out[r["supersedes"]] = "superseded"
        elif r["record"] == "review" and r["id_ref"] in out:
            out[r["id_ref"]] = r["outcome"]
    return out


def _live(rows: list[dict]) -> list[dict]:
    """Decision rows that still count (not superseded / reclassified away)."""
    oc = effective_outcomes(rows)
    return [r for r in rows if r["record"] == "decision" and oc[r["id"]] not in ("superseded", "reclassified")]


def _covers(row_path: str, f: str) -> bool:
    rp = row_path.rstrip("/")
    return f == rp or f.startswith(rp + "/")


# ── actions ──────────────────────────────────────────────────────────────────

def record(root: Path, *, slice_id: str, agent: str, branch: str, tier: str, cls: str, criteria_hit: list,
           reversibility: str, blast_radius: str, surprise_test: str, paths: list, decision: str,
           commit_sha: str | None = None, ac_ref: str | None = None, options_considered: str | None = None,
           revert_hint: str | None = None, supersedes: str | None = None, ts: str | None = None,
           product: str | None = None) -> dict:
    if not isinstance(slice_id, str) or not _SLICE_RE.match(slice_id):
        return _err(f"slice_id must match {_SLICE_RE.pattern}; got {slice_id!r}", refused=True)
    ts = ts or now_iso()
    path = slice_file(root, slice_id, month=ts[:7])
    existing = read_rows(path) if path.exists() else []
    n = sum(1 for r in existing if r["record"] == "decision") + 1
    row: dict[str, Any] = {"record": "decision", "id": f"D-{slice_id}-{n:03d}", "ts": ts, "agent": agent,
                           "slice_id": slice_id, "branch": branch}
    for k, v in (("commit_sha", commit_sha), ("ac_ref", ac_ref), ("product", product)):
        if v is not None:
            row[k] = v
    row.update({"tier": tier, "class": cls, "criteria_hit": criteria_hit, "reversibility": reversibility,
                "blast_radius": blast_radius, "surprise_test": surprise_test, "paths": paths, "decision": decision})
    for k, v in (("options_considered", options_considered), ("revert_hint", revert_hint),
                 ("supersedes", supersedes)):
        if v is not None:
            row[k] = v
    errs = validate_row(row)  # includes the tier-floor refusal
    if errs:
        return _err("; ".join(errs[:6]), refused=True)
    errs = validate_file_rows(existing + [row])
    if errs:
        return _err("; ".join(errs[:6]), refused=True)
    live = _live(existing)
    if tier == "autonomous":
        same = [r for r in live if r["tier"] == "autonomous" and r["class"] == cls
                and any(_covers(a, b) or _covers(b, a) for a in r["paths"] for b in paths)]
        if len(same) >= SAME_CLASS_FILE_LIMIT - 1:
            return _err(f"{len(same) + 1}rd decision of class {cls!r} on the same file: it can no longer be autonomous "
                        f"(contract §5: ONE decision, reclassified up). Record it as tier=notify (or higher) with "
                        f"supersedes=<the earlier id>.", refused=True, status="reclassify_required",
                        same_class_file=[r["id"] for r in same])
    cap = {"autonomous": CAP_AUTONOMOUS, "notify": CAP_NOTIFY}.get(tier)
    if cap is not None:
        used = [r["id"] for r in live if r["tier"] == tier]
        if len(used) >= cap:
            return {"ok": False, "status": "checkin_required", "tier": tier, "cap": cap, "used": used,
                    "error": f"cap reached: {len(used)}/{cap} {tier} decisions in slice {slice_id}. Check in with the "
                             f"tech-lead before deciding anything else (contract §5); nothing was written."}
    append_row(path, row)
    left = {t: c - sum(1 for r in _live(existing + [row]) if r["tier"] == t)
            for t, c in (("autonomous", CAP_AUTONOMOUS), ("notify", CAP_NOTIFY))}
    return {"ok": True, "id": row["id"], "file": str(path.relative_to(root)), "tier": tier, "remaining": left,
            "trailer": f"Decisions: {row['id']}"}


def review(root: Path, *, id_ref: str, outcome: str, reviewer_kind: str, reviewer: str, note: str | None = None,
           ts: str | None = None) -> dict:
    m = _ID_RE.match(id_ref or "")
    if not m:
        return _err(f"id_ref must look like D-<slice>-<NNN>; got {id_ref!r}", refused=True)
    path = slice_file(root, m.group(1))
    if path is None or not path.exists():
        return _err(f"unknown slice {m.group(1)!r}: no ledger file", refused=True)
    row: dict[str, Any] = {"record": "review", "ts": ts or now_iso(), "id_ref": id_ref, "outcome": outcome,
                           "reviewer_kind": reviewer_kind, "reviewer": reviewer}
    if note is not None:
        row["note"] = note
    errs = validate_file_rows(read_rows(path) + [row])
    if errs:
        return _err("; ".join(errs[:6]), refused=True)
    append_row(path, row)
    return {"ok": True, "file": str(path.relative_to(root)), "id_ref": id_ref, "outcome": outcome}


def _all_rows(root: Path) -> list[tuple[Path, list[dict]]]:
    return [(p, read_rows(p)) for p in all_files(root)]


def list_decisions(root: Path, *, slice_id: str | None = None, tier: str | None = None, cls: str | None = None,
                   outcome: str | None = None, agent: str | None = None, limit: int = 200,
                   product: str | None = None) -> dict:
    out: list[dict] = []
    for _p, rows in _all_rows(root):
        oc = effective_outcomes(rows)
        for r in rows:
            if r["record"] != "decision":
                continue
            if ((slice_id and r["slice_id"] != slice_id) or (tier and r["tier"] != tier) or
                    (cls and r["class"] != cls) or (product and r.get("product") != product) or (agent and r["agent"] != agent) or
                    (outcome and oc[r["id"]] != outcome)):
                continue
            out.append({**r, "outcome": oc[r["id"]]})
    out.sort(key=lambda r: r["ts"], reverse=True)
    return {"ok": True, "count": len(out), "decisions": out[:limit], "truncated": len(out) > limit}


# ── audit (contract §6) ──────────────────────────────────────────────────────
MIGRATION_RE = re.compile(r"(^|/)migrations/[^/]+\.sql$")
ACCESS_TIER_RE = re.compile(r"access[-_]tier", re.IGNORECASE)
CONTRACT_RE = re.compile(r"(^|/)contracts?/")
RLS_RE = re.compile(r"ENABLE\s+ROW\s+LEVEL|FORCE\s+ROW\s+LEVEL|\b(CREATE|ALTER|DROP)\s+POLICY\b", re.IGNORECASE)
ROUTE_RE = re.compile(r"^\+\s*@(\w+\.)?(router|app|api)\.(get|post|put|patch|delete)\(", re.IGNORECASE)
PAGE_RE = re.compile(r"(^|/)(frontend/src/pages|pages|app)/[^/]+\.(tsx|jsx|vue)$|(^|/)routes?/[^/]+\.(tsx|jsx)$")
TEXT_FILE_RE = re.compile(r"(\.(tsx|jsx|html|vue)$)|(^|/)(locales?|i18n|messages|templates)/.*\.(json|ya?ml|txt|html)$")
TEXT_LINE_RE = re.compile(r">[^<>{}]*[A-Za-zÀ-ÿ]{3,}[^<>{}]*<|(label|title|placeholder|aria-label|description|"
                          r"subject)\s*[=:]\s*[\"'`][^\"'`]*[A-Za-zÀ-ÿ]{3,}", re.IGNORECASE)
SENSITIVE_RE = re.compile(r"(^|/)(auth|billing|payments?|secrets?|credentials?)[^/]*(/|\.[a-z]+$)|stripe", re.IGNORECASE)
DEP_MANIFEST_RE = re.compile(r"(^|/)(package\.json|pyproject\.toml|requirements[^/]*\.txt)$")
TRAILER_RE = re.compile(r"^(AC|AC-Ref|Ac-Ref):\s*(.+)$", re.MULTILINE)
ASSIGNED_RE = re.compile(r"^Assigned:\s*(.+)$", re.MULTILINE)
DECIDED_RE = re.compile(r"^Decided:\s*\S+", re.MULTILINE)
SPEC_TRAILER_RE = re.compile(r"^Spec:\s*(\S+)\s*$", re.MULTILINE)
DECISIONS_TRAILER_RE = re.compile(r"^Decisions:\s*(.+)$", re.MULTILINE)
# Severity of the merge-path audit (task_branch enqueue/integrate). Contract §10: starts as warn, promoted to block on data.
MERGE_PATH_AUDIT_MODE = "warn"

# A spec criterion "assigns" a gated surface when its text names the file/dir, or the surface's own keyword.
_SURFACE_WORDS = (
    (MIGRATION_RE, re.compile(r"migrations?\b", re.IGNORECASE)),
    (CONTRACT_RE, re.compile(r"\bcontracts?\b", re.IGNORECASE)),
    (ACCESS_TIER_RE, re.compile(r"access[- _]tiers?", re.IGNORECASE)),
    (RLS_RE, re.compile(r"\bRLS\b|row[- ]level", re.IGNORECASE)),
)


def _norm_token(t: str) -> str:
    t = t.strip().strip("`*.,;:()[]").lower()
    t = re.sub(r"^ac[-_ ]*", "", t)
    return t.lstrip("0") or ("0" if t.startswith("0") else t)


def spec_criteria(text: str) -> dict[str, str]:
    """The spec's numbered acceptance criteria -> {normalized id: criterion text}. Sources: numbered list items inside a
    heading containing 'acceptance criteria'; explicit ``AC-<id>`` / ``AC<n>`` labelled lines anywhere."""
    out: dict[str, str] = {}
    cur: str | None = None
    sec_level: int | None = None
    for ln in text.splitlines():
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            if sec_level is not None and len(h.group(1)) <= sec_level:
                sec_level = None
            if re.search(r"acceptance\s+criteri", h.group(2), re.IGNORECASE):
                sec_level = len(h.group(1))
            cur = None
            continue
        m_ac = re.match(r"^\s*(?:[-*]\s*)?\**AC[-_ ]?([A-Za-z0-9][\w-]*)\**[:.)\s-]+(.*)$", ln)
        m_num = re.match(r"^\s*(\d+)[.)]\s+(.*)$", ln) if sec_level is not None else None
        m = m_ac or m_num
        if m:
            cur = _norm_token(m.group(1))
            out[cur] = (out.get(cur, "") + " " + m.group(2)).strip()
        elif cur and ln.strip() and ln[:1].isspace():
            out[cur] += " " + ln.strip()
        else:
            cur = None
    return out


def _tokens(raw: str) -> list[str]:
    return [t for t in re.split(r"[,;\s]+", raw) if t.strip("`*.()[]")]


def _criterion_assigns(crit_text: str, f: str) -> bool:
    """Does this criterion's text assign file ``f`` (named path/dir/basename, or the gated surface's keyword)?"""
    parts = f.split("/")
    names = {f, parts[-1]} | {"/".join(parts[:i]) for i in range(2, len(parts))}
    if any(n and n in crit_text for n in names):
        return True
    return any(fr.search(f) and w.search(crit_text) for fr, w in _SURFACE_WORDS if fr is not RLS_RE) or False


def _g(root: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return p.returncode, p.stdout


def _parse_patch(patch: str) -> dict[str, dict[str, list[str]]]:
    files: dict[str, dict[str, list[str]]] = {}
    cur: dict[str, list[str]] | None = None
    for ln in patch.splitlines():
        if ln.startswith("+++ "):
            name = ln[4:]
            cur = files.setdefault(name[2:] if name.startswith("b/") else name, {"added": [], "removed": []}) \
                if name != "/dev/null" else None
        elif ln.startswith("--- "):
            continue
        elif cur is not None and ln.startswith("+"):
            cur["added"].append(ln[1:])
        elif cur is not None and ln.startswith("-"):
            cur["removed"].append(ln[1:])
    return files


def _deps_at(root: Path, ref: str, rel: str) -> set[str]:
    rc, text = _g(root, "show", f"{ref}:{rel}") if ref != "WORKTREE" else (0, (root / rel).read_text(errors="replace")
                                                                          if (root / rel).exists() else "")
    if rc != 0 or not text.strip():
        return set()
    name = rel.rsplit("/", 1)[-1]
    try:
        if name == "package.json":
            return set((json.loads(text).get("dependencies") or {}).keys())
        if name == "pyproject.toml":
            import tomllib
            deps = tomllib.loads(text).get("project", {}).get("dependencies", []) or []
            return {re.split(r"[<>=!~\[; ]", d, 1)[0].lower() for d in deps}
        return {re.split(r"[<>=!~\[; ]", ln.strip(), 1)[0].lower() for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith(("#", "-"))}
    except (ValueError, KeyError):
        return set()


def select_recheck(rows: list[dict], seed: str) -> dict:
    """Contract §6: 1 in 5 autonomous rows + EVERY class=other row go back through the surprise test. Deterministic
    given ``seed`` (rank by sha256(seed:id), take ceil(n/5))."""
    live = _live(rows)
    auto = [r["id"] for r in live if r["tier"] == "autonomous" and r["class"] != "other"]
    k = math.ceil(len(auto) / SAMPLE_ONE_IN) if auto else 0
    picked = sorted(auto, key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())[:k]
    return {"sample": sorted(picked), "class_other": sorted(r["id"] for r in live if r["class"] == "other"),
            "autonomous_total": len(auto), "seed": seed}


def audit(root: Path, *, slice_id: str, base: str, slice_paths: list[str] | None = None, seed: str | None = None,
          spec: str | None = None) -> dict:
    """Contract §6 findings for ``git diff <base>...HEAD`` in ``root`` against the slice's ledger."""
    path = slice_file(root, slice_id)
    rows = read_rows(path) if path and path.exists() else []
    findings: list[dict] = []

    def add(check: str, sev: str, msg: str, **kw: Any) -> None:
        findings.append({"check": check, "severity": sev, "message": msg, **kw})

    rc, ns = _g(root, "diff", "--name-status", "-M", f"{base}...HEAD")
    rc2, patch = _g(root, "diff", "-U0", "-M", f"{base}...HEAD")
    if rc != 0 or rc2 != 0:
        return {"ok": False, "status": "inconclusive", "error": f"git diff {base}...HEAD failed (unknown base ref?): "
                "the audit could not measure anything; an unmeasurable audit is never clear.", "findings": []}
    status: dict[str, str] = {}
    for ln in ns.splitlines():
        parts = ln.split("\t")
        status[parts[-1]] = parts[0][0]
    ledger_rel = str(DECISIONS_REL)
    changed = sorted(f for f in status if not f.startswith(ledger_rel + "/"))
    pf = _parse_patch(patch)
    live = _live(rows)
    oc = effective_outcomes(rows)
    decs = [r for r in rows if r["record"] == "decision"]
    reviews: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["record"] == "review":
            reviews[r["id_ref"]].append(r)
    if not decs:
        add("ledger", "warn", f"no decision rows for slice {slice_id!r} ({path.relative_to(root) if path else 'no file'}"
            "): every changed file must then be justified by an AC trailer.")

    def rows_for(f: str) -> list[dict]:
        return [r for r in decs if any(_covers(p, f) for p in r["paths"])]

    # commit facts (checks 1, 6, N): trailers per commit, per file; the spec (explicit or `Spec:` trailer) validates them
    rc3, log = _g(root, "log", "--format=%x1e%H%n%B%x1f", "--name-only", f"{base}..HEAD")
    commits: list[dict] = []
    for blk in log.split("\x1e")[1:]:
        head, _, files_part = blk.partition("\x1f")
        sha, _, msg = head.partition("\n")
        commits.append({"sha": sha, "msg": msg, "files": [x.strip() for x in files_part.splitlines() if x.strip()]})
    spec_rel = spec or next((m.group(1) for c in commits for m in [SPEC_TRAILER_RE.search(c["msg"])] if m), None)
    crits: dict[str, str] | None = None
    if spec_rel:
        sp = (root / spec_rel).resolve()
        if root.resolve() in sp.parents and sp.is_file():
            crits = spec_criteria(sp.read_text(errors="replace"))
        if not crits:
            add("spec", "block", f"spec {spec_rel!r} is missing, outside the tree, or has no numbered acceptance "
                "criteria: AC:/Assigned: trailers cannot be validated (an unmeasurable check is never clear)")
            crits = None
    elif any(TRAILER_RE.search(c["msg"]) or ASSIGNED_RE.search(c["msg"]) for c in commits):
        add("spec", "warn", "no spec referenced (spec=<path> or a `Spec: <path>` commit trailer): AC:/Assigned: trailers "
            "were NOT validated against the acceptance criteria and count unverified (contract §10: promote to block)")
    ids = {r["id"] for r in decs}
    file_ref: dict[str, bool] = defaultdict(bool)       # file -> some commit carrying a valid AC/Assigned/Decisions ref
    file_assigned: dict[str, list[str]] = defaultdict(list)  # file -> criterion texts of valid Assigned: tokens
    unknown_seen: set[tuple[str, str]] = set()
    for c in commits:
        sha, msg = c["sha"], c["msg"]
        valid_ac = unverified_ac = False
        valid_assigned: list[str] = []
        for kind, raw in [("AC", m[1]) for m in TRAILER_RE.findall(msg)] + [("Assigned", m) for m in ASSIGNED_RE.findall(msg)]:
            for tok in _tokens(raw):
                if crits is None:
                    unverified_ac = True
                elif _norm_token(tok) in crits:
                    valid_ac = True
                    if kind == "Assigned":
                        valid_assigned.append(crits[_norm_token(tok)])
                elif (sha, tok) not in unknown_seen:
                    unknown_seen.add((sha, tok))
                    add("ac_unknown", "block", f"commit {sha[:9]}: {kind}: {tok} is not a numbered acceptance criterion "
                        f"of {spec_rel}", commit=sha)
        for tid in (t for m in DECISIONS_TRAILER_RE.findall(msg) for t in re.split(r"[,\s]+", m) if t):
            if tid not in ids:
                add("trailer", "block", f"commit {sha[:9]}: Decisions: trailer names {tid}, which is not a row of "
                    f"slice {slice_id!r}")
        if DECIDED_RE.search(msg) and not DECISIONS_TRAILER_RE.search(msg):
            add("unlogged_decision", "block", f"commit {sha[:9]}: marked `Decided:` (executor-decided) but carries no "
                "`Decisions: D-…` trailer and so no log row", commit=sha)
        has_ref = valid_ac or unverified_ac or bool(DECISIONS_TRAILER_RE.search(msg))
        for f in c["files"]:
            if has_ref:
                file_ref[f] = True
            file_assigned[f] += valid_assigned

    def assigned(f: str) -> bool:
        return any(_criterion_assigns(t, f) for t in file_assigned.get(f, []))

    # 1. migrations / RLS / access tiers / contracts: spec-ASSIGNED work passes (Assigned: <AC> naming the surface in the
    #    spec); an executor-DECIDED change there needs an owner-accepted escalate row
    owner_ok = [r for r in decs if r["tier"] == "escalate" and oc[r["id"]] == "accepted"
                and any(v["reviewer_kind"] == "owner" and v["outcome"] == "accepted" for v in reviews[r["id"]])]
    gated = [f for f in changed if MIGRATION_RE.search(f) or ACCESS_TIER_RE.search(f) or CONTRACT_RE.search(f)
             or any(RLS_RE.search(l) for l in pf.get(f, {}).get("added", []) + pf.get(f, {}).get("removed", []))]
    for f in gated:
        if any(any(_covers(p, f) for p in r["paths"]) for r in owner_ok):
            continue
        if assigned(f):
            add("gated_surface", "info", f"{f}: gated surface, spec-assigned (Assigned: trailer matches a criterion "
                "naming it); no owner escalate row needed", file=f)
            continue
        add("gated_surface", "block", f"{f}: migration/RLS/access-tier/contract change that is neither spec-assigned "
            "(Assigned: <AC> naming it) nor covered by an owner-accepted escalate row", file=f)
    # 2. new route / page / customer-facing text under autonomous rows
    for f in changed:
        added = pf.get(f, {}).get("added", [])
        new_route = any(ROUTE_RE.match("+" + l) for l in added) and f.endswith(".py")
        new_page = status.get(f) == "A" and bool(PAGE_RE.search(f))
        text = bool(TEXT_FILE_RE.search(f)) and any(TEXT_LINE_RE.search(l) for l in added)
        if not (new_route or new_page or text):
            continue
        cov = rows_for(f)
        if cov and all(r["tier"] == "autonomous" for r in cov):
            what = "new route" if new_route else "new page" if new_page else "customer-facing text"
            add("autonomous_surface", "block" if (new_route or new_page) else "warn",
                f"{f}: {what} covered only by autonomous rows ({', '.join(r['id'] for r in cov)})", file=f)
    # 3. billing / secrets / auth: loosening is not mechanically provable -> warn on any uncovered-by-notify+ touch
    for f in changed:
        if SENSITIVE_RE.search(f) and not any(r["tier"] != "autonomous" for r in rows_for(f)):
            add("sensitive_path", "warn", f"{f}: billing/secrets/auth path changed with no notify-or-higher row; "
                "confirm nothing is loosened (loosening is never pre-approved)", file=f)
    # 4. paths outside the declared slice paths while a row claims slice_paths
    claims = [r for r in decs if r["blast_radius"] == "slice_paths"]
    if slice_paths is None:
        add("slice_paths", "warn", "declared slice paths were not supplied (slice_paths=[...]): the "
            "outside-declared-paths check was NOT measured")
    elif claims:
        for f in changed:
            if not any(_covers(p, f) for p in slice_paths):
                add("slice_paths", "block", f"{f}: outside the declared slice paths while rows "
                    f"({', '.join(r['id'] for r in claims[:5])}) claim blast_radius=slice_paths", file=f)
    # 5. new runtime dependency without a notify-or-higher row
    for f in changed:
        if not DEP_MANIFEST_RE.search(f):
            continue
        new = sorted(_deps_at(root, "WORKTREE", f) - _deps_at(root, base, f))
        if new and not any(r["tier"] != "autonomous" for r in rows_for(f)):
            add("runtime_dep", "block", f"{f}: new runtime dependency {', '.join(new)} with no notify-or-higher row "
                "covering the manifest", file=f)
    # 6. changed file with no row and no VALID AC/Assigned trailer
    for f in changed:
        if not rows_for(f) and not file_ref.get(f):
            add("unjustified_file", "block", f"{f}: changed with no decision row covering it and no valid "
                "AC:/Assigned:/Decisions: trailer on any commit that touches it", file=f)
    # N. presence: a new route / page / runtime dependency is an executor decision; with no row and no spec assignment
    #    it was made silently
    for f in changed:
        added = pf.get(f, {}).get("added", [])
        kinds = []
        if f.endswith(".py") and any(ROUTE_RE.match("+" + l) for l in added):
            kinds.append("new route")
        if status.get(f) == "A" and PAGE_RE.search(f):
            kinds.append("new page")
        if DEP_MANIFEST_RE.search(f) and sorted(_deps_at(root, "WORKTREE", f) - _deps_at(root, base, f)):
            kinds.append("new runtime dependency")
        if kinds and not rows_for(f) and not assigned(f):
            add("unlogged_decision", "block", f"{f}: {', '.join(kinds)} with no decision row and no spec assignment "
                "(Assigned: <AC> naming it): an executor decision was made without logging it", file=f)
    # 7. one_commit rows with a migration in the diff
    if any(MIGRATION_RE.search(f) for f in changed):
        for r in live:
            if r["reversibility"] == "one_commit":
                add("one_commit_migration", "block", f"{r['id']}: reversibility=one_commit but the slice diff has a "
                    "migration (a migration is not one git revert)", row=r["id"])
    # 8. caps exceeded
    for t, cap in (("autonomous", CAP_AUTONOMOUS), ("notify", CAP_NOTIFY)):
        n = sum(1 for r in live if r["tier"] == t)
        if n > cap:
            add("caps", "block", f"{n} {t} decisions exceed the cap of {cap}")
    blocks = [f for f in findings if f["severity"] == "block"]
    return {"ok": not blocks, "status": "blocked" if blocks else "clear", "slice": slice_id, "base": base,
            "changed_files": len(changed), "findings": findings, "recheck": select_recheck(rows, seed or slice_id)}


# ── merge-path wiring (contract §10) ─────────────────────────────────────────

def merge_path_audit(root: Path, *, slice_id: str, base: str, telemetry_path: Path | None = None) -> dict:
    """The audit as the merge path runs it (``task_branch`` enqueue/integrate), independent of any reviewer dispatch.
    Mode is ``MERGE_PATH_AUDIT_MODE`` ('warn': findings are reported, nothing is blocked). Returns a compact summary
    (never raises: an unmeasurable audit is reported ``inconclusive``) and appends one telemetry row (best effort) to
    ``~/.noctus/decision-audit.ndjson`` so the promote-to-block criterion can be measured."""
    try:
        res = audit(root, slice_id=slice_id, base=base)
    except Exception as exc:  # noqa: BLE001 - surfaced, never a silent pass
        res = {"ok": False, "status": "inconclusive", "error": f"audit raised: {exc}", "findings": []}
    fs = res.get("findings", [])
    blocks = [f for f in fs if f["severity"] == "block"]
    summary = {"mode": MERGE_PATH_AUDIT_MODE, "status": res.get("status"), "slice": slice_id,
               "blocks": len(blocks), "warns": sum(1 for f in fs if f["severity"] == "warn"),
               "block_checks": sorted({f["check"] for f in blocks}),
               "blocking": bool(blocks) and MERGE_PATH_AUDIT_MODE == "block"}
    if res.get("error"):
        summary["error"] = res["error"]
    try:
        tp = telemetry_path or Path.home() / ".noctus" / "decision-audit.ndjson"
        tp.parent.mkdir(parents=True, exist_ok=True)
        with tp.open("a") as fh:
            fh.write(json.dumps({"ts": now_iso(), **summary}) + "\n")
    except OSError:
        pass
    return summary


# ── report (contract §5, proposals only) ─────────────────────────────────────

def report(root: Path) -> dict:
    per: dict[str, dict] = {}
    for _p, rows in _all_rows(root):
        oc = effective_outcomes(rows)
        for r in rows:
            if r["record"] != "decision":
                continue
            c = per.setdefault(r["class"], {"class": r["class"], "uses": 0, "by_tier": defaultdict(int), "vetoed": 0,
                                            "reclassified": 0, "_seq": []})
            c["uses"] += 1
            c["by_tier"][r["tier"]] += 1
            o = oc[r["id"]]
            c["vetoed"] += o == "vetoed"
            c["reclassified"] += o == "reclassified"
            c["_seq"].append((r["ts"], r["id"], o))
    proposals: list[dict] = []
    classes = []
    for cls, c in sorted(per.items()):
        seq = sorted(c.pop("_seq"))
        last_bad = max((i for i, (_t, _i, o) in enumerate(seq) if o in ("vetoed", "reclassified")), default=-1)
        clean_since = sum(1 for _t, _i, o in seq[last_bad + 1:] if o in ("pending_review", "accepted"))
        c["by_tier"] = dict(c["by_tier"])
        c["clean_since_last_bad"] = clean_since
        if cls == "other":
            c["status"] = "never_autonomous"
        elif last_bad >= 0 and clean_since < CLEAN_USES_TO_PROMOTE:
            c["status"] = "demoted"
            proposals.append({"class": cls, "proposal": "demote", "reason": f"{c['vetoed']} vetoed / "
                              f"{c['reclassified']} reclassified; {clean_since}/{CLEAN_USES_TO_PROMOTE} clean uses since"})
        elif last_bad >= 0:
            c["status"] = "eligible_for_repromotion"
            proposals.append({"class": cls, "proposal": "promote", "reason": f"{clean_since} clean uses since the "
                              f"last veto/reclassification (>= {CLEAN_USES_TO_PROMOTE})"})
        else:
            c["status"] = "autonomous"
        classes.append(c)
    return {"ok": True, "classes": classes, "proposals": proposals,
            "note": "proposals only: the owner ratifies every cap/class change (contract §5)"}


# ── keeper (offline pre-commit) ──────────────────────────────────────────────

def check_schema(root: Path, paths: Iterable[str] | None = None, *, staged: bool = False,
                 name_status: dict[str, str] | None = None, diffs: dict[str, str] | None = None,
                 old_counts: dict[str, int] | None = None) -> list[dict]:
    """Keeper issues for decision-ledger files: every row valid (incl. the tier floor), ids sequential, append-only
    against the index when ``staged``. Git facts injectable like council_ledger.check_schema."""
    pat = re.compile(rf"^{re.escape(str(DECISIONS_REL))}/[^/]+/[^/]+\.ndjson$")
    files = ([p for p in paths if pat.match(p)] if paths is not None
             else [str(p.relative_to(root)) for p in all_files(root)])
    issues: list[dict] = []

    def add(rel: str, msg: str) -> None:
        issues.append({"file": rel, "issue": msg, "severity": "high", "line": 0})

    if staged and name_status is None:
        name_status = {}
        for ln in _git(root, "diff", "--cached", "--name-status", "--", str(DECISIONS_REL)).splitlines():
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
        for e in validate_file_rows(rows, file_slice=f.stem, file_month=f.parent.name):
            add(rel, e)
    if staged:
        for rel, st in (name_status or {}).items():
            if st == "D" and rel not in files and rel.endswith(".ndjson") and rel.startswith(str(DECISIONS_REL)):
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
            if action in ("record", "review") and (root / ".git").is_dir():
                # The server's fixed cwd is the PRIMARY checkout; a write without worktree_path lands in the primary's
                # project-history/decisions/ instead of the caller's branch (2026-11-11). Refuse, name the fix.
                return _err("refusing to write to the primary checkout: pass worktree_path=<your worktree's absolute root> "
                            "so the decision lands in (and is committed with) your branch")
    else:
        kw.pop("worktree_path", None)
    if action == "record":
        e = _req(kw, "slice_id", "agent", "branch", "tier", "decision_class", "criteria_hit", "reversibility",
                 "blast_radius", "surprise_test", "paths", "decision")
        return _err(e) if e else record(
            root, slice_id=kw["slice_id"], agent=kw["agent"], branch=kw["branch"], tier=kw["tier"],
            cls=kw["decision_class"], criteria_hit=kw["criteria_hit"], reversibility=kw["reversibility"],
            blast_radius=kw["blast_radius"], surprise_test=kw["surprise_test"], paths=kw["paths"],
            decision=kw["decision"], commit_sha=kw.get("commit_sha"), ac_ref=kw.get("ac_ref"),
            options_considered=kw.get("options_considered"), revert_hint=kw.get("revert_hint"),
            supersedes=kw.get("supersedes"), ts=kw.get("ts"), product=kw.get("product"))
    if action == "review":
        e = _req(kw, "id_ref", "outcome", "reviewer_kind", "reviewer")
        return _err(e) if e else review(root, id_ref=kw["id_ref"], outcome=kw["outcome"],
                                        reviewer_kind=kw["reviewer_kind"], reviewer=kw["reviewer"],
                                        note=kw.get("note"), ts=kw.get("ts"))
    if action == "list":
        return list_decisions(root, slice_id=kw.get("slice_id"), tier=kw.get("tier"), cls=kw.get("decision_class"),
                              outcome=kw.get("outcome"), agent=kw.get("agent"), limit=int(kw.get("limit") or 200), product=kw.get("product"))
    if action == "audit":
        e = _req(kw, "slice", "base")
        return _err(e) if e else audit(root, slice_id=kw["slice"], base=kw["base"], slice_paths=kw.get("slice_paths"),
                                       seed=kw.get("seed"), spec=kw.get("spec"))
    if action == "report":
        return report(root)
    return _err(f"action must be one of record|review|list|audit|report; got {action!r}")


def register(server) -> None:  # noqa: ANN001
    @server.tool(
        name="noctus.dev.decision_log",
        description=(
            "The executor decision log (every executor; contract: project-history/assistant-chatbot/contracts/decision-log.md). "
            "ndjson per slice under project-history/decisions/<YYYY-MM>/, append-only, ledger-first (no DB).\n\n"
            "ACTIONS\n"
            "  record — slice_id, agent, branch, tier{autonomous,notify,escalate}, decision_class{edge_case,"
            "internal_error_text,internal_naming,test_added,in_file_refactor,log_line,validation_tightened,null_handling,"
            "typo,other}, criteria_hit[C1..C9] (the criteria whose autonomous level is EXCEEDED), reversibility, "
            "blast_radius, surprise_test, paths[], decision ('We will …', <=200 chars); optional commit_sha, ac_ref, "
            "options_considered, revert_hint, supersedes, product (slug; per-product aggregation). Refuses a tier below the floor the fields imply, class=other as "
            "autonomous, and the 3rd same class+file as autonomous (status reclassify_required); the 6th autonomous / 4th "
            "notify returns status checkin_required and writes nothing. Returns the id + the `Decisions:` commit trailer.\n"
            "  review — id_ref, outcome{pending_review,accepted,vetoed,reclassified,superseded}, reviewer_kind"
            "{compliance_reviewer,tech_lead,owner,product_analyst}, reviewer; optional note.\n"
            "  list   — filters slice_id, tier, decision_class, outcome, agent, limit.\n"
            "  audit  — slice, base (git diff <base>...HEAD in worktree_path); optional slice_paths[] (declared paths; "
            "without it that check is reported unmeasured), seed, spec (repo-relative spec file whose numbered acceptance criteria validate AC:/Assigned: trailers; else a `Spec:` commit trailer). Contract §6 findings (block/warn) + the 1-in-5 recheck "
            "sample and every class=other row.\n"
            "  report — per class uses/vetoed/reclassified + demote/promote PROPOSALS (the owner ratifies).\n"
            "worktree_path pins the tree."
        ),
    )
    def _decision_log(
        action: str,
        slice_id: str | None = None,
        agent: str | None = None,
        branch: str | None = None,
        tier: str | None = None,
        decision_class: str | None = None,
        criteria_hit: list[str] | None = None,
        reversibility: str | None = None,
        blast_radius: str | None = None,
        surprise_test: str | None = None,
        paths: list[str] | None = None,
        decision: str | None = None,
        commit_sha: str | None = None,
        ac_ref: str | None = None,
        options_considered: str | None = None,
        revert_hint: str | None = None,
        supersedes: str | None = None,
        product: str | None = None,
        spec: str | None = None,
        id_ref: str | None = None,
        outcome: str | None = None,
        reviewer_kind: str | None = None,
        reviewer: str | None = None,
        note: str | None = None,
        slice: str | None = None,  # noqa: A002 - the contract names it `slice`
        base: str | None = None,
        slice_paths: list[str] | None = None,
        seed: str | None = None,
        limit: int = 200,
        worktree_path: str | None = None,
    ) -> dict:
        return run(action, worktree_path=worktree_path, slice_id=slice_id, agent=agent, branch=branch, tier=tier,
                   decision_class=decision_class, criteria_hit=criteria_hit, reversibility=reversibility,
                   blast_radius=blast_radius, surprise_test=surprise_test, paths=paths, decision=decision,
                   commit_sha=commit_sha, ac_ref=ac_ref, options_considered=options_considered,
                   revert_hint=revert_hint, supersedes=supersedes, product=product, spec=spec, id_ref=id_ref, outcome=outcome,
                   reviewer_kind=reviewer_kind, reviewer=reviewer, note=note, slice=slice, base=base,
                   slice_paths=slice_paths, seed=seed, limit=limit)


__all__ = ["run", "record", "review", "audit", "report", "validate_row", "validate_file_rows", "tier_floor",
           "check_schema", "select_recheck", "merge_path_audit", "spec_criteria", "register", "ENUMS"]
