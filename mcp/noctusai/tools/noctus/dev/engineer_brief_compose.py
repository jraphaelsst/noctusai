"""noctus.dev.engineer_brief_compose — auto-compose engineer dispatch briefs.

Queries three keeper-mirror caches to enrich briefs with semantic context:
  1. kb-embeddings    — top-K relevant KB chunks (discovery layer).
  2. auto-improvement — top-3 open improvement surfaces that touch the
                        same territory (consult-before-editing discipline).
  3. agent-context    — vector-pick the best-matched agent when `agent`
                        is omitted (cosine vs each agent's owned-KB centroid).

Plus the agent's own track record (closes the learning loop):
  4. recent misses    — open auto-improvement entries the agent itself
                        surfaced + its weakest RUBRIC_V1 dimensions from
                        the latest `slice-scores.ndjson` rows, rendered as a
                        `### Your recent misses (do not repeat)` block.

All caches are advisory — when the embedding provider is unreachable or a
cache is empty the tool degrades: `kb_references` /
`auto_improvement_context` / `recent_misses` become `[]`,
`suggested_agent` falls back to `"backend-engineer"`. A degradation is
NEVER silent: every swallowed failure appends a reason to `degraded`.

Every cache source is an injectable parameter of `compose_brief` (tests pass
fakes; nothing patches this module).

Output shape:
  {
    brief: str,                      # rendered brief in dispatch-engineer-tuning §4d shape
    suggested_agent: str,            # agent slug (picked or passed)
    auto_improvement_context: list,  # [{ts, kind, target, description, status}]
    kb_references: list,             # [{path, chunk_text, score}]
    recent_misses: list,             # [{ts, source, kind, target, text}]
    degraded: list[str],             # one reason per swallowed failure ([] = clean)
  }

Render shape (dispatch-engineer-tuning §4d):
  ## Engineer Brief — <description[:60]>
  ### Goal
  <description>
  ### Reference
  <top-kb-chunk links / titles>
  ### Your recent misses (do not repeat)   ← omitted when there are none
  <agent's own open drifts + weakest rubric dims>
  ### Scope
  <target_files list>
  ### Acceptance
  - TODO(architect) placeholder — the composer cannot derive "done" for a slice.
  ---
  Two-leg footer:
    Leg 1: commit early on the worker branch — a commit survives a harness kill.
    Leg 2: commit own branch, never push — return short-form per product-engineer §4.

KB § PATTERNS/architect/dispatch-engineer-tuning.md.
"""
from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

# Canonical cosine — single source at _embedding_corpus (N=7 consolidation).
from . import _embedding_corpus as _ec

_cosine = _ec.cosine
logger = logging.getLogger(__name__)

#: Signature of `auto_improvement.query` as used here (keyword-only args).
AiQuery = Callable[..., list[dict]]


def _note(degraded: list[str] | None, source: str, exc: BaseException | str) -> None:
    """Record a degradation reason — the non-silent half of every guarded call."""
    reason = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
    logger.warning("engineer_brief_compose degraded — %s: %s", source, reason)
    if degraded is not None:
        degraded.append(f"{source}: {reason}")


def _centroid(vecs: list[list[float]]) -> list[float]:
    """Average vector of a list of equal-length float lists. Returns [] if empty."""
    if not vecs:
        return []
    dim = len(vecs[0])
    c = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            c[i] += v[i]
    n = len(vecs)
    return [x / n for x in c]


# ── Embedding call (delegates to vectorize.embed_text) ───────────────────────
def _embed(
    text: str,
    *,
    embed_text: Callable[[str], dict] | None = None,
    degraded: list[str] | None = None,
) -> list[float]:
    """Return the embedding vector for `text`, or [] (reason noted) on failure."""
    try:
        if embed_text is None:
            from tools.noctus.dev.vectorize import embed_text
        result = embed_text(text)
    except Exception as exc:  # noqa: BLE001 — advisory layer; reason surfaced below
        _note(degraded, "embedding", exc)
        return []
    if result.get("ok") and result.get("vector"):
        return result["vector"]
    _note(degraded, "embedding", str(result.get("error") or "provider returned no vector"))
    return []


