"""noctus.dev.predeploy_check — the pre-deploy verification + learning gate (P5).

Only code that BUILDS the slim deploy image + passes tests should reach prod
("always-only functional code online", `KB § GUIDES/production-deploy.md § 2a`
safety-net P5). This tool is that gate for a product: it runs the deploy-
relevant checks, then — the "learning" half of the user's ask ("create
mechanisms that learn from pre-deploy issues to auto-fix them … if not
executable via code, generate reports") — it:

  • CLASSIFIES each failure against the known boundary-contract classes
    (`KB § PATTERNS/boundary-contract-tests.md`): npm root-hoist (TS2307),
    pip framework-implicit (Django fieldsE/Pillow), VITE-baked-localhost,
    bare missing-module imports;
  • AUTO-FIXES the one class that is safely code-fixable today — framework
    dep drift — by composing the existing `check_framework_deps` fixer
    (only when `auto_fix=True`); source-mutating fixes (TS2307/Pillow) are
    SUGGESTED, never blind-applied (they need AST edits — deferred);
  • for an UNKNOWN failure, writes `predeploy-reports/<utc>-<product>.md` +
    logs a `phase_learnings` row (s1 of the codification pipeline) so a
    recurring unknown class can graduate to a detector. The taxonomy is
    OPEN — a non-matching failure becomes `unknown` + a report, never a
    force-fit into a wrong class.

IO is injectable (`run_check`, `write_report`, `log_fn`, `now`) so the
colocated test exercises every path with zero real builds (the smoke_fleet
pattern). The default `run_check` shells out (mirrors `noctus.dev.vite_build`
/ `noctus.dev.pytest`); `framework_deps` composes `check_framework_deps`.
"""
from __future__ import annotations

import datetime as _dt
import functools
import os
import pathlib
import re
import subprocess
from typing import Any, Callable

from deploy_state import DEPLOY_LOCAL_FILES
from settings import REPO_ROOT, resolve_test_python
from workspace import resolve_caller_root

from . import check_framework_deps as _cfd
from . import phase_learnings as _pl

# Default deploy-relevant checks, in run order. Each is (name, kind).
DEFAULT_CHECKS: list[str] = [
    "framework_deps",
    "frontend_build",
    "backend_tests",
    "deploy_local_gitignored",  # D3 — every deploy_state.DEPLOY_LOCAL_FILES pattern is gitignored
    "prod_config_parity",  # value-correctness: prod env resolves a non-localhost URL per product
    "required_prod_env_present",  # newly-required-at-boot env keys (seed baseline) present in prod snapshot
    "cors_roster_complete",  # backstop: every registry slug has a CORS-resolvable origin
]

PROJECT_SLUG = "deploy-hardening-and-dev-isolation"


