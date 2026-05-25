"""noctus.dev.sso_smoke — end-to-end SSO login smoke against a LIVE core.

Promotes the one-off `sso_e2e` check into a repeatable, agent-runnable tool.
Drives the FULL cross-product SSO chain the way a product's SSOCallback does:

  1. mint a real core Supabase session (admin magic-link OTP + verify)
  2. POST /api/sso/token   — license-checked SSO token ("click a product")
  3. POST /api/sso/session — token → Supabase session (the product's call)
  4. GET  /api/auth/me     — the session reads the profile ("logged in")

Network-gated + honest: with no creds it returns ``status='not_configured'``
(never a faked pass). The HTTP layer is injected (``http``) so the colocated
test exercises the whole chain with zero network. A browser ``User-Agent`` is
sent on every request — core sits behind Cloudflare, whose WAF 1010-bans the
default urllib client signature (same rule as the Hostinger MCP).

Side effects: step 1 mints a one-time login OTP for the test user and step 3
re-syncs that user's ``user_metadata`` — both benign; use a TEST account
(`NOCTUS_SSO_SMOKE_EMAIL`) whose org holds a non-expired license for `product`.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Any, Callable

from settings import REPO_ROOT

# (method, url, json_body, headers) -> (status_code, parsed_json)
HttpFn = Callable[[str, str, "dict | None", "dict | None"], "tuple[int, dict]"]

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)  # clears Cloudflare WAF (error 1010 on the default urllib signature)

_STEPS = [
    "supabase_generate_link",
    "supabase_verify_otp",
    "core_sso_token",
    "core_sso_session",
    "core_auth_me",
]


def _default_http(method: str, url: str, body: dict | None, headers: dict | None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": _UA}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _parse(exc.read())
    except Exception as exc:  # connection refused / timeout / DNS
        return 0, {"_error": str(exc)}


def _parse(raw: bytes) -> dict:
    text = (raw or b"").decode(errors="replace") or "{}"
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {"_value": out}
    except json.JSONDecodeError:
        return {"_raw": text[:300]}


def _load_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _resolve_creds(env_file: str | None, creds: dict | None) -> dict:
    """Caller-injected creds win (tests); else env overlaid by an env file
    (defaults to the repo-root .env). File values take precedence."""
    if creds is not None:
        return creds
    path = env_file or str(pathlib.Path(REPO_ROOT) / ".env")
    env = {**os.environ, **_load_env_file(path)}
    return {
        "supabase_url": env.get("SUPABASE_URL", ""),
        "service_key": env.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        "anon_key": env.get("SUPABASE_ANON_KEY", ""),
        "email": env.get("NOCTUS_SSO_SMOKE_EMAIL", ""),
    }


def sso_smoke(
    core_url: str = "https://core.noctusai.com",
    email: str | None = None,
    product: str = "erp-imobiliario",
    env_file: str | None = None,
    http: HttpFn | None = None,
    creds: dict | None = None,
) -> dict[str, Any]:
    """Run the SSO login chain; return pass/fail + per-step detail.

    status: 'pass' (full chain + /api/auth/me identity matches) | 'fail'
    (a step did not return its expected token / final identity mismatch) |
    'not_configured' (missing Supabase creds or test email — honest, never
    a faked pass).
    """
    fetch = http or _default_http
    c = _resolve_creds(env_file, creds)
    email = (email or c.get("email") or "").strip()
    supa = (c.get("supabase_url") or "").rstrip("/")
    service = c.get("service_key") or ""
    anon = c.get("anon_key") or ""
    core = core_url.rstrip("/")

    if not (supa and service and anon and email):
        missing = [k for k, v in {
            "SUPABASE_URL": supa,
            "SUPABASE_SERVICE_ROLE_KEY": service,
            "SUPABASE_ANON_KEY": anon,
            "email/NOCTUS_SSO_SMOKE_EMAIL": email,
        }.items() if not v]
        return {
            "ok": False,
            "status": "not_configured",
            "exit_code": 1,
            "missing": missing,
            "detail": "SSO smoke needs Supabase creds + a test-account email (env / env_file / args).",
        }

    steps: list[dict[str, Any]] = []

    def record(name: str, status: int, ok: bool, extra: dict | None = None) -> bool:
        steps.append({"step": name, "http": status, "ok": ok, **(extra or {})})
        return ok

    def _fail() -> dict[str, Any]:
        return {"ok": False, "status": "fail", "exit_code": 1,
                "core_url": core, "product": product, "email": email, "steps": steps}

    # 1 — admin generate magic-link → one-time OTP (the login)
    st, j = fetch("POST", f"{supa}/auth/v1/admin/generate_link",
                  {"type": "magiclink", "email": email},
                  {"apikey": service, "Authorization": f"Bearer {service}"})
    otp = j.get("email_otp") or (j.get("properties") or {}).get("email_otp")
    if not record("supabase_generate_link", st, bool(otp)):
        return _fail()

    # 2 — verify OTP → real core access_token
    st, j = fetch("POST", f"{supa}/auth/v1/verify",
                  {"type": "magiclink", "email": email, "token": otp},
                  {"apikey": anon})
    core_tok = j.get("access_token")
    if not record("supabase_verify_otp", st, bool(core_tok)):
        return _fail()

    # 3 — mint SSO token (license-checked)
    st, j = fetch("POST", f"{core}/api/sso/token", {"product_slug": product},
                  {"Authorization": f"Bearer {core_tok}"})
    sso_tok = j.get("sso_token")
    if not record("core_sso_token", st, bool(sso_tok), {"product": product}):
        return _fail()

    # 4 — exchange SSO token for a session (the product SSOCallback call)
    st, j = fetch("POST", f"{core}/api/sso/session", {"token": sso_tok}, None)
    prod_tok = j.get("access_token")
    if not record("core_sso_session", st, bool(prod_tok), {"email": j.get("email")}):
        return _fail()

    # 5 — use the session to read the profile (proves "logged in")
    st, j = fetch("GET", f"{core}/api/auth/me", None,
                  {"Authorization": f"Bearer {prod_tok}"})
    me = (j.get("data") or j) if isinstance(j, dict) else {}
    me_email = me.get("email") or (me.get("user") or {}).get("email")
    passed = st == 200 and me_email == email
    record("core_auth_me", st, passed, {"email": me_email})

    return {
        "ok": passed,
        "status": "pass" if passed else "fail",
        "exit_code": 0 if passed else 1,
        "core_url": core,
        "product": product,
        "email": email,
        "steps": steps,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.sso_smoke",
        description=(
            "End-to-end SSO login smoke against a LIVE core (promotes the "
            "one-off sso_e2e check). Drives the full chain a product's "
            "SSOCallback uses: Supabase magic-link login → POST /api/sso/token "
            "(license-checked) → POST /api/sso/session → GET /api/auth/me. "
            "status='pass'|'fail'|'not_configured' — honest: no creds ⇒ "
            "not_configured, never a faked pass. Reads Supabase creds + "
            "NOCTUS_SSO_SMOKE_EMAIL from env / env_file (repo .env default); "
            "sends a browser UA (core is behind Cloudflare's WAF, err 1010). "
            "Side effects: a one-time login OTP + a user_metadata re-sync for "
            "the test user — use a TEST account. See KB § PATTERNS/core-url-routing.md."
        ),
    )
    def _sso_smoke(
        core_url: str = "https://core.noctusai.com",
        email: str | None = None,
        product: str = "erp-imobiliario",
        env_file: str | None = None,
    ) -> dict:
        return sso_smoke(core_url=core_url, email=email, product=product, env_file=env_file)


__all__ = ["sso_smoke", "register", "HttpFn"]
