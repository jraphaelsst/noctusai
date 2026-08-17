"""noctus.dev.deploy_verify — the INDEPENDENT prod revision-drift witness.

The incident this closes (2026-08-13, real). A social-wiring promote looked
fully shipped: `release stage=bless` OK, `stage=promote` OK (prod tip ==
57807ada), `deploy_pull` OK. Then `deploy_image` **timed out without
returning**, and the MCP server disconnected before reporting anything. A
manual `docker inspect` — not any tool — was what caught it: the container
was still `org.opencontainers.image.revision=ecff5585`, "Up 2 days". The
swap had never happened. Two bug fixes were reported-adjacent to "shipped"
while prod served the old code for hours.

The structural hole is not "`deploy_image` has a bug" — it is that the ONLY
witness to whether a deploy landed was the deploying tool itself. When that
tool dies mid-flight, the system has NO independent answer to "what is prod
actually running?", because every branch-level signal (`prod` tip,
`deploy_pull`'s outcome) describes **git**, not the **running container**.

This tool is that independent answer. It has ZERO dependency on
`deploy_image` having run, succeeded, or even existed in this process —
it is composed entirely from read-only primitives (`noctus.vps.exec`'s
`docker inspect` / `docker exec … curl` allowlist) plus a LOCAL git
resolution of the `prod` branch tip (never a caller-supplied sha — a wrong
answer there would defeat the whole point).

TWO LESSONS FROM THE FIRST LIVE RUN (2026-08-17), both folded in:

1. **Roster must be catalog-driven, not compose-driven.** The compose file
   answers "what CAN run"; `ativo=true AND deploy_scope='live'` (`KB §
   PATTERNS/architect/product-working-scope.md` — "the catalog IS the
   working guide") answers "what we are ACCOUNTABLE for". A product that is
   `ativo=false` will NEVER reach the prod tip — flagging it drifted forever
   trains people to ignore the gate (same failure mode as a noisy keeper).
   Symmetric miss the first roster shipped without: `ativo=true`+`live`+
   ABSENT from the fleet entirely (no container at all — e.g. p-studio,
   2026-08-17) is a real finding of its own (`missing`), not something a
   compose-driven loop could ever see since it never iterates a product with
   no service block. `core` is the one documented non-catalog member (the
   platform shell; `KB § PATTERNS/architect/product-working-scope.md`) —
   always actionable regardless of the catalog. Live source:
   `build_scope._live_slugs_from_catalog` (the SAME query
   `noctus.dev.refresh_build_scope` uses — no second hand-rolled notion of
   "what's active", `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`).
   Offline fallback: the checked-in, DERIVED `deploy/fleet/build-scope.txt`
   snapshot — never a hand-maintained list, but its staleness risk is
   reported in `catalog_source`/`catalog_warning`, never silently trusted.
   Non-actionable products are still READ (never silently dropped) and
   reported in `skipped_inactive` with their revision — just excluded from
   the pass/fail verdict.

2. **Raw sha inequality is the WRONG drift predicate.** Running an older
   revision than the prod tip is the NORMAL steady state here — images
   rebuild only when their build scope changes
   (`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`), so under a
   bare `revision != expected_sha` test every product goes "red" the moment
   ANY single product deploys, which is most days. The correct predicate:
   does the diff between the RUNNING revision and the prod tip touch this
   product's build inputs? `git diff --name-only <running>..<prod-tip>`
   fed through `deploy_pull._rebuild_decision` (reused verbatim — never a
   second hand-rolled "what belongs to a product" mapping) answers exactly
   that: a per-product runtime-path touch, OR any `seed/`/Dockerfile/compose/
   config change (fleet-wide — a shared base moved). Empty ⇒ `ok`. Non-empty
   ⇒ `drift`, and the record says WHICH/how-many files, because "you are 27
   seed-changes behind" is what makes it actionable where a bare sha
   mismatch does not. A running revision unresolvable in this clone (an
   image built off a sha never fetched here) is `unverifiable`, never
   silently `ok`.

Composes `noctus.vps.exec.exec_cmd` (the existing bounded read-only VPS
exec) + `deploy_pull._rebuild_decision` (the build-scope diff oracle) +
`build_scope._live_slugs_from_catalog`/`read_build_scope` (the catalog
roster) rather than re-deriving any of the three — same reuse shape as
`release.py` composing `deploy_pull._rebuild_decision` for its own rebuild
hint. IO is injectable (`run_remote` threaded into `exec_cmd`, `run_local`
for both the git resolution AND the build-scope diff, `live_products_fn`
for the catalog query) so the colocated test drives every path with zero
real SSH, zero real git, and zero real network.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from settings import REPO_ROOT
from workspace import resolve_caller_root

from . import build_scope as _build_scope
from . import vps_exec as _vps_exec
from .deploy_pull import _rebuild_decision

DEFAULT_HOST = "noctus-vps"
DEFAULT_COMPOSE = "deploy/fleet/docker-compose.prod.yml"

# The same OCI label build-and-push.sh bakes at build time (mirrors
# deploy_image._REVISION_LABEL — a plain string constant, not a functional
# dependency: this module never calls into deploy_image, by design).
_REVISION_LABEL = "org.opencontainers.image.revision"

_INSPECT_TEMPLATE = (
    "{{.State.Status}}|"
    "{{if .State.Health}}{{.State.Health.Status}}{{end}}|"
    f'{{{{ index .Config.Labels "{_REVISION_LABEL}" }}}}'
)


def _default_run_local(cmd: list[str]) -> tuple[int, str, str]:
    """Local git — resolving the prod tip (and diffing against it) is
    deliberately NOT an SSH op; it must work even when the VPS/SSH path is
    the thing that's broken."""
    import subprocess

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _resolve_expected_sha(
    run_local: Callable[[list[str]], tuple[int, str, str]],
    remote: str, prod_branch: str,
) -> tuple[str | None, str]:
    """The prod branch tip, resolved FRESH — never a parameter (a caller
    passing the wrong answer would get a false green, defeating the point).
    Returns (sha_or_None, detail)."""
    rc_f, _o, err_f = run_local(["git", "fetch", remote, "--quiet"])
    if rc_f != 0:
        return None, f"git fetch {remote} failed: {err_f.strip()}"
    ref = f"{remote}/{prod_branch}"
    rc_r, out_r, err_r = run_local(["git", "rev-parse", "--verify", "--quiet", ref])
    sha = out_r.strip()
    if rc_r != 0 or not sha:
        return None, f"cannot resolve '{ref}': {err_r.strip() or 'unknown ref'}"
    return sha, f"resolved {ref} = {sha}"