# ── Known failure classes — OPEN taxonomy (non-match ⇒ `unknown` + report) ──
# Each: (class_id, compiled regex over the check output, human explanation,
# suggested fix, auto_fixable). Patterns drawn from the deploy GUIDE §6
# table + KB § PATTERNS/boundary-contract-tests.md.
_KNOWN: list[dict[str, Any]] = [
    {
        "class_id": "npm_root_hoist",
        "rx": re.compile(r"TS2307: Cannot find module '([^']+)'|Cannot find module '([^']+)'"),
        "boundary": "B1 build-injection",
        "explanation": (
            "A frontend dependency resolves in dev (root-hoisted node_modules) "
            "but is absent from the product's own package.json, so a clean "
            "Docker build can't find it."
        ),
        "suggested_fix": (
            "Add the missing module to products/<product>/frontend/package.json "
            "dependencies (pinned), then `npm install` in that dir."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "pip_framework_implicit",
        "rx": re.compile(r"fields\.E210|Cannot use ImageField because Pillow|ModuleNotFoundError: No module named 'PIL'"),
        "boundary": "B4 container env",
        "explanation": (
            "A framework-implicit Python dep (e.g. Pillow for a Django "
            "ImageField) is installed in the working env but missing from the "
            "manifest the Dockerfile installs → fails only in a clean build."
        ),
        "suggested_fix": "Add the implicit dep (e.g. Pillow) to requirements.txt, pinned.",
        "auto_fixable": False,
    },
    {
        # Ordered BEFORE vite_baked_localhost: a parity violation message can
        # quote a localhost value, so this specific class must win the first-match.
        "class_id": "prod_config_localhost",
        "rx": re.compile(
            r"prod-config parity VIOLATED|prod URL unresolved for|"
            r"carries a localhost/loopback host"
        ),
        "boundary": "B4 container env",
        "explanation": (
            "The prod env would reproduce the ARC1/ARC2 cutover drift: a product "
            "has no PRODUCT_URL_<SLUG>/PRODUCT_URL_PATTERN override (nav + CORS "
            "fall through to the DB localhost default), or a PRODUCT_URL_*/"
            "CORS_ORIGINS value still carries a localhost/loopback host. The "
            "deploy-config boot guard checks only PRESENCE, so a present-but-"
            "localhost value passes it but is caught here. Both shapes broke apex "
            "login + cross-product nav on the 2026-05-22 cutover."
        ),
        "suggested_fix": (
            "On the deploy box's root .env set PRODUCT_URL_PATTERN="
            "https://{slug}.<domain> (or per-product PRODUCT_URL_<SLUG>="
            "https://…) with NO localhost; core uses @registry:all so CORS "
            "auto-allows every prod origin. See KB § PATTERNS/deploy-config-"
            "contract.md + KB § GUIDES/production-deploy.md."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "vite_baked_localhost",
        "rx": re.compile(r"http://localhost:\d+"),
        "boundary": "B1 build-injection",
        "explanation": (
            "A built bundle contains a hardcoded http://localhost:<port> API "
            "base — the seed's same-origin contract (window.location.origin) "
            "was bypassed; the deployed SPA will call localhost, not the host."
        ),
        "suggested_fix": (
            "Use the seed vite factory's window.location.origin define-injection; "
            "never hardcode the API base. See KB § PATTERNS/containerization.md § same-origin."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "framework_dep_drift",
        "rx": re.compile(r"framework[- ]dep|package\.json .*drift|missing framework dep", re.I),
        "boundary": "B1 build-injection",
        "explanation": "Product frontend package.json is missing a seed-framework dep.",
        "suggested_fix": "Run check_framework_deps with fix=True (or predeploy_check auto_fix=True).",
        "auto_fixable": True,
    },
    {
        "class_id": "deploy_local_tracked",
        "rx": re.compile(
            r"D3 deploy-local invariant VIOLATED|is TRACKED — must be gitignored|NOT gitignored — a future write"
        ),
        "boundary": "D3 deploy-state manifest",
        "explanation": (
            "A deploy-local file (filled-in-place on the VPS — tunnel config.yml, "
            "creds *.json, root .env) is git-tracked or not gitignored, so a "
            "`git pull` on the production box could clobber it (the §2a P4/D3 net). "
            "The manifest lives in deploy_state.DEPLOY_LOCAL_FILES."
        ),
        "suggested_fix": (
            "git rm --cached <path> + add the path (or its **/ glob) to .gitignore, "
            "then re-render the file in-place on the box. See deploy_state.py + "
            "KB § GUIDES/production-deploy.md § 2a (P4/D3)."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "cors_roster_missing",
        "rx": re.compile(r"CORS roster INCOMPLETE|no CORS origin resolvable for|cors_roster_complete VIOLATED"),
        "boundary": "B4 container env",
        "explanation": (
            "One or more registry slugs have no resolvable CORS origin: neither "
            "PRODUCT_URL_<SLUG> nor PRODUCT_URL_PATTERN is set for them in the "
            "VPS .env. core's CORS allowlist is derived from explicit "
            "PRODUCT_URL_<SLUG> env vars (the slim prod container ships no start.sh, "
            "so PRODUCT_URL_PATTERN alone is invisible there). A missing origin means "
            "the product's SSO POST is rejected with a CORS error ('Failed to fetch')."
        ),
        "suggested_fix": (
            "Run `noctus.dev.ensure_product_url_roster(confirm=True)` to write the "
            "closed, registry-derived PRODUCT_URL roster into the VPS .env and "
            "recreate core. Short-name products (erp-imobiliario → erp.noctusai.com) "
            "keep their existing overrides; new products (e.g. orbity) are "
            "pattern-filled automatically. See KB § PATTERNS/frontend/core-url-routing.md § 6."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "required_prod_env_missing",
        "rx": re.compile(r"required prod env MISSING|required-in-prod env '[^']+' is absent"),
        "boundary": "B4 container env",
        "explanation": (
            "A seed-baseline env var that is REQUIRED at boot in a deploy context "
            "(e.g. REDIS_SESSION_ENCRYPTION_KEY — every product's auth_router "
            "builds a Redis-backed session store with require_encryption=True) is "
            "absent/empty in the prod env snapshot. The boot guard "
            "(create_product_app → require_prod_config, folding in "
            "deploy_config.BASELINE_REQUIRED_PROD_ENV) would abort this deploy at "
            "startup. The prior parity gate only knew PRODUCT_URL_*/CORS keys, so "
            "a newly-required key like this slipped through to a prod boot failure "
            "(the REDIS_SESSION_ENCRYPTION_KEY incident) — this check closes that gap."
        ),
        "suggested_fix": (
            "Set the missing key(s) on the deploy box's root .env before promoting "
            "(they are required in production/staging; dev leaves them unset). The "
            "authoritative list is deploy_config.BASELINE_REQUIRED_PROD_ENV — the "
            "same one the boot guard reads. See KB § PATTERNS/deploy-config-contract.md."
        ),
        "auto_fixable": False,
    },
]


def classify_failure(output: str) -> dict[str, Any] | None:
    """Pure classifier: first known class whose regex matches, else None
    (unknown — caller writes a report + logs s1). OPEN taxonomy."""
    text = output or ""
    for cls in _KNOWN:
        m = cls["rx"].search(text)
        if m:
            hit = next((g for g in (m.groups() or ()) if g), m.group(0))
            return {
                "class_id": cls["class_id"],
                "boundary": cls["boundary"],
                "explanation": cls["explanation"],
                "suggested_fix": cls["suggested_fix"],
                "auto_fixable": cls["auto_fixable"],
                "matched": hit,
            }
    return None


# ── D3 deploy-state manifest assertion (deploy_state.DEPLOY_LOCAL_FILES) ──
# The §2a safety-net D3: every deploy-local file (filled-in-place on the VPS)
# MUST be gitignored so a pull cannot touch it BY CONSTRUCTION. The manifest is
# a code constant (deploy_state.py) — durable, can't be lost to an archive — so
# this gate ALWAYS runs (it cannot silently skip on a missing file).
def _default_run_git(root: pathlib.Path, args: list[str]) -> tuple[int, str]:
    """(returncode, stdout) for `git -C <root> <args>`. Injectable in
    audit_deploy_local so the test exercises every branch with zero real git."""
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout or "")


def audit_deploy_local(
    root: pathlib.Path,
    run_git: Callable[[pathlib.Path, list[str]], tuple[int, str]] | None = None,
    entries: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Assert every `deploy_state.DEPLOY_LOCAL_FILES` pattern is (a) NOT tracked
    and (b) covered by a gitignore rule. Patterns are gitignore-style globs
    (e.g. `**/tunnel/*.json`) — `git ls-files` pathspec finds any tracked match,
    and the ignore probe substitutes a placeholder for `*`. Returns
    {source, checked, violations}. `entries` is injectable for the test."""
    run = run_git or _default_run_git
    manifest = entries if entries is not None else DEPLOY_LOCAL_FILES
    violations: list[str] = []
    for e in manifest:
        pattern = (e.get("pattern") or "").strip()
        if not pattern:
            continue
        _rc_ls, out_ls = run(root, ["ls-files", "--", pattern])
        if out_ls.strip():
            violations.append(f"{pattern} is TRACKED — must be gitignored (D3)")
            continue
        probe = pattern.replace("*", "__probe__")
        rc_ci, _ = run(root, ["check-ignore", "-q", "--", probe])
        if rc_ci != 0:
            violations.append(f"{pattern} is NOT gitignored — a future write could be committed (D3)")
    return {"source": "deploy_state.DEPLOY_LOCAL_FILES", "checked": len(manifest), "violations": violations}


# ── Prod-config parity (value-correctness, pre-deploy) ────────────────────
# The THIRD leg of the deploy-config-contract (KB § PATTERNS/deploy-config-contract.md):
#   • check_derives_from_dev_only_artifact — STATIC (seed source derives a value
#     from a dev-only artifact without an env fallback);
#   • require_prod_config / resolve_config — RUNTIME boot guard (a required key is
#     PRESENT in a deploy context);
#   • prod_config_parity (this) — PRE-DEPLOY VALUE-correctness over the actual prod
#     env snapshot: every product resolves a prod URL (no DB-localhost fallthrough)
#     AND no PRODUCT_URL_*/CORS_ORIGINS value carries a localhost/loopback host.
#     The boot guard checks PRESENCE only — a present-but-localhost value (the exact
#     ARC1/ARC2 cutover drift) passes it but is caught here.
# Deterministic core (deploy-config-contract option b): operates on a PROVIDED prod
# env snapshot mapping, so the test needs no real environment; the runner resolves
# the snapshot from an explicit path / NOCTUS_PROD_ENV_FILE / a PROD-named file
# (never the ambiguous dev `.env`, which legitimately carries localhost).

# loopback / non-routable hosts that must never appear in a prod-destined URL.
_LOOPBACK_RE = re.compile(r"localhost|127\.0\.0\.1|0\.0\.0\.0|::1", re.I)
# PROD-named snapshot discovery probes (NEVER plain `.env` — the dev-local file).
_PROD_ENV_NAMES: tuple[str, ...] = (".env.prod", ".env.production")
_PROD_URL_PREFIX = "PRODUCT_URL_"
_PROD_URL_PATTERN_KEY = "PRODUCT_URL_PATTERN"


def _slug_env_key(slug: str) -> str:
    """`media-scheduling` → `PRODUCT_URL_MEDIA_SCHEDULING` (the exact scheme
    noctusai_lib.config.product_urls.resolve_product_url reads)."""
    return f"{_PROD_URL_PREFIX}{slug.replace('-', '_').upper()}"


def audit_prod_config_parity(
    roster_slugs: list[str], env: dict[str, str] | None
) -> dict[str, Any]:
    """Pure: assert a prod env snapshot resolves a non-localhost URL for every
    product. For each slug a prod origin must resolve WITHOUT the DB-localhost
    fallthrough — ``PRODUCT_URL_<SLUG>`` set OR ``PRODUCT_URL_PATTERN`` set (one
    pattern covers the whole fleet) — and no ``PRODUCT_URL_*`` / ``CORS_ORIGINS``
    value may carry a localhost/loopback host. ``env`` is any str→str mapping (a
    parsed prod ``.env`` snapshot), injected so the test needs no real
    environment. Returns ``{source, checked, violations}``."""
    env = dict(env or {})
    pattern_set = bool((env.get(_PROD_URL_PATTERN_KEY) or "").strip())
    violations: list[str] = []
    # (1) per-product prod URL resolves (no silent DB-localhost fallthrough).
    # A fleet-wide PRODUCT_URL_PATTERN covers every slug, so per-slug vars are
    # only required when no pattern is set.
    if not pattern_set:
        for slug in roster_slugs:
            key = _slug_env_key(slug)
            if not (env.get(key) or "").strip():
                violations.append(
                    f"prod URL unresolved for '{slug}': neither {key} nor "
                    f"{_PROD_URL_PATTERN_KEY} set — nav + CORS fall through to the "
                    "DB localhost default (the ARC1/ARC2 cutover drift)"
                )
    # (2) value-correctness: no loopback host in a prod-destined URL value (this
    # is what the PRESENCE-only boot guard cannot catch).
    for key in sorted(env):
        value = env[key]
        if (
            (key.startswith(_PROD_URL_PREFIX) or key == "CORS_ORIGINS")
            and value
            and _LOOPBACK_RE.search(value)
        ):
            violations.append(
                f"{key} carries a localhost/loopback host ({value!r}) — not "
                "prod-safe (present-but-wrong passes the boot guard, fails here)"
            )
    return {
        "source": "prod-env-snapshot",
        "checked": len(roster_slugs),
        "violations": violations,
    }


def audit_required_prod_env_present(
    required_keys: list[str], env: dict[str, str] | None
) -> dict[str, Any]:
    """Pure: assert every ``required_keys`` entry is present + non-empty in the
    prod env snapshot. Closes the "a code change makes a NEW env var required at
    boot, but the parity gate has no knowledge of it, so the boot guard fails in
    production instead" gap (the ``REDIS_SESSION_ENCRYPTION_KEY`` incident).

    The key list is the seed's ``deploy_config.BASELINE_REQUIRED_PROD_ENV`` (the
    same source of truth ``create_product_app``'s boot guard folds in), so this
    gate and the boot enforcement can never disagree. ``env`` is any str→str
    mapping (a parsed prod ``.env`` snapshot), injected so the test needs no real
    environment. Returns ``{source, checked, violations}``."""
    env = dict(env or {})
    violations: list[str] = []
    for key in required_keys:
        if not (env.get(key) or "").strip():
            violations.append(
                f"required-in-prod env '{key}' is absent/empty in the prod "
                "snapshot — the boot guard "
                "(create_product_app → require_prod_config, seed baseline) will "
                "abort this deploy at startup. Set it on the deploy env before "
                "promoting (present-but-missing fails HERE, pre-deploy, instead "
                "of at boot)."
            )
    return {
        "source": "prod-env-snapshot",
        "checked": len(required_keys),
        "violations": violations,
    }


def audit_cors_roster_complete(
    roster_slugs: list[str], env: dict[str, str] | None
) -> dict[str, Any]:
    """Pure backstop: assert every registry slug has a resolvable CORS origin.

    core's ``derive_cors_origins`` (source b) reads explicit ``PRODUCT_URL_<SLUG>``
    env vars directly — it does NOT rely on ``start.sh`` (absent in the slim prod
    container). A slug with neither ``PRODUCT_URL_<SLUG>`` nor ``PRODUCT_URL_PATTERN``
    will be absent from core's CORS allowlist → the product's SSO POST is
    rejected ("Failed to fetch"). This is exactly the drift that broke orbity's SSO.

    Read-only / advisory: the tool that FIXES this is
    ``noctus.dev.ensure_product_url_roster``.

    Returns ``{source, checked, violations}``.
    """
    env = dict(env or {})
    pattern_set = bool((env.get(_PROD_URL_PATTERN_KEY) or "").strip())
    violations: list[str] = []

    for slug in roster_slugs:
        key = _slug_env_key(slug)
        has_override = bool((env.get(key) or "").strip())
        if not has_override and not pattern_set:
            violations.append(
                f"no CORS origin resolvable for '{slug}': neither {key} nor "
                f"{_PROD_URL_PATTERN_KEY} is set — core's CORS allowlist will "
                "exclude this product's prod origin (the orbity 'Failed to fetch' "
                "shape). Fix: run `noctus.dev.ensure_product_url_roster(confirm=True)`."
            )

    return {
        "source": "cors-roster-check",
        "checked": len(roster_slugs),
        "violations": violations,
    }


def _parse_env_file(text: str) -> dict[str, str]:
    """Minimal ``.env`` parser (KEY=VALUE; ignores blanks / ``#`` comments /
    ``export `` prefix; strips one layer of matching quotes). Config-file
    parsing, not source — no dotenv dependency, no AST."""
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _resolve_prod_env_path(
    root: pathlib.Path, explicit: str | None = None
) -> pathlib.Path | None:
    """Resolve the prod env snapshot to audit, in priority order: explicit arg →
    ``NOCTUS_PROD_ENV_FILE`` → a PROD-named file in ``root``. Returns ``None``
    when none exists (the runner then SKIPs loudly — never silently passes). The
    ambiguous dev ``.env`` is deliberately NOT a source (it carries localhost by
    design)."""
    if explicit:
        explicit_path = pathlib.Path(explicit)
        return explicit_path if explicit_path.exists() else None
    from_env = os.environ.get("NOCTUS_PROD_ENV_FILE")
    if from_env and pathlib.Path(from_env).exists():
        return pathlib.Path(from_env)
    for name in _PROD_ENV_NAMES:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _load_roster_slugs(root: pathlib.Path) -> list[str]:
    """Live product roster slugs via the seed registry parser (never a frozen
    list). Lazy seed import (the seed is on the MCP runtime path); returns ``[]``
    if unavailable so the caller SKIPs rather than crashing."""
    try:
        from noctusai_lib.config.cors_registry import parse_products_registry
    except Exception:
        return []
    return [entry["slug"] for entry in parse_products_registry(root / "start.sh")]


def _load_baseline_required_env() -> list[str]:
    """The seed's fleet-wide baseline required-in-prod env keys (the SAME source
    of truth ``create_product_app``'s boot guard reads). Lazy seed import;
    returns ``[]`` if the seed is unavailable so the caller SKIPs loudly rather
    than crashing — never silently passing a check it could not run."""
    try:
        from noctusai_lib.config.deploy_config import baseline_required_prod_env
    except Exception:
        return []
    return baseline_required_prod_env()


def _default_run_check(
    check: str, product: str, root: pathlib.Path, prod_env_path: str | None = None
) -> tuple[bool, str]:
    """Real runner — shells the deploy-relevant build/test (mirrors
    noctus.dev.vite_build / pytest); framework_deps composes the existing
    audit. Returns (ok, combined_output)."""
    if check == "framework_deps":
        drift, _missing, _ok = _cfd._audit(root)
        prod_drift = {p: deps for p, deps in (drift or {}).items() if p == product and deps}
        if prod_drift:
            return False, f"framework-dep drift for {product}: {prod_drift}"
        return True, "framework deps OK"
    if check == "frontend_build":
        fe = root / "products" / product / "frontend"
        if not fe.exists():
            return True, f"no frontend dir for {product} (skipped)"
        r = subprocess.run(["npx", "vite", "build"], cwd=fe, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)
    if check == "backend_tests":
        be = root / "products" / product / "backend"
        if not be.exists():
            return True, f"no backend dir for {product} (skipped)"
        r = subprocess.run([resolve_test_python(), "-m", "pytest", "-q"], cwd=be, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)
    if check == "deploy_local_gitignored":
        # Platform-wide invariant (product arg unused): D3 manifest assertion.
        # The manifest is a code constant, so this always runs (never skips).
        audit = audit_deploy_local(root)
        if audit["violations"]:
            return False, "D3 deploy-local invariant VIOLATED: " + "; ".join(audit["violations"])
        return True, f"D3 ok — {audit['checked']} deploy-local pattern(s) gitignored (deploy_state.py)"
    if check == "prod_config_parity":
        # Platform-wide value-correctness (product arg unused): audit the prod
        # env snapshot. SKIPs (ok=True, loud note) when no snapshot resolves —
        # local dev has none and its `.env` is deliberately excluded.
        env_path = _resolve_prod_env_path(root, prod_env_path)
        if env_path is None:
            return True, (
                "prod_config_parity SKIPPED — no prod env snapshot resolvable "
                "(pass prod_env_path, set NOCTUS_PROD_ENV_FILE, or add a "
                ".env.prod/.env.production at the repo root). The dev .env is "
                "intentionally NOT used (it carries localhost by design)."
            )
        roster = _load_roster_slugs(root)
        if not roster:
            return True, (
                "prod_config_parity SKIPPED — empty product roster "
                "(start.sh registry unreadable from here)."
            )
        env = _parse_env_file(env_path.read_text(encoding="utf-8"))
        audit = audit_prod_config_parity(roster, env)
        if audit["violations"]:
            return False, "prod-config parity VIOLATED: " + "; ".join(audit["violations"])
        return True, (
            f"prod-config parity ok — {audit['checked']} product(s) resolve a "
            f"non-localhost prod URL ({env_path.name})"
        )
    if check == "required_prod_env_present":
        # Platform-wide (product arg unused): every seed-baseline required-in-prod
        # env key must be present + non-empty in the prod snapshot. SKIPs loudly
        # (ok=True) when no snapshot resolves (same pattern as prod_config_parity)
        # or when the seed baseline is unreadable from here.
        env_path = _resolve_prod_env_path(root, prod_env_path)
        if env_path is None:
            return True, (
                "required_prod_env_present SKIPPED — no prod env snapshot "
                "resolvable (pass prod_env_path, set NOCTUS_PROD_ENV_FILE, or add "
                "a .env.prod/.env.production at the repo root). The dev .env is "
                "intentionally NOT used (a required key may legitimately be unset "
                "in dev)."
            )
        required = _load_baseline_required_env()
        if not required:
            return True, (
                "required_prod_env_present SKIPPED — seed baseline "
                "required-env list unreadable from here (deploy_config import "
                "failed)."
            )
        env = _parse_env_file(env_path.read_text(encoding="utf-8"))
        audit = audit_required_prod_env_present(required, env)
        if audit["violations"]:
            return False, "required prod env MISSING: " + "; ".join(audit["violations"])
        return True, (
            f"required prod env ok — {audit['checked']} baseline key(s) present "
            f"in the prod snapshot ({env_path.name})"
        )
    if check == "cors_roster_complete":
        # Backstop: every registry slug must have a resolvable CORS origin for
        # core's allowlist. SKIPs loudly (ok=True) when no prod env snapshot is
        # available (same pattern as prod_config_parity — dev .env excluded).
        # The FIX is `noctus.dev.ensure_product_url_roster(confirm=True)`.
        env_path = _resolve_prod_env_path(root, prod_env_path)
        if env_path is None:
            return True, (
                "cors_roster_complete SKIPPED — no prod env snapshot resolvable "
                "(pass prod_env_path, set NOCTUS_PROD_ENV_FILE, or add a "
                ".env.prod/.env.production at the repo root)."
            )
        roster = _load_roster_slugs(root)
        if not roster:
            return True, (
                "cors_roster_complete SKIPPED — empty product roster "
                "(start.sh registry unreadable from here)."
            )
        env = _parse_env_file(env_path.read_text(encoding="utf-8"))
        audit = audit_cors_roster_complete(roster, env)
        if audit["violations"]:
            return False, "cors_roster_complete VIOLATED: " + "; ".join(audit["violations"])
        return True, (
            f"cors_roster_complete ok — {audit['checked']} product(s) have a "
            f"resolvable CORS origin ({env_path.name})"
        )
    return False, f"unknown check '{check}'"


def _default_fix_framework_deps(root: pathlib.Path, product: str) -> bool:
    """Compose the existing check_framework_deps fixer for the one safely
    code-fixable class. Returns True iff a fix was applied. Injectable in
    predeploy_check so the orchestration is testable without touching disk."""
    drift, _m, _o = _cfd._audit(root)
    prod_drift = {p: d for p, d in (drift or {}).items() if p == product and d}
    if not prod_drift:
        return False
    _cfd._fix(root, prod_drift)
    return True


def _render_report(product: str, unknowns: list[dict], when: str) -> str:
    lines = [
        f"# pre-deploy report — {product} — {when}",
        "",
        "Unknown pre-deploy failure(s) — no known boundary-contract class matched.",
        "Logged to phase_learnings (s1). If this recurs, graduate it to a keeper",
        "detector (`KB § PATTERNS/methodology-codification-pipeline.md`).",
        "",
    ]
    for u in unknowns:
        lines += [f"## check: {u['check']}", "", "```", u["output"].strip()[:4000], "```", ""]
    return "\n".join(lines)


def predeploy_check(
    product: str,
    checks: list[str] | None = None,
    auto_fix: bool = False,
    prod_env_path: str | None = None,
    run_check: Callable[[str, str, pathlib.Path], tuple[bool, str]] | None = None,
    write_report: Callable[[str, str], str] | None = None,
    log_fn: Callable[..., int] | None = None,
    fix_framework_deps: Callable[[pathlib.Path, str], bool] | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    now: Callable[[], _dt.datetime] | None = None,
) -> dict[str, Any]:
    """Run the deploy-relevant checks for `product`; classify + (auto_fix the
    safe class) + report/learn unknowns. status='ready' (all pass) |
    'blocked' (≥1 fail). Never raises on a check failure — it returns it."""
    if not product or not product.strip():
        return {"ok": False, "status": "error", "error": "product required", "exit_code": 1}
    # default runner threads the resolved prod env path; injected runners keep
    # the 3-arg (check, product, root) contract the tests rely on.
    runner = run_check or functools.partial(_default_run_check, prod_env_path=prod_env_path)
    logger = log_fn or _pl.log_learning
    fixer = fix_framework_deps or _default_fix_framework_deps
    clock = now or _dt.datetime.utcnow
    if repo_root is not None:
        root = pathlib.Path(repo_root)
    elif worktree_path:
        root = pathlib.Path(resolve_caller_root(worktree_path))
    else:
        root = pathlib.Path(REPO_ROOT)

    check_set = checks or DEFAULT_CHECKS
    results: list[dict[str, Any]] = []
    classified: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    auto_fixed: list[str] = []

    for check in check_set:
        ok, output = runner(check, product, root)
        entry: dict[str, Any] = {"check": check, "ok": ok}
        if not ok:
            cls = classify_failure(output)
            if cls:
                entry["classified"] = cls
                classified.append({"check": check, **cls})
                # auto-fix only the safe, code-fixable class (framework deps)
                if auto_fix and cls["auto_fixable"] and check == "framework_deps":
                    fixed = fixer(root, product)
                    entry["fix_attempted"] = fixed
                    if fixed:
                        ok2, _out2 = runner(check, product, root)
                        entry["auto_fixed"] = ok2
                        if ok2:
                            entry["ok"] = True
                            auto_fixed.append(check)
            else:
                entry["classified"] = None
                unknowns.append({"check": check, "output": output})
            entry["output_tail"] = (output or "").strip()[-600:]
        results.append(entry)

    report_path: str | None = None
    if unknowns:
        when = clock().strftime("%Y%m%dT%H%M%SZ")
        report_md = _render_report(product, unknowns, when)
        if write_report is not None:
            report_path = write_report(f"{when}-{product}.md", report_md)
        else:
            rdir = root / "predeploy-reports"
            rdir.mkdir(exist_ok=True)
            rp = rdir / f"{when}-{product}.md"
            rp.write_text(report_md)
            report_path = str(rp.relative_to(root))
        for u in unknowns:
            logger(
                PROJECT_SLUG, 4, "predeploy unknown failure", "technical",
                f"[{product}/{u['check']}] unhandled pre-deploy failure (see {report_path}): "
                f"{u['output'].strip()[:200]}",
            )

    failed = [r for r in results if not r["ok"]]
    healthy = not failed
    return {
        "ok": True,
        "product": product,
        "status": "ready" if healthy else "blocked",
        "exit_code": 0 if healthy else 1,
        "checks": results,
        "classified": classified,
        "auto_fixed": auto_fixed,
        "unknown_count": len(unknowns),
        "report_path": report_path,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.predeploy_check",
        description=(
            "Pre-deploy verification + learning gate (deploy-hardening P5). "
            "For a product, runs the deploy-relevant checks (framework-dep "
            "parity, frontend vite build, backend pytest, the D3 "
            "deploy-local-gitignored manifest assertion, and the "
            "prod_config_parity value-correctness gate — the 3rd leg of the "
            "deploy-config-contract: every product resolves a non-localhost "
            "prod URL, no PRODUCT_URL_*/CORS_ORIGINS value carries a loopback "
            "host; feed it a snapshot via prod_env_path / NOCTUS_PROD_ENV_FILE "
            "/ a .env.prod, else it SKIPs loudly), CLASSIFIES any "
            "failure against the known boundary-contract classes, AUTO-FIXES "
            "the framework-dep class when auto_fix=True (composes "
            "check_framework_deps), and for an UNKNOWN failure writes "
            "predeploy-reports/<utc>-<product>.md + logs phase_learnings (s1). "
            "status='ready' (all pass, exit 0) | 'blocked' (≥1 fail, exit 1). "
            "Pass worktree_path when called from inside a git worktree. "
            "See KB § GUIDES/production-deploy.md § 2a + "
            "KB § PATTERNS/boundary-contract-tests.md."
        ),
    )
    def _predeploy_check(
        product: str,
        auto_fix: bool = False,
        worktree_path: str | None = None,
        prod_env_path: str | None = None,
    ) -> dict:
        return predeploy_check(
            product,
            auto_fix=auto_fix,
            worktree_path=worktree_path,
            prod_env_path=prod_env_path,
        )


__all__ = [
    "predeploy_check",
    "classify_failure",
    "audit_deploy_local",
    "audit_prod_config_parity",
    "audit_required_prod_env_present",
    "audit_cors_roster_complete",
    "DEFAULT_CHECKS",
    "PROJECT_SLUG",
    "register",
]