# ── Auto-improvement query ────────────────────────────────────────────────────
def _load_ai_query(degraded: list[str] | None) -> AiQuery | None:
    try:
        from tools.noctus.dev.auto_improvement import query
    except ImportError as exc:
        _note(degraded, "auto-improvement", exc)
        return None
    return query


def _query_auto_improvement(
    description: str,
    target_files: list[str],
    *,
    ai_query: AiQuery | None = None,
    degraded: list[str] | None = None,
) -> list[dict]:
    """Return top-3 open auto-improvement entries related to this task.

    Scores by text substring overlap across target_files + description;
    falls back to a simple recency-first fetch when the cache is empty.
    Each failed sub-query appends a reason to `degraded` (never swallowed).
    """
    if ai_query is None:
        ai_query = _load_ai_query(degraded)
        if ai_query is None:
            return []

    # Collect candidate entries — search by each target file path, deduplicate.
    seen_ids: set[int] = set()
    candidates: list[dict] = []
    for tf in target_files[:8]:  # cap queries for speed
        try:
            rows = ai_query(target=tf, open_only=True, limit=20)
            for r in rows:
                rid = r.get("rowid_alias") or id(r)
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    candidates.append(r)
        except Exception as exc:  # noqa: BLE001 — per-target; reason surfaced
            _note(degraded, f"auto-improvement query(target={tf!r})", exc)
            continue

    # Also fetch by description keywords (first 60 chars as a broad target search).
    keyword = description[:60]
    try:
        rows = ai_query(target=keyword, open_only=True, limit=20)
        for r in rows:
            rid = r.get("rowid_alias") or id(r)
            if rid not in seen_ids:
                seen_ids.add(rid)
                candidates.append(r)
    except Exception as exc:  # noqa: BLE001 — keyword leg; reason surfaced
        _note(degraded, "auto-improvement query(keyword)", exc)

    # If no candidates, return a recency-first sample.
    if not candidates:
        try:
            candidates = ai_query(open_only=True, limit=20)
        except Exception as exc:  # noqa: BLE001 — recency fallback; reason surfaced
            _note(degraded, "auto-improvement query(recency)", exc)
            return []

    # Score by description-overlap (simple term count, no embedding needed here —
    # the auto-improvement entries are structural, not semantic).
    desc_lower = description.lower()
    tf_set = {tf.lower() for tf in target_files}

    def _score(entry: dict) -> float:
        score = 0.0
        entry_desc = (entry.get("description") or "").lower()
        entry_target = (entry.get("target") or "").lower()
        # Exact target path match is highest signal.
        if entry_target in tf_set:
            score += 2.0
        # Keyword overlap in description.
        words = [w for w in desc_lower.split() if len(w) > 4]
        for word in words:
            if word in entry_desc:
                score += 0.2
        return score

    ranked = sorted(candidates, key=_score, reverse=True)
    out = []
    for entry in ranked[:3]:
        out.append({
            "ts": entry.get("ts", ""),
            "kind": entry.get("kind", ""),
            "target": entry.get("target", ""),
            "description": entry.get("description", ""),
            "status": entry.get("status", ""),
        })
    return out


# ── KB search ────────────────────────────────────────────────────────────────
def _query_kb(
    description: str,
    *,
    kb_search: Callable[..., list[dict]] | None = None,
    degraded: list[str] | None = None,
) -> list[dict]:
    """Return top-3 KB chunks most semantically relevant to `description`."""
    try:
        if kb_search is None:
            from tools.noctus.dev.kb_embeddings import search as kb_search
        hits = kb_search(description, top_k=3)
        return [
            {
                "path": h.get("path", ""),
                "chunk_text": (h.get("chunk_text") or "")[:300],
                "score": round(float(h.get("score", 0.0)), 4),
            }
            for h in hits
        ]
    except Exception as exc:  # noqa: BLE001 — advisory layer; reason surfaced
        _note(degraded, "kb-embeddings", exc)
        return []


