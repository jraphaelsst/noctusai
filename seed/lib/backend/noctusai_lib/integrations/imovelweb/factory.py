"""The single seam consumers reach for — Fake or Real, by flag."""

from __future__ import annotations

from typing import Any, Optional, Union

from .endpoints import IMOVELWEB_SANDBOX_BR
from .fake import FakeImovelWebClient
from .real import DEFAULT_TIMEOUT_SECONDS, ImovelWebClient


def make_imovelweb_client(
    *,
    use_fake: bool = False,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    region: str = "br",
    sandbox: bool = False,
    base_url: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    http_client: Any = None,
    callback_header_value: Optional[str] = None,
    fake_configured: bool = True,
    fake_base_url: str = IMOVELWEB_SANDBOX_BR,
) -> Union[ImovelWebClient, FakeImovelWebClient]:
    """Build an OpenNavent client.

    Both branches expose the same surface, so a consumer selects here and
    never branches on environment itself.

    `use_fake=False` with no credentials does **not** raise — it returns a
    real client that raises `ImovelWebConfigError` (424) on the first
    call. That is the seed's leniency contract: an unconfigured tenant
    must not stop the host app from starting, and "not configured" is a
    different fact from "the vendor is down".

    One decision, one branch. If you find yourself wanting a third, the
    thing you want is probably a second factory.
    """
    if use_fake:
        return FakeImovelWebClient(
            configured=fake_configured, base_url=fake_base_url
        )
    return ImovelWebClient(
        client_id=client_id,
        client_secret=client_secret,
        region=region,
        sandbox=sandbox,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
        callback_header_value=callback_header_value,
    )


__all__ = ["make_imovelweb_client"]
