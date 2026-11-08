# Prompts from the registry — an agent's prompt is read from the database, never from code

> **What this is.** The rule, the sanctioned call path, the exemptions and the gate for "no LLM prompt lives
> in code". Owner: `ai-engineer` (rule) with `tooling-engineer` (gate). Authored 2026-11-08.
>
> **Why it exists.** Owner rule 2026-11-08: "agents are built consuming 100% of the prompt straight from the
> database, to protect our prompts from malicious users; never from code", and "maintenance through the UI is
> much easier than at code level". A prompt in a repo file or a Python constant ships in images, diffs and
> logs and can be read by anyone who gets the code; a prompt in the database is reached only through the
> service role and is edited by a person in the UI without a deploy.

## 1 The rule

Every call that sends a prompt to a model takes that prompt from the prompt registry (a database row), not
from a constant, an f-string template, or a repo `.md` file loaded at runtime.

## 2 The sanctioned path

`noctusai_lib.integrations.prompt_registry`:

- `chamar_ia(chave, messages, ...)` for chat; `chamar_ia_visao(...)` for images; `transcrever_ia(...)` for audio.
- `prompt_e_modelo(chave)` returns the prompt text and model for a caller that must drive the seam itself
  (for example a seam with tools). A function that calls `prompt_e_modelo` counts as registry-fed.

The registry itself lives on branch `feat/agents-plataforma-ia-registro`.

## 3 What the gate flags (`check_llm_prompt_from_registry`)

AST scan (`mcp/noctusai/tools/noctus/dev/llm_prompt_registry_scan.py`) over `products/`, `seed/lib/backend`,
`seed/framework/backend` and `mcp/`:

- a reference to a seam entry point imported from `noctusai_lib.integrations.llm`: `chat_completion`,
  `chat_completion_with_usage`, `chat_completion_stream`, `chat_with_tools`, `run_tool_loop(_sync)`,
  `analyze_image(s)`, `analyze_image_with_refusal_retry`; `digest.narrative`; `create_help_chat_router`.
  References count (a DI default `chat_fn=chat_completion`, an alias), not only calls;
- a vendor SDK call: `messages.create`, `chat.completions.create`, `responses.create`, `images.edit`,
  `ClaudeSDKClient(...)`;
- a prompt-shaped constant (`*_SYSTEM*`, `*PROMPT*`, but not `*VERSION*`) used in a flagged function, and a
  repo `.md` file read via `read_text()`/`open()` in a file that has a flagged site.

A site inside a function that calls `prompt_e_modelo` / `chamar_ia*` is registry-fed and not flagged.

## 4 Exemptions (each with its reason)

| Path | Reason |
|---|---|
| the `noctusai_lib.integrations.llm` and `.image_edit` packages | the seam's own provider modules |
| the `noctusai_lib.integrations.prompt_registry` package | the sanctioned path itself |
| `mcp/openai_mcp/tools/`, `mcp/noctusai/tools/llm/` | pass-through tools: the prompt is the caller's input |
| `products/agents/backend/app/runtime/llm_runtime.py`, `runtime/eval_driver_live.py`, `studio/geracao.py` | the runtime that runs Julia's DB-compiled spec |
| tests | fixtures, not production prompts |
| `transcribe_audio`, embeddings | no prompt |

## 5 Ratchet, shadow and telemetry

- Baseline `mcp/noctusai/tests/llm_prompt_from_registry_baseline.json` (`{"files": {path: sites}}`) is derived by
  `python mcp/noctusai/cli.py --refresh-llm-prompt-from-registry-baseline` and only shrinks; an entry whose file no
  longer exists drops out, so deleting an absorbed product's code shrinks it. A NEW file or a GROWN count is flagged.
  Never hand-edit it.
- Placement: pre-push, WARN-first shadow from 2026-11-08 for 7 days (decision D24, gate-alignment inventory);
  promote to blocking only after the shadow record shows a low false-alarm rate.
- Telemetry: the cli wrapper logs every run to `guard-events.ndjson`; `--llm-prompt-log` files one
  auto-improvement drift row per flagged file (`llm_prompt_not_from_registry:<file>`), which closes itself via
  predicate `llm_prompt_registry_clean:<file>` once the file is migrated or deleted.
- False-alarm research: `--check-llm-prompt-from-registry --llm-prompt-replay` lists every site ignoring the baseline.

## 6 Migrating a site

1. Create the prompt row in the registry (UI); give it a `chave`.
2. Replace the constant and the seam call with `chamar_ia(chave, messages, ...)`.
3. Run `--refresh-llm-prompt-from-registry-baseline` in the same commit so the ratchet shrinks.

Composes with: `KB § PATTERNS/ai/ai-engineering-canon.md`, `KB § PATTERNS/backend/llm-usage.md`,
`KB § PATTERNS/common/gate-methodology-sync.md`.
