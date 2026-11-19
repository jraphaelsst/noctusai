# `mcp/elevenlabs` — ElevenLabs audio connector MCP

Lets agents create audio with ElevenLabs: text-to-speech with word timings, voice lookup
(own + shared + public library), model list, account usage, instant voice cloning, voice
deletion. A platform tool (noc level) — nothing client-specific in its defaults.
Composes `mcp/_kit` (same shape as `mcp/waha`); HTTP via `_kit.transport`
(`request_json`, plus the new binary/multipart path `request_bytes` / `encode_multipart`).

## Enable it (owner steps)

1. Create an API key at <https://elevenlabs.io/app/settings/api-keys>; restrict its scopes
   (text-to-speech, voices, models, user read).
2. `cp mcp/elevenlabs/.env.example mcp/elevenlabs/.env` and paste the key into
   `ELEVENLABS_API_KEY=`. The file is gitignored (repo-wide `.env` rule).
3. Add the server to your local, gitignored `.mcp.json` (mirror the `waha` entry):
   ```json
   "elevenlabs": {"command": "mcp/noctusai/.venv/bin/python", "args": ["mcp/elevenlabs/server.py"], "cwd": "<repo root>"}
   ```
4. Restart Claude Code and check `/mcp` shows `elevenlabs` connected.

No key => the server still boots; every tool returns a typed `424` naming `ELEVENLABS_API_KEY`.

## Tools (`elevenlabs.<service>.<action>`)

| Tool | Kind / gate | Endpoint |
|---|---|---|
| `elevenlabs.user.usage` | READ | `GET /v1/user/subscription` |
| `elevenlabs.model.list` | READ (filters: `tts_only`, `language`) | `GET /v1/models` |
| `elevenlabs.voice.list` | READ (`include_library=true` also searches the public library) | `GET /v2/voices`, `GET /v1/shared-voices` |
| `elevenlabs.voice.get` | READ | `GET /v1/voices/{voice_id}` |
| `elevenlabs.tts.synthesize` | SPENDS CREDITS — `confirm=true` (412) | `POST /v1/text-to-speech/{voice_id}[/with-timestamps]` |
| `elevenlabs.voice.clone_instant` | `consent_reference` required (422) + `confirm=true` (412) | `POST /v1/voices/add` (multipart) |
| `elevenlabs.voice.delete` | IRREVERSIBLE — `confirm=true` (412) | `DELETE /v1/voices/{voice_id}` |

`voice.list` without `voice_type` returns every voice the account can use, which includes
voices another account shared to it; pass `search` to find one by name.

### `tts.synthesize`

- **Without `confirm`**: returns an estimate (`characters x model character_cost_multiplier`
  from `/v1/models`) and the current balance; nothing is spent, no file is written.
- **Guards before any spend**: per-call cap `ELEVENLABS_MAX_CHARS` (default 5000) -> model max
  length -> output path -> estimate vs remaining balance.
- **Output**: `output_path` (absolute) or, by default,
  `<ELEVENLABS_OUTPUT_DIR | $NOCTUS_PRIVATE_DIR/elevenlabs | ~/.noctusai/private/elevenlabs>/<YYYY-MM-DD>/<slug>.<ext>`
  — outside every git tree, like every other noc private artifact. A path inside the repo is
  refused unless git ignores it; an existing file is never overwritten.
- **Word timings**: `timestamps=true` (default) uses the `with-timestamps` endpoint and writes
  `<audio>.timings.json` next to the audio: `{words: [{word, start, end}], alignment, normalized_alignment}`
  (seconds; the API returns character-level times, words are grouped on whitespace).
- **Returns**: `audio_path`, `timings_path`, `duration_seconds` (+ source), `characters_billed`
  (+ source), `request_id`.
- Example: `{"text": "Olá, bem-vindo.", "voice_id": "<voice_id>", "model_id": "eleven_multilingual_v2", "confirm": true}`.

### `voice.clone_instant` and consent

A real person's voice needs their documented consent. `consent_reference` (path/ID of the
signed term; >= 6 chars) is mandatory and checked **before** the confirm gate; the tool never
reads that file, it only records the reference in the result. Samples must be absolute paths
outside the repo (or git-ignored). Honour a revoked consent with `voice.delete`.

## Privacy

- Request text and keys are never logged; error text carries the upstream status/body only.
- `ELEVENLABS_ZERO_RETENTION` (default `true`) sends `enable_logging=false`. ElevenLabs documents
  zero-retention mode as **enterprise-only**. On other plans the call fails with a hint; retry
  with `zero_retention=false` (or set the env to `false`) only as a deliberate privacy decision —
  history/retention then applies on ElevenLabs' side.

## Config

| Var | Meaning | Default |
|---|---|---|
| `ELEVENLABS_API_KEY` | secret | required |
| `ELEVENLABS_OUTPUT_DIR` | default audio dir | `~/.noctusai/private/elevenlabs` |
| `ELEVENLABS_MAX_CHARS` | per-call text cap | 5000 |
| `ELEVENLABS_ZERO_RETENTION` | `enable_logging=false` | true |
| `ELEVENLABS_BASE_URL` | regional host (US/EU/IN/SG residency exist) | `https://api.elevenlabs.io` |

Key rotation: `KEY-ROTATION-RUNBOOK.md`.

## Tests

`cd mcp && ../mcp/noctusai/.venv/bin/python -m pytest elevenlabs/tests _kit/tests -q` — no network, no credits:
only `elevenlabs.api.request_json|request_bytes` (the external seam) is faked.

## Doc sources (verified 2026-11-18 against the live docs)

- <https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps> and `.../convert`
- <https://elevenlabs.io/docs/api-reference/user/subscription/get>
- <https://elevenlabs.io/docs/api-reference/voices/search> · `.../voices/get` · `.../voices/delete` · `.../voices/ivc/create`
- <https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared>
- <https://elevenlabs.io/docs/api-reference/models/list> · <https://elevenlabs.io/docs/overview/models>

**Not verifiable from the docs (handled defensively):** the TTS response header names for request id
and character cost (we read `request-id` and `x-character-count`; if absent, `request_id` is null and
`characters_billed` falls back to the estimate, flagged by `characters_billed_source`); credit price per
character per model (we use `model_rates.character_cost_multiplier`, the documented field, and treat 1
character = 1 credit x multiplier as an estimate, not a bill); which paid tier unlocks instant cloning
(read `can_use_instant_voice_cloning` from `user.usage`); the exact `labels` encoding for voice add (sent as JSON).

## Next step (named destination)

A seed IO adapter — Protocol + Fake + Real + factory under `noctusai_lib/integrations/` — when a
product (CoreStudio / agents) consumes TTS. This connector is the agent-side tool only; products must
not call it.
