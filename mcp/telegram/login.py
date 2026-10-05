"""Interactive one-time Telegram login — creates the Telethon session.

    mcp/noctusai/.venv/bin/python mcp/telegram/login.py

Prompts on the TTY for phone, the login code, and (if enabled) the 2FA
password (getpass, never echoed). Writes `mcp/telegram/.session/noctus.session`
(dir 0700, file 0600). This is a justified carve-out from MCP-first-scripts:
it needs an interactive TTY, and MCP tools must NEVER accept codes/passwords.
The session file is a FULL account login — gitignored, never share it.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram.settings import SESSION_DIR, SESSION_FILE, get_settings  # noqa: E402


def _lock_down() -> None:
    SESSION_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(SESSION_DIR, 0o700)
    for p in SESSION_DIR.glob("*.session*"):
        os.chmod(p, 0o600)


async def main() -> int:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    s = get_settings()
    if not s.configured:
        print("TELEGRAM_API_ID / TELEGRAM_API_HASH missing in mcp/telegram/.env", file=sys.stderr)
        return 2
    SESSION_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(SESSION_DIR, 0o700)
    tg = TelegramClient(s.session_base, int(s.api_id), s.api_hash)
    await tg.connect()
    try:
        if not await tg.is_user_authorized():
            phone = input("Phone (international format, e.g. +5511...): ").strip()
            await tg.send_code_request(phone)
            code = input("Login code sent by Telegram: ").strip()
            try:
                await tg.sign_in(phone, code)
            except SessionPasswordNeededError:
                await tg.sign_in(password=getpass.getpass("2FA password: "))
        me = await tg.get_me()
        print(f"Logged in as id={me.id} username={me.username}")
    finally:
        await tg.disconnect()
        _lock_down()
    print(f"Session saved: {SESSION_FILE} (0600)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
