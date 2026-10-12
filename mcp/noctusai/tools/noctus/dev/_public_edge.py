"""Stdlib-only helpers for talking to the PUBLIC prod edge (Cloudflare tunnel).

Shared by `spa_smoke` (post-deploy SPA gate) and `prod_watchdog` (off-host
liveness checker that runs in GitHub Actions with NO pip install). That second
consumer is why this module exists and why it must stay stdlib-only: the
watchdog imports it under a bare `python3`, where `yaml`, `pydantic` and
`noctusai_lib` are absent. Do not add a non-stdlib import here.

  • `BROWSER_UA`       — WAF rule 1010 rejects programmatic User-Agents.
  • `fetch`            — GET with that UA; never raises.
  • `read_slug_file`   — one-slug-per-line roster files (`build-scope.txt`).
  • `ingress_routes`   — the `routes:` list of `deploy/tunnel/ingress.yml`.
  • `public_hostname`  — slug → the hostname it is ACTUALLY served at.
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

#: WAF rule 1010 rejects non-browser User-Agents at the Cloudflare edge.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

INGRESS_RELPATH = Path("deploy") / "tunnel" / "ingress.yml"
BUILD_SCOPE_RELPATH = Path("deploy") / "fleet" / "build-scope.txt"


def fetch(url: str, timeout: float = 25) -> tuple[int, bytes, str]:
    """GET with a browser UA. Returns `(status, body, content_type)`.

    A non-2xx is returned as its status rather than raised; an unreachable
    host (DNS, refused, timeout, TLS) is status `0`. Callers report both as
    findings — an exception here would look like a tool bug, not an outage.
    """
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", exc.headers.get("Content-Type", "") if exc.headers else ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("public_edge: %s unreachable (%s)", url, exc)
        return 0, b"", ""


def read_slug_file(path: Path) -> list[str]:
    """Sorted unique slugs from a one-per-line file; `#` comments ignored.

    A missing file is `[]` — the caller decides whether an empty roster is an
    error (both current callers refuse to report success on it).
    """
    if not path.exists():
        return []
    return sorted({
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    })


def _scalar(raw: str) -> str:
    """A YAML plain/quoted scalar as used in ingress.yml (no flow syntax)."""
    v = raw.strip()
    if v[:1] in ("'", '"'):
        q = v[0]
        end = v.find(q, 1)
        return v[1:end] if end != -1 else v[1:]
    # A plain scalar ends at ` #` (inline comment).
    return re.split(r"\s+#", v, maxsplit=1)[0].strip()


def ingress_routes(text: str) -> list[dict[str, str]]:
    """Parse the top-level `routes:` list of ingress.yml without PyYAML.

    The file's shape is fixed and documented in its own header
    (`- hostname: …` / `service: …` / optional `note: …`), so a line parser is
    exact for it; `test_prod_watchdog` asserts parity with `yaml.safe_load` on
    the real file so a future shape change fails a test instead of silently
    resolving the wrong hostname.
    """
    routes: list[dict[str, str]] = []
    in_routes = False
    current: dict[str, str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1].isspace() and not stripped.startswith("-"):
            in_routes = stripped.split(":", 1)[0] == "routes"
            current = None
            continue
        if not in_routes:
            continue
        body = stripped
        if body.startswith("- ") or body == "-":
            current = {}
            routes.append(current)
            body = body[1:].strip()
            if not body:
                continue
        if current is None or ":" not in body:
            continue
        key, _, val = body.partition(":")
        current[key.strip()] = _scalar(val)
    return routes


def public_hostname(slug: str, repo_root: Path, domain: str = "noctusai.com") -> str:
    """The hostname `slug` is ACTUALLY served at, per `deploy/tunnel/ingress.yml`.

    `f"{slug}.{domain}"` was a guess that stopped being true on 2026-08-25
    (`erp.` / `social.` replaced the long-slug hosts). The route whose service
    names this slug wins; when several do, the SHORTEST hostname is the
    canonical public one. Falls back to the guess when the file is unreadable
    or the slug has no route, so hostname resolution can never be the thing
    that breaks a probe.
    """
    try:
        text = (Path(repo_root) / INGRESS_RELPATH).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("public_edge: cannot read ingress.yml (%s) — guessing %s.%s", exc, slug, domain)
        return f"{slug}.{domain}"
    pat = re.compile(rf"^https?://{re.escape(slug)}:\d+$")
    matches = [
        r.get("hostname", "").strip()
        for r in ingress_routes(text)
        if pat.match(r.get("service", "").strip())
    ]
    matches = [m for m in matches if m]
    if matches:
        return min(matches, key=len)
    return f"{slug}.{domain}"


__all__ = [
    "BROWSER_UA",
    "BUILD_SCOPE_RELPATH",
    "INGRESS_RELPATH",
    "fetch",
    "ingress_routes",
    "public_hostname",
    "read_slug_file",
]
