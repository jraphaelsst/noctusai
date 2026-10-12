"""`noctus.dev.spa_smoke` — post-deploy gate for the SPA the user actually loads.

THE GAP THIS CLOSES (2026-08-11). Every existing deploy gate is blind to a broken
frontend bundle:

  • `deploy_image`'s health probe  → the CONTAINER is up
  • `/api/health`                  → the BACKEND answers
  • the public edge returning 200   → the HTML SHELL was served

None of them touches the JavaScript. A shipped bundle that 404s, is truncated, or
is served as the HTML fallback still leaves all three green while every user sees
a blank page. That is exactly the exposure of a UI-library change (the
react-router v6→v7 fleet migration), and under PROD-ONLY there is no dev fleet to
catch it first.

WHAT IT CHECKS, per product:
  1. the shell responds 200 and carries `<div id="root">` + a `/assets/*.js` tag
  2. that bundle responds 200, is big enough to be real, and is JS — not the SPA
     HTML fallback (the classic "asset 404 → index.html" silent failure, which
     returns 200 and would fool a naive status check)
  3. a DEEP LINK responds 200 (client-side routing / SPA fallback is wired)
  4. optional `expect_absent` / `expect_present` markers in the bundle text —
     how the react-router migration was verified (`@remix-run/router` is v6-only,
     so zero occurrences proves the v7 bundle actually shipped)

🔴 WHAT IT DOES NOT DO: it does not execute JavaScript, so it cannot catch a
runtime render crash inside a component. It closes the "bundle never arrived /
arrived wrong" class, which is the failure mode a deploy actually introduces.
Executing JS needs a headless browser; that is a deliberate non-goal here.

Prod sits behind the Cloudflare tunnel, so every request sends a browser
User-Agent — WAF rule 1010 rejects programmatic UAs (`KB § GUIDES/production-deploy.md`).

Depth: `KB § PATTERNS/devops/prod-deploy-safety-gates.md` · skill `noc-ship` § 6.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT

from . import _public_edge as _edge
from . import toolkit_freshness as _toolkit_freshness

#: WAF rule 1010 rejects non-browser User-Agents at the Cloudflare edge. The UA,
#: `_fetch` and the ingress resolver live in the stdlib-only `_public_edge`
#: module, shared with `prod_watchdog` (which runs in CI with no pip install).
_BROWSER_UA = _edge.BROWSER_UA

#: A real product bundle is hundreds of KB. Anything this small is a stub, an
#: error page, or a truncated upload — all of which would otherwise pass as 200.
_MIN_BUNDLE_BYTES = 10_000

#: A same-origin bundle path whose LAST directory is `assets/`, under an optional
#: Vite `base` prefix: `/assets/index-x.js`, and core's public site entry
#: `/_site/assets/index-site-x.js` (4cc4cf301). Anchored to a leading `/`, so an
#: absolute CDN URL never counts as "this product ships its own bundle".
_ASSET_RE = re.compile(r'src="(/(?:[^"/]+/)*assets/[^"]+\.js)"')
_ROOT_DIV_RE = re.compile(r'<div\s+id="root"\s*>')

#: Routes every seed-built SPA serves through its client router. `/` is checked
#: separately as the shell; this is the DEEP-LINK leg (SPA fallback must rewrite
#: an unknown path to index.html, else the router never boots on a direct hit).
DEFAULT_DEEP_LINK = "/login"

BUILD_SCOPE = REPO_ROOT / "deploy" / "fleet" / "build-scope.txt"
_fetch = _edge.fetch  # shared, stdlib-only; module-level so tests can inject


def _live_slugs() -> list[str]:
    """The active set — same source the build workflow scopes on."""
    return _edge.read_slug_file(BUILD_SCOPE)


def public_hostname(slug: str, domain: str = "noctusai.com") -> str:
    """The hostname this product is ACTUALLY served at.

    Resolved from `deploy/tunnel/ingress.yml` (the declared single source of
    truth for hostname → service routing) by the stdlib-only shared helper
    `_public_edge.public_hostname`, which `prod_watchdog` also uses — the
    history (the 2026-08-25 `erp.` / `social.` rename that turned a guessed
    `f"{slug}.{domain}"` into a false red) lives in that docstring.
    """
    return _edge.public_hostname(slug, Path(REPO_ROOT), domain)


def smoke_product(
    slug: str,
    *,
    domain: str = "noctusai.com",
    deep_link: str = DEFAULT_DEEP_LINK,
    expect_absent: list[str] | None = None,
    expect_present: list[str] | None = None,
) -> dict:
    """Smoke ONE product's public SPA. Returns `{ok, slug, url, checks, failures}`."""
    base = f"https://{public_hostname(slug, domain)}"
    checks: list[dict] = []
    failures: list[str] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}")

    # 1 — the shell
    status, body, _ = _fetch(base + "/")
    html = body.decode("utf-8", "replace")
    record("shell_http", status == 200, f"GET / -> {status or 'unreachable'}")
    if status != 200:
        return {"ok": False, "slug": slug, "url": base, "checks": checks, "failures": failures}

    record("shell_root_div", bool(_ROOT_DIV_RE.search(html)),
           "<div id=\"root\"> present" if _ROOT_DIV_RE.search(html) else "no mount point in the shell")

    m = _ASSET_RE.search(html)
    record("shell_bundle_tag", bool(m), m.group(1) if m else "no same-origin …/assets/*.js <script> in the shell")
    if not m:
        return {"ok": False, "slug": slug, "url": base, "checks": checks, "failures": failures}

    # 2 — the bundle itself
    asset = m.group(1)
    b_status, b_body, b_ctype = _fetch(base + asset)
    record("bundle_http", b_status == 200, f"GET {asset} -> {b_status or 'unreachable'}")
    if b_status == 200:
        record("bundle_size", len(b_body) >= _MIN_BUNDLE_BYTES,
               f"{len(b_body)} bytes (min {_MIN_BUNDLE_BYTES})")
        # The silent killer: a missing asset rewritten to index.html still 200s.
        looks_html = b_body.lstrip()[:15].lower().startswith(b"<!doctype html") or "text/html" in b_ctype
        record("bundle_is_js", not looks_html,
               f"content-type={b_ctype or '?'}" + (" — SPA fallback served instead of the asset!" if looks_html else ""))
        text = b_body.decode("utf-8", "replace")
        for marker in (expect_absent or []):
            record(f"absent:{marker}", marker not in text,
                   "absent" if marker not in text else f"UNEXPECTED marker {marker!r} in bundle")
        for marker in (expect_present or []):
            record(f"present:{marker}", marker in text,
                   "present" if marker in text else f"MISSING marker {marker!r} in bundle")

    # 3 — client routing on a direct hit
    d_status, _, _ = _fetch(base + deep_link)
    record("deep_link", d_status == 200, f"GET {deep_link} -> {d_status or 'unreachable'}")

    return {"ok": not failures, "slug": slug, "url": base, "checks": checks, "failures": failures}


