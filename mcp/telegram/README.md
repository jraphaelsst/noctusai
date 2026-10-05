# Telegram connector MCP (`mcp/telegram`)

Telegram **user-account** client (MTProto via [Telethon](https://docs.telethon.dev)),
shaped like every connector on `mcp/_kit` (`server.py` / `settings.py` / `tools/` / `tests/`).
Tools are `telegram.<service>.<action>`.

## Architecture / deliberate deviations

- **MTProto, not HTTP** — `_kit.transport` does not apply; Telethon owns the wire.
  `client.py` wraps it in a `TelegramGateway` behind a DI seam
  (`client.configure_client(fake)`), connecting per call and always disconnecting
  (`tools/_run.py`), so the stdio server never holds a socket. Telethon is imported lazily.
- **Not seed-backed** — no product consumes Telegram, so no `noctusai_lib.integrations`
  Fake+Real+factory module exists for it (same stance as `mcp/trello`).
- **Login is interactive, outside MCP** — `login.py` needs a TTY (phone, login code, 2FA
  password via `getpass`). Justified carve-out from MCP-first-scripts. MCP tools never
  accept codes or passwords.

## Setup

```bash
# 1. dependency (range-declared in mcp/noctusai/requirements.txt + pyproject.toml)
mcp/noctusai/.venv/bin/pip install 'telethon>=1.36,<2'
# 2. credentials: mcp/telegram/.env (gitignored) with TELEGRAM_API_ID / TELEGRAM_API_HASH
#    (https://my.telegram.org -> API development tools); see .env.example
# 3. one-time interactive login (writes mcp/telegram/.session/noctus.session, 0600 in 0700 dir)
mcp/noctusai/.venv/bin/python mcp/telegram/login.py
```

## Tools (8)

| Tool | Kind |
|---|---|
| `telegram.diagnostics.connection_status` | READ — creds + session authorized? |
| `telegram.diagnostics.me` | READ — id/username/name (never the phone) |
| `telegram.dialogs.list` | READ — limit, optional query |
| `telegram.messages.list` | READ — chat, limit<=500, offset_id, min_id, reverse |
| `telegram.messages.search` | READ — chat optional (global), query |
| `telegram.messages.export` | READ — all text + media METADATA to NDJSON (+ md) under `.exports/`; FloodWait slept (bounded), no media bytes |
| `telegram.media.download` | WRITE-to-disk, confirm-gated (412) — explicit ids, max 20 |
| `telegram.messages.send` | WRITE, confirm-gated (412 before any Telegram call) |

## Security

A `.session` file is a **full account login**. `mcp/telegram/.session/`, `*.session`,
`*.session-journal` and `mcp/telegram/.exports/` are gitignored; never share or commit them.
Exports contain private chat content (LGPD) — keep them local. `api_hash` is never echoed.

## Tests

`mcp/noctusai/.venv/bin/python -m pytest mcp/telegram/tests` — no live network; the gateway
is injected through `client.configure_client`.
