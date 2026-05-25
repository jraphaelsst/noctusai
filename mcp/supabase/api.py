"""Supabase Management API runner — the external-service seam for this
connector.

Every `supabase.*` tool talks to the Supabase Management API
(`https://api.supabase.com`) *through the operator's Personal Access
Token*. `request_json` is the single HTTP boundary; the urllib mechanics
are delegated to the shared `_kit.transport.request_json` seam
(kit-connector-boilerplate-consolidation). This wrapper keeps Supabase's
own `SupabaseApiError` type, the 424 not-configured gate, the
canonical-base normalizer, the empty-body→`None` convention, and the
30s default timeout (`db.query` can run a slow statement).

**Test seam.** Supabase is an external service, so tests
`unittest.mock.patch("supabase.api.request_json", ...)` to feed canned
payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"). The header /
transport tests patch the shared boundary `_kit.transport.urlopen`. Our
own code is never patched.

**No envelope.** Unlike Cloudflare (which wraps every response in
`{success, errors, result}`), the Supabase Management API returns the
resource JSON directly (a project object, an array of projects, a query
result-set). The shared seam therefore just parses + returns the body;
the truth of success/failure is the HTTP status, which `urllib` raises as
`HTTPError`. A non-2xx is surfaced as a typed `SupabaseApiError` carrying
the upstream status (401/403/404/4xx/5xx passed through).

**Gated-capability honesty** (CLAUDE.md §1). No access token, an
unreachable host, or an upstream non-2xx is a typed, never-faked signal:
tools return a `SupabaseApiError` envelope (status carried), and
`supabase.diagnostics.connection_status` reports `configured=false` /
`reachable=false` / `authenticated=false`. We never fabricate success.

**No WAF UA trick.** `api.supabase.com` is NOT behind a Cloudflare WAF
that bans the default urllib UA (unlike `mcp/hostinger` / `mcp/cloudflare`
against Cloudflare-fronted hosts), so a plain descriptive `User-Agent`
suffices. Auth is header `Authorization: Bearer <token>`.

Paths are **absolute** under the fixed base (`/v1/projects`,
`/v1/projects/{ref}/database/query`, ...) — `normalize_base_url` only
strips a trailing slash and supplies the canonical base when unset
(mirrors WAHA/hostinger/cloudflare absolute paths, unlike n8n's `/api/v1`
suffix).
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from _kit.transport import request_json as _http_request_json

# Canonical Supabase Management API base. Effectively fixed (a single
# public API), but kept overridable via settings for testing.
DEFAULT_BASE_URL = "https://api.supabase.com"

# Plain descriptive UA — api.supabase.com is not WAF-gated, so no
# browser-impersonation header is needed (contrast cloudflare/hostinger).
_USER_AGENT = "noctusai-supabase-connector/1.0"


class SupabaseApiError(Exception):
    """A Supabase Management API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — connector not configured (no access token, or no project ref)
    - 401/403/404/422/4xx/5xx — the upstream Supabase HTTP status,
      passed through
    - 502 — host unreachable / timeout / unparseable (non-JSON) response
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(SupabaseApiError):
    """A write tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    The message states the concrete effect so the operator understands
    what they are authorizing (esp. `db.query` with mutating SQL and
    `migration.apply`, which change the live database).
    """

    def __init__(self, action: str, effect: str = ""):
        super().__init__(
            confirmation_required_message(action, effect),
            status=412,
        )


def resolve_ref(settings, passed: Optional[str]) -> tuple[str, Optional["SupabaseApiError"]]:
    """Resolve the project ref for a project-scoped tool: the passed arg
    wins, then the settings' configured default. Returns `(ref, None)` on
    success, else `("", SupabaseApiError(424))` — a project-scoped path
    cannot be built without a ref, so we surface a typed never-faked 424
    rather than a malformed URL.

    Takes the settings object explicitly (rather than calling
    `get_settings()` itself) so each leaf module resolves against ITS OWN
    `get_settings` binding — mirroring how cloudflare's per-module
    `_account_id_or_error` reads its own module's settings, which keeps
    `patch("<module>.get_settings")` honest in tests.
    """
    ref = passed or getattr(settings, "project_ref", None)
    if not ref:
        return "", SupabaseApiError(
            "no project ref — pass project_ref or set SUPABASE_PROJECT_REF "
            "in mcp/supabase/.env.",
            status=424,
        )
    return ref, None


def normalize_base_url(raw: str) -> str:
    """Return the API base with no trailing slash.

    Empty / unset ⇒ the canonical `DEFAULT_BASE_URL` (the Supabase
    Management API is a single public host). Paths are absolute
    (`/v1/projects`, ...) — there is no per-call suffix to normalize
    (mirrors WAHA/hostinger/cloudflare, unlike n8n's `/api/v1`).
    """
    base = (raw or "").rstrip("/")
    return base or DEFAULT_BASE_URL


def request_json(
    method: str,
    path: str,
    *,
    access_token: str,
    base_url: str = "",
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 30.0,
) -> object:
    """Call `<base><path>` and return the parsed JSON body (no envelope).

    `access_token` comes from the connector settings (resolved by the
    tool layer). Missing it is the connector-not-configured signal (424).
    Sends `Authorization: Bearer <token>`. Raises `SupabaseApiError`
    (typed `status`) on ANY failure — never a fabricated success. A 2xx
    with an empty body returns `None` (some Management endpoints answer
    with no body).

    `timeout` defaults to 30s — `db.query` can run a slow SQL statement
    (longer than the 20s connector default elsewhere).
    """
    if not access_token:
        raise SupabaseApiError(
            "Supabase connector not configured — set SUPABASE_ACCESS_TOKEN "
            "in mcp/supabase/.env (or the environment).",
            status=424,
        )
    # Delegate the urllib mechanics to the shared seam; Supabase keeps its
    # own canonical-base normalizer + SupabaseApiError type + the 424 gate +
    # the empty-body→None convention (empty_result=None) + the 30s timeout.
    # No WAF UA trick needed (api.supabase.com is not WAF-gated) — a plain
    # descriptive UA suffices.
    url = f"{normalize_base_url(base_url)}{path}"
    return _http_request_json(
        method,
        url,
        auth_header=("Authorization", f"Bearer {access_token}"),
        user_agent=_USER_AGENT,
        params=params,
        body=body,
        timeout=timeout,
        error_cls=SupabaseApiError,
        empty_result=None,
        label=f"Supabase API {method.upper()} {path}",
    )


__all__ = [
    "request_json",
    "resolve_ref",
    "normalize_base_url",
    "SupabaseApiError",
    "ConfirmationRequiredError",
    "DEFAULT_BASE_URL",
]
