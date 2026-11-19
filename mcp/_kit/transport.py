"""`_kit.transport` — the shared connector HTTP seam.

Every connector MCP (`n8n`, `waha`, `hostinger`, `cloudflare`, `supabase`)
hand-rolled a near-identical stdlib-`urllib` `request_json` (N=5 ⇒ formalized
here per the DRY recurrence rule). Connectors compose this; per-connector code
shrinks to the auth-header construction + base-URL normalization + (for the few
that need it) response-envelope handling.

Named `transport` (NOT `http`) on purpose: a module called `http.py` shadows the
stdlib `http` package the moment `mcp/_kit/` lands on `sys.path` (urllib's
`import http.client` then finds this file → circular import).

**Test seam.** The `urlopen` call site is the module attribute
`_kit.transport.urlopen` — a consuming connector's tests
`unittest.mock.patch("_kit.transport.urlopen", ...)` to feed canned responses
without a network call (external-boundary patch, sanctioned by `CLAUDE.md §1`;
our own code is never patched).

**Gated-capability honesty** (`CLAUDE.md §1`). Any HTTP / network / timeout /
non-JSON failure raises `error_cls(message, status=...)` — a typed, never-faked
signal carrying the upstream status (or 502 for unreachable/timeout/unparseable).
We never fabricate or partially-return a success.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import uuid
from typing import Callable, Optional
from urllib.request import Request, urlopen  # patch target: `_kit.transport.urlopen`

# Browser UA — LOAD-BEARING for endpoints behind Cloudflare's WAF: the default
# urllib UA is 403'd (hit live on developers.hostinger.com + api.cloudflare.com).
# Pass `user_agent=BROWSER_USER_AGENT` from a WAF-fronted connector.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_USER_AGENT = "noctusai-connector/1.0"


class ConnectorHttpError(Exception):
    """Default typed error for the shared seam. `status` feeds the
    `_kit.errors.typed_error` contract (`getattr(e, "status", None)`).

    A connector passes its OWN `error_cls` (its `<Vendor>ApiError`, ctor
    `(message, *, status=...)`) so the raised type — and any `isinstance`
    on it — stays connector-specific.
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def normalize_base_url(raw: str) -> str:
    """Trim trailing slashes. Connectors that need a path suffix (e.g. n8n's
    `/api/v1`) wrap this with their own normalizer."""
    return (raw or "").rstrip("/")


