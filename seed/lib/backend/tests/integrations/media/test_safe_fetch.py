"""safe_fetch -- SSRF guard. DNS and network are the injected boundary
(``resolver`` / ``transport``); the validation under test is the real code."""
from __future__ import annotations

import httpx
import pytest

from noctusai_lib.integrations.media.safe_fetch import (
    DEFAULT_ALLOWED_HOSTS,
    MAGIC_JPEG,
    MAGIC_MP4,
    MAGIC_PNG,
    MAGIC_WEBP,
    FakeSafeFetcher,
    FetchResult,
    RealSafeFetcher,
    SafeFetchError,
    host_allowed,
    ip_is_public,
    make_safe_fetcher,
)

CDN = "https://scontent-gru1-1.cdninstagram.com/v/t51/a.jpg"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PUBLIC_IP = "93.184.216.34"


def _resolver(mapping: dict[str, list[str]], calls: list | None = None):
    def resolve(host: str, port: int) -> list[str]:
        if calls is not None:
            calls.append(host)
        if host not in mapping:
            raise SafeFetchError("dns", "nxdomain")
        return mapping[host]

    return resolve


def _fetcher(handler, mapping=None, **kw) -> RealSafeFetcher:
    mapping = mapping or {"scontent-gru1-1.cdninstagram.com": [PUBLIC_IP]}
    return RealSafeFetcher(resolver=_resolver(mapping), transport=httpx.MockTransport(handler), **kw)


def _ok(body=JPEG, ctype="image/jpeg", **headers):
    return httpx.Response(200, content=body, headers={"content-type": ctype, **headers})


def _fetch(f, url=CDN, **kw):
    kw.setdefault("max_bytes", 1024)
    kw.setdefault("allowed_content_types", ("image/jpeg",))
    return f.fetch(url, **kw)


def _code(exc: pytest.ExceptionInfo) -> str:
    return exc.value.code


# ─── pure predicates ──────────────────────────────────────────────────────


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1",
    "0.0.0.0", "224.0.0.1", "240.0.0.1", "::1", "fe80::1", "fc00::1", "ff02::1", "::",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "64:ff9b::7f00:1", "garbage",
])
def test_non_public_addresses_are_rejected(ip):
    assert ip_is_public(ip) is False


@pytest.mark.parametrize("ip", [PUBLIC_IP, "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"])
def test_public_addresses_pass(ip):
    assert ip_is_public(ip) is True


def test_host_allowlist_matches_on_dot_boundary_only():
    allow = DEFAULT_ALLOWED_HOSTS
    assert host_allowed("scontent.cdninstagram.com", allow)
    assert host_allowed("a.b.fbcdn.net", allow)
    assert host_allowed("SCONTENT.CDNINSTAGRAM.COM.", allow)
    assert not host_allowed("cdninstagram.com", allow)  # wildcard = subdomains only
    assert not host_allowed("evilcdninstagram.com", allow)
    assert not host_allowed("cdninstagram.com.evil.io", allow)
    assert not host_allowed("fbcdn.net.evil.io", allow)
    assert host_allowed("example.com", ("example.com",))
    assert not host_allowed("a.example.com", ("example.com",))


# ─── URL gate (before any DNS or network) ─────────────────────────────────


@pytest.mark.parametrize("url,code", [
    ("http://scontent.cdninstagram.com/a.jpg", "scheme"),
    ("ftp://scontent.cdninstagram.com/a.jpg", "scheme"),
    ("file:///etc/passwd", "scheme"),
    ("https://scontent.cdninstagram.com:8443/a.jpg", "port"),
    ("https://user:pw@scontent.cdninstagram.com/a.jpg", "invalid_url"),
    ("https://evil.example.com/a.jpg", "host_not_allowed"),
    ("https://169.254.169.254/latest/meta-data", "host_not_allowed"),
    ("https://localhost/a.jpg", "host_not_allowed"),
    ("https://scontent.cdninstagram.com.evil.io/a.jpg", "host_not_allowed"),
    ("https://[::1]/a.jpg", "host_not_allowed"),
    ("not a url", "scheme"),
])
def test_url_gate_rejects_before_dns_or_network(url, code):
    dns_calls: list = []
    hits: list = []

    def handler(request):
        hits.append(request)
        return _ok()

    f = RealSafeFetcher(resolver=_resolver({}, dns_calls), transport=httpx.MockTransport(handler))
    with pytest.raises(SafeFetchError) as exc:
        _fetch(f, url)
    assert _code(exc) == code
    assert dns_calls == [] and hits == []


