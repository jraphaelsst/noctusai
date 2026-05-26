# Dispatch warmup — pre-dispatch context bundle for the brief

**What it is.** Compose-time companion to `engineer_brief_compose`: given target_files + agent_name + brief description, returns formatted markdown the architect can paste into the brief's "## Context warmup" section. Removes wasted engineer-first-turn reads. Born v4.0-beta follow-up (F9).

## What it returns

A markdown block with:
1. **Agent body excerpt** + `owns_kb:` territory list (from `agent_context_cache.lookup`).
2. **Relevant KB chunks** (top-3 from `kb_embeddings.search` anchored on description + target files).
3. **Relevant code symbols** (top-3 from `code_embeddings.search` for cross-product reference).
4. **Related auto-improvement entries** (top-3 from `kb_recurrence_radar.consult` — decisions in flight).

All ALREADY formatted; the architect copy-pastes into the brief.

## Why opt-in (not auto-injected by engineer_brief_compose)

- The architect curates. Auto-inject would bloat briefs.
- Warmup content can be stale (cached vectors); architect judges relevance before pasting.
- Some briefs don't need warmup (small file-disjoint fix); auto-injection wastes tokens.

## API

```python
dispatch_warmup.warmup(
    agent_name: str,
    description: str | None = None,
    target_files: list[str] | None = None,
    kb_top_k: int = 3,
    code_top_k: int = 3,
    ai_top_k: int = 3,
) -> dict
```

## Composes with

- `engineer_brief_compose` (the upstream tool the warmup feeds).
- `agent_context_cache.lookup` (agent bundle source).
- `kb_embeddings.search`, `code_embeddings.search`, `kb_recurrence_radar.consult` (semantic feeders).

## Anti-patterns

- **DON'T** auto-inject the full warmup into briefs. Architect judges what's relevant.
- **DON'T** lower `top_k` per source so much that warmup misses important context.
