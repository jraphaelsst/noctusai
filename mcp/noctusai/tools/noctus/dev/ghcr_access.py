"""noctus.dev.ghcr_access -- install + verify the VPS's read credential for private GHCR images, in the one order that cannot break a pull.

**Why.** The fleet's images live on GHCR (`ghcr.io/<owner>/noctus-<slug>`). Making the packages private (security audit
2026-10-19) is only safe if the VPS can pull them first: flip first and every `deploy_image --source pull` 401s.
This tool owns that ORDER so it holds by construction, not by a runbook someone has to follow:

  install (the ONLY human step is making the token; this does the rest)
    1. take the token from a LOCAL env var (`GHCR_READ_TOKEN` of this process) or stdin (CLI) -- never an argument;
    2. write it to the VPS `deploy/fleet/.env.fleet` as `GHCR_READ_TOKEN=` (mode 0600, atomic, over ssh STDIN -- the
       value is never on an argv, in a log or in a result);
    3. `docker login ghcr.io` on the VPS FROM that file (the username is DERIVED from the image namespace in
       `docker-compose.prod.yml`; the token never crosses the wire again);
    4. verify: the credential is recorded (redacted read of docker's config.json) and an authenticated manifest
       request for the core image answers;
    5. only THEN report the packages that are still public, with their settings URLs.

  What is NOT automated, honestly: GitHub exposes NO API to change a container package's visibility (REST nor GraphQL;
  it is a UI action). So the tool cannot flip it -- it makes the flip SAFE: the URLs are handed over only after a
  verified login, and `status` / the `ghcr_login` predeploy leg derive "private yet?" from REALITY (an anonymous pull
  probe), so there is no flag to forget: while packages are public a missing login is fine, and the moment they are
  private the leg requires the login.

  status: visibility per package (anonymous pull probe) + whether the VPS is logged in (redacted read). Read-only.

Seams: `fetch` (HTTP) and `run_remote` (ssh) are injectable; tests run with zero network.
KB § GUIDES/security-infra-hardening-runbook.md § 1 · KB § PATTERNS/devops/ci-security-gates.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_HOST = "noctus-vps"
VPS_REPO = "/opt/noctus/noctusai"
ENV_FLEET = f"{VPS_REPO}/deploy/fleet/.env.fleet"
COMPOSE_REL = "deploy/fleet/docker-compose.prod.yml"
SCOPE_REL = "deploy/fleet/build-scope.txt"
TOKEN_ENV = "GHCR_READ_TOKEN"
GHCR = "ghcr.io"
DOCKER_CONFIG = "/root/.docker/config.json"
#: Read docker's config with every credential VALUE redacted at the source (non-empty only, so a logged-out empty
#: `"auth": ""` stays distinguishable): the secret never crosses the wire into a tool result.
DOCKER_CONFIG_REDACTED_CMD = (
    "sed -E 's/(\"(auth|identitytoken|password|registrytoken)\"[[:space:]]*:[[:space:]]*\")[^\"]+\"/\\1<redacted>\"/g' "
    + DOCKER_CONFIG
)
#: Packages built outside build-scope.txt that the VPS also pulls.
EXTRA_PACKAGES = ("noctus-transcriber",)
CORE_PACKAGE = "noctus-core"

# A classic PAT (`ghp_...`, or the 40-hex legacy form). Fine-grained `github_pat_...` tokens cannot read GHCR.
_TOKEN_RE = re.compile(r"^(?:ghp_[A-Za-z0-9]{30,}|[0-9a-f]{40})$")
_OWNER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38})$")
_IMAGE_NS_RE = re.compile(r"ghcr\.io/(?P<owner>[a-z0-9][a-z0-9-]*)/noctus-", re.I)

Fetch = Callable[[str, dict], "tuple[int, str]"]


# ── pure ──────────────────────────────────────────────────────────────────

def derive_owner(compose_text: str) -> str:
    """The registry namespace, read from the image refs already in the prod compose (no second source of truth)."""
    owners = {m.group("owner").lower() for m in _IMAGE_NS_RE.finditer(compose_text)}
    if len(owners) != 1:
        raise ValueError(f"expected exactly one ghcr.io namespace in {COMPOSE_REL}, found {sorted(owners) or 'none'}")
    owner = owners.pop()
    if not _OWNER_RE.match(owner):
        raise ValueError(f"derived namespace {owner!r} is not a valid GitHub login")
    return owner


def derive_packages(scope_text: str) -> list[str]:
    """`noctus-<slug>` for every live product (build-scope.txt) + the out-of-scope images the VPS pulls."""
    slugs = [ln.strip() for ln in scope_text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return sorted({f"noctus-{s}" for s in slugs} | set(EXTRA_PACKAGES))


def validate_token(token: str | None) -> str | None:
    """None when usable, else a reason that never quotes the value."""
    if not token:
        return f"no token: set {TOKEN_ENV} in this process's environment (or pipe it on stdin with the CLI)"
    if token.startswith("github_pat_"):
        return "a fine-grained PAT cannot read GHCR: create a CLASSIC token with only the read:packages scope"
    if not _TOKEN_RE.match(token):
        return "token is not shaped like a classic GitHub PAT (ghp_...)"
    return None


def classify_visibility(token_status: int, manifest_status: int | None) -> str:
    """public | private | unknown, from an ANONYMOUS pull probe (token endpoint, then the manifest)."""
    if token_status in (401, 403):
        return "private"
    if token_status != 200:
        return "unknown"
    if manifest_status == 200:
        return "public"
    if manifest_status in (401, 403, 404):
        return "private"
    return "unknown"


def audit_login(config_text: str) -> tuple[bool, str]:
    """Pure verdict on a (redacted) docker config.json: logged into ghcr.io? Never echoes a credential."""
    try:
        cfg = json.loads(config_text or "")
    except ValueError:
        return False, "docker config.json on the VPS is not valid JSON"
    if not isinstance(cfg, dict):
        return False, "docker config.json on the VPS is not a JSON object"
    helpers = cfg.get("credHelpers") or {}
    if isinstance(helpers, dict) and helpers.get(GHCR):
        return True, f"credHelper configured for {GHCR}"
    if cfg.get("credsStore"):
        return True, "a global credsStore is configured"
    entry = (cfg.get("auths") or {}).get(GHCR)
    if isinstance(entry, dict) and (entry.get("auth") or entry.get("identitytoken")):
        return True, f"{GHCR} credential present in auths"
    return False, f"the VPS is not logged into {GHCR}"


INSTALL_HINT = (f"run `noctus.dev.ghcr_access install confirm=True` (token from the {TOKEN_ENV} env var), or the CLI "
                f"`--ghcr-access install --ghcr-access-confirm` with the token on stdin")


def _install_cmd() -> str:
    """Remote: read ONE line from stdin and set GHCR_READ_TOKEN in .env.fleet, 0600, atomically. The value only ever
    lives in the shell variable, never on a command line."""
    script = (
        "umask 077; f=%(f)s; [ -e \"$f\" ] || : > \"$f\"; IFS= read -r t || exit 2; [ -n \"$t\" ] || exit 2; "
        "tmp=$(mktemp \"$f.XXXXXX\") || exit 3; "
        "grep -v '^%(k)s=' \"$f\" > \"$tmp\" || true; printf '%(k)s=%%s\\n' \"$t\" >> \"$tmp\"; "
        "chmod 600 \"$tmp\" && mv \"$tmp\" \"$f\""
    ) % {"f": ENV_FLEET, "k": TOKEN_ENV}
    return "sh -c " + _sq(script)


def _login_cmd(owner: str) -> str:
    """Remote: log in FROM the file (only that one key is read; the rest of .env.fleet is never sourced)."""
    script = (f"t=$(grep '^{TOKEN_ENV}=' {ENV_FLEET} | tail -n 1 | cut -d= -f2-); [ -n \"$t\" ] || exit 4; "
              f"printf %s \"$t\" | docker login {GHCR} -u {owner} --password-stdin")
    return "sh -c " + _sq(script)


def _sq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _scrub(text: str, secret: str | None) -> str:
    out = text or ""
    if secret:
        out = out.replace(secret, "<redacted>")
    return out[:400]


# ── io ────────────────────────────────────────────────────────────────────

def _real_fetch(url: str, headers: dict) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 - https only, fixed host
            return r.status, r.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def probe_visibility(owner: str, package: str, fetch: Fetch | None = None, tag: str = "latest") -> str:
    """Anonymous pull probe: public | private | unknown. No credential is ever sent."""
    fetch = fetch or _real_fetch
    repo = f"{owner}/{package}"
    st, body = fetch(f"https://{GHCR}/token?service={GHCR}&scope=repository:{repo}:pull", {})
    if st != 200:
        return classify_visibility(st, None)
    try:
        bearer = json.loads(body).get("token", "")
    except ValueError:
        return "unknown"
    mst, _ = fetch(
        f"https://{GHCR}/v2/{repo}/manifests/{tag}",
        {"Authorization": f"Bearer {bearer}",
         "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, "
                   "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"},
    )
    return classify_visibility(st, mst)


def _root(repo_root: str | None, worktree_path: str | None) -> Path:
    return Path(worktree_path or repo_root or Path(__file__).resolve().parents[5])


def _context(root: Path) -> tuple[str, list[str]]:
    owner = derive_owner((root / COMPOSE_REL).read_text(encoding="utf-8"))
    return owner, derive_packages((root / SCOPE_REL).read_text(encoding="utf-8"))


def _remote(run_remote, host: str):
    if run_remote is not None:
        return run_remote
    from . import _vps_ssh

    return lambda cmd, **kw: _vps_ssh.run_remote(host, cmd, **kw)


def ghcr_access(
    action: str = "status",
    *,
    confirm: bool = False,
    ssh_host: str = DEFAULT_HOST,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    env: dict[str, str] | None = None,
    token: str | None = None,
    run_remote: Callable | None = None,
    fetch: Fetch | None = None,
) -> dict[str, Any]:
    """action='status' (read-only: per-package visibility + VPS login) | 'install' (plan; confirm=True performs it)."""
    if action not in ("status", "install"):
        return {"ok": False, "action": action, "error": "unknown action -- expected 'status' or 'install'"}
    try:
        owner, packages = _context(_root(repo_root, worktree_path))
    except (OSError, ValueError) as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    run = _remote(run_remote, ssh_host)
    vis = {p: probe_visibility(owner, p, fetch) for p in packages}
    public = sorted(p for p, v in vis.items() if v == "public")
    unknown = sorted(p for p, v in vis.items() if v == "unknown")

    def _logged_in() -> tuple[bool | None, str]:
        rc, out, err = run(DOCKER_CONFIG_REDACTED_CMD)
        if rc != 0:
            return None, f"could not read the VPS docker config ({(err or '').strip()[:120] or 'rc=%s' % rc})"
        ok, why = audit_login(out)
        return ok, why

    base = {"action": action, "owner": owner, "user": owner, "packages": vis,
            "public": public, "unknown": unknown}
    if action == "status":
        logged, why = _logged_in()
        required = bool(set(vis.values()) & {"private"})
        return {**base, "ok": logged is not False or not required, "status": "status", "vps_logged_in": logged,
                "login_required": required, "detail": why,
                **({} if logged or not required else {"fix": INSTALL_HINT})}

    # install
    tok = token if token is not None else (env if env is not None else os.environ).get(TOKEN_ENV)
    bad = validate_token(tok)
    plan = {**base, "writes": f"{ENV_FLEET} ({TOKEN_ENV}, mode 0600)", "then": f"docker login {GHCR} -u {owner} on the VPS",
            "token_present": bool(tok)}
    if not confirm:
        return {**plan, "ok": bad is None, "status": "planned", **({"error": bad} if bad else {})}
    if bad:
        return {**plan, "ok": False, "status": "error", "error": bad}
    rc, _, err = run(_install_cmd(), stdin_text=tok + "\n", timeout=60)
    if rc != 0:
        return {**plan, "ok": False, "status": "error", "step": "write_env",
                "error": f"could not write {TOKEN_ENV} on the VPS: {_scrub(err, tok)}"}
    rc, out, err = run(_login_cmd(owner), timeout=90)
    if rc != 0:
        return {**plan, "ok": False, "status": "error", "step": "docker_login",
                "error": f"docker login {GHCR} failed (token rejected or no read:packages scope): {_scrub(err or out, tok)}"}
    logged, why = _logged_in()
    rc, _, err = run(f"docker manifest inspect {GHCR}/{owner}/{CORE_PACKAGE}:latest", timeout=90)
    if not logged or rc != 0:
        return {**plan, "ok": False, "status": "error", "step": "verify",
                "error": f"login recorded={logged} ({why}); authenticated manifest rc={rc}: {_scrub(err, tok)}"}
    owner_step = [f"https://github.com/users/{owner}/packages/container/{p}/settings" for p in public]
    return {**plan, "ok": True, "status": "installed", "vps_logged_in": True, "verified": "login recorded + authenticated manifest",
            "owner_step": (
                "Change visibility -> Private for each of these (GitHub has no API for it; safe now, the VPS can pull): "
                + ", ".join(owner_step)) if owner_step else "all packages already private",
            "after_flip": "predeploy_check leg ghcr_login now requires the login and passes."}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.ghcr_access",
        description=(
            "Private-GHCR access for the VPS, in the one safe order. action='status' (read-only): anonymous visibility "
            "probe per package + whether the VPS is logged in. action='install' (confirm=True to perform): takes the "
            "classic read:packages PAT from THIS process's GHCR_READ_TOKEN env var (never an argument), writes it to the "
            "VPS .env.fleet (0600, over ssh stdin), runs `docker login ghcr.io` there (user derived from the image "
            "namespace), verifies login + an authenticated manifest, and only then returns the package-settings URLs "
            "for the owner's visibility flip (GitHub has no API for it). Never returns or logs the token. KB § GUIDES/"
            "security-infra-hardening-runbook.md § 1."
        ),
    )
    def _ghcr_access(action: str = "status", confirm: bool = False, ssh_host: str = DEFAULT_HOST,
                     worktree_path: str = "") -> dict:
        return ghcr_access(action, confirm=confirm, ssh_host=ssh_host, worktree_path=worktree_path or None)


__all__ = ["ghcr_access", "register", "derive_owner", "derive_packages", "validate_token", "classify_visibility",
           "audit_login", "probe_visibility", "DOCKER_CONFIG_REDACTED_CMD", "CORE_PACKAGE", "TOKEN_ENV"]
