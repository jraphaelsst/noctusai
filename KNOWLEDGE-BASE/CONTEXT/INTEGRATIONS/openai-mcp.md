# OpenAI connector MCP — `mcp/openai_mcp/`

> OpenAI API surface (embed / chat / vision / transcription) + semantic
> search over all 4 indexed corpora, exposed as LLM-callable `openai.*`
> MCP tools. Composes `mcp/_kit` (same shape as vista / meta / google /
> github). Shipped v4.0.

## Why this connector exists

The platform did embeddings + semantic search internally via `kb_embeddings.py`
+ `code_embeddings.py` (later `memory_embeddings.py` + `corpus_embeddings.py`),
but the underlying OpenAI capabilities — chat, vision, transcription — had no
MCP surface. An agent couldn't send an audio file to transcribe or an image to
analyze. This connector closes that gap and provides a clean facade over the
4 search engines too, so semantic search is reachable from any MCP-aware host.

## Tool surface (9 tools)

| Tool | Kind | What it does |
|---|---|---|
| `openai.embed` | READ | Text → 1536-D vector (text-embedding-3-small default) |
| `openai.chat` | READ | Chat completion (gpt-4o-mini default; pass ordered messages) |
| `openai.vision` | READ | Image + question → text (gpt-4o; accepts URL or local path) |
| `openai.transcribe` | READ | Audio file → text (whisper-1; auto-detect language) |
| `openai.search.kb` | READ | Semantic search over `KNOWLEDGE-BASE/**/*.md` |
| `openai.search.code` | READ | Semantic search over `mcp/**` + `noctusai_lib/**` + `products/seed/**` |
| `openai.search.memory` | READ | Semantic search over agent memory (out-of-repo) |
| `openai.search.corpus` | READ | Semantic search over CHANGELOG + templates + agents-full + skills + history; pass `source_type` to scope |
| `openai.diagnostics.connection_status` | READ | Never-faked READY/UNCONFIGURED signal — call before assuming any other tool works |

All tools are READ-only. No fine-tuning / file-upload / assistant CRUD / model
creation in this connector — these would be account-mutating + need separate
deliberate provisioning, not session-level access.

## Settings

Config resolves from (in precedence order):
1. Explicit kwargs to `OpenAISettings(...)` (test seam)
2. Process env (`OPENAI_API_KEY`, `OPENAI_DEFAULT_*_MODEL`)
3. Co-located `mcp/openai_mcp/.env`
4. **Repo-root `/.env`** (the platform's single shared secret)

| Env var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required.** Auto-loaded from repo-root `.env`. |
| `OPENAI_DEFAULT_CHAT_MODEL` | `gpt-4o-mini` | Chat completion model |
| `OPENAI_DEFAULT_EMBEDDING_MODEL` | `text-embedding-3-small` | 1536-D embeddings |
| `OPENAI_DEFAULT_VISION_MODEL` | `gpt-4o` | Vision/image analysis |
| `OPENAI_DEFAULT_AUDIO_MODEL` | `whisper-1` | Transcription |

Settings model fields are `Optional` + resolved via `@property` (mirrors github's
`gh_path` pattern) — the kit's `make_get_settings` passes `None` for unset env
vars, which would shadow non-Optional defaults.

## Why `openai_mcp/` and not `openai/`

The PyPI `openai` Python SDK ships as top-level `import openai`. If the
connector directory were `mcp/openai/`, our internal `from openai.tools import ...`
imports would collide with the SDK. Renaming to `openai_mcp/` keeps both
namespaces clean: `import openai` = SDK, `import openai_mcp` = this connector.

## `.mcp.json` wire-up

```json
{
  "mcpServers": {
    "openai": {
      "command": "mcp/noctusai/.venv/bin/python",
      "args": ["mcp/openai_mcp/server.py"],
      "cwd": "/Users/rapha/Documents/repository/NoctusAI/noctusai"
    }
  }
}
```

The connector reuses `mcp/noctusai/.venv` (which already has `openai>=1.0.0`
installed from prior work). No separate venv needed.

`.mcp.json` is gitignored — per-operator config. Add the `openai` entry to
your `.mcp.json` to enable the tools in Claude Code sessions.

## Composes with

- `mcp/_kit` — bootstrap + settings + registry + error envelope + seed pin.
- `KB § PATTERNS/common/kb-vector-search.md` — what `openai.search.kb` reads.
- `KB § PATTERNS/common/code-embeddings.md` — what `openai.search.code` reads.
- `KB § PATTERNS/common/memory-embeddings.md` — what `openai.search.memory` reads.
- `KB § PATTERNS/common/corpus-embeddings.md` — what `openai.search.corpus` reads.
- `KB § PATTERNS/devops/ssh-deploy-key-restrictions.md` — relevant for any
  future CI-side OpenAI usage.

## Verified live (v4.0 ship)

`openai.diagnostics.connection_status` returns `{ok=true, reachable=true,
sdk_version=2.32.0}` against the operator's `.env`-loaded key. All 9 tool
descriptors register cleanly via `_kit.build_registry`. Embed-then-search
round-trip works against the 4 populated caches.
