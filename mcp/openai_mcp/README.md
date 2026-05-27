# `mcp/openai` — OpenAI connector MCP

OpenAI API surface as LLM-callable `openai.<service>.<action>` tools.
Composes `mcp/_kit` (same shape as `vista` / `meta` / `google` / `github`).

## Tool surface

| Tool | Kind | What it does |
|---|---|---|
| `openai.embed` | READ | Text → 1536-D vector (text-embedding-3-small default) |
| `openai.chat` | READ | Chat completion (gpt-4o-mini default) |
| `openai.vision` | READ | Image + question → text (gpt-4o; accepts URL or local path) |
| `openai.transcribe` | READ | Audio file → text (whisper-1) |
| `openai.search.kb` | READ | Semantic search over `KNOWLEDGE-BASE/**/*.md` |
| `openai.search.code` | READ | Semantic search over `mcp/**/*.py` + `noctusai_lib/**` + `products/seed/**` |
| `openai.diagnostics.connection_status` | READ | Never-faked READY/UNCONFIGURED signal |

All tools are READ-only — no writes touch the user's OpenAI account beyond the API calls themselves (no model creation, fine-tuning, file uploads, or assistant CRUD in this connector).

## Why this connector exists

The platform already does embeddings + semantic search via `noctusai/tools/noctus/dev/kb_embeddings.py` + `code_embeddings.py`, but the underlying OpenAI capabilities (chat, vision, transcription) had no MCP surface. Agents couldn't send an audio file to transcribe or an image to analyze. This connector closes that gap and provides a clean facade over the search engines too.

## Settings (`mcp/openai/.env` OR repo-root `/.env`)

| Var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required.** Loaded from `mcp/openai/.env` or repo-root `/.env`. |
| `OPENAI_DEFAULT_CHAT_MODEL` | `gpt-4o-mini` | Default chat model |
| `OPENAI_DEFAULT_EMBEDDING_MODEL` | `text-embedding-3-small` | 1536-D embeddings |
| `OPENAI_DEFAULT_VISION_MODEL` | `gpt-4o` | Vision/image analysis |
| `OPENAI_DEFAULT_AUDIO_MODEL` | `whisper-1` | Transcription |

## Run

```bash
python mcp/openai/server.py
```

Wired into `.mcp.json` so it auto-starts in Claude Code sessions:

```json
{
  "mcpServers": {
    "openai": {
      "command": "python",
      "args": ["mcp/openai/server.py"]
    }
  }
}
```

## Composes with

- `_kit` — bootstrap / settings / registry / error envelope / seed pin.
- `KB § PATTERNS/common/kb-vector-search.md` — what `openai.search.kb` reads from.
- `KB § PATTERNS/common/code-embeddings.md` — what `openai.search.code` reads from.
- `KB § PATTERNS/common/gated-capability-honesty.md` — `connection_status` shape.