# ─── DNS / address gate ───────────────────────────────────────────────────


@pytest.mark.parametrize("answers", [
    ["127.0.0.1"], ["10.1.2.3"], ["169.254.169.254"], ["::1"], ["fe80::1"],
    [PUBLIC_IP, "10.0.0.1"],  # mixed answer set: one bad address rejects the host
    ["::ffff:192.168.0.1"],
])
def test_hostname_resolving_to_non_public_address_is_blocked(answers):
    hits: list = []
    f = _fetcher(lambda r: hits.append(r) or _ok(), {"scontent-gru1-1.cdninstagram.com": answers})
    with pytest.raises(SafeFetchError) as exc:
        _fetch(f)
    assert _code(exc) == "blocked_address" and hits == []


def test_dns_failure_is_typed():
    f = _fetcher(lambda r: _ok(), {"other.cdninstagram.com": [PUBLIC_IP]})
    with pytest.raises(SafeFetchError) as exc:
        _fetch(f)
    assert _code(exc) == "dns"


# ─── connection pinning ───────────────────────────────────────────────────


def test_connects_to_resolved_ip_with_host_and_sni_preserved_and_resolves_once():
    seen = {}
    dns_calls: list = []

    def handler(request):
        seen["host_url"] = request.url.host
        seen["host_header"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        seen["path"] = request.url.raw_path
        return _ok()

    f = RealSafeFetcher(
        resolver=_resolver({"scontent-gru1-1.cdninstagram.com": [PUBLIC_IP]}, dns_calls),
        transport=httpx.MockTransport(handler),
    )
    res = _fetch(f, CDN + "?_nc_ht=x&oh=1")
    assert seen["host_url"] == PUBLIC_IP
    assert seen["host_header"] == "scontent-gru1-1.cdninstagram.com"
    assert seen["sni"] == "scontent-gru1-1.cdninstagram.com"
    assert seen["path"] == b"/v/t51/a.jpg?_nc_ht=x&oh=1"
    assert dns_calls == ["scontent-gru1-1.cdninstagram.com"]
    assert res.peer_ip == PUBLIC_IP and res.data == JPEG and res.content_type == "image/jpeg"


def test_ipv6_target_is_bracketed():
    seen = {}

    def handler(request):
        seen["host"] = request.url.host
        return _ok()

    f = _fetcher(handler, {"scontent-gru1-1.cdninstagram.com": ["2606:4700:4700::1111"]})
    _fetch(f)
    assert seen["host"] == "2606:4700:4700::1111"


def test_falls_through_to_next_address_on_connect_error():
    tried: list[str] = []

    def handler(request):
        tried.append(request.url.host)
        if request.url.host == "8.8.4.4":
            raise httpx.ConnectError("refused")
        return _ok()

    f = _fetcher(handler, {"scontent-gru1-1.cdninstagram.com": ["8.8.4.4", "8.8.8.8"]})
    assert _fetch(f).peer_ip == "8.8.8.8" and tried == ["8.8.4.4", "8.8.8.8"]


def test_all_addresses_failing_is_a_network_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(handler))
    assert _code(exc) == "network"


# ─── redirects ────────────────────────────────────────────────────────────


def test_redirect_to_allowed_host_is_followed_and_revalidated():
    dns_calls: list = []

    def handler(request):
        if request.headers["host"] == "a.cdninstagram.com":
            return httpx.Response(302, headers={"location": "https://b.fbcdn.net/x.jpg"})
        return _ok()

    f = RealSafeFetcher(
        resolver=_resolver({"a.cdninstagram.com": [PUBLIC_IP], "b.fbcdn.net": ["8.8.8.8"]}, dns_calls),
        transport=httpx.MockTransport(handler),
    )
    res = _fetch(f, "https://a.cdninstagram.com/x.jpg")
    assert res.url == "https://b.fbcdn.net/x.jpg" and res.redirects == 1
    assert dns_calls == ["a.cdninstagram.com", "b.fbcdn.net"]


