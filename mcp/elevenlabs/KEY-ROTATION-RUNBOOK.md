# ElevenLabs API key rotation runbook

> Plan for a human; one consumer holds the key, so rotation is simple. Rotate on suspected
> leak, on a team change, or on a schedule you choose.

## Consumers of the key

| # | Where | How |
|---|---|---|
| 1 | `mcp/elevenlabs/.env` -> `ELEVENLABS_API_KEY` (gitignored) | edit file, restart the MCP server (`/mcp` reconnect or restart Claude Code) |
| 2 | Any `ELEVENLABS_API_KEY` exported in your shell / process env | env wins over the file — `unset` or update it, or the old key keeps being used |
| 3 | (future) a seed adapter / product credential store | not yet; when it exists it uses per-org `CredentialStore`, never this file |

## Steps (ElevenLabs supports several keys at once, so no hard cutover)

1. Pre-check: `elevenlabs.user.usage` works (baseline).
2. In <https://elevenlabs.io/app/settings/api-keys> create a NEW key with minimal scopes (text-to-speech,
   voices, models, user read) and, if offered, a credit quota. Store it in the password manager first.
3. Paste it into `mcp/elevenlabs/.env`; clear any shell-exported old value; restart the MCP server.
4. Verify: `elevenlabs.user.usage` returns the tier (not 401).
5. Only then delete the OLD key in the ElevenLabs dashboard. If anything fails, the old key is still valid —
   restore it in `.env` and retry.
6. If the old key leaked: delete it immediately (step 5 first), check usage history for unknown spend, and
   check `elevenlabs.voice.list` for voices you did not create (`elevenlabs.voice.delete` them).
