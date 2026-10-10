"""SSRF-safe media downloader -- Protocol + Fake + Real + factory.

For fetching a URL that a THIRD PARTY controls (an Instagram ``media_url`` read
through Business Discovery, a thumbnail, a Reel for transcription). A URL that
data names must never make the server reach an internal address, so every
fetch is gated, in this order, per hop:

1. ``https`` only, no userinfo, port 443 only.
2. Host allow-list (CALLER-supplied; default = Instagram/Facebook CDNs). A
   ``*.example.com`` entry matches subdomains on a DOT boundary
   (``evilcdninstagram.com`` and ``cdninstagram.com.evil.io`` do not match);
   a bare ``example.com`` entry matches that host exactly.
3. DNS is resolved ONCE. EVERY returned address must be globally routable
   (no private, loopback, link-local -- cloud metadata 169.254.169.254 --
   multicast, CGNAT, reserved, unspecified, NAT64, IPv4-mapped IPv6 of any of
   those). One bad answer rejects the host (DNS-rebinding / mixed answers).
4. The TCP/TLS connection goes to THAT resolved IP -- the hostname is never
   resolved a second time (no TOCTOU) -- with ``Host`` and TLS SNI/certificate
   verification pinned to the original hostname.
5. Redirects are followed manually, at most ``max_redirects`` (default 3), and
   each hop is re-validated from step 1.
6. The body is streamed under a hard byte cap (``Content-Length`` is only an
   early-out, never trusted), a total deadline, connect/read timeouts, a
   content-type allow-list, and a caller-declared magic-byte check.

Failure is a typed :class:`SafeFetchError` with a stable ``code``; there is no
silent fallback and no partial result.

    from noctusai_lib.integrations.media.safe_fetch import (
        MAGIC_JPEG, MAGIC_PNG, MAGIC_WEBP, safe_fetch,
    )
    result = safe_fetch(
        thumbnail_url, max_bytes=2 * 1024 * 1024,
        allowed_content_types=("image/jpeg", "image/png", "image/webp"),
        expect_magic=(MAGIC_JPEG, MAGIC_PNG, MAGIC_WEBP),
    )

Tests inject ``resolver`` / ``transport`` (the DNS + network boundary); the
validation logic is never bypassed.
"""
from __future__ import annotations

import ipaddress
import socket
import time
import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol, Sequence
from urllib.parse import SplitResult, urljoin, urlsplit

import httpx

#: Instagram / Facebook media CDNs (contract geracao section 9.2).
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("*.cdninstagram.com", "*.fbcdn.net")
DEFAULT_MAX_REDIRECTS = 3
DEFAULT_CONNECT_TIMEOUT_S = 10.0
DEFAULT_READ_TIMEOUT_S = 30.0
DEFAULT_TOTAL_TIMEOUT_S = 60.0
_USER_AGENT = "noctusai-safe-fetch/1"

#: Stable machine codes of :class:`SafeFetchError`.
ERROR_CODES = (
    "invalid_url", "scheme", "port", "host_not_allowed", "dns", "blocked_address",
    "redirect_limit", "redirect_invalid", "http_status", "too_large",
    "content_type", "magic", "timeout", "network",
)