# ── Recent misses (the agent's own track record) ─────────────────────────────
#: auto-improvement kinds that describe something the agent got wrong / left.
MISS_KINDS = frozenset({"drift", "improvement", "finding", "phase-learning"})
#: How many of the agent's latest scored slices feed the rubric leg.
RUBRIC_WINDOW = 5
#: A dimension whose mean is below this (0-4 scale) counts as a miss.
RUBRIC_MISS_BELOW = 3.0
#: At most this many weak rubric dimensions are reported.
RUBRIC_MAX_DIMS = 2


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _weak_rubric_dims(agent: str, rows: list[dict]) -> list[dict]:
    """The agent's weakest RUBRIC_V1 dimensions over its latest scored slices."""
    from tools.noctus.dev.dispatch_token_log import RUBRIC_V1

    mine = sorted(
        (r for r in rows if r.get("agent") == agent and isinstance(r.get("q"), dict)),
        key=lambda r: r.get("ts") or "",
        reverse=True,
    )[:RUBRIC_WINDOW]
    if not mine:
        return []
    latest_ts = mine[0].get("ts") or ""
    weak: list[tuple[float, str, int]] = []
    for dim in RUBRIC_V1["weights"]:
        vals = [float(r["q"][dim]) for r in mine if r["q"].get(dim) is not None]
        if vals and (mean := sum(vals) / len(vals)) < RUBRIC_MISS_BELOW:
            weak.append((mean, dim, len(vals)))
    weak.sort()
    hi = RUBRIC_V1["scale"][1]
    return [
        {
            "ts": latest_ts,
            "source": "rubric",
            "kind": "rubric",
            "target": f"{dim} {RUBRIC_V1['names'][dim]}",
            "text": (
                f"{RUBRIC_V1['names'][dim]} scored {mean:.1f}/{hi} on average "
                f"over your last {n} scored slice(s)"
            ),
        }
        for mean, dim, n in weak[:RUBRIC_MAX_DIMS]
    ]