@_toolkit_freshness.warn_gate("spa_smoke")
def spa_smoke(
    products: list[str] | None = None,
    *,
    domain: str = "noctusai.com",
    deep_link: str = DEFAULT_DEEP_LINK,
    expect_absent: list[str] | None = None,
    expect_present: list[str] | None = None,
) -> dict:
    """Smoke every live product's SPA (or the given subset).

    `products=None` uses `deploy/fleet/build-scope.txt` — the same active set the
    build workflow scopes on, so the gate and the build can never disagree about
    which products matter.
    """
    slugs = products or _live_slugs()
    if not slugs:
        return {"ok": False, "status": "error", "results": [],
                "error": ("no products to smoke — deploy/fleet/build-scope.txt is missing or "
                          "empty. Pass products=[...] explicitly, or regenerate it with "
                          "`python mcp/noctusai/cli.py --refresh-build-scope`.")}

    results = [
        smoke_product(s, domain=domain, deep_link=deep_link,
                      expect_absent=expect_absent, expect_present=expect_present)
        for s in slugs
    ]
    failed = [r for r in results if not r["ok"]]
    return {
        "ok": not failed,
        "status": "healthy" if not failed else "degraded",
        "checked": len(results),
        "failed": [r["slug"] for r in failed],
        "results": results,
        "summary": f"{len(results) - len(failed)}/{len(results)} SPA(s) serving a real bundle",
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.spa_smoke",
        description=(
            "Post-deploy gate for the FRONTEND the user actually loads. Every other "
            "deploy gate is blind here: deploy_image proves the container is up, "
            "/api/health proves the backend answers, and the edge returns 200 for the "
            "HTML shell even when the JS bundle is missing — a blank page for every "
            "user, all gates green. Per product: shell 200 + mount point + bundle tag; "
            "the bundle 200, big enough, and actually JS (not the SPA HTML fallback, "
            "which 200s and fools a naive check); and a DEEP LINK 200 (client routing "
            "wired). Optional expect_absent/expect_present markers assert what shipped "
            "— e.g. expect_absent=['@remix-run/router'] proves a react-router v7 bundle. "
            "products=None uses deploy/fleet/build-scope.txt. Sends a browser UA (CF WAF "
            "1010). Does NOT execute JS, so it cannot catch an in-component render crash. "
            "Run it after every deploy_image sweep. KB § PATTERNS/devops/prod-deploy-safety-gates.md."
        ),
    )
    def _spa_smoke(
        products: list[str] | None = None,
        domain: str = "noctusai.com",
        deep_link: str = DEFAULT_DEEP_LINK,
        expect_absent: list[str] | None = None,
        expect_present: list[str] | None = None,
    ) -> dict:
        return spa_smoke(products=products, domain=domain, deep_link=deep_link,
                         expect_absent=expect_absent, expect_present=expect_present)


__all__ = ["spa_smoke", "smoke_product", "BUILD_SCOPE", "DEFAULT_DEEP_LINK", "register"]