def test_relative_redirect_is_resolved_against_current_url():
    def handler(request):
        if request.url.path == "/old.jpg":
            return httpx.Response(301, headers={"location": "/new.jpg"})
        return _ok()

    res = _fetch(_fetcher(handler), "https://scontent-gru1-1.cdninstagram.com/old.jpg")
    assert res.url == "https://scontent-gru1-1.cdninstagram.com/new.jpg"


@pytest.mark.parametrize("target,code", [
    ("http://scontent-gru1-1.cdninstagram.com/a.jpg", "scheme"),
    ("https://evil.example.com/a.jpg", "host_not_allowed"),
    ("https://169.254.169.254/latest/meta-data/", "host_not_allowed"),
    ("https://localhost/", "host_not_allowed"),
])
def test_redirect_to_disallowed_target_is_refused(target, code):
    def handler(request):
        return httpx.Response(302, headers={"location": target})

    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(handler))
    assert _code(exc) == code


def test_redirect_to_allowed_name_that_resolves_private_is_refused():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://rebind.fbcdn.net/a.jpg"})

    f = RealSafeFetcher(
        resolver=_resolver({"scontent-gru1-1.cdninstagram.com": [PUBLIC_IP], "rebind.fbcdn.net": ["127.0.0.1"]}),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(SafeFetchError) as exc:
        _fetch(f)
    assert _code(exc) == "blocked_address"


def test_redirect_loop_is_capped():
    hops: list = []

    def handler(request):
        hops.append(1)
        return httpx.Response(302, headers={"location": CDN})

    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(handler, max_redirects=3))
    assert _code(exc) == "redirect_limit" and len(hops) == 4  # initial + 3


def test_redirect_without_location_is_invalid():
    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(lambda r: httpx.Response(302)))
    assert _code(exc) == "redirect_invalid"


# ─── body limits, content type, magic ─────────────────────────────────────


def test_streaming_cap_enforced_without_content_length():
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "image/jpeg"},
            content=iter([JPEG] + [b"\x00" * 600] * 4),  # chunked, no length
        )

    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(handler), max_bytes=1000)
    assert _code(exc) == "too_large"


def test_lying_content_length_cannot_bypass_the_cap():
    def handler(request):
        return httpx.Response(
            200, content=JPEG + b"\x00" * 5000,
            headers={"content-type": "image/jpeg", "content-length": "10"},
        )

    with pytest.raises(SafeFetchError):
        _fetch(_fetcher(handler), max_bytes=1000)


def test_declared_oversize_is_rejected_early():
    def handler(request):
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg", "content-length": "99999"})

    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(handler), max_bytes=1000)
    assert _code(exc) == "too_large"


def test_exactly_at_cap_is_accepted():
    body = JPEG + b"\x00" * (1000 - len(JPEG))
    assert len(_fetch(_fetcher(lambda r: _ok(body)), max_bytes=1000).data) == 1000


@pytest.mark.parametrize("ctype", ["text/html", "application/octet-stream", ""])
def test_content_type_allowlist(ctype):
    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(lambda r: _ok(ctype=ctype)))
    assert _code(exc) == "content_type"


def test_content_type_parameters_and_case_are_normalized():
    assert _fetch(_fetcher(lambda r: _ok(ctype="Image/JPEG; charset=binary"))).content_type == "image/jpeg"


def test_magic_bytes_must_match_declared_type():
    html_pretending_to_be_jpeg = b"<html>" + b"x" * 40
    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(lambda r: _ok(html_pretending_to_be_jpeg)), expect_magic=(MAGIC_JPEG,))
    assert _code(exc) == "magic"


def test_magic_accepts_any_declared_signature():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    res = _fetch(_fetcher(lambda r: _ok(png, "image/png")),
                 allowed_content_types=("image/png",), expect_magic=(MAGIC_JPEG, MAGIC_PNG))
    assert res.data == png


def test_webp_and_mp4_signatures():
    webp = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
    assert MAGIC_WEBP.matches(webp) and not MAGIC_WEBP.matches(b"RIFF\x10\x00\x00\x00WAVEfmt ")
    assert MAGIC_MP4.matches(mp4) and not MAGIC_MP4.matches(webp)


