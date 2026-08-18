"""Register OUR receiver with ImovelWeb — the most dangerous write we make.

``PUT /v1/configuracao/callbacks`` takes **no agency code**. The
configuration is integrator-wide, so a single call redirects the leads of
every agency authorized to our integration, at once, and the vendor reports
nothing when the new URL is unreachable — it believes it delivered.

So this service is register-then-read-back-then-diff, and it keeps the
previous configuration, because after a bad PUT the vendor cannot tell you
what you had. Three guards, in order:

1. **Refuse an unreachable URL** — localhost, a private range, an ephemeral
   tunnel. The seed's ``receiver_url_problems`` is the single implementation,
   shared with ``mcp/imovelweb``, so the connector and the product cannot
   drift into disagreeing about what is safe to register.
2. **Refuse an empty subscription list.** The vendor accepts it and then
   delivers nothing, silently, while every health indicator stays green.
   That is the likeliest production incident on this integration.
3. **Diff what was applied against what was asked.** A PUT that quietly
   drops ``subscriptions`` is otherwise invisible.

Never called from a startup hook or the scheduler: this is an explicit,
authenticated, confirmed admin action.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_LEAD_EVENT_TYPES,
    CallbackConfig,
    basic_credential,
    receiver_url_problems,
)

logger = logging.getLogger(__name__)

#: The receiver path we register. One place, so the product, the connector
#: and the docs cannot disagree about where deliveries land.
RECEIVER_PATH = "/api/portals/imovelweb/leads"

_REDACTED = "***REDACTED***"


class CallbackRegistrationError(Exception):
    """A refusal, with the reason. Carries an HTTP-ish status so the router
    maps it without re-deriving the classification."""

    def __init__(self, message: str, *, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def receiver_url(public_base_url: str) -> str:
    """The full URL we register, from the deployment's public base."""
    return f"{(public_base_url or '').rstrip('/')}{RECEIVER_PATH}"


def public_view(config: Optional[CallbackConfig]) -> Optional[dict[str, Any]]:
    """The wire shape minus the credential.

    There is no signature scheme, so ``authorizationHeaderValue`` IS the
    entire inbound security boundary. It never leaves this service — not to
    an API response, not to a log line.
    """
    if config is None:
        return None
    wire = config.to_wire()
    if wire.get("authorizationHeaderValue"):
        wire["authorizationHeaderValue"] = _REDACTED
    return wire


def diff_config(requested: CallbackConfig, applied: CallbackConfig) -> list[str]:
    """What the vendor did differently from what we asked for.

    Field by field so the report NAMES the field. ``subscriptions`` compares
    as a set: the vendor may reorder, and reporting a reordering as drift
    would train the reader to skip the list — which is exactly the list that
    matters.
    """
    out: list[str] = []
    if requested.url != applied.url:
        out.append(f"url: requested {requested.url!r}, vendor has {applied.url!r}")
    if requested.language != applied.language:
        out.append(
            f"lenguajeCallbackBody: requested {requested.language!r}, vendor has "
            f"{applied.language!r} — this changes the FIELD NAMES of every body"
        )
    if requested.authorization_header_key != applied.authorization_header_key:
        out.append(
            f"authorizationHeaderKey: requested "
            f"{requested.authorization_header_key!r}, vendor has "
            f"{applied.authorization_header_key!r}"
        )
    if requested.authorization_header_value != applied.authorization_header_value:
        # Never echo either value.
        out.append(
            "authorizationHeaderValue: the vendor stored something different "
            "from what we sent — every delivery will fail our verifier with 401"
        )
    if set(requested.subscriptions) != set(applied.subscriptions):
        dropped = sorted(set(requested.subscriptions) - set(applied.subscriptions))
        added = sorted(set(applied.subscriptions) - set(requested.subscriptions))
        out.append(
            f"subscriptions: dropped={dropped or None} added={added or None} — "
            "a dropped subscription delivers nothing and reports no error"
        )
    return out


async def read_config(adapter: Any) -> dict[str, Any]:
    """Read the registration back from the vendor — the health check.

    Reports ``delivers_nothing`` separately from ``problems`` because it is
    not a validation failure: a configuration with a perfect URL and no
    subscriptions is entirely legal to the vendor, and entirely useless to
    us, and nothing else in the system will ever complain about it.
    """
    config = await adapter.get_callback_config()
    return {
        "config": public_view(config),
        "subscriptions": list(config.subscriptions),
        "delivers_nothing": not config.subscriptions,
        "problems": list(config.validate()),
    }


