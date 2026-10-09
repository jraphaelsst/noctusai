"""Promotion precondition: does a product's PROD bundle run the new SSOCallback?

SSO P2.1 (roadmap ``sso-identity-hardening-2026-10``) runs a MIXED regime
derived from the catalog: ``ativo + dev`` products may still run the OLD
callback (reads only ``?token=``, sends no ``product_slug``); every other
product is *strict* and is launched with ``/sso#token=`` and must send its
slug. Flipping a product to ``deploy_scope='live'`` therefore flips it to
strict -- so the product must first be REBUILT on the current seed. This probe
enforces that order: it fetches the product's served SPA (the shell plus its
entry/preloaded scripts) and looks for the build-time marker the new callback
emits (``data-sso-callback``). No marker => the promotion is refused.

The prober is a DI seam (``get_sso_callback_prober`` in the products router) so
tests never reach the network.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

#: Must equal ``SSO_CALLBACK_MARKER`` in seed ``SSOCallback.tsx`` (test-enforced).
SSO_CALLBACK_MARKER = "noctus-sso-callback/p21"

_TIMEOUT_SECONDS = 10.0
_MAX_SCRIPTS = 12
_MAX_BYTES = 8 * 1024 * 1024
_BROWSER_UA = "Mozilla/5.0 (compatible; NoctusCore-SSOProbe/1.0)"
_SCRIPT_RE = re.compile(
    r'(?:src|href)="((?:https?://[^"/]+)?/(?:[^"/]+/)*assets/[^"]+\.js)"'
)


@dataclass(frozen=True)
class CallbackProbeResult:
    ok: bool
    detail: str


SSOCallbackProber = Callable[[str], Awaitable[CallbackProbeResult]]


def _absolute(base: str, ref: str) -> str:
    return ref if ref.startswith("http") else f"{base}{ref}"


async def probe_sso_callback(
    url_base: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> CallbackProbeResult:
    """Fetch ``url_base`` + its script assets; ok iff the marker is present.

    Fail-closed: an unreachable product, a shell without bundles, or a bundle
    without the marker are all ``ok=False`` with a human-readable detail.
    """
    base = url_base.rstrip("/")
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, follow_redirects=True, transport=transport,
            headers={"User-Agent": _BROWSER_UA},
        ) as client:
            shell = await client.get(f"{base}/")
            if shell.status_code >= 400:
                return CallbackProbeResult(False, f"GET {base}/ -> {shell.status_code}")
            scripts = list(dict.fromkeys(_SCRIPT_RE.findall(shell.text)))[:_MAX_SCRIPTS]
            if not scripts:
                return CallbackProbeResult(False, f"no /assets/*.js bundle referenced by {base}/")
            for ref in scripts:
                resp = await client.get(_absolute(base, ref))
                if resp.status_code < 400 and SSO_CALLBACK_MARKER in resp.text[:_MAX_BYTES]:
                    return CallbackProbeResult(True, f"marker found in {ref}")
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("sso callback probe failed for %s: %s", base, exc)
        return CallbackProbeResult(False, f"{base} unreachable: {type(exc).__name__}")
    return CallbackProbeResult(
        False, f"no '{SSO_CALLBACK_MARKER}' marker in {len(scripts)} bundle(s) of {base}"
    )
