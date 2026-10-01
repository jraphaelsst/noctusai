"""Fake-or-refuse adapter resolution — the ONE place a consumer decides
"Real, Fake, or a declared not-configured state".

**What this is.** Every seed IO module ships Protocol + Fake + Real +
factory (`KB § PATTERNS/backend/seed-fake-real-adapter.md`). The factory
picks between Fake and Real by an explicit flag — but a CONSUMER still has
to decide what happens when its credentials are simply absent in a real
deploy. Left to each call site, that decision drifts into the silent
shape: "no key → the Fake", so prod runs a fake Pix QR, a fake WhatsApp
send that reads "Enviada", or a captcha that accepts any token.

`resolve_fake_or_refuse` makes the decision structural:

- **configured** → `build_real()`. The Fake is never constructed.
- **unconfigured + `allow_fake`** → `build_fake()`. `allow_fake` is an
  EXPLICIT opt-in (a test-harness / local-dev setting the consumer owns,
  default `False`) — never inferred from the missing credential.
- **unconfigured otherwise** → `unconfigured()`. REQUIRED, no default:
  the caller must declare the state — raise an honest refusal (a 503
  domain error), or return an explicit sentinel (`None`, a "disabled"
  value object) its callers already branch on.

There is deliberately no path from "credential missing" to "Fake" that
does not pass through `allow_fake=True`.

**Recipe:**

    from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse

    def _gateway(key: str | None):
        return resolve_fake_or_refuse(
            configured=bool(key),
            build_real=lambda: make_payment_gateway(provider="stripe", stripe_api_key=key),
            build_fake=lambda: make_payment_gateway(use_fake=True),
            allow_fake=settings.payments_allow_fake,
            unconfigured=_refuse_503,
        )

Pure selection logic — no IO of its own, so it carries no Fake/Real pair
itself; the adapters it selects between do.
"""
from __future__ import annotations

from typing import Callable, Optional, TypeVar, Union

T = TypeVar("T")
U = TypeVar("U")


def resolve_fake_or_refuse(
    *,
    configured: bool,
    build_real: Callable[[], T],
    unconfigured: Callable[[], U],
    allow_fake: bool = False,
    build_fake: Optional[Callable[[], T]] = None,
) -> Union[T, U]:
    """Select Real / Fake / declared-unconfigured state.

    Args:
        configured: whether the Real adapter's credentials resolved.
        build_real: builds the Real adapter (called only when configured).
        unconfigured: the declared not-configured outcome — raise a
            refusal or return an explicit sentinel. Called only when not
            configured and the Fake is not opted into.
        allow_fake: explicit opt-in to the Fake when unconfigured (test
            harness / local dev). Ignored when `configured` — a configured
            consumer always gets the Real.
        build_fake: builds the Fake. Required iff `allow_fake` is True on
            an unconfigured resolution.

    Raises:
        ValueError: `allow_fake=True` on an unconfigured resolution with
            no `build_fake` — a misconfigured opt-in, surfaced loudly
            rather than silently falling through to `unconfigured()`.
    """
    if configured:
        return build_real()
    if allow_fake:
        if build_fake is None:
            raise ValueError(
                "resolve_fake_or_refuse: allow_fake=True but no build_fake was "
                "supplied — the Fake opt-in cannot be honoured"
            )
        return build_fake()
    return unconfigured()


__all__ = ["resolve_fake_or_refuse"]
