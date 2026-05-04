"""`make_oauth_provider` — single seam for selecting concrete + fake providers.

Today only `"google"` is registered; the factory is intentionally
designed to grow (Stripe, Slack, etc. as future-projects). Adding a
new vendor is a 3-line change here + the new concrete module.

`use_fake=True` short-circuits to `FakeOAuthProvider(name=name, ...)`
regardless of the requested vendor — useful in dev / FakeMode where
the consumer just wants the four-method contract satisfied without
network.
"""

from __future__ import annotations

from noctusai_lib.security.oauth.fake import FakeOAuthProvider
from noctusai_lib.security.oauth.google_provider import GoogleProvider
from noctusai_lib.security.oauth.protocol import OAuthProvider


def make_oauth_provider(
    name: str,
    *,
    use_fake: bool = False,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> OAuthProvider:
    """Resolve a vendor name to a concrete `OAuthProvider` instance.

    Args:
        name: vendor identifier. Currently supported: `"google"`.
            Unknown names raise `ValueError`.
        use_fake: when True, return a `FakeOAuthProvider` carrying
            `name`. The vendor doesn't need to be registered for this
            path — `use_fake=True` works for any name, by design.
            (Tests + FakeMode dev frequently want a Fake of an
            unimplemented vendor.)
        client_id: OAuth Client ID. Required when `use_fake=False`.
        client_secret: OAuth Client Secret. Required when `use_fake=False`.

    Returns:
        An `OAuthProvider` instance.

    Raises:
        ValueError: when `name` is unknown (and `use_fake=False`), or
            when `client_id` / `client_secret` are missing for a real
            provider.
    """
    if use_fake:
        return FakeOAuthProvider(name=name)

    if name == "google":
        if not client_id or not client_secret:
            raise ValueError(
                "make_oauth_provider(name='google') requires non-empty "
                "client_id and client_secret"
            )
        return GoogleProvider(client_id=client_id, client_secret=client_secret)

    raise ValueError(f"unknown provider: {name}")


__all__ = ["make_oauth_provider"]