async def register_callback(
    adapter: Any,
    *,
    public_base_url: str,
    webhook_secret: str,
    language: str = "EN2",
    events: tuple[str, ...] = IMOVELWEB_LEAD_EVENT_TYPES,
    allow_local_url: bool = False,
    store: Any = None,
) -> dict[str, Any]:
    """Validate → PUT → read back → diff → persist. Returns the whole story.

    ``store`` is the app-config store used to keep the applied and previous
    configurations. Optional, because a caller rehearsing against a Fake has
    nothing worth persisting — but in production it is what makes a bad write
    reversible.
    """
    if not webhook_secret:
        raise CallbackRegistrationError(
            "no ImovelWeb webhook secret is configured. We choose this value "
            "ourselves and it becomes the entire inbound security boundary; "
            "registering without one would accept any request that reached "
            "the receiver.",
            status=424,
        )

    url = receiver_url(public_base_url)
    warnings: list[str] = []
    url_problems = receiver_url_problems(url)
    if url_problems and not allow_local_url:
        raise CallbackRegistrationError(
            "refusing to register this receiver url: " + "; ".join(url_problems)
            + ". The registration is integrator-wide, so an unreachable url "
            "blackholes every agency's leads and reports no error anywhere."
        )
    if url_problems:
        warnings.append("registered anyway (allow_local_url): " + "; ".join(url_problems))

    requested = CallbackConfig(
        url=url,
        authorization_header_value=basic_credential(webhook_secret),
        language=language,
        subscriptions=tuple(events),
    )
    problems = requested.validate()
    if problems:
        raise CallbackRegistrationError(
            "refusing to register an invalid config: " + "; ".join(problems)
        )

    previous: Optional[CallbackConfig] = None
    try:
        previous = await adapter.get_callback_config()
    except Exception as exc:  # noqa: BLE001 — first-time registration has nothing to read
        # Not fatal, but say what was lost: this was the only copy, and the
        # vendor cannot reproduce it after the write.
        warnings.append(
            f"could not read the previous configuration ({type(exc).__name__}) — "
            "if this write is wrong there is nothing to roll back to"
        )

    applied = await adapter.put_callback_config(requested)
    drift = diff_config(requested, applied)
    if not applied.subscriptions:
        warnings.append(
            "the vendor reports NO subscriptions after this write — it will "
            "deliver nothing, silently. Fix before relying on it."
        )

    if store is not None:
        _persist(store, applied=applied, previous=previous)

    logger.info(
        "imovelweb-callback: registered url=%s language=%s events=%s drift=%s",
        url, language, list(events), len(drift),
    )
    return {
        "registered": True,
        "requested": public_view(requested),
        "previous": public_view(previous),
        "applied": public_view(applied),
        "drift": drift,
        "warnings": warnings,
    }


def _persist(store: Any, *, applied: CallbackConfig, previous: Optional[CallbackConfig]) -> None:
    """Keep the applied config and the one it replaced.

    Stored WITHOUT the credential: the store is Fernet-encrypted, but the
    header value is recoverable at any time from the webhook secret via
    ``basic_credential``, and a secret that is never written down in two
    places cannot be leaked from the second one.
    """
    from app.services.app_config_store import (
        IMOVELWEB_CALLBACK_CONFIG_KEY,
        IMOVELWEB_CALLBACK_CONFIG_PREVIOUS_KEY,
    )

    try:
        store.put(IMOVELWEB_CALLBACK_CONFIG_KEY, json.dumps(public_view(applied)))
        if previous is not None:
            store.put(
                IMOVELWEB_CALLBACK_CONFIG_PREVIOUS_KEY,
                json.dumps(public_view(previous)),
            )
    except Exception as exc:  # noqa: BLE001 — the vendor write already happened
        # Loud, and not fatal: the registration IS applied at this point, and
        # raising here would report a failure for a write that succeeded —
        # which would send an operator to re-run it against a vendor that
        # already has it.
        logger.warning(
            "imovelweb-callback: registration applied but could not be persisted "
            "locally (%s) — the rollback copy is missing", exc,
        )


__all__ = [
    "RECEIVER_PATH",
    "CallbackRegistrationError",
    "diff_config",
    "public_view",
    "read_config",
    "receiver_url",
    "register_callback",
]
