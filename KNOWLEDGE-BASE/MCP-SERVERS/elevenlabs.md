# ElevenLabs connector MCP — `mcp/elevenlabs`

> Platform (noc-level) tool that lets agents create audio with ElevenLabs: text-to-speech with
> word timings, voice lookup (own / shared / library), model list, usage, instant voice cloning,
> voice deletion. Composes `mcp/_kit`. Built 2026-11-18. Full reference: `mcp/elevenlabs/README.md`
> (setup, tool table, doc URLs + the facts that could not be verified).

## Tool surface (`elevenlabs.<service>.<action>`)

`user.usage` · `model.list` · `voice.list` · `voice.get` (READ) · `tts.synthesize` (spends credits,
`confirm=true`, else estimate + balance) · `voice.clone_instant` (`consent_reference` required +
`confirm=true`) · `voice.delete` (`confirm=true`).

## Rules this connector encodes

- **Spend and consent are gated.** TTS/clone/delete refuse with 412 without `confirm`; clone refuses
  with 422 without a documented-consent reference (checked first). A real person's voice needs their
  documented consent (LGPD: a voice sample is biometric/personal data — `KB § PATTERNS/security/lgpd.md`).
- **Artifacts never land on a committable path.** Default dir = `<ELEVENLABS_OUTPUT_DIR | $NOCTUS_PRIVATE_DIR/elevenlabs
  | ~/.noctusai/private/elevenlabs>/<date>/` (the same private root as `drive_pull` / Google tokens). A path inside
  a git work tree is refused unless git ignores it; samples follow the same rule.
- **Privacy default**: `enable_logging=false` (documented enterprise-only) — on other plans the call fails with an
  actionable hint, and accepting retention is a deliberate per-call/env decision.
- **Transport**: `_kit.transport.request_bytes` / `encode_multipart` (new generic binary + multipart path, tested in
  `_kit/tests/test_http.py`); `request_json` now delegates to `request_bytes` (one HTTP error path).
- **Test seam**: `patch("elevenlabs.api.request_json" | "elevenlabs.api.request_bytes")` — external service only.

## Config

The connector's co-located `.env` (gitignored by the repo-wide `.env` rule; template `.env.example`) — `ELEVENLABS_API_KEY`,
optional `ELEVENLABS_OUTPUT_DIR`, `ELEVENLABS_MAX_CHARS` (5000), `ELEVENLABS_ZERO_RETENTION` (true),
`ELEVENLABS_BASE_URL`. Rotation: `mcp/elevenlabs/KEY-ROTATION-RUNBOOK.md`.

## Registration

Owner-requested 2026-11-18; registration is local-only in `.mcp.json` (gitignored) — the owner adds the entry
(mirror of `waha`), see the README "Enable it". Reuses the `noctusai` MCP venv interpreter (connector adds no deps).

## Named next step

Seed IO adapter (Protocol + Fake + Real + factory, `noctusai_lib/integrations/`) when a product (CoreStudio /
agents) consumes TTS — products never call this connector.
