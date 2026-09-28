"""`create_limiter` — the Limiter's own default key_func must be the
Cloudflare-aware `client_ip_key`, never the bare `get_remote_address`.

In prod every product sits behind the Cloudflare tunnel, so
`get_remote_address` (the slowapi default) reads the TUNNEL CONNECTOR's
socket address — the same value for every visitor. Every
`@limiter.limit(...)` decorator across the fleet that does not pass its own
`key_func=` (the overwhelming majority) inherits whatever key_func the
Limiter was constructed with, so this was a fleet-wide single-shared-bucket
bug, not merely a "no default limit" gap. `client_ip_key` (already
regression-tested in `test_client_ip_key.py`) resolves the real
CF-Connecting-IP visitor address, and falls back to `get_remote_address`
identically in local dev/tests where no tunnel is present — so this fix is
behavior-identical outside prod and strictly corrective inside it.
"""
from starlette.requests import Request

from noctusai_lib.api.rate_limit import create_limiter, client_ip_key


def _request(headers: dict[str, str], peer: str = "172.18.0.5") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 51000),
    })


def test_default_key_func_is_client_ip_key_not_the_shared_tunnel_peer():
    limiter = create_limiter()
    assert limiter._key_func is client_ip_key


def test_default_key_func_resolves_the_real_visitor_behind_the_tunnel():
    limiter = create_limiter()
    # Two different visitors sharing the same tunnel-peer socket address must
    # resolve to two different keys via CF-Connecting-IP.
    req_a = _request({"CF-Connecting-IP": "203.0.113.7"})
    req_b = _request({"CF-Connecting-IP": "203.0.113.99"})
    assert limiter._key_func(req_a) != limiter._key_func(req_b)
    assert limiter._key_func(req_a) == "203.0.113.7"


def test_default_key_func_falls_back_to_socket_peer_without_the_header():
    # Local dev / tests — no tunnel, no CF-Connecting-IP header. Identical
    # to the pre-fix behavior (get_remote_address), so no dev/test breakage.
    limiter = create_limiter()
    assert limiter._key_func(_request({})) == "172.18.0.5"


def test_unreachable_redis_falls_back_to_in_memory_and_still_uses_client_ip_key():
    """The Redis-unreachable fallback branch must not regress to the old
    default either — this exercises the SAME `return Limiter(key_func=...)`
    statement the (unreachable-in-CI) Redis-backed branch does, since a real
    reachable Redis is not available in this suite."""
    limiter = create_limiter(redis_url="redis://noctus-nonexistent-host:6379")
    assert limiter._key_func is client_ip_key
