# Funnel self-satisfies its preconditions

> **Rule.** A shared funnel / single-entry helper (the one place all callers
> route through) must **satisfy its own config/env preconditions**, not document
> them as "caller MUST call `setup()` first." An offloaded precondition is a
> **drift generator**: it works for the one caller who remembers (usually the
> CLI, which set the precedent) and silently breaks every other caller path
> (the MCP server, a hook, a test, a fresh import).

## The provenance — the recurring "LLM not configured" drift (2026-05-30)

The seed LLM client requires `configure_llm(config)` once before any embed/chat.
A product app auto-wires it via `create_product_app()`. The noctusai dev toolkit
is **not** a product app, so something had to call it — and only the CLI did
(`cli._ensure_llm_configured`, which also auto-sources `.env`). The single embed
funnel `_embedding_corpus.embed_sync` documented the precondition rather than
satisfying it:

```python
# BEFORE — the funnel offloads its precondition:
def embed_sync(text):
    """... Caller MUST ensure configure_llm() was called
    (the noctusai CLI's _ensure_llm_configured helper does this) ..."""
    from noctusai_lib.integrations.llm import generate_embedding
    return run_coro_blocking(generate_embedding(text))   # 💥 RuntimeError if no caller did
```

Every non-CLI caller forgot. The live FastMCP server runs every tool in-process
**without** sourcing `.env` or calling `configure_llm`, so
`refresh_memory_embeddings` / `kb_embeddings_refresh` / `code_embeddings_refresh`
/ `find_reusable_component` **all** raised `"LLM not configured. Call
configure_llm(config) at application startup"` whenever invoked from the MCP
server — repeatedly, because each fix only ever patched the *caller* that hit it,
never the funnel. (Sibling-but-distinct from the asyncio-bridge drift
[run_coro_blocking] and the `.env`-not-sourced symptom — same funnel, different
offloaded precondition.)

## The fix — satisfy the precondition AT the funnel

```python
# AFTER — the funnel self-configures (one bootstrap, every caller benefits):
def embed_sync(text):
    from noctusai_lib.integrations.llm import generate_embedding
    ensure_llm_configured()      # ← funnel satisfies its OWN precondition
    _throttle_embed()
    return run_coro_blocking(generate_embedding(text))
```

`ensure_llm_configured()` lives in **one** module
(`mcp/noctusai/tools/noctus/dev/_llm_bootstrap.py`): idempotent, auto-sources
`.env` (repo root + primary worktree, since `.env` is gitignored and the MCP
server is launched without it), graceful-degrades to `False` when the lib isn't
importable (fresh clone / no key) instead of crashing. The CLI's
`_ensure_llm_configured` now **delegates** to it (DRY — one source for the
`.env`-sourcing + `configure_llm` logic). Net: CLI, MCP server, pre-push hook
and tests all behave identically.

## How to apply (the general rule, not just LLM)

- Writing/auditing a **single funnel** (the consolidated point all callers route
  through — embed, http client, db session, an adapter factory)? Make it
  **self-satisfy** lazy/idempotent config: if it needs `setup()`, it calls
  `ensure_setup()` itself; it does not put "caller must call setup() first" in a
  docstring.
- A docstring that says **"Caller MUST …"** for a *config/bootstrap* step is the
  smell. Reading-time discipline ≠ structural guarantee — the next caller won't
  read it. Convert the instruction into a self-call.
- Keep the bootstrap **one module**, delegated-to by every entry (CLI, server,
  hook). Duplicating it is how the CLI and the server drift apart again.
- **Verify on the path that breaks, not the one that works.** The CLI "worked"
  for months; the bug only ever showed on the MCP-server path. Reproduce the
  failing caller (no pre-config, no `.env` in env) — see the regression test
  `test_llm_bootstrap.py::TestEmbedSyncSelfConfigures`.

## Structural guard — the keeper (2026-05-31)

The prose above is discipline; the keeper is the structural guarantee. After the
SECOND funnel (`vectorize.embed_text`) needed the bootstrap added by hand
(2026-05-31, sibling of the `embed_sync` patch the day before), the recurrence
was ratified and locked:

**`check_embed_funnel_self_configures`** (severity `high`) — AST-walks every
`.py` under `mcp/noctusai/tools/`; any function that makes a DIRECT
`generate_embedding(...)` call MUST also call `ensure_llm_configured(...)` in the
same body. Both live funnels (`embed_sync` + `embed_text`) pass; everything else
routes through them and holds no direct embed call, so it is correctly ignored.
Zero violations exist today, so any hit is a genuine regression — a new direct
embedder that forgot the bootstrap, before it fails at runtime on the MCP-server
path. Exempt: `_llm_bootstrap.py` (defines the bootstrap) + `compliance.py` (the
keeper's own source). CLI: `--check-embed-funnel-self-configures`. Test:
`test_embed_funnel_self_configures.py::TestEmbedFunnelSelfConfigures`.

This is the N=2 ratified-promotion variant of the keeper that was DEFERRED at the
N=1 s3 codification ("promote at N≥2 if another funnel offloads config") — the
second funnel arrived, so the keeper shipped.

## Provenance + surfaces

- Born: session 2026-05-30 (`fix/realtime-dep-resolver-thrash` wrap-up surfaced
  it via `refresh_memory_embeddings` failing in the MCP server). Auto-improvement
  ledger: the s1 drift + its s3 codification; the s2→s4 keeper promotion 2026-05-31.
- Code: `_llm_bootstrap.ensure_llm_configured` · `_embedding_corpus.embed_sync` ·
  `vectorize.embed_text` (both self-configure) · `cli._ensure_llm_configured`
  (delegates) · tests `test_llm_bootstrap.py` + `test_embed_funnel_self_configures.py`.
- Keeper: `compliance.check_embed_funnel_self_configures` (CLI
  `--check-embed-funnel-self-configures`).
- Memory: `feedback_funnel_self_satisfies_preconditions`.
- Composes with: `KB § PATTERNS/common/vectorize-embed-cache-framework.md` (the
  embed funnel) · `KB § 01-PHILOSOPHY.md` (no silent errors · fix-at-root).
