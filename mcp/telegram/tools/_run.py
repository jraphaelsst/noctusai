"""Shared handler plumbing: build the gateway, run, ALWAYS disconnect, and
render any failure as the typed-error envelope."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from _kit.errors import typed_error

from .. import client


async def run_with_gateway(fn: Callable[[Any], Awaitable[dict]], **error_defaults: Any) -> dict:
    try:
        gw = client.get_client()
    except Exception as e:  # NotConfiguredError and friends -> typed 424
        return {**error_defaults, "error": typed_error(e)}
    try:
        return await fn(gw)
    except Exception as e:
        return {**error_defaults, "error": typed_error(e)}
    finally:
        try:
            await gw.disconnect()
        except Exception:  # disconnect must never mask the real result
            pass
