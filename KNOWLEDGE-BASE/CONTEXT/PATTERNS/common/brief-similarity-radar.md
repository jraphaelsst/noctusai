# Brief similarity radar — pre-dispatch "did we do this last week?"

**What it is.** Pre-dispatch sensor: given a new draft brief, find past briefs (per-user ledger) semantically similar + suggest the closest-matching specialist agent via owns_kb centroid. Born v4.0-beta follow-up (F7).

## Two questions it answers

1. **Was this dispatched recently?** Reads `brief_ledger.ndjson` (per-user, gitignored), embeds the draft, scores cosine vs. past briefs within the time window (default 7 days). Returns ranked matches above `min_score=0.5`.
2. **Which agent fits?** Embeds the draft (+ optional target files) and scores against each agent's compact bundle (`agent_context_cache.lookup(agent).body`). Returns ranked agents + a suggested top pick.

## Why per-user, not committed

Briefs are ephemeral architect work-product. Cross-user aggregation is noise unless multiple architects work the same codebase. Keep per-user; promote later if needed.

## API

```python
brief_similarity_radar.similarity_check(description, since_days=7, top_k=5, min_score=0.5) -> dict
brief_similarity_radar.route_to_agent(description, target_files=None) -> dict
```

## When to use

- BEFORE composing a new brief: check the ledger for near-duplicates → consult the past engineer's work instead of duplicating.
- BEFORE picking an agent: ask the centroid which specialist owns the territory closest to the brief.

## Composes with

- `brief_ledger` (the storage layer feeding the radar).
- `engineer_brief_compose` (the upstream tool that writes to the ledger).
- `agent_context_cache` (the source of agent centroids).
- [`kb-recurrence-radar`](kb-recurrence-radar.md) — sister sensor for auto-improvement entries.

## Anti-patterns

- **DON'T** auto-skip a brief because the radar found a match. The match is a HINT (review past work); a fresh brief may still be appropriate.
- **DON'T** auto-route to the suggested agent. The suggestion is a STARTING POINT; architect judgment trumps.