def _recent_misses(
    agent: str,
    *,
    limit: int = 5,
    ai_query: AiQuery | None = None,
    score_rows: Callable[[], list[dict]] | None = None,
    degraded: list[str] | None = None,
) -> list[dict]:
    """The agent's own recent misses — newest first, deduplicated, bounded.

    Two legs: (a) open auto-improvement entries the agent itself surfaced
    (kinds in MISS_KINDS); (b) its weakest RUBRIC_V1 dimensions from the
    latest slice-scores rows (`noctus.team.agent_metrics.load_rows`).
    Returns `[{ts, source, kind, target, text}]`; a failing leg notes a
    reason in `degraded` and the other leg still contributes.
    """
    if not agent or limit <= 0:
        return []
    found: list[dict] = []

    if ai_query is None:
        ai_query = _load_ai_query(degraded)
    if ai_query is not None:
        try:
            rows = ai_query(agent=agent, open_only=True, limit=50)
        except Exception as exc:  # noqa: BLE001 — advisory leg; reason surfaced
            _note(degraded, "recent-misses auto-improvement", exc)
            rows = []
        for r in rows:
            if r.get("kind") not in MISS_KINDS or not (r.get("description") or "").strip():
                continue
            found.append({
                "ts": r.get("ts") or "",
                "source": "auto-improvement",
                "kind": r.get("kind", ""),
                "target": r.get("target") or "*",
                "text": r["description"].strip(),
            })

    try:
        if score_rows is None:
            from tools.noctus.team.agent_metrics import load_rows as score_rows
        found += _weak_rubric_dims(agent, score_rows())
    except Exception as exc:  # noqa: BLE001 — advisory leg; reason surfaced
        _note(degraded, "recent-misses slice-scores", exc)

    found.sort(key=lambda m: m["ts"], reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for m in found:
        key = _norm(m["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) >= limit:
            break
    return out


# ── Agent routing ─────────────────────────────────────────────────────────────
_FALLBACK_AGENT = "backend-engineer"

def _pick_agent(query_vec: list[float], *, degraded: list[str] | None = None) -> str:
    """Pick the best-matched agent by cosine vs each agent's owned-KB centroid.

    Returns the agent slug. Falls back to _FALLBACK_AGENT if:
      - agent-context cache is unavailable / empty
      - embedding is unavailable
      - no agent has owned KB chunks in the kb-embeddings cache
    """
    if not query_vec:
        _note(degraded, "agent-routing", f"no query embedding; fell back to {_FALLBACK_AGENT}")
        return _FALLBACK_AGENT

    try:
        from tools.noctus.dev.agent_context_cache import list_agents, lookup
        from tools.noctus.dev.kb_embeddings import _load_all_chunk_vectors  # internal
    except ImportError as exc:
        _note(degraded, "agent-routing", exc)
        return _FALLBACK_AGENT

    try:
        agents = list_agents()
        if not agents:
            return _FALLBACK_AGENT

        all_rows = _load_all_chunk_vectors()  # [(path, chunk_idx, chunk_text, vec), …]
        if not all_rows:
            return _FALLBACK_AGENT

        best_agent = _FALLBACK_AGENT
        best_score = -1.0

        for agent_name in agents:
            try:
                bundle = lookup(agent_name)
                if not bundle.get("ok"):
                    continue
                owned_paths = {o["path"] for o in bundle.get("owned_kb", [])}
            except Exception as exc:  # noqa: BLE001 — per-agent; reason surfaced
                _note(degraded, f"agent-routing lookup({agent_name})", exc)
                continue

            if not owned_paths:
                continue

            # Collect vectors for chunks belonging to this agent's owned KB paths.
            agent_vecs = [vec for path, _, _, vec in all_rows if path in owned_paths]
            if not agent_vecs:
                continue

            centroid = _centroid(agent_vecs)
            if not centroid:
                continue

            score = _cosine(query_vec, centroid)
            if score > best_score:
                best_score = score
                best_agent = agent_name

        return best_agent

    except Exception as exc:  # noqa: BLE001 — advisory layer; reason surfaced
        _note(degraded, "agent-routing", exc)
        return _FALLBACK_AGENT


# ── Brief renderer ────────────────────────────────────────────────────────────
#: SINGLE SOURCE of the pre-return checklist. Appended to every composed brief;
#: `.claude/agents/product-engineer.md` §3 points here rather than restating it.
#: Born of two 2026-10-24 defects: a branch added hooks a page harness did not
#: stub (only the tests next to the change were run -> merged tip red in CI),
#: and 5 branches bounced at the pre-push doc-staleness gate after returning.
BEFORE_RETURNING_BLOCK = (
    "### Before returning (mandatory - bounces at integrate otherwise)\n"
    "1. Run the FULL suite of every product/package you touched, not only the "
    "files next to your change: `vitest run` (`npm test`) in each touched "
    "`products/<slug>/frontend` and `seed/**` frontend, `pytest` in each touched "
    "backend. A page harness that does not stub a hook you added fails only here.\n"
    "2. `mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --check-doc-staleness "
    "--doc-range origin/dev..HEAD` from your worktree must be clean: update each "
    "listed doc, or add `Docs-Reviewed: <doc> - <why still accurate>` to a commit.\n"
    "3. Added a `check_*` detector => run `pytest mcp/noctusai/tests/"
    "test_compliance.py::TestCheckDetectorHasRegressionTest` (needs a "
    "`class Test<DetectorCamel>`; the `keeper_meta` gate blocks integrate "
    "otherwise).\n"
    "4. Commit everything; report the commands and results in your return."
)


def _open_findings(target_files: list[str], degraded: list[str] | None) -> list[str]:
    """Open rows of every registered living ledger for the product / agent scopes `target_files` touch."""
    scopes: list[str] = []
    for tf in target_files:
        parts = tf.replace("\\", "/").split("/")
        scope = parts[1] if parts[0] == "products" and len(parts) > 1 else ("seed" if parts[0] == "seed" else None)
        if scope and scope not in scopes:
            scopes.append(scope)
    out: list[str] = []
    try:
        from tools.noctus.dev import findings_ledger

        for sc in scopes:
            out += findings_ledger.open_for_scope(sc)
    except Exception as exc:  # noqa: BLE001 -- a brief without findings is degraded, never silent
        _note(degraded, "findings_ledger", exc)
    return out


def _source_warnings(
    description: str, target_files: list[str], sources: dict[str, str] | None, degraded: list[str],
) -> list[dict]:
    """F4 lint: names of absorption SOURCES (derived from the absorptions ledger) in the brief, outside a slice."""
    from . import absorption_sources as _abs
    live = sources is None
    sources_resolved = sources
    if live:
        try:
            from settings import LEDGER_ROOT
            sources_resolved, err = _abs.load_sources(LEDGER_ROOT)
        except Exception as exc:  # noqa: BLE001 - advisory lint, never blocks a brief; the reason is not silent
            sources_resolved, err = {}, f"{type(exc).__name__}: {exc}"
        if err:
            _note(degraded, "absorption-sources", err)
    warns = _abs.lint_text_for_source_reference("\n".join([description, *target_files]), sources_resolved)
    if warns and live:  # F6: a live fire is a gate-fire row (injected sources = a test, never telemetry)
        from .gate_alignment import record_event
        for w in warns:
            record_event("lint:absorption-source-reference", "warn", kind="lint", target=w["source"],
                         reason=w["message"], source="engineer_brief_compose")
    return warns


def _render_brief(
    *,
    description: str,
    target_files: list[str],
    agent: str,
    kb_references: list[dict],
    auto_improvement_context: list[dict],
    recent_misses: list[dict] | None = None,
    open_findings: list[str] | None = None,
    source_warnings: list[dict] | None = None,
) -> str:
    """Render the brief in dispatch-engineer-tuning §4d shape."""
    title_slug = description[:60].rstrip()
    lines: list[str] = [
        f"## Engineer Brief — {title_slug}",
        "",
        "### Goal",
        description,
        "",
    ]

    # Reference block — KB chunks.
    lines.append("### Reference")
    if kb_references:
        for ref in kb_references:
            path = ref.get("path", "")
            score = ref.get("score", 0.0)
            first_line = (ref.get("chunk_text") or "").splitlines()[0][:100] if ref.get("chunk_text") else ""
            lines.append(f"- `KB § {path}` (score={score:.3f}) — {first_line}")
    else:
        lines.append("- (KB embeddings cache empty or embedding provider unreachable — use `KB § INDEX.md` + grep)")

    # The agent's own recent misses — omitted entirely when there are none.
    if recent_misses:
        lines += ["", "### Your recent misses (do not repeat)"]
        for m in recent_misses:
            short = (m.get("text") or "")[:160].replace("\n", " ")
            day = (m.get("ts") or "")[:10] or "?"
            lines.append(f"- [{m.get('kind', '?')}] {m.get('target', '*')} — {short} ({day})")

    # Living findings ledgers (access-tier burn-down, Julia's mistakes, ...): the scope's open rows come first.
    if open_findings:
        lines += ["", "### Open findings in your scope (fix-on-contact; the ledger is written only by `noctus.dev.findings_ledger`)"]
        lines += [f"- {ln.strip()}" for ln in open_findings]

    # F4 (Phase 5a): a brief naming a frozen absorption SOURCE outside an absorption slice (warn, never blocks).
    if source_warnings:
        lines += ["", "### Frozen absorption source named (warning - reference the canon instead)"]
        lines += [f"- `{w['source']}`: {w['message']}" for w in source_warnings]

    # Auto-improvement context block.
    if auto_improvement_context:
        lines += ["", "### Auto-improvement context (consult before editing)"]
        for entry in auto_improvement_context:
            short = (entry.get("description") or "")[:120].replace("\n", " ")
            lines.append(f"- [{entry.get('kind', '?')}] {entry.get('target', '?')} — {short}")

    lines += ["", "### Scope"]
    for tf in target_files:
        lines.append(f"- `{tf}`")

    # The composer cannot know what "done" means for an arbitrary slice, so the
    # Acceptance block is an explicit TODO for the architect — never criteria
    # borrowed from some other feature (it used to ship this tool's OWN
    # acceptance lines in every brief it composed).
    lines += [
        "",
        "### Acceptance",
        "- TODO(architect): the narrowest check that proves this slice — one test "
        "file / one product build / one grep that must return zero. Fill in before "
        "dispatch.",
        "",
        "---",
        "",
        f"**Suggested agent:** `{agent}`",
        "",
        "**Leg 1 (harness safety):** Commit early on your worker branch — a commit "
        "survives a harness kill; tidy un-reported commits with `git commit --amend` / "
        "`git reset --soft` before you return.",
        "",
        "**Leg 2 (return shape):** Commit your own worker branch (product-engineer §3), "
        "never push. Return short-form per product-engineer §4: commit SHAs, the scoped "
        "check + pass/fail, the three footer legs. The architect integrates.",
        "",
        BEFORE_RETURNING_BLOCK,
    ]
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────
def compose_brief(
    target_files: list[str],
    description: str,
    agent: str | None = None,
    *,
    embed_text: Callable[[str], dict] | None = None,
    ai_query: AiQuery | None = None,
    kb_search: Callable[..., list[dict]] | None = None,
    pick_agent: Callable[[list[float]], str] | None = None,
    score_rows: Callable[[], list[dict]] | None = None,
    misses_limit: int = 5,
    sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Auto-compose an engineer dispatch brief.

    Steps:
      1. Embed `description` via vectorize.embed_text.
      2. Query auto-improvement.ndjson cache for related open surfaces.
      3. Query kb-embeddings cache for top-3 related KB chunks.
      4. If `agent` is None, cosine-pick best agent from agent-context cache.
      5. Collect the agent's own recent misses (open drifts + weak rubric dims).
      6. Render the brief in dispatch-engineer-tuning §4d shape.

    Every source is injectable (`embed_text`, `ai_query`, `kb_search`,
    `pick_agent`, `score_rows`); None = the live cache. Degrade is never
    silent: each swallowed failure appends a reason to `degraded`.

    Returns:
      {
        brief: str,
        suggested_agent: str,
        auto_improvement_context: list[dict],
        kb_references: list[dict],
        recent_misses: list[dict],
        degraded: list[str],
      }
    """
    degraded: list[str] = []

    # Step 1: embed the description.
    query_vec = _embed(description, embed_text=embed_text, degraded=degraded)

    # Step 2: auto-improvement context.
    ai_ctx = _query_auto_improvement(
        description, target_files, ai_query=ai_query, degraded=degraded,
    )

    # Step 3: KB references.
    kb_refs = _query_kb(description, kb_search=kb_search, degraded=degraded)

    # Step 4: agent selection.
    if agent is not None:
        suggested_agent = agent
    elif pick_agent is not None:
        suggested_agent = pick_agent(query_vec)
    else:
        suggested_agent = _pick_agent(query_vec, degraded=degraded)

    # Step 5: the agent's own recent misses.
    misses = _recent_misses(
        suggested_agent, limit=misses_limit, ai_query=ai_query,
        score_rows=score_rows, degraded=degraded,
    )

    # Step 5b: the open rows of every living findings ledger for the scopes the target files sit in.
    open_findings = _open_findings(target_files, degraded)

    # Step 5c (F4): frozen absorption sources named in the brief text / targets, outside an absorption slice.
    source_warnings = _source_warnings(description, target_files, sources, degraded)

    # Step 6: render.
    brief = _render_brief(
        description=description,
        target_files=target_files,
        agent=suggested_agent,
        kb_references=kb_refs,
        auto_improvement_context=ai_ctx,
        recent_misses=misses,
        open_findings=open_findings,
        source_warnings=source_warnings,
    )

    return {
        "brief": brief,
        "suggested_agent": suggested_agent,
        "auto_improvement_context": ai_ctx,
        "kb_references": kb_refs,
        "recent_misses": misses,
        "open_findings": open_findings,
        "source_warnings": source_warnings,
        "degraded": degraded,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.engineer_brief_compose",
        description=(
            "Auto-compose a dispatch brief for an engineer by querying the "
            "keeper-mirror caches (kb-embeddings, auto-improvement, agent-context). "
            "Returns {brief, suggested_agent, auto_improvement_context, kb_references, "
            "recent_misses, degraded}. The brief carries a 'Your recent misses (do not "
            "repeat)' block: the agent's own open drifts + weakest rubric dimensions. "
            "Degrades (never silently) when a cache/provider is unreachable — each "
            "reason lands in `degraded`. "
            "KB § PATTERNS/architect/dispatch-engineer-tuning.md."
        ),
    )
    def _compose(
        target_files: list[str],
        description: str,
        agent: str | None = None,
    ) -> dict:
        return compose_brief(
            target_files=target_files,
            description=description,
            agent=agent,
        )


__all__ = ["compose_brief", "register"]