class SafeFetchError(Exception):
    def __init__(self, code: str, message: str, *, url: str | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.url = url


@dataclass(frozen=True)
class Magic:
    """A file signature: every ``(offset, bytes)`` part must match."""

    name: str
    parts: tuple[tuple[int, bytes], ...]

    @property
    def needed(self) -> int:
        return max(off + len(sig) for off, sig in self.parts)

    def matches(self, head: bytes) -> bool:
        return all(head[off:off + len(sig)] == sig for off, sig in self.parts)


MAGIC_JPEG = Magic("jpeg", ((0, b"\xff\xd8\xff"),))
MAGIC_PNG = Magic("png", ((0, b"\x89PNG\r\n\x1a\n"),))
MAGIC_WEBP = Magic("webp", ((0, b"RIFF"), (8, b"WEBP")))
MAGIC_MP4 = Magic("mp4", ((4, b"ftyp"),))


@dataclass(frozen=True)
class FetchResult:
    url: str  # final URL after redirects
    status: int
    content_type: str  # lowercased, parameters stripped
    data: bytes
    redirects: int = 0
    peer_ip: str | None = None


class SafeFetcher(Protocol):
    def fetch(
        self,
        url: str,
        *,
        max_bytes: int,
        allowed_content_types: Sequence[str],
        allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
        expect_magic: Sequence[Magic] | None = None,
    ) -> FetchResult: ...


# ─── validation (shared by Fake and Real, so Fake cannot be laxer) ─────────


def host_allowed(host: str, allowed_hosts: Sequence[str]) -> bool:
    """Dot-boundary suffix match. ``*.x.com`` = strict subdomains of x.com;
    ``x.com`` = exactly x.com."""

    host = host.lower().rstrip(".")
    for entry in allowed_hosts:
        e = entry.strip().lower().rstrip(".")
        if not e:
            continue
        if e.startswith("*."):
            if host.endswith("." + e[2:]) and len(host) > len(e) - 1:
                return True
        elif host == e:
            return True
    return False


def ip_is_public(ip: str) -> bool:
    """True only for a globally routable unicast address."""

    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return ip_is_public(str(addr.ipv4_mapped))
        if addr.sixtofour is not None and not ip_is_public(str(addr.sixtofour)):
            return False
        if addr.teredo is not None:
            return False  # tunnelled; the embedded server/client is not vettable
        if addr in ipaddress.ip_network("64:ff9b::/96"):  # NAT64: embeds an IPv4
            return False
    return bool(addr.is_global) and not (
        addr.is_multicast or addr.is_private or addr.is_loopback
        or addr.is_link_local or addr.is_reserved or addr.is_unspecified
    )


def validate_url(url: str, allowed_hosts: Sequence[str]) -> SplitResult:
    """Scheme / userinfo / port / host allow-list. Returns the parsed URL."""

    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
    except ValueError as exc:
        raise SafeFetchError("invalid_url", "unparseable URL", url=url) from exc
    if parts.scheme.lower() != "https":
        raise SafeFetchError("scheme", "only https is allowed", url=url)
    if not host:
        raise SafeFetchError("invalid_url", "no host", url=url)
    if parts.username is not None or parts.password is not None:
        raise SafeFetchError("invalid_url", "userinfo is not allowed", url=url)
    if port not in (None, 443):
        raise SafeFetchError("port", "only port 443 is allowed", url=url)
    if not host_allowed(host, allowed_hosts):
        raise SafeFetchError("host_not_allowed", f"host {host!r} is not allow-listed", url=url)
    return parts


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SafeFetchError("dns", f"cannot resolve {host!r}") from exc
    seen: dict[str, None] = {}
    for info in infos:
        seen.setdefault(str(info[4][0]), None)
    return list(seen)


def resolve_public(host: str, resolver: Callable[[str, int], list[str]]) -> list[str]:
    """Resolve once; every address must be public or the host is rejected."""

    try:
        literal = ipaddress.ip_address(host)
        addrs = [str(literal)]
    except ValueError:
        addrs = list(resolver(host, 443))
    if not addrs:
        raise SafeFetchError("dns", f"no addresses for {host!r}")
    bad = [a for a in addrs if not ip_is_public(a)]
    if bad:
        raise SafeFetchError("blocked_address", f"{host!r} resolves to a non-public address")
    return addrs


def _normalize_content_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _check_args(max_bytes: int, allowed_content_types: Sequence[str]) -> None:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")
    if not allowed_content_types:
        raise ValueError("allowed_content_types must not be empty")


def _check_magic(head: bytes, expect_magic: Sequence[Magic]) -> None:
    if not any(m.matches(head) for m in expect_magic):
        raise SafeFetchError("magic", "content does not match the declared file type")


# ─── Fake ─────────────────────────────────────────────────────────────────


class FakeSafeFetcher:
    """Deterministic, no IO. Serves ``responses[url]`` (a ``FetchResult`` or a
    ``SafeFetchError`` to raise) AFTER running the real URL validation, size,
    content-type and magic checks -- so a consumer's wrong allow-list or cap
    fails in its tests, not in production."""

    def __init__(self, responses: Mapping[str, FetchResult | SafeFetchError] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[str] = []

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int,
        allowed_content_types: Sequence[str],
        allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
        expect_magic: Sequence[Magic] | None = None,
    ) -> FetchResult:
        _check_args(max_bytes, allowed_content_types)
        validate_url(url, allowed_hosts)
        self.calls.append(url)
        item = self.responses.get(url)
        if item is None:
            raise SafeFetchError("http_status", "404 (fake: no response seeded)", url=url)
        if isinstance(item, SafeFetchError):
            raise item
        if len(item.data) > max_bytes:
            raise SafeFetchError("too_large", f"body exceeds {max_bytes} bytes", url=url)
        if _normalize_content_type(item.content_type) not in {c.lower() for c in allowed_content_types}:
            raise SafeFetchError("content_type", f"{item.content_type!r} not allowed", url=url)
        if expect_magic:
            _check_magic(item.data[:64], expect_magic)
        return item


# ─── Real ─────────────────────────────────────────────────────────────────


@dataclass
class RealSafeFetcher:
    """Real downloader. ``resolver`` / ``transport`` are the DNS and network
    seams (tests inject them); production uses the system resolver and httpx's
    default transport."""

    max_redirects: int = DEFAULT_MAX_REDIRECTS
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_S
    read_timeout: float = DEFAULT_READ_TIMEOUT_S
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT_S
    resolver: Callable[[str, int], list[str]] = system_resolver
    transport: httpx.BaseTransport | None = None
    _clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int,
        allowed_content_types: Sequence[str],
        allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
        expect_magic: Sequence[Magic] | None = None,
    ) -> FetchResult:
        _check_args(max_bytes, allowed_content_types)
        allowed_ct = {c.lower() for c in allowed_content_types}
        deadline = self._clock() + self.total_timeout
        current = url
        for hop in range(self.max_redirects + 1):
            parts = validate_url(current, allowed_hosts)
            host = (parts.hostname or "").lower().rstrip(".")
            addrs = self._resolve_with_deadline(host, deadline, current)
            response = self._get_once(current, parts, host, addrs, max_bytes, allowed_ct,
                                      expect_magic, deadline, hop)
            if isinstance(response, FetchResult):
                return response
            current = response  # the next (unvalidated) redirect target
        raise SafeFetchError("redirect_limit", f"more than {self.max_redirects} redirects", url=url)

    def _resolve_with_deadline(self, host: str, deadline: float, url: str) -> list[str]:
        """DNS in a worker thread so ``getaddrinfo`` (which has no timeout of
        its own) cannot outlive the total deadline."""

        remaining = deadline - self._clock()
        if remaining <= 0:
            raise SafeFetchError("timeout", "total deadline exceeded before DNS", url=url)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="safe-fetch-dns")
        future = pool.submit(resolve_public, host, self.resolver)
        try:
            return future.result(timeout=remaining)
        except concurrent.futures.TimeoutError as exc:
            raise SafeFetchError("timeout", "DNS resolution exceeded the total deadline", url=url) from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _get_once(
        self, url: str, parts: SplitResult, host: str, addrs: list[str], max_bytes: int,
        allowed_ct: set[str], expect_magic: Sequence[Magic] | None, deadline: float, hop: int,
    ) -> FetchResult | str:
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise SafeFetchError("timeout", "total deadline exceeded", url=url)
        # Connect + header read are bounded by what is left of the total deadline.
        timeout = httpx.Timeout(
            min(self.read_timeout, remaining), connect=min(self.connect_timeout, remaining)
        )
        last_exc: Exception | None = None
        for ip in addrs:
            host_ip = f"[{ip}]" if ":" in ip else ip
            target = f"https://{host_ip}{path}"
            try:
                with httpx.Client(
                    transport=self.transport, timeout=timeout, follow_redirects=False,
                    trust_env=False, headers={"User-Agent": _USER_AGENT},
                ) as client:
                    with client.stream(
                        "GET", target,
                        headers={"Host": host, "Accept": "*/*", "Accept-Encoding": "identity"},
                        extensions={"sni_hostname": host},
                    ) as resp:
                        return self._consume(resp, url, ip, max_bytes, allowed_ct,
                                             expect_magic, deadline, hop)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc  # try the next resolved address
                continue
            except httpx.TimeoutException as exc:
                raise SafeFetchError("timeout", "request timed out", url=url) from exc
            except httpx.HTTPError as exc:
                raise SafeFetchError("network", type(exc).__name__, url=url) from exc
        if isinstance(last_exc, httpx.ConnectTimeout):
            raise SafeFetchError("timeout", "connect timed out", url=url) from last_exc
        raise SafeFetchError("network", "could not connect", url=url) from last_exc

    def _consume(
        self, resp: httpx.Response, url: str, ip: str, max_bytes: int, allowed_ct: set[str],
        expect_magic: Sequence[Magic] | None, deadline: float, hop: int,
    ) -> FetchResult | str:
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                raise SafeFetchError("redirect_invalid", "redirect without Location", url=url)
            return urljoin(url, location)
        if not 200 <= resp.status_code < 300:
            raise SafeFetchError("http_status", f"upstream status {resp.status_code}", url=url)
        ctype = _normalize_content_type(resp.headers.get("content-type"))
        if ctype not in allowed_ct:
            raise SafeFetchError("content_type", f"{ctype or 'missing'!r} not allowed", url=url)
        encoding = resp.headers.get("content-encoding", "").strip().lower()
        if encoding not in ("", "identity"):
            # Refused before any body is read: one compressed chunk could
            # otherwise expand ~1000x past the byte cap in memory.
            raise SafeFetchError("content_type", f"content-encoding {encoding!r} is not allowed", url=url)
        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise SafeFetchError("too_large", f"declared length exceeds {max_bytes} bytes", url=url)
        need = max((m.needed for m in expect_magic), default=0) if expect_magic else 0
        buf = bytearray()
        magic_checked = not expect_magic
        for chunk in resp.iter_bytes():  # identity-only: compressed refused above
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise SafeFetchError("too_large", f"body exceeds {max_bytes} bytes", url=url)
            if self._clock() > deadline:
                raise SafeFetchError("timeout", "total download time exceeded", url=url)
            if not magic_checked and len(buf) >= need:
                _check_magic(bytes(buf[:need]), expect_magic or ())
                magic_checked = True
        if not magic_checked:
            _check_magic(bytes(buf), expect_magic or ())
        return FetchResult(url=url, status=resp.status_code, content_type=ctype,
                           data=bytes(buf), redirects=hop, peer_ip=ip)