def request_json(
    method: str,
    url: str,
    *,
    auth_header: Optional[tuple[str, str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 20.0,
    error_cls: type = ConnectorHttpError,
    empty_result: object = None,
    label: str = "",
    on_http_error: Optional[Callable[[int, str, str], Optional[Exception]]] = None,
) -> object:
    """Issue `method url`, return parsed JSON (or `empty_result` on empty body).

    - `auth_header` — `(header_name, value)` injected verbatim. Covers Bearer
      (`("Authorization", f"Bearer {tok}")`), `X-Api-Key`, `X-N8N-API-KEY`, …;
      pass `None` for an unauthenticated call (e.g. WAHA `/ping`).
    - `user_agent` — pass `BROWSER_USER_AGENT` for WAF-fronted hosts.
    - `params` — `None`-valued entries are dropped (callers pass optional
      filters flatly).
    - `error_cls` — the connector's `<Vendor>ApiError`; raised (with `status`)
      on ANY failure. Never returns a partial/fabricated success.
    - `empty_result` — returned on an empty (2xx) body (n8n wants `{}`,
      supabase wants `None`).
    - `label` — human tag for error messages (default `"<METHOD> <url>"`).
    - `on_http_error` — OPTIONAL vendor error-body hook, called as
      `(status, body, tag)` on an `HTTPError` **before** the default raise.
      Return an exception to raise it instead (so a connector can attach a
      typed vendor error code — cloudflare's `errors[0].code`, omie's
      `faultstring`/`faultcode`); return `None` to fall through to the
      default `error_cls(...)`. A hook that itself raises is not swallowed.

      Formalized at N=2 (cloudflare's `cf_code` + omie's `faultstring`) —
      the seam extension this module's README flagged as the revisit
      trigger. Default `None` ⇒ byte-for-byte prior behavior for the five
      connectors that don't pass it.
    """
    tag = label or f"{method.upper()} {url}"
    payload, _ = request_bytes(
        method,
        url,
        auth_header=auth_header,
        user_agent=user_agent,
        params=params,
        body=body,
        accept="application/json",
        timeout=timeout,
        error_cls=error_cls,
        label=tag,
        on_http_error=on_http_error,
    )
    raw = payload.decode("utf-8", errors="replace")
    if not raw:
        return empty_result
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise error_cls(f"{tag} returned non-JSON output", status=502) from e


def encode_multipart(
    fields: Optional[dict] = None,
    files: Optional[list[tuple[str, str, bytes, str]]] = None,
) -> tuple[bytes, str]:
    """Encode a `multipart/form-data` body. Returns `(body, content_type)`.

    - `fields` — `{name: str}` text parts (`None` values dropped).
    - `files`  — `[(field_name, filename, content_bytes, mime_type), ...]`;
      a repeated `field_name` is how APIs take a list of files.
    """
    boundary = "noctus" + uuid.uuid4().hex
    crlf = b"\r\n"
    out = bytearray()
    for name, value in (fields or {}).items():
        if value is None:
            continue
        out += f"--{boundary}".encode() + crlf
        out += f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf
        out += str(value).encode("utf-8") + crlf
    for name, filename, content, mime in files or []:
        safe = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
        out += f"--{boundary}".encode() + crlf
        out += (
            f'Content-Disposition: form-data; name="{name}"; filename="{safe}"'
        ).encode() + crlf
        out += f"Content-Type: {mime}".encode() + crlf + crlf
        out += content + crlf
    out += f"--{boundary}--".encode() + crlf
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def request_bytes(
    method: str,
    url: str,
    *,
    auth_header: Optional[tuple[str, str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    params: Optional[dict] = None,
    body: Optional[object] = None,
    raw_body: Optional[tuple[bytes, str]] = None,
    accept: str = "*/*",
    timeout: float = 20.0,
    error_cls: type = ConnectorHttpError,
    label: str = "",
    on_http_error: Optional[Callable[[int, str, str], Optional[Exception]]] = None,
) -> tuple[bytes, dict]:
    """Issue `method url`, return `(raw response bytes, lower-cased headers)`.

    The binary sibling of `request_json` (audio/images/archives, or a JSON
    call whose RESPONSE HEADERS matter). Same typed-error contract: ANY
    HTTP/network/timeout failure raises `error_cls(message, status=...)`.

    - `body` — JSON-encoded (like `request_json`); `raw_body=(bytes,
      content_type)` sends a pre-encoded body (e.g. `encode_multipart`).
      Pass at most one of the two.
    - Error bodies are truncated to 500 chars and never include request data.
    """
    if body is not None and raw_body is not None:
        raise ValueError("pass either body (JSON) or raw_body, not both")
    tag = label or f"{method.upper()} {url}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"

    data: Optional[bytes] = None
    headers = {"Accept": accept, "User-Agent": user_agent}
    if auth_header is not None:
        headers[auth_header[0]] = auth_header[1]
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        data = raw_body[0]
        headers["Content-Type"] = raw_body[1]

    req = Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            resp_headers = {
                str(k).lower(): str(v)
                for k, v in (getattr(getattr(resp, "headers", None), "items", lambda: [])())
            }
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001 — body read is best-effort context
            detail = ""
        if on_http_error is not None:
            vendor_exc = on_http_error(e.code, detail, tag)
            if vendor_exc is not None:
                raise vendor_exc from e
        raise error_cls(
            f"{tag} → HTTP {e.code}" + (f": {detail}" if detail else ""),
            status=e.code,
        ) from e
    except urllib.error.URLError as e:
        raise error_cls(f"{tag} — host unreachable: {e.reason}", status=502) from e
    except TimeoutError as e:
        raise error_cls(f"{tag} timed out after {timeout}s", status=502) from e
    return payload, resp_headers


__all__ = [
    "BROWSER_USER_AGENT",
    "DEFAULT_USER_AGENT",
    "ConnectorHttpError",
    "normalize_base_url",
    "request_json",
    "request_bytes",
    "encode_multipart",
]
