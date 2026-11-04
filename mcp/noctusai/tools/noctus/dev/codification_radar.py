"""Codification radar — cluster open auto-improvement entries to surface
s1/s2 → s3/s4 promotion candidates.

Converts the manual codification pipeline (s1 emergent → s2 memory → s3 KB
→ s4 keeper) into a SENSOR. Reads `project-history/auto-improvement.ndjson`
(via the existing `auto_improvement` MCP module), embeds each open entry's
description via `vectorize.embed_text`, clusters by cosine similarity,
returns ranked clusters ready for human review.

Architecture rationale (codified 2026-05-26 Wave-2 — empersonating
backend-engineer per the inline-empersonation rule):

  · Reuse existing seed-shipped APIs: `auto_improvement.query()` for
    loading + `vectorize.embed_text()` for embedding. No new dependencies.
  · Pure-Python cosine (no numpy / sqlite-vec — the open-entry set is
    small, ~10-100 entries).
  · Graceful-degrade: any failure mode (provider unreachable, malformed
    entries, empty cache) returns a structured `{ok: False, error}` —
    NEVER crashes a caller.
  · Companion tool `auto_improvement_promote(matches, target_status)`
    finds entries by `ts+target+description` and rewrites status. The
    ndjson is rewritten atomically (read all → mutate → write all) to
    avoid partial-update races.

KB § PATTERNS/common/scoped-auto-improvement.md § Codification radar.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

# Canonical cosine — single source at _embedding_corpus (N=7 consolidation).
from . import _embedding_corpus as _ec

_cosine = _ec.cosine


DEFAULT_THRESHOLD = 0.75
SUGGESTED_PROMOTION_STATUS = {
    # entries' current_status → target if cluster size ≥ N
    ("s1-emergent", 2): "s2-memory",
    ("s1-emergent", 3): "s3-kb",
    ("s2-memory", 2): "s3-kb",
    ("s2-memory", 3): "s4-keeper",
    ("s3-kb", 2): "s4-keeper",
}


def _suggested_next(entries: list[dict], cluster_size: int) -> str:
    """Map (current_status of entries, cluster_size) → suggested next status.

    Conservative: takes the LOWEST current_status across the cluster and
    suggests the next promotion stage. e.g., cluster of 3 entries all at
    s1 → suggest s3-kb; mixed s1/s2 → suggest s2-memory first.
    """
    statuses = [e.get("status", "s1-emergent") for e in entries]
    if "closed" in statuses:
        # Cluster contains a closed entry → suggest re-open / re-evaluate.
        return "review-needed"
    # Order: s1 → s2 → s3 → s4
    order = ["s1-emergent", "s2-memory", "s3-kb", "s4-keeper"]
    lowest = min(statuses, key=lambda s: order.index(s) if s in order else 99)
    key = (lowest, cluster_size if cluster_size < 3 else 3)
    return SUGGESTED_PROMOTION_STATUS.get(key, "s4-keeper")


def _first_sentence(text: str, width: int = 90) -> str:
    """One-line distillation of a description: first sentence, whitespace
    collapsed, no '@' (it would break a `grep_present:<term>@<path>` predicate)."""
    flat = " ".join((text or "").split()).replace("@", "")
    head = flat.split(". ")[0].rstrip(".")
    return head[:width].rstrip()


def _agent_rule_proposal(agent: str, members: list[dict]) -> dict:
    """A cluster of >=2 entries from one agent type proposes a one-line L1 rule
    for `.claude/agents/<agent>.md` (a DRAFT — the tech-lead applies it)."""
    lead = max(members, key=lambda m: m.get("ts", ""))
    phrase = _first_sentence(lead.get("description", ""))
    return {
        "agent_file": f".claude/agents/{agent}.md",
        "agent_file_exists": (REPO_ROOT / ".claude" / "agents" / f"{agent}.md").is_file(),
        "proposed_l1_rule": f"- {phrase}. (recurred {len(members)}x)",
    }


def _cluster_vectored(vectored: list[tuple[dict, list[float]]], threshold: float, start_id: int = 0) -> list[dict]:
    """Greedy agglomerative clustering over (row, vector) pairs; clusters of
    size >= 2 only, each with cohesion + suggested_status_next."""
    visited: set[int] = set()
    clusters_raw: list[list[int]] = []
    for i in range(len(vectored)):
        if i in visited:
            continue
        cluster_indices = [i]
        visited.add(i)
        for j in range(i + 1, len(vectored)):
            if j in visited:
                continue
            score = _cosine(vectored[i][1], vectored[j][1])
            if score >= threshold:
                cluster_indices.append(j)
                visited.add(j)
        clusters_raw.append(cluster_indices)
    clusters: list[dict] = []
    for cid, indices in enumerate(clusters_raw, start=start_id):
        if len(indices) < 2:
            continue
        members = [vectored[i][0] for i in indices]
        member_vecs = [vectored[i][1] for i in indices]
        pair_scores: list[float] = []
        for a_idx in range(len(member_vecs)):
            for b_idx in range(a_idx + 1, len(member_vecs)):
                pair_scores.append(_cosine(member_vecs[a_idx], member_vecs[b_idx]))
        avg_score = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0
        recencies = [m.get("ts", "") for m in members]
        clusters.append({
            "cluster_id": cid,
            "size": len(indices),
            "avg_score": round(avg_score, 4),
            "avg_recency": max(recencies) if recencies else "",
            "suggested_status_next": _suggested_next(members, len(indices)),
            "entries": members,
        })
    return clusters


def cluster(threshold: float = DEFAULT_THRESHOLD, limit: int = 200, group_by: str | None = None) -> dict:
    """Cluster open auto-improvement entries by cosine similarity.

    Returns:
        Success: `{ok: True, clusters: [...], total_entries: N, threshold,
                   engine: 'pure-python'}`
        Provider unreachable: `{ok: False, error: 'embedding-unreachable',
                                clusters: []}`
        Empty ledger: `{ok: True, clusters: [], total_entries: 0}`

    Each cluster: `{cluster_id, size, avg_score, suggested_status_next,
                    entries: [{ts, agent, scope, kind, target, description,
                               current_status, source_ref}]}`. Sorted by
    `(size DESC, avg_recency DESC)`.
    """
    # 1. Load open entries via the existing seed-shipped API.
    try:
        from tools.noctus.dev import auto_improvement as ai
        # Methodology trials are validated by verdict, not clustering: skip.
        rows = [r for r in ai.query(open_only=True, limit=limit)
                if ai.is_workable(r, include_trial_heads=False)]
    except Exception as e:  # noqa: BLE001 — surface the load error
        return {"ok": False, "error": f"auto_improvement.query failed: {e}", "clusters": []}

    if not rows:
        return {"ok": True, "clusters": [], "total_entries": 0, "threshold": threshold}

    # 2. Embed each entry's description. Skip entries the provider rejects.
    try:
        from tools.noctus.dev.vectorize import embed_text
    except ImportError as e:
        return {"ok": False, "error": f"vectorize unreachable: {e}", "clusters": []}

    vectored: list[tuple[dict, list[float]]] = []
    for row in rows:
        description = row.get("description") or ""
        if not description.strip():
            continue
        result = embed_text(description, namespace="codification_radar")
        if not result.get("ok") or not result.get("vector"):
            # Provider issue — abort cluster (partial clusters mislead).
            return {
                "ok": False,
                "error": result.get("error", "embedding-failed"),
                "clusters": [],
                "partial_rows_loaded": len(vectored),
            }
        vectored.append((row, result["vector"]))

    if not vectored:
        return {"ok": True, "clusters": [], "total_entries": 0, "threshold": threshold}

    # 3-5. Cluster (globally, or per agent type), rank by (size DESC, recency DESC).
    if group_by not in (None, "agent"):
        return {"ok": False, "error": f"group_by must be None or 'agent'; got {group_by!r}", "clusters": []}
    clusters: list[dict] = []
    if group_by == "agent":
        groups: dict[str, list[tuple[dict, list[float]]]] = {}
        for row, vec in vectored:
            groups.setdefault(row.get("agent") or "unknown", []).append((row, vec))
        for agent, items in sorted(groups.items()):
            for c in _cluster_vectored(items, threshold, start_id=len(clusters)):
                c["agent"] = agent
                c.update(_agent_rule_proposal(agent, c["entries"]))
                clusters.append(c)
    else:
        clusters = _cluster_vectored(vectored, threshold)
    clusters.sort(key=lambda c: (c["size"], c["avg_recency"]), reverse=True)

    return {
        "ok": True,
        "clusters": clusters,
        "total_entries": len(rows),
        "threshold": threshold,
        "engine": "pure-python",
        "group_by": group_by,
    }


_AGENT_NAME_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9-]*$")
_S3_STATUSES = frozenset({"s3-kb", "s3-codified"})


def promote(matches: list[dict], target_status: str, target_agent: str | None = None) -> dict:
    """Rewrite the `status` field of matching ndjson entries.

    `matches`: a list of dicts each containing at minimum `ts`, `target`,
    `description` — used as a composite key against the ndjson.
    `target_status`: one of {'s1-emergent', 's2-memory', 's3-kb',
    's4-keeper', 'closed'}.

    Returns: `{ok, updated, no_match, target_status}`.

    Idempotent — running with the same input is a no-op (entries already
    at `target_status` are skipped, counted in `no_match`).

    `target_agent` (s3 only): the row gets a DRAFT L1 line (`draft_l1`) for
    `.claude/agents/<agent>.md` and `resolve_when=grep_present:<phrase>@<that
    file>`, so `reconcile` closes it once the tech-lead applies the line. This
    function never edits the agent file.
    """
    from tools.noctus.dev import auto_improvement as ai
    if target_agent is not None:
        if target_status not in _S3_STATUSES:
            return {"ok": False, "error": f"target_agent requires target_status in {sorted(_S3_STATUSES)}; got {target_status!r}"}
        if not _AGENT_NAME_RE.match(target_agent):
            return {"ok": False, "error": f"target_agent must be an agent file stem (a-z0-9-); got {target_agent!r}"}
    if target_status not in ai.STATUSES:
        return {
            "ok": False,
            "error": f"status must be one of {sorted(ai.STATUSES)}; got {target_status!r}",
        }
    # Dual-read (origin/ledgers ∪ the dev copy) — the rewrite itself goes
    # through the ledger store (`ai._rewrite_ledger`).
    text, _store_err = ai.merged_text()
    if not text:
        return {"ok": False, "error": f"ledger not found: {ai.LEDGER_PATH} (and empty on origin/ledgers)"}

    # Build a match-set keyed by (ts, target, description) for O(1) lookup.
    match_keys: set[tuple[str, str, str]] = {ai._entry_key(m) for m in matches}

    # Route through the shared atomic-rewrite helper (one source of truth for
    # the tmp+rename + malformed-line-preservation invariants; reconcile uses
    # the same). Counters are tracked in the mutate closure so the
    # updated/no_match return shape is preserved exactly.
    counters = {"updated": 0, "no_match": 0}

    def _mutate(entry: dict) -> dict:
        if ai._entry_key(entry) in match_keys:
            if entry.get("status") == target_status:
                counters["no_match"] += 1
            else:
                entry["status"] = target_status
                if target_agent is not None:
                    phrase = _first_sentence(entry.get("description", ""))
                    tgt = entry.get("target", "")
                    entry["target_agent"] = target_agent
                    entry["draft_l1"] = f"- {phrase}." + (f" → `{tgt}`" if tgt and tgt != "*" else "")
                    if entry.get("resolve_when"):
                        entry["prior_resolve_when"] = entry["resolve_when"]
                    entry["resolve_when"] = f"grep_present:{phrase}@.claude/agents/{target_agent}.md"
                    entry["resolve_to"] = "closed"
                counters["updated"] += 1
        return entry

    ai._rewrite_ledger(_mutate)

    return {
        "ok": True,
        "updated": counters["updated"],
        "no_match": counters["no_match"],
        "target_status": target_status,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.codification_radar",
        description=(
            "Cluster open auto-improvement entries by cosine similarity "
            "to surface s1/s2 → s3/s4 promotion candidates. The "
            "codification pipeline's SENSOR: converts manual surface-"
            "spotting into a queryable ranked list. `threshold` (default "
            "0.75) tunes cluster tightness; `limit` (default 200) caps "
            "open-entry load. Returns clusters of size ≥ 2, ranked by "
            "(size DESC, recency DESC), each with a suggested_status_next. "
            "Graceful-degrade if the embedding provider is unreachable. "
            "KB § PATTERNS/common/scoped-auto-improvement.md § Codification radar."
        ),
    )
    def _cluster(threshold: float = DEFAULT_THRESHOLD, limit: int = 200,
                 group_by: str | None = None) -> dict:
        return cluster(threshold=threshold, limit=limit, group_by=group_by)

    @server.tool(
        name="noctus.dev.auto_improvement_promote",
        description=(
            "Promote auto-improvement.ndjson entries to a higher "
            "codification stage. `matches` is a list of entry dicts "
            "(typically from `codification_radar` output's `entries`); "
            "each must contain `ts` + `target` + `description` (the "
            "composite key). `target_status` ∈ {'s1-emergent', "
            "'s2-memory', 's3-kb', 's4-keeper', 'closed'}. Idempotent. "
            "The ndjson is rewritten atomically (tmp + rename) — no "
            "partial-update race. `group_by='agent'` on the radar clusters per agent "
            "type and proposes a one-line L1 rule per cluster; `target_agent` "
            "(s3 only) drafts an L1 line + resolve_when so reconcile closes the "
            "row once the line lands in .claude/agents/<agent>.md."
        ),
    )
    def _promote(matches: list[dict], target_status: str, target_agent: str | None = None) -> dict:
        return promote(matches, target_status, target_agent=target_agent)


__all__ = ["cluster", "promote", "DEFAULT_THRESHOLD", "register"]
