"""noctus.dev.engineer_brief_compose — auto-compose engineer dispatch briefs.

Queries three keeper-mirror caches to enrich briefs with semantic context:
  1. kb-embeddings    — top-K relevant KB chunks (discovery layer).
  2. auto-improvement — top-3 open improvement surfaces that touch the
                        same territory (consult-before-editing discipline).
  3. agent-context    — vector-pick the best-matched agent when `agent`
                        is omitted (cosine vs each agent's owned-KB centroid).

All three caches are advisory — when the embedding provider is unreachable
or a cache is empty the tool gracefully degrades: `kb_references` and
`auto_improvement_context` become `[]`, `suggested_agent` falls back to
`"backend-engineer"` (safest default for code-level work).

Output shape:
  {
    brief: str,                      # rendered brief in engineer-default §11 shape
    suggested_agent: str,            # agent slug (picked or passed)
    auto_improvement_context: list,  # [{ts, kind, target, description, status}]
    kb_references: list,             # [{path, chunk_text, score}]
  }

Render shape (engineer-default §11):
  ## Engineer Brief — <description[:60]>
  ### Goal
  <description>
  ### Reference
  <top-kb-chunk links / titles>
  ### Scope
  <target_files list>
  ### Acceptance
  - MCP / CLI round-trip is importable and exercised by tests.
  - Tests pass (`cd mcp/noctusai && pytest tests/ -q`).
  - Existing keeper tests still pass.
  ---
  Two-leg footer:
    Leg 1: write a /tmp/*.patch file early so your work survives harness kill.
    Leg 2: stage-only (no commit) — return short-form per engineer-default §3+§7.

KB § PATTERNS/dispatch-engineer-tuning.md.
"""
from __future__ import annotations

import math
from typing import Any

# ── Cosine (pure-Python; no numpy dep) ──────────────────────────────────────
def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity between two equal-length float lists."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


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
def _embed(text: str) -> list[float]:
    """Return the embedding vector for `text`, or [] on any failure."""
    try:
        from tools.noctus.dev.vectorize import embed_text
        result = embed_text(text)
        if result.get("ok") and result.get("vector"):
            return result["vector"]
        return []
    except Exception:  # noqa: BLE001 — graceful degrade
        return []


# ── Auto-improvement query ────────────────────────────────────────────────────
def _query_auto_improvement(description: str, target_files: list[str]) -> list[dict]:
    """Return top-3 open auto-improvement entries related to this task.

    Scores by text substring overlap across target_files + description;
    falls back to a simple recency-first fetch when the cache is empty.
    """
    try:
        from tools.noctus.dev.auto_improvement import query as ai_query
    except ImportError:
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
        except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        pass

    # If no candidates, return a recency-first sample.
    if not candidates:
        try:
            candidates = ai_query(open_only=True, limit=20)
        except Exception:  # noqa: BLE001
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
def _query_kb(description: str) -> list[dict]:
    """Return top-3 KB chunks most semantically relevant to `description`."""
    try:
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
    except Exception:  # noqa: BLE001
        return []


# ── Agent routing ─────────────────────────────────────────────────────────────
_FALLBACK_AGENT = "backend-engineer"

def _pick_agent(query_vec: list[float]) -> str:
    """Pick the best-matched agent by cosine vs each agent's owned-KB centroid.

    Returns the agent slug. Falls back to _FALLBACK_AGENT if:
      - agent-context cache is unavailable / empty
      - embedding is unavailable
      - no agent has owned KB chunks in the kb-embeddings cache
    """
    if not query_vec:
        return _FALLBACK_AGENT

    try:
        from tools.noctus.dev.agent_context_cache import list_agents, lookup
        from tools.noctus.dev.kb_embeddings import _load_all_chunk_vectors  # internal
    except ImportError:
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
            except Exception:  # noqa: BLE001
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

    except Exception:  # noqa: BLE001
        return _FALLBACK_AGENT


# ── Brief renderer ────────────────────────────────────────────────────────────
def _render_brief(
    *,
    description: str,
    target_files: list[str],
    agent: str,
    kb_references: list[dict],
    auto_improvement_context: list[dict],
) -> str:
    """Render the brief in engineer-default §11 shape."""
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

    # Auto-improvement context block.
    if auto_improvement_context:
        lines += ["", "### Auto-improvement context (consult before editing)"]
        for entry in auto_improvement_context:
            short = (entry.get("description") or "")[:120].replace("\n", " ")
            lines.append(f"- [{entry.get('kind', '?')}] {entry.get('target', '?')} — {short}")

    lines += ["", "### Scope"]
    for tf in target_files:
        lines.append(f"- `{tf}`")

    lines += [
        "",
        "### Acceptance",
        "- MCP tool `noctus.dev.engineer_brief_compose(target_files, description, agent=None)` returns the dict.",
        "- CLI command works: `python mcp/noctusai/cli.py --compose-brief --files X,Y --description \"...\"`.",
        "- Tests pass (`cd mcp/noctusai && pytest tests/ -q`).",
        "- Existing keeper tests (test_agent_kb_alignment, test_agent_context_cache) still pass.",
        "",
        "---",
        "",
        f"**Suggested agent:** `{agent}`",
        "",
        "**Leg 1 (harness safety):** Write a `/tmp/<slug>.patch` early via "
        "`git diff HEAD > /tmp/<slug>.patch` — the harness watchdog kills stalled agents "
        "and the patch survives.",
        "",
        "**Leg 2 (return shape):** Stage-only, no commit. Return short-form per "
        "engineer-default §3+§7: staged files, test command, pass/fail, findings.md entry "
        "(if any). The architect integrates.",
    ]
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────
def compose_brief(
    target_files: list[str],
    description: str,
    agent: str | None = None,
) -> dict[str, Any]:
    """Auto-compose an engineer dispatch brief.

    Steps:
      1. Embed `description` via vectorize.embed_text.
      2. Query auto-improvement.ndjson cache for related open surfaces.
      3. Query kb-embeddings cache for top-3 related KB chunks.
      4. If `agent` is None, cosine-pick best agent from agent-context cache.
      5. Render the brief in engineer-default §11 shape.

    Graceful-degrade: if the embedding provider is unreachable or any cache
    is missing, returns the brief with `kb_references=[]` and/or
    `auto_improvement_context=[]`.

    Returns:
      {
        brief: str,
        suggested_agent: str,
        auto_improvement_context: list[dict],
        kb_references: list[dict],
      }
    """
    # Step 1: embed the description.
    query_vec = _embed(description)

    # Step 2: auto-improvement context.
    ai_ctx = _query_auto_improvement(description, target_files)

    # Step 3: KB references.
    kb_refs = _query_kb(description)

    # Step 4: agent selection.
    if agent is None:
        suggested_agent = _pick_agent(query_vec)
    else:
        suggested_agent = agent

    # Step 5: render.
    brief = _render_brief(
        description=description,
        target_files=target_files,
        agent=suggested_agent,
        kb_references=kb_refs,
        auto_improvement_context=ai_ctx,
    )

    return {
        "brief": brief,
        "suggested_agent": suggested_agent,
        "auto_improvement_context": ai_ctx,
        "kb_references": kb_refs,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.engineer_brief_compose",
        description=(
            "Auto-compose a dispatch brief for an engineer by querying the "
            "keeper-mirror caches (kb-embeddings, auto-improvement, agent-context). "
            "Returns {brief, suggested_agent, auto_improvement_context, kb_references}. "
            "Graceful-degrade when embedding provider is unreachable. "
            "KB § PATTERNS/dispatch-engineer-tuning.md."
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