# ─── factory + convenience ────────────────────────────────────────────────


def make_safe_fetcher(*, real: bool = False, **real_kwargs) -> SafeFetcher:
    """``FakeSafeFetcher`` by default (dev/test); ``real=True`` for the real one."""

    if real:
        return RealSafeFetcher(**real_kwargs)
    return FakeSafeFetcher()


def safe_fetch(
    url: str,
    *,
    max_bytes: int,
    allowed_content_types: Sequence[str],
    allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
    expect_magic: Sequence[Magic] | None = None,
) -> FetchResult:
    """One-shot Real fetch with default timeouts."""

    return RealSafeFetcher().fetch(
        url, max_bytes=max_bytes, allowed_content_types=allowed_content_types,
        allowed_hosts=allowed_hosts, expect_magic=expect_magic,
    )


__all__ = [
    "DEFAULT_ALLOWED_HOSTS", "ERROR_CODES", "FakeSafeFetcher", "FetchResult", "MAGIC_JPEG",
    "MAGIC_MP4", "MAGIC_PNG", "MAGIC_WEBP", "Magic", "RealSafeFetcher", "SafeFetchError",
    "SafeFetcher", "host_allowed", "ip_is_public", "make_safe_fetcher", "resolve_public",
    "safe_fetch", "system_resolver", "validate_url",
]
