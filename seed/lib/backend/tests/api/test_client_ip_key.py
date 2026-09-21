"""`client_ip_key` — the per-visitor rate-limit key behind the Cloudflare tunnel."""
from starlette.requests import Request

from noctusai_lib.api.rate_limit import client_ip_key


def _request(headers: dict[str, str], peer: str = "172.18.0.5") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 51000),
    })


def test_uses_cloudflare_visitor_ip_over_tunnel_peer():
    assert client_ip_key(_request({"CF-Connecting-IP": "203.0.113.7"})) == "203.0.113.7"


def test_falls_back_to_socket_peer_without_the_header():
    assert client_ip_key(_request({})) == "172.18.0.5"


def test_ignores_spoofable_x_forwarded_for():
    assert client_ip_key(_request({"X-Forwarded-For": "198.51.100.1"})) == "172.18.0.5"


def test_blank_header_falls_back_to_socket_peer():
    assert client_ip_key(_request({"CF-Connecting-IP": "  "})) == "172.18.0.5"