def _scope_refresh_date(path: Path) -> str | None:
    """Best-effort 'Last refresh: YYYY-MM-DD' parse from build-scope.txt's
    generated header — surfaced in the fallback warning so its staleness
    risk is visible in the OUTPUT, not buried in a source comment."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"Last refresh:\s*(\S+)", text)
    return m.group(1) if m else None


def _resolve_live_products(
    live_products_fn: Callable[[], list[str]] | None = None,
) -> tuple[set[str] | None, str, str | None]:
    """The catalog-derived ACTIONABLE set: `ativo=true AND deploy_scope=
    'live'` (`build_scope._live_slugs_from_catalog` — the SAME source of
    truth `noctus.dev.refresh_build_scope` uses) plus `core` (the platform
    shell; deliberately not a `products` row —
    `KB § PATTERNS/architect/product-working-scope.md`).

    PRIMARY: a live catalog query. FALLBACK (catalog unreachable — offline,
    missing SUPABASE_* creds, or a query error of any shape): the checked-in,
    DERIVED `deploy/fleet/build-scope.txt` snapshot — it is never a
    hand-maintained list (`check_hardcoded_product_slug_set`'s rule; the file
    is itself generated FROM this same catalog query), but it can go stale
    between refreshes, so that risk rides in the returned `warning`, never
    silently absorbed. Returns (live_slugs_or_None, source, warning);
    `source` ∈ {live_catalog, build_scope_fallback, unavailable}. Never
    raises — every failure mode returns `None` + an explanatory warning."""
    fn = live_products_fn or _build_scope._live_slugs_from_catalog
    try:
        live = set(fn()) | set(_build_scope.ALWAYS_BUILD)
        return live, "live_catalog", None
    except Exception as exc:  # noqa: BLE001 — ANY catalog-reach failure falls back, never crashes
        fallback = _build_scope.read_build_scope()
        if fallback:
            refreshed = _scope_refresh_date(_build_scope.SCOPE_PATH)
            warning = (
                f"live catalog unreachable ({exc}) — FELL BACK to the checked-in "
                "deploy/fleet/build-scope.txt snapshot (derived from this same "
                f"catalog query, never hand-maintained, but last refreshed "
                f"{refreshed or 'unknown'} — a product activated/deactivated since "
                "then will misclassify here). Run `noctus.dev.refresh_build_scope` "
                "once catalog access is restored, then re-run this check."
            )
            return set(fallback) | set(_build_scope.ALWAYS_BUILD), "build_scope_fallback", warning
        return None, "unavailable", (
            f"live catalog unreachable ({exc}) AND deploy/fleet/build-scope.txt is "
            "missing/empty — cannot determine which products are actionable. "
            "REFUSING to guess (no silent errors)."
        )


def _load_compose_roster(root: Path, compose_file: str) -> tuple[list[dict[str, Any]], str | None]:
    """[{slug, container, port}] from the prod compose file's `services:`
    block — used ONLY for container-name/port LOOKUP (the catalog, not this
    file, now drives which slugs get an actionable verdict). Returns
    (roster, error_or_None). Lazy `yaml` import (only paid when the caller
    doesn't supply `products=`)."""
    import yaml

    path = root / compose_file
    if not path.exists():
        return [], f"compose file not found: {path}"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [], f"could not parse {path}: {exc}"
    services = data.get("services") or {}
    if not isinstance(services, dict) or not services:
        return [], f"no services found in {path}"
    roster: list[dict[str, Any]] = []
    for slug in sorted(services):
        svc = services[slug] or {}
        container = svc.get("container_name") or f"noctus-{slug}"
        expose = svc.get("expose") or []
        port = None
        if expose:
            m = re.search(r"\d+", str(expose[0]))
            port = m.group(0) if m else None
        roster.append({"slug": slug, "container": container, "port": port})
    return roster, None


def _diff_drift(
    run_local: Callable[[list[str]], tuple[int, str, str]],
    slug: str, running_rev: str, expected_sha: str,
) -> dict[str, Any]:
    """Whether the diff between the RUNNING revision and the prod tip
    touches THIS product's build inputs — the actionable-drift predicate.
    Reuses `deploy_pull._rebuild_decision` verbatim (never a second
    hand-rolled "what belongs to a product" mapping): a per-product runtime
    path (`products/<slug>/backend|frontend/`) touch, OR any `seed/`/
    Dockerfile/compose/edge-config change (fleet-wide — a shared base
    moved). A running revision that fails to resolve locally (image built
    off a sha never fetched into this clone, or an unparented/rewritten
    history) is UNVERIFIABLE, never silently `ok` — a stale-but-safe
    revision and an unauditable one must never look the same."""
    rc_v, _o, _e = run_local(["git", "cat-file", "-e", f"{running_rev}^{{commit}}"])
    if rc_v != 0:
        return {
            "actionable_drift": None, "changed_file_count": None, "fleet_wide_change": None,
            "build_relevant_files": [],
            "reason": (
                f"running revision {running_rev[:12]} does not resolve to a known "
                "commit in this clone (an image built off a sha never fetched here, "
                "or an unparented/rewritten history) — cannot compute the "
                "build-relevant diff. UNVERIFIABLE, not assumed clean."
            ),
        }
    rc_d, out_d, err_d = run_local(["git", "diff", "--name-only", f"{running_rev}..{expected_sha}"])
    if rc_d != 0:
        return {
            "actionable_drift": None, "changed_file_count": None, "fleet_wide_change": None,
            "build_relevant_files": [],
            "reason": f"`git diff --name-only {running_rev[:12]}..{expected_sha[:12]}` failed: "
                      f"{err_d.strip()}",
        }
    files = [ln.strip() for ln in out_d.splitlines() if ln.strip()]
    decision = _rebuild_decision(files)
    touches_product = slug in decision["products"]
    actionable = touches_product or decision["fleet_wide"]
    if actionable:
        reason = (
            f"{len(files)} file(s) changed between the running revision and the prod "
            f"tip, including build-relevant path(s) for '{slug}' "
            f"({'fleet-wide — seed/ or Dockerfile/compose/config change' if decision['fleet_wide'] else 'product-own path'})"
            + (f": {', '.join(decision['reasons'][:5])}" if decision["reasons"] else "")
        )
    else:
        reason = (
            f"{len(files)} file(s) changed between the running revision and the prod "
            f"tip, but NONE touch '{slug}'s build inputs — running an older revision "
            "is the expected steady state here (images rebuild only when their "
            "build scope changes, KB § PATTERNS/devops/product-lockfile-and-slug-drift.md)."
        )
    return {
        "actionable_drift": actionable,
        "changed_file_count": len(files),
        "fleet_wide_change": decision["fleet_wide"],
        "build_relevant_files": decision["reasons"][:20],
        "reason": reason,
    }


def _verify_one(
    entry: dict[str, Any],
    expected_sha: str,
    ssh_host: str,
    run_remote: Callable | None,
    run_local: Callable[[list[str]], tuple[int, str, str]],
) -> dict[str, Any]:
    """Independent per-product read: running revision + the build-scope
    drift predicate + health + startup_hook_error. Never raises — an
    unreachable probe is reported, not swallowed. `entry["actionable"]`
    (catalog-derived) gates whether a verdict is computed at all — a
    non-actionable product is still READ (never silently dropped), just
    excluded from the pass/fail bucket."""
    slug = entry["slug"]
    container = entry["container"]
    port = entry.get("port")
    actionable = bool(entry.get("actionable", True))
    out: dict[str, Any] = {
        "product": slug, "container": container, "port": port, "actionable": actionable,
        "found": False, "state": None, "health": None,
        "revision": None, "expected_sha": expected_sha, "verdict": None,
        "startup_hook_error": None, "health_probe": "skipped", "note": None,
    }

    r_inspect = _vps_exec.exec_cmd(
        f"docker inspect -f '{_INSPECT_TEMPLATE}' {container}",
        ssh_host=ssh_host, run_remote=run_remote,
    )
    if not r_inspect["ok"]:
        if actionable:
            out["verdict"] = "missing"
            out["note"] = (
                f"catalog-active+live product has NO running container "
                f"'{container}' on '{ssh_host}' — not deployed at all, a distinct "
                f"finding from stale-but-running ({(r_inspect.get('stderr') or '').strip()[:200]})."
            )
        else:
            out["note"] = "not ativo+live in the catalog — no container found; nothing to report."
        return out

    out["found"] = True
    parts = (r_inspect["stdout"].strip().split("|") + ["", "", ""])[:3]
    state, health, revision = (p.strip() for p in parts)
    out["state"] = state or None
    out["health"] = health or None
    revision = revision if revision and revision != "<no value>" else None
    out["revision"] = revision

    if not actionable:
        out["note"] = (
            "not ativo+live in the catalog — informational only, excluded from "
            "the pass/fail verdict (skipped_inactive)."
        )
        return out

    if revision is None:
        out["verdict"] = "unverifiable"
        out["note"] = (
            "no org.opencontainers.image.revision label on the running container "
            "(image predates the revision guard, or was built by a path other than "
            "build-and-push.sh) — drift is UNVERIFIABLE, not assumed clean."
        )
    elif revision == expected_sha:
        out["verdict"] = "ok"
        out["note"] = "running revision exactly matches the prod tip."
    else:
        diff = _diff_drift(run_local, slug, revision, expected_sha)
        out["changed_file_count"] = diff.get("changed_file_count")
        out["fleet_wide_change"] = diff.get("fleet_wide_change")
        if diff.get("build_relevant_files"):
            out["build_relevant_files"] = diff["build_relevant_files"]
        out["note"] = diff["reason"]
        if diff["actionable_drift"] is None:
            out["verdict"] = "unverifiable"
        elif diff["actionable_drift"]:
            out["verdict"] = "drift"
        else:
            out["verdict"] = "ok"

    # ── active health probe (in-container /api/health) — reuses the SAME
    #    exec_cmd allowlist noc-ship step 6 already calls by hand. ──
    if port:
        r_health = _vps_exec.exec_cmd(
            f"curl -fsS -m 3 http://localhost:{port}/api/health",
            container=container, ssh_host=ssh_host, run_remote=run_remote,
        )
        if r_health["ok"]:
            out["health_probe"] = "ok"
            try:
                body = json.loads(r_health["stdout"])
            except (ValueError, TypeError):
                body = {}
                out["health_probe"] = "ok_unparsed"
            out["startup_hook_error"] = body.get("startup_hook_error")
        else:
            out["health_probe"] = "unreachable"
            out["startup_hook_error"] = "unknown (probe unreachable)"
    else:
        out["health_probe"] = "skipped (no port resolved)"

    # A health problem downgrades a clean revision-verdict to 'degraded'.
    # It never RELABELS 'drift'/'missing'/'unverifiable' — those are already
    # actionable findings in their own right; the health signal stays
    # visible on the record either way, it just doesn't hide behind them.
    if out["verdict"] == "ok" and (
        out["health"] == "unhealthy" or out["state"] not in (None, "running")
        or out["health_probe"] == "unreachable" or out.get("startup_hook_error")
    ):
        out["verdict"] = "degraded"

    return out


def deploy_verify(
    products: list[str] | None = None,
    ssh_host: str = DEFAULT_HOST,
    compose_file: str = DEFAULT_COMPOSE,
    remote: str = "origin",
    prod_branch: str = "prod",
    run_remote: Callable[[list[str]], tuple[int, str, str]] | None = None,
    run_local: Callable[[list[str]], tuple[int, str, str]] | None = None,
    live_products_fn: Callable[[], list[str]] | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Independent revision-drift verification — callable standalone with NO
    dependency on `deploy_image` having run. Roster: catalog-driven
    (`ativo=true AND deploy_scope='live'` + `core`) — or an explicit
    `products=` override, which bypasses the catalog and treats every named
    slug as actionable (deliberately, e.g. to debug an inactive product).

    Per actionable product: the RUNNING container's revision vs the
    FRESHLY-resolved `prod` branch tip, fed through the build-scope
    diff predicate (NOT raw sha inequality — a stale-but-untouched revision
    is the expected steady state), plus health + `startup_hook_error`.
    Non-actionable (catalog-inactive/non-live) products are still read and
    reported in `skipped_inactive`, never silently dropped, but excluded
    from the verdict + exit code.

    status ∈ {missing, drift_detected, degraded, unverifiable, verified,
    error}. exit_code 0 ONLY for 'verified'. Never raises — every failure
    mode is a returned status, not an exception (no silent errors)."""
    local_runner = run_local or _default_run_local
    expected_sha, sha_detail = _resolve_expected_sha(local_runner, remote, prod_branch)
    if not expected_sha:
        return {
            "ok": False, "status": "error", "exit_code": 1,
            "error": f"cannot resolve the expected prod sha — {sha_detail}. "
                     "REFUSING to verify against an unknown target (fail-closed; "
                     "an unresolved expectation is not a passed check).",
        }

    if repo_root is not None:
        root = Path(repo_root)
    elif worktree_path:
        root = Path(resolve_caller_root(worktree_path))
    else:
        root = Path(REPO_ROOT)

    catalog_source = "explicit_override"
    catalog_warning = None

    if products:
        # An explicit roster BYPASSES the catalog entirely (deliberate — the
        # caller may want to check an inactive product) and needs the
        # compose file only for port lookup; a miss there degrades to "no
        # port" (health probe skipped), never a hard failure.
        roster, _roster_note = _load_compose_roster(root, compose_file)
        by_slug = {r["slug"]: r for r in roster}
        entries = [
            {**by_slug.get(p, {"slug": p, "container": f"noctus-{p}", "port": None}), "actionable": True}
            for p in products
        ]
    else:
        live_set, catalog_source, catalog_warning = _resolve_live_products(live_products_fn)
        if live_set is None:
            return {
                "ok": False, "status": "error", "exit_code": 1,
                "catalog_source": catalog_source,
                "error": f"cannot resolve the actionable product roster — {catalog_warning}",
            }
        compose_roster, roster_error = _load_compose_roster(root, compose_file)
        if roster_error:
            return {"ok": False, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve the product roster — {roster_error}"}
        compose_by_slug = {r["slug"]: r for r in compose_roster}
        # UNION, not the compose set alone — a catalog-live product absent
        # from the fleet entirely (p-studio, 2026-08-17) must still surface
        # as 'missing', which a compose-driven loop could never see.
        all_slugs = sorted(live_set | set(compose_by_slug))
        entries = []
        for slug in all_slugs:
            comp = compose_by_slug.get(slug)
            entries.append({
                "slug": slug,
                "container": comp["container"] if comp else f"noctus-{slug}",
                "port": comp["port"] if comp else None,
                "actionable": slug in live_set,
            })

    results = [_verify_one(e, expected_sha, ssh_host, run_remote, local_runner) for e in entries]

    actionable_results = [r for r in results if r["actionable"]]
    missing = [r["product"] for r in actionable_results if r["verdict"] == "missing"]
    drifted = [r["product"] for r in actionable_results if r["verdict"] == "drift"]
    degraded = [r["product"] for r in actionable_results if r["verdict"] == "degraded"]
    unverifiable = [r["product"] for r in actionable_results if r["verdict"] == "unverifiable"]
    skipped_inactive = [r["product"] for r in results if not r["actionable"]]

    if missing:
        status, exit_code = "missing", 1
    elif drifted:
        status, exit_code = "drift_detected", 1
    elif degraded:
        status, exit_code = "degraded", 1
    elif unverifiable:
        status, exit_code = "unverifiable", 1
    else:
        status, exit_code = "verified", 0

    return {
        "ok": True, "status": status, "exit_code": exit_code,
        "expected_sha": expected_sha, "ssh_host": ssh_host,
        "catalog_source": catalog_source, "catalog_warning": catalog_warning,
        "checked": len(actionable_results),
        "missing": missing, "drifted": drifted, "degraded": degraded, "unverifiable": unverifiable,
        "skipped_inactive": skipped_inactive,
        "products": results,
        "message": (
            f"{len(actionable_results)} actionable product(s) checked against prod "
            f"tip {expected_sha[:12]} ({catalog_source}) — {len(missing)} missing, "
            f"{len(drifted)} drifted, {len(degraded)} degraded, "
            f"{len(unverifiable)} unverifiable; {len(skipped_inactive)} skipped "
            "(not ativo+live)."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.deploy_verify",
        description=(
            "The INDEPENDENT prod revision-drift witness (closes the 2026-08-13 "
            "phantom-deploy hole: deploy_image timed out mid-swap and nothing "
            "caught it but a manual docker inspect). Roster is CATALOG-DRIVEN "
            "(ativo=true AND deploy_scope='live' + core), not compose-driven — a "
            "product that can never reach the prod tip must never report drift "
            "forever (a permanently-red gate gets ignored); a catalog-live product "
            "with NO running container at all surfaces as 'missing', a real finding "
            "a compose-driven loop could never see. Non-actionable products are "
            "still read + reported in skipped_inactive, never silently dropped. "
            "Per actionable product: the RUNNING container's "
            "org.opencontainers.image.revision vs the expected sha (resolved FRESH "
            "from origin/<prod_branch> — never a parameter), fed through the SAME "
            "build-scope diff predicate deploy_pull uses (a stale-but-untouched "
            "revision is the expected steady state; only a diff that actually "
            "touches this product's build inputs is 'drift') — plus health + "
            "startup_hook_error. Callable standalone — ZERO dependency on "
            "deploy_image having run, succeeded, or even existed in this process. "
            "products= explicit override bypasses the catalog (checks a named "
            "product, including an inactive one, deliberately). "
            "status: missing | drift_detected | degraded | unverifiable | "
            "verified | error. exit_code 0 ONLY for 'verified'."
        ),
    )
    def _deploy_verify(
        products: list[str] | None = None,
        ssh_host: str = DEFAULT_HOST,
        prod_branch: str = "prod",
    ) -> dict:
        return deploy_verify(products=products, ssh_host=ssh_host, prod_branch=prod_branch)


__all__ = [
    "deploy_verify", "_load_compose_roster", "_resolve_expected_sha",
    "_resolve_live_products", "_scope_refresh_date", "_diff_drift",
    "_verify_one", "_REVISION_LABEL", "register",
]