def test_body_shorter_than_signature_fails_magic():
    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(lambda r: _ok(b"\xff\xd8")), expect_magic=(MAGIC_JPEG,))
    assert _code(exc) == "magic"


@pytest.mark.parametrize("status", [403, 404, 500])
def test_upstream_error_status_is_typed(status):
    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(lambda r: httpx.Response(status)))
    assert _code(exc) == "http_status"


def test_timeouts_are_typed():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SafeFetchError) as exc:
        _fetch(_fetcher(handler))
    assert _code(exc) == "timeout"


def test_total_deadline_aborts_a_slow_drip():
    ticks = iter(range(0, 1000, 20))  # +20 s per clock read

    def handler(request):
        return httpx.Response(200, headers={"content-type": "image/jpeg"},
                              content=iter([JPEG, b"\x00" * 10, b"\x00" * 10, b"\x00" * 10]))

    f = RealSafeFetcher(resolver=_resolver({"scontent-gru1-1.cdninstagram.com": [PUBLIC_IP]}),
                        transport=httpx.MockTransport(handler), total_timeout=30,
                        _clock=lambda: float(next(ticks)))
    with pytest.raises(SafeFetchError) as exc:
        _fetch(f, max_bytes=10_000)
    assert _code(exc) == "timeout"


@pytest.mark.parametrize("kw", [{"max_bytes": 0}, {"allowed_content_types": ()}])
def test_bad_arguments_raise_value_error(kw):
    with pytest.raises(ValueError):
        _fetch(_fetcher(lambda r: _ok()), **kw)


def test_no_ambient_proxy_or_cookies_are_used():
    seen = {}

    def handler(request):
        seen["headers"] = dict(request.headers)
        return _ok()

    _fetch(_fetcher(handler))
    assert "cookie" not in seen["headers"] and "authorization" not in seen["headers"]


# ─── Fake + factory ───────────────────────────────────────────────────────


class TestFake:
    def test_serves_seeded_and_records_calls(self):
        fake = FakeSafeFetcher({CDN: FetchResult(url=CDN, status=200, content_type="image/jpeg", data=JPEG)})
        res = fake.fetch(CDN, max_bytes=1024, allowed_content_types=("image/jpeg",), expect_magic=(MAGIC_JPEG,))
        assert res.data == JPEG and fake.calls == [CDN]

    def test_fake_runs_the_real_url_gate(self):
        fake = FakeSafeFetcher()
        with pytest.raises(SafeFetchError) as exc:
            fake.fetch("https://evil.example.com/a.jpg", max_bytes=1, allowed_content_types=("image/jpeg",))
        assert _code(exc) == "host_not_allowed"

    def test_fake_enforces_size_type_and_magic(self):
        big = FakeSafeFetcher({CDN: FetchResult(url=CDN, status=200, content_type="image/jpeg", data=JPEG)})
        with pytest.raises(SafeFetchError) as exc:
            big.fetch(CDN, max_bytes=10, allowed_content_types=("image/jpeg",))
        assert _code(exc) == "too_large"
        with pytest.raises(SafeFetchError) as exc:
            big.fetch(CDN, max_bytes=1024, allowed_content_types=("image/png",))
        assert _code(exc) == "content_type"
        with pytest.raises(SafeFetchError) as exc:
            big.fetch(CDN, max_bytes=1024, allowed_content_types=("image/jpeg",), expect_magic=(MAGIC_PNG,))
        assert _code(exc) == "magic"

    def test_seeded_error_is_raised_and_unseeded_is_http_status(self):
        err = SafeFetchError("timeout", "slow")
        fake = FakeSafeFetcher({CDN: err})
        with pytest.raises(SafeFetchError) as exc:
            fake.fetch(CDN, max_bytes=1, allowed_content_types=("image/jpeg",))
        assert exc.value is err
        with pytest.raises(SafeFetchError) as exc:
            FakeSafeFetcher().fetch(CDN, max_bytes=1, allowed_content_types=("image/jpeg",))
        assert _code(exc) == "http_status"


def test_factory_defaults_to_fake_and_builds_real():
    assert isinstance(make_safe_fetcher(), FakeSafeFetcher)
    assert isinstance(make_safe_fetcher(real=True, max_redirects=1), RealSafeFetcher)
