"""Seed compliance checks — migrated from agents/keeper/checks/.

Validates that products follow the seed framework pattern.
All checks are deterministic, fast, zero AI.

──────────────────────────────────────────────────────────────────────
ADDING A NEW DETECTOR — read this first.
──────────────────────────────────────────────────────────────────────
1. Add the `check_<name>(product_path: Path) -> list[dict]` function
   in this file (NOT a sibling module). The meta-detector
   `check_detector_has_regression_test` self-parses
   `compliance.py` via `Path(__file__)` to enumerate detectors;
   placing the function in a sibling silently drops it from the
   meta-check + leads to "regression test missing" false negatives.
2. Plumb it into BOTH:
     - `check_all_products()` here
     - `tools/noctus/dev/review.py::_detect()`
   Updating only one is a silent drop — `noctus.dev.review` will not
   surface the findings. (Knowledge contributed by
   `keeper-test-status-assertion` Phase 1 retro, 2026-05-06.)
3. Ship a colocated `Test<CamelCase>` regression suite in
   `mcp/noctusai/tests/` per `KB § PATTERNS/testing.md
   § Regression-test-the-detector`.
──────────────────────────────────────────────────────────────────────
"""
# accept-with-rationale: "MCP detectors keep raw `import ast`" in
# KB § PATTERNS/accept-with-rationale.md — compliance walks
# create_product_app(...) Call.keywords + List literals + monkeypatch
# Call.args[0/1] Constants + ImportFrom mapping; all node-level
# surfaces outline_python deliberately omits. Migration evaluated
# 2026-05-02 by ast-callers-consolidation Phase 0 → accept.
import ast
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)


# Control-plane products OWN the identity/team/notifications/... routes — they
# ARE the provider, not consumers. Warnings about "has own team.py — framework
# provides this" are noise for them. Folded in by `seed-inheritance-hardening`
# Phase 5 (was the `keeper-control-plane-classification` backlog item).
#
# Any divergence across three or more products in this set would signal the
# classification is under-specified — re-open the decision.
CONTROL_PLANE_PRODUCTS: set[str] = {"core"}


# Synonyms: a standard-router name the framework ships (key) vs. the router
# module names a product may use when self-providing the same surface.
# Used by the AST-based self-provision detector below.
SELF_PROVIDED_ROUTER_MODULES: dict[str, set[str]] = {
    "notificacoes": {"notificacoes", "notifications"},
    "team": {"team"},
    "llm": {"llm", "llm_router"},
}


# Repo-root directories that are NOT products and must NOT be flagged as
# out-of-contract product trees. Extend only when a new non-product layer
# earns a home at the repo root (platform-wide infra).
_KNOWN_NON_PRODUCT_ROOT_DIRS: set[str] = {
    "products",
    "seed",
    "templates",
    "mcp",
    "KNOWLEDGE-BASE",
    "projects",
    "scripts",
    "venv",
    ".git",
    ".github",
    ".claude",
    ".venv",
    "node_modules",
    "docs",
    "tests",
}


def _parse_self_provided_routers(main_content: str) -> tuple[str, set[str] | None]:
    """AST-parse the `routers=[...]` kwarg on `create_product_app(...)` and
    return the set of router module names (e.g., `{"team", "notifications"}`).

    Returns:
      ("found", {names})  — parsed a list of `<Name>.router` Attributes
      ("absent", None)    — no `create_product_app(...)` call in the file
      ("unparseable", None) — call present but kwarg missing or not a simple
                              list of `<module>.router` attribute accesses

    Never silently returns an empty set for an unparseable value — callers
    must distinguish the three cases so the keeper doesn't quietly pretend
    a product self-provides nothing when the real answer is "can't tell."
    """
    try:
        tree = ast.parse(main_content)
    except SyntaxError as exc:
        logger.warning("compliance: cannot parse main.py (%s); marking as unparseable", exc)
        return "unparseable", None

    call = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_product_app"
        ):
            call = node
            break

    if call is None:
        return "absent", None

    routers_kwarg = next((k for k in call.keywords if k.arg == "routers"), None)
    if routers_kwarg is None:
        return "found", set()

    if not isinstance(routers_kwarg.value, ast.List):
        return "unparseable", None

    names: set[str] = set()
    for elt in routers_kwarg.value.elts:
        if (
            isinstance(elt, ast.Attribute)
            and elt.attr == "router"
            and isinstance(elt.value, ast.Name)
        ):
            names.add(elt.value.id)
        else:
            return "unparseable", None

    return "found", names


def check_seed_compliance(product_path: Path) -> list[dict]:
    """Check a product's seed framework compliance."""
    issues = []
    name = product_path.name
    main_py = product_path / "backend" / "app" / "main.py"
    req_txt = product_path / "backend" / "requirements.txt"
    vite_config = product_path / "frontend" / "vite.config.ts"
    app_tsx = product_path / "frontend" / "src" / "App.tsx"

    # Backend checks
    if main_py.exists():
        content = main_py.read_text()
        if "create_product_app" not in content:
            issues.append({"product": name, "file": "backend/app/main.py", "issue": "Does not use create_product_app()", "severity": "critical"})
        if "noctusai_seed" not in content:
            issues.append({"product": name, "file": "backend/app/main.py", "issue": "Does not import from noctusai_seed", "severity": "critical"})

    if req_txt.exists():
        req_content = req_txt.read_text()
        if "seed/framework/backend" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/framework/backend", "severity": "high"})
        if "seed/lib/backend" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/lib/backend", "severity": "high"})

    # "Has own <router>.py — framework provides this" — suppress for control-plane
    # products that legitimately OWN the route (e.g., core owns team + notifications
    # because it's the identity source; seed would collide with its version).
    if name not in CONTROL_PLANE_PRODUCTS:
        for router_name in ["health.py", "notificacoes.py", "team.py"]:
            if (product_path / "backend" / "app" / "routers" / router_name).exists():
                issues.append({"product": name, "file": f"backend/app/routers/{router_name}", "issue": f"Has own {router_name} — framework provides this", "severity": "warning"})

    # Frontend checks
    if vite_config.exists():
        content = vite_config.read_text()
        if "createViteConfig" not in content:
            issues.append({"product": name, "file": "frontend/vite.config.ts", "issue": "Does not use createViteConfig()", "severity": "critical"})

    if app_tsx.exists():
        app_content = app_tsx.read_text()
        uses_fw = "createProductApp" in app_content or "createProductLayout" in app_content or "@noctusai/seed" in app_content
        if not uses_fw and "QueryClientProvider" in app_content and "BrowserRouter" in app_content:
            issues.append({"product": name, "file": "frontend/src/App.tsx", "issue": "Manual App structure — should use createProductApp()", "severity": "high"})

        src_dir = product_path / "frontend" / "src"
        layout_file = product_path / "frontend" / "src" / "components" / "layout" / "Layout.tsx"
        if layout_file.exists():
            uses_fw_layout = any("createProductLayout" in f.read_text() for f in src_dir.rglob("*.ts") if f.is_file()) or any("createProductLayout" in f.read_text() for f in src_dir.rglob("*.tsx") if f.is_file())
            # Skip for control-plane products that provide a custom Layout via the
            # `createProductApp({ Layout })` named seam — not a divergence, an
            # approved extension point.
            if not uses_fw_layout and name not in CONTROL_PLANE_PRODUCTS:
                issues.append({"product": name, "file": "frontend/src/components/layout/Layout.tsx", "issue": "Has own Layout.tsx — should use createProductLayout()", "severity": "high"})

    return issues


def check_path_references(product_path: Path) -> list[dict]:
    """Check that seed path references are correct."""
    issues = []
    name = product_path.name

    for rel, old, label in [
        ("backend/requirements.txt", "shared/backend", "old shared/backend path"),
        ("frontend/tsconfig.json", "shared/frontend", "old shared/frontend path"),
        ("frontend/tailwind.config.ts", "shared/frontend", "old shared/frontend path"),
    ]:
        target = product_path / rel
        if target.exists():
            content = target.read_text()
            if old in content and "seed/" not in content:
                issues.append({"product": name, "file": rel, "issue": f"References {label} — should be seed/", "severity": "critical"})

    return issues


# Signal map: each standard-router name → regex patterns whose presence in a
# product's frontend source indicates the product consumes that router.
# Keep narrow and curated — grep-based, not AST. Extend as new signals emerge.
# "health" is universal — every product should opt in; no frontend signal needed.
STANDARD_ROUTER_FRONTEND_SIGNALS: dict[str, list[str]] = {
    "notificacoes": [
        r"NotificationBell",  # direct import or alias via infra.NotificationBell
    ],
    "team": [
        r"['\"`]/api/team\b",  # literal path string in hooks / components
    ],
    "llm": [
        r"useLLM(?:Providers|Models|Preferences)\b",  # shared LLM preference hooks
    ],
}

# Fallback filename-based self-provision table — used only when the AST
# parser returns `unparseable` (v1 compatibility). AST parse of the actual
# `routers=[...]` list is the preferred path (set by self-provision v2, folded
# in by `seed-inheritance-hardening` Phase 5).
SELF_PROVIDED_ROUTER_FILES: dict[str, list[str]] = {
    "notificacoes": ["notificacoes.py", "notifications.py"],
    "team": ["team.py"],
    "llm": ["llm.py", "llm_router.py"],
}


def _parse_standard_routers(main_content: str) -> tuple[str, set[str] | None]:
    """Parse the `standard_routers=[...]` kwarg from a product's main.py.

    Returns:
      ("found", {"health", "team", ...})  — parsed a simple list literal
      ("absent", None)                    — no `standard_routers` kwarg at all
      ("unparseable", None)               — kwarg present but not a simple list
                                            literal (e.g., variable reference)

    Never silently returns an empty set for an unparseable value — per the
    "no silent errors" rule, the caller must distinguish these three cases.
    """
    match = re.search(r"standard_routers\s*=\s*\[([^\]]*)\]", main_content, re.DOTALL)
    if match:
        items = [
            s.strip().strip("'\"")
            for s in match.group(1).split(",")
            if s.strip() and s.strip() not in {"'", '"'}
        ]
        return "found", {r for r in items if r}
    if "standard_routers" in main_content:
        return "unparseable", None
    return "absent", None


def check_standard_routers_audit(product_path: Path) -> list[dict]:
    """Verify a product's `standard_routers=[...]` opt-in list matches
    the routers its frontend actually consumes.

    Two directions:
      - **Under-grant** (severity=critical): frontend uses router X but
        backend does not opt into it AND does not self-provide it.
        Runtime 404 risk — this is what the Phase 2 manual audit of
        `core-seed-wiring` missed for adconnect (NotificationBell
        rendered; `notificacoes` opt-out caused silent 404s).
      - **Over-grant** (severity=warning): backend opts into router X
        but no frontend signal found. Dead router registered at boot.

    `health` is universal — skipped (every product should opt in).

    Never silent: if `main.py` exists but `standard_routers` can't be
    parsed as a simple list literal, emits a `warning` finding asking
    for manual audit instead of pretending there is no kwarg.

    Self-provision detection (v2): primary path is AST-parse of
    `routers=[...]` in `main.py` (exact — knows what's wired, not what
    files exist). Falls back to filename-based detection when AST parse
    returns `unparseable`. Closes the gap `keeper-standard-routers-audit`
    Phase 1 noted: a product naming its router file oddly (`my_team_router.py`)
    would previously evade self-provision detection.
    """
    issues: list[dict] = []
    name = product_path.name
    main_py = product_path / "backend" / "app" / "main.py"
    frontend_src = product_path / "frontend" / "src"
    routers_dir = product_path / "backend" / "app" / "routers"

    if not main_py.exists():
        return []  # product has no backend/main.py — not in scope

    main_content = main_py.read_text()
    if "create_product_app" not in main_content:
        # Pre-migration product; other checks handle that. Nothing to audit here.
        return []

    state, opt_in = _parse_standard_routers(main_content)

    if state == "absent":
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                "create_product_app() called without explicit standard_routers=[...]. "
                "Defaults to () — opts out of every bundled router. If intentional, "
                "add `standard_routers=[]` for explicit clarity; if not, add the "
                "routers the product needs."
            ),
            "severity": "high",
        })
        return issues

    if state == "unparseable":
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                "standard_routers kwarg is present but not a simple list literal "
                "(likely a variable reference or dynamic). Keeper cannot audit; "
                "review manually or inline the list."
            ),
            "severity": "warning",
        })
        return issues

    # state == "found" — opt_in is a real set
    assert opt_in is not None  # narrowing for type-checkers

    if not frontend_src.exists():
        # Backend-only product (e.g., webhooks-only service). Audit complete
        # with what we have — no frontend signals to compare.
        return []

    # Self-provision set: AST-parse the `routers=[...]` list first (v2). Fall
    # back to filename-based detection if the file can't be parsed as a simple
    # list of `<module>.router` attribute accesses.
    sp_state, sp_modules = _parse_self_provided_routers(main_content)

    def _self_provides(router: str) -> bool:
        if sp_state == "found":
            assert sp_modules is not None
            synonyms = SELF_PROVIDED_ROUTER_MODULES.get(router, {router})
            return bool(sp_modules & synonyms)
        # Fallback — filename-based. Kept for unparseable `routers=...`
        # (variable reference, dynamic list, SyntaxError). One-line rationale
        # on the "no silent errors" front: the standard_routers parse above
        # already surfaces the `unparseable` state to the user; here we do
        # best-effort self-provision detection so we don't over-flag under-grants.
        for filename in SELF_PROVIDED_ROUTER_FILES.get(router, []):
            if (routers_dir / filename).exists():
                return True
        return False

    # Collect frontend signals.
    signals_found: set[str] = set()
    frontend_files: list[Path] = []
    for ext in ("*.ts", "*.tsx"):
        frontend_files.extend(f for f in frontend_src.rglob(ext) if f.is_file())

    # Concatenate is fine for a small-ish frontend; keeps the scan simple.
    corpus = "\n".join(f.read_text(errors="ignore") for f in frontend_files)

    for router, patterns in STANDARD_ROUTER_FRONTEND_SIGNALS.items():
        if any(re.search(p, corpus) for p in patterns):
            signals_found.add(router)

    # Under-grant: signal exists, NOT in opt-in, NOT self-provided.
    for router in sorted(signals_found - opt_in):
        if _self_provides(router):
            continue  # product serves it from its own router file
        patterns_str = " | ".join(STANDARD_ROUTER_FRONTEND_SIGNALS[router])
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                f"Frontend uses '{router}' router (matched pattern: {patterns_str}) "
                f"but backend does not opt into it via standard_routers=[...] and does "
                f"not self-provide it. Runtime requests to /api/{router}* will 404. "
                f"Fix by adding '{router}' to the opt-in list."
            ),
            "severity": "critical",
        })

    # Over-grant: in opt-in, no signal (and we actually look for one — skip health).
    for router in sorted(opt_in - signals_found):
        if router not in STANDARD_ROUTER_FRONTEND_SIGNALS:
            continue  # health or future-added router without a signal — skip
        patterns_str = " | ".join(STANDARD_ROUTER_FRONTEND_SIGNALS[router])
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                f"Backend opts into '{router}' via standard_routers=[...] but no "
                f"frontend signal found (searched: {patterns_str}). Likely a dead "
                f"router — remove from the list, OR add the missing frontend feature, "
                f"OR extend STANDARD_ROUTER_FRONTEND_SIGNALS if the consumption "
                f"pattern is new."
            ),
            "severity": "warning",
        })

    return issues


def check_frontend_entrypoint(product_path: Path) -> list[dict]:
    """Verify the product's frontend entrypoint actually CALLS `createProductApp()`
    rather than just importing from `@noctusai/seed` or rendering a raw React tree.

    Two valid shapes:
      1. `main.tsx` calls `createProductApp(...)` directly (core pattern).
      2. `main.tsx` delegates to `./App` and `App.tsx` calls `createProductApp(...)`
         (therapy pattern).

    Rendering `<BrowserRouter>` / `<QueryClientProvider>` / `ReactDOM.createRoot(<...>)`
    without routing through `createProductApp` is a structural fork — the framework's
    Suspense, error boundary, routing, providers, and auth path are bypassed.

    Folded in by `seed-inheritance-hardening` Phase 5 — closes the "main.tsx
    bypasses createProductApp" gap that the existing App.tsx-scoped check missed
    (core has no App.tsx; the old detector never fires on core).
    """
    issues: list[dict] = []
    name = product_path.name
    main_tsx = product_path / "frontend" / "src" / "main.tsx"
    app_tsx = product_path / "frontend" / "src" / "App.tsx"

    if not main_tsx.exists():
        return []  # backend-only product

    main_content = main_tsx.read_text()

    # Path 1 — direct call in main.tsx.
    if re.search(r"createProductApp\s*\(", main_content):
        return []

    # Path 2 — delegates to ./App whose default export uses createProductApp.
    imports_app = bool(re.search(r"""from\s+['"]\./App(?:\.tsx)?['"]""", main_content))
    if imports_app and app_tsx.exists():
        app_content = app_tsx.read_text()
        if re.search(r"createProductApp\s*\(", app_content):
            return []

    # Neither path matched — entrypoint is not wired through the framework.
    issues.append({
        "product": name,
        "file": "frontend/src/main.tsx",
        "issue": (
            "Frontend entrypoint does not call createProductApp() — not in main.tsx "
            "and not in an imported ./App. Consumer products must construct the app "
            "via createProductApp() from @noctusai/seed (named seam). Rendering a raw "
            "React tree bypasses the framework's routing, providers, error boundary, "
            "and Suspense fallback."
        ),
        "severity": "critical",
    })
    return issues


def check_out_of_contract_trees(repo_root: Path | None = None) -> list[dict]:
    """Detect product-shaped directories living outside `products/*/`.

    A directory "looks like a product" when it has `backend/app/main.py` OR
    `frontend/src/main.tsx`. `templates/product-seed/` is the scaffolding
    template — not a product; excluded by the known-non-product allow-list.

    Folded in by `seed-inheritance-hardening` Phase 5 — catches future
    `/adconnect/`-style strays before they drift. Returns issues with
    `product="<root>"` so the review pipeline can attribute them at the
    platform level.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name in _KNOWN_NON_PRODUCT_ROOT_DIRS:
            continue
        has_backend_main = (d / "backend" / "app" / "main.py").exists()
        has_frontend_main = (d / "frontend" / "src" / "main.tsx").exists()
        if has_backend_main or has_frontend_main:
            shapes = []
            if has_backend_main:
                shapes.append("backend/app/main.py")
            if has_frontend_main:
                shapes.append("frontend/src/main.tsx")
            issues.append({
                "product": "<root>",
                "file": f"{d.name}/",
                "issue": (
                    f"Directory `{d.name}/` at repo root looks like a product tree "
                    f"(has {', '.join(shapes)}) but lives outside `products/*/`. "
                    f"Either migrate to `products/{d.name}/` (filing a `{d.name}-seed-wiring` "
                    f"project per CLAUDE.md rule 1) or delete the directory if it's "
                    f"legacy / migrational reference with no unique content."
                ),
                "severity": "critical",
            })
    return issues


def check_seed_version_propagation(repo_root: Path | None = None) -> list[dict]:
    """Detect seed-install drift: stale `__seed_version__` / `__lib_version__`.

    Shipped by `seed-inheritance-hardening` Phase 3 via `seed-core-consolidation` §7.1
    (user decision: git-tag/SHA-derived at install time).

    Logic:
    1. Read the current git short SHA from the repo HEAD.
    2. Import `noctusai_seed.__seed_version__` + `noctusai_lib.__lib_version__`
       from the currently-installed packages.
    3. If either reports a SHA different from git HEAD — flag. Actionable
       remediation: `bash scripts/stamp-seed-version.sh` (or restart via
       `./start.sh` which does it automatically).
    4. If either reports a `runtime:<sha>` tag (fallback path, no install
       stamp yet) — flag as warning so a never-stamped environment gets
       noticed.
    5. If either reports "unknown" — flag as critical (import failed, or
       no git + no stamp — detector is blind).

    Returns a list of issue dicts compatible with the existing detector
    protocol. `product="<platform>"` because this is a single-pointed
    platform-wide check, not per-product.
    """
    import subprocess

    issues: list[dict] = []
    root = repo_root or REPO_ROOT

    try:
        git_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if git_result.returncode != 0 or not git_result.stdout.strip():
            # Can't determine current HEAD — skip check rather than error noisily.
            return issues
        current_sha = git_result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("compliance: git unavailable for version-propagation check (%s); skipping", exc)
        return issues

    for package_name, attr_name, stamp_hint in (
        ("noctusai_seed", "__seed_version__", "seed/framework/backend"),
        ("noctusai_lib", "__lib_version__", "seed/lib/backend"),
    ):
        # Prefer reading `_version_static.py` from the filesystem — this
        # avoids requiring `pip install -e` of the seed packages in the venv
        # that runs `--validate` (e.g. the MCP toolkit's own venv). The
        # static stamp IS the propagation source of truth; importing the
        # package only adds the live-git fallback path which we can apply
        # ourselves below if the static stamp is missing.
        static_path = root / stamp_hint / package_name / "_version_static.py"
        reported: str | None = None
        if static_path.exists():
            try:
                static_content = static_path.read_text(encoding="utf-8")
                m = re.search(
                    r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]',
                    static_content,
                    re.MULTILINE,
                )
                if m:
                    reported = m.group(1)
            except OSError as exc:
                logger.warning("compliance: cannot read %s (%s); falling through to import", static_path, exc)
                reported = None
        if reported is None:
            # Static stamp missing or unreadable. Try importing as a last
            # resort — only fires if the package happens to be installed.
            try:
                module = __import__(package_name)
                reported = getattr(module, attr_name, None)
            except ImportError as exc:
                logger.warning("compliance: cannot import %s (%s); will surface as critical issue", package_name, exc)
                issues.append({
                    "product": "<platform>",
                    "file": f"{stamp_hint}/{package_name}/_version_static.py",
                    "issue": (
                        f"`{package_name}` has no `_version_static.py` stamp "
                        f"AND is not installed in this venv. Run "
                        f"`bash scripts/stamp-seed-version.sh` to write the "
                        f"stamp, or `pip install -e {stamp_hint}` to install "
                        f"the package."
                    ),
                    "severity": "critical",
                })
                continue

        if not isinstance(reported, str) or not reported:
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/{package_name}/_version_static.py",
                "issue": (
                    f"`{package_name}.{attr_name}` is missing or empty — "
                    f"propagation detector is blind. Expected a git short SHA."
                ),
                "severity": "critical",
            })
            continue

        if reported == "unknown":
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/{package_name}/_version_static.py",
                "issue": (
                    f"`{package_name}.{attr_name}` reports 'unknown' — "
                    f"neither install-time stamp nor live git succeeded. "
                    f"Run `bash scripts/stamp-seed-version.sh` from a git clone."
                ),
                "severity": "critical",
            })
            continue

        if reported.startswith("runtime:"):
            live_sha = reported.split(":", 1)[1]
            if live_sha != current_sha:
                # This should be impossible (runtime read happens in-process
                # from the same git tree), but catch it defensively.
                issues.append({
                    "product": "<platform>",
                    "file": f"{stamp_hint}/",
                    "issue": (
                        f"`{package_name}.{attr_name}` reports live-git SHA "
                        f"{live_sha!r} but current `git rev-parse --short HEAD` "
                        f"is {current_sha!r}. Filesystem inconsistency — "
                        f"investigate."
                    ),
                    "severity": "high",
                })
            else:
                # Runtime-fallback path took over. Flag as warning so the
                # developer stamps explicitly and shifts to the install-time path.
                issues.append({
                    "product": "<platform>",
                    "file": f"{stamp_hint}/{package_name}/_version_static.py",
                    "issue": (
                        f"`{package_name}.{attr_name}` falls back to live git "
                        f"(reports {reported!r}) — no install-time stamp exists. "
                        f"Run `bash scripts/stamp-seed-version.sh` once to "
                        f"enable drift detection across future pulls."
                    ),
                    "severity": "warning",
                })
            continue

        if reported != current_sha:
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/{package_name}/_version_static.py",
                "issue": (
                    f"Seed drift: installed `{package_name}.{attr_name}` is "
                    f"{reported!r} but current `git rev-parse --short HEAD` "
                    f"is {current_sha!r}. The running Python sees stale seed "
                    f"code. Remediate: `bash scripts/stamp-seed-version.sh` "
                    f"(or restart via `./start.sh` which does it automatically)."
                ),
                "severity": "high",
            })

    return issues


def _resolve_base_name(node: ast.expr) -> str | None:
    """Resolve a class-base AST node to its terminal name.

    Handles `Name` (`ProductSettings`) and `Attribute` (`pkg.ProductSettings`).
    Returns None for unrecognized shapes — caller treats that as 'doesn't match
    a known seed base', which is the safe default.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def check_config_extends_product_settings(product_path: Path) -> list[dict]:
    """Every product config class must extend `noctusai_seed.ProductSettings`.

    Direct extension of `BaseAppSettings` is a structural fork: the product
    duplicates env_file resolution and loses the seed's `parents[4] / .env`
    math. This was the root cause of the 2026-04-25 core login regression
    (path resolved to `products/.env`, supabase_url loaded as ""). Filed
    after `core-seed-wiring` Phase 6 closed the symptom — this detector
    closes the recurrence path.

    Detection: AST-walks `app/config.py`, finds every `ClassDef`, and checks
    that any class extending `BaseAppSettings` also extends `ProductSettings`.
    Returns severity=critical findings (silent prod failure class).

    Skips products without `app/config.py` (returns empty).

    Opt-out: a `# noctusai-keeper: allow-base-app-settings` comment on or
    immediately above the offending `class` line suppresses the finding.
    Build the recognizer when the first legitimate case appears (YAGNI).
    """
    issues: list[dict] = []
    name = product_path.name
    config_file = product_path / "backend" / "app" / "config.py"
    if not config_file.exists():
        return issues

    try:
        tree = ast.parse(config_file.read_text())
    except SyntaxError as e:
        logger.warning("compliance: cannot parse %s (%s); will surface as critical issue", config_file, e)
        issues.append({
            "product": name,
            "file": "backend/app/config.py",
            "issue": f"Failed to parse config.py: {e.msg} at line {e.lineno}",
            "severity": "critical",
        })
        return issues

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {_resolve_base_name(b) for b in node.bases}
        base_names.discard(None)
        if "BaseAppSettings" in base_names and "ProductSettings" not in base_names:
            issues.append({
                "product": name,
                "file": "backend/app/config.py",
                "issue": (
                    f"Class {node.name!r} extends BaseAppSettings directly. "
                    f"Should extend noctusai_seed.ProductSettings to inherit "
                    f"env_file resolution (parents[4] / .env). Hand-rolling the "
                    f"env_file path silently breaks env loading — see the "
                    f"2026-04-25 core login regression."
                ),
                "severity": "critical",
            })

    return issues


# Matches a quoted relative path that targets the seed directory.
# - Must start with `.` or `..` (relative path marker) inside the quote
# - Must contain `seed` followed by either `/` (path continues) or a terminal quote
# - No quote characters inside the captured path
# Rejects non-paths like "seed-loader" (no leading dot) or "docs/seed.md"
# (terminal `seed.md`, not `seed/...` or terminal `seed`). Programmatic
# path construction (`path.resolve(__dirname, "..", "seed")`) is out of
# scope per Q1 (YAGNI — extend if a programmatic-form bug surfaces).
_SEED_RELATIVE_PATH_PATTERN = re.compile(
    r"""['"](\.{1,2}[^'"]*?seed(?:/[^'"]*)?)['"]"""
)

# Module-resolution extensions tried by vite/typescript when an import omits
# the file extension. Order matches typical bundler probe order.
_TS_MODULE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_TS_INDEX_FILES = ("index.ts", "index.tsx", "index.js", "index.jsx")


def _resolves_via_module_resolution(resolved: Path) -> bool:
    """True if a TS/JS import path resolves to something that exists.

    Mimics vite/typescript probe order:
      1. literal path as-is
      2. literal path + .ts / .tsx / .js / .jsx / .mts / .cts
      3. literal path / index.ts (etc.)
    """
    if resolved.exists():
        return True
    for ext in _TS_MODULE_EXTENSIONS:
        if Path(f"{resolved}{ext}").exists():
            return True
    for idx in _TS_INDEX_FILES:
        if (resolved / idx).exists():
            return True
    return False


def _glob_prefix_resolves(resolved_str: str) -> bool:
    """True if a glob pattern's literal prefix points to an existing directory.

    Tailwind `content` arrays use globs like `<dir>/**/*.{ts,tsx}`. The bug
    class we're catching is "the directory before the glob doesn't exist",
    not "the glob matches zero files" (which is a runtime concern).
    """
    glob_chars = "*?[{"
    first_glob = next((i for i, c in enumerate(resolved_str) if c in glob_chars), None)
    if first_glob is None:
        return False  # caller should not have called this for non-glob paths
    prefix = resolved_str[:first_glob].rsplit("/", 1)[0]
    return Path(prefix).is_dir()


def check_frontend_config_paths(product_path: Path) -> list[dict]:
    """Verify relative paths to `seed/` in frontend config files actually resolve.

    Reads `frontend/vite.config.ts`, `frontend/tailwind.config.ts`, and
    `frontend/postcss.config.js`. Extracts every relative path containing
    `seed/`, resolves it against the config file's location, and flags
    paths whose resolution targets nothing.

    Resolution mimics vite/typescript:
      - Literal imports without extensions probe `.ts` / `.tsx` / `.js` /
        etc., and `/index.ts` directory-indexes (handled by
        `_resolves_via_module_resolution`).
      - Glob patterns (containing `*`, `?`, `[`, or `{`) verify the
        literal-prefix directory exists (handled by `_glob_prefix_resolves`).

    Skips silently when a config file doesn't exist (postcss is optional;
    the missing-vite-config case is already covered by `check_seed_compliance`).

    Filed by `projects/keeper-frontend-config-paths-audit/` after the
    2026-04-20 seed-relocation broke core's frontend (`../../seed/` →
    `../../../seed/`). The bug class is "stale relative path = unbuildable
    frontend"; severity matches the inheritance-bypass class.
    """
    issues: list[dict] = []
    name = product_path.name
    config_files = [
        product_path / "frontend" / "vite.config.ts",
        product_path / "frontend" / "tailwind.config.ts",
        product_path / "frontend" / "postcss.config.js",
    ]
    glob_chars = "*?[{"
    for config_file in config_files:
        if not config_file.exists():
            continue
        content = config_file.read_text()
        for match in _SEED_RELATIVE_PATH_PATTERN.finditer(content):
            rel_path = match.group(1)
            resolved = (config_file.parent / rel_path).resolve()
            if any(c in str(resolved) for c in glob_chars):
                ok = _glob_prefix_resolves(str(resolved))
            else:
                ok = _resolves_via_module_resolution(resolved)
            if not ok:
                issues.append({
                    "product": name,
                    "file": str(config_file.relative_to(product_path)),
                    "issue": (
                        f"Stale relative path {rel_path!r} resolves to "
                        f"{resolved} which does not exist (tried TS module "
                        f"resolution + glob prefix). Frontend will fail to build."
                    ),
                    "severity": "critical",
                })
    return issues


def check_mock_schema_validation(product_path: Path) -> list[dict]:
    """Verify the product's test conftest does not opt OUT of MockSupabaseClient
    schema validation without an explicit rationale comment.

    Default as of `mock-supabase-schema-validation` Phase 4 (2026-04-24) is
    `validate_schema=True`. A conftest that passes `validate_schema=False`
    must include a nearby comment explaining WHY (pointing at the follow-up
    reconciliation project that will flip it back).

    Detection rules:
      - If conftest passes `validate_schema=False` literally AND the file
        contains no comment mentioning `schema-drift` / `reconciliation` /
        `follow-up` → warning with severity=high.
      - If conftest uses the shared `MockSupabaseClient()` with no flag →
        fine (the default is now True).
      - If conftest doesn't instantiate `MockSupabaseClient` at all → skip.

    This closes the "silent opt-out" loophole: a product CAN drop validation
    if the drift is too big to fix in-session, but the next agent inherits
    the rationale and the pointer to the remediation project.
    """
    issues: list[dict] = []
    name = product_path.name
    conftest = product_path / "backend" / "tests" / "conftest.py"
    if not conftest.exists():
        return issues
    content = conftest.read_text()

    # Opt-out detector — string-match `validate_schema=False` anywhere in file.
    if "validate_schema=False" not in content:
        return issues

    # Rationale detector — look for any explanatory keyword.
    rationale_keywords = (
        "schema-drift",
        "schema drift",
        "reconciliation",
        "follow-up",
        "follow up",
        "TODO",
    )
    has_rationale = any(kw.lower() in content.lower() for kw in rationale_keywords)
    if has_rationale:
        return issues

    issues.append({
        "product": name,
        "file": "backend/tests/conftest.py",
        "issue": (
            "MockSupabaseClient is constructed with `validate_schema=False` but "
            "the conftest has no rationale comment. Silent opt-out from schema "
            "validation re-opens the silent-fail class closed by the "
            "`mock-supabase-schema-validation` project. Either flip back to "
            "`validate_schema=True` (default) or add a comment block naming the "
            "drift points + the follow-up reconciliation project that will "
            "resolve them (see `products/therapy-platform/projects/"
            "therapy-audio-lifecycle-schema-reconciliation/` for the reference "
            "shape)."
        ),
        "severity": "high",
    })
    return issues


def check_ai_feature_completeness(product_path: Path) -> list[dict]:
    """Verify a product's AI-feature wiring is complete.

    Tier 1.5 G3 hardening (ai-expansion, 2026-04-24). For each product that
    has `app/services/ai_service.py`, verify:

      1. The `app/routers/ai.py` (or any `app/routers/<x>.py` containing AI
         endpoints) is registered in `main.py`'s `routers=[...]` list.
      2. The product's `MASTER-PROMPT.md` has an "AI" section mentioning
         the service file (otherwise an agent can't discover it).
      3. Every `chat_completion(..., cache=True, ...)` call in the service
         passes `org_id=` (cross-org cache-leak guard — pairs with the cache
         key isolation shipped by G5).

    Skips products without an `ai_service.py` (no AI features → nothing to check).
    """
    issues: list[dict] = []
    name = product_path.name
    ai_service = product_path / "backend" / "app" / "services" / "ai_service.py"
    if not ai_service.exists():
        return issues

    # ── Check 1: ai.py router (if present) is in main.py's routers list ──
    main_py = product_path / "backend" / "app" / "main.py"
    ai_router = product_path / "backend" / "app" / "routers" / "ai.py"
    if ai_router.exists() and main_py.exists():
        main_content = main_py.read_text()
        # Look for any of: `ai.router`, `ai_router.router`, or import-form.
        wired = bool(
            re.search(r"\bai\.router\b", main_content)
            or re.search(r"\bai_router\.router\b", main_content)
            or re.search(r"from\s+app\.routers(?:\.|\s+import\s+\(?[^)]*?\b)ai\b", main_content)
        )
        if not wired:
            issues.append({
                "product": name,
                "file": "backend/app/main.py",
                "issue": (
                    f"{name} has `app/services/ai_service.py` and `app/routers/ai.py` "
                    f"but the router is NOT registered in `main.py`'s `routers=[...]`. "
                    f"AI endpoints will 404 in production. Add the import + the router "
                    f"to the create_product_app(routers=[...]) list."
                ),
                "severity": "high",
            })

    # ── Check 2: MASTER-PROMPT.md mentions AI ──
    master_prompt = product_path / "MASTER-PROMPT.md"
    if master_prompt.exists():
        mp_content = master_prompt.read_text()
        # Heuristic: any-level Markdown heading mentioning AI, OR an explicit
        # `ai_service` mention in the prose.
        has_ai_section = bool(
            re.search(r"^#{2,}\s+.*\bAI\b", mp_content, re.MULTILINE)
            or "ai_service" in mp_content
        )
        if not has_ai_section:
            issues.append({
                "product": name,
                "file": "MASTER-PROMPT.md",
                "issue": (
                    f"{name} ships `app/services/ai_service.py` but `MASTER-PROMPT.md` "
                    f"has no AI section. An agent reading the master prompt cannot "
                    f"discover the AI surface. Add an `## AI Features` section listing "
                    f"the service functions + endpoints + hooks."
                ),
                "severity": "warning",
            })

    # ── Check 3: cache=True calls thread org_id ──
    service_content = ai_service.read_text()
    # Find every `chat_completion(...)` call block — naive but works for our
    # call style (multi-line with kwargs on separate lines).
    # Pattern: `chat_completion(` ... `)` matching balanced parens at top level.
    for match in re.finditer(r"chat_completion\s*\(", service_content):
        start = match.end()
        # Walk forward to find the matching close paren at depth 0.
        depth = 1
        i = start
        while i < len(service_content) and depth > 0:
            if service_content[i] == "(":
                depth += 1
            elif service_content[i] == ")":
                depth -= 1
            i += 1
        block = service_content[start : i - 1]
        # Only check if cache=True is in this call block.
        if not re.search(r"\bcache\s*=\s*True\b", block):
            continue
        if not re.search(r"\borg_id\s*=", block):
            line_num = service_content[:match.start()].count("\n") + 1
            issues.append({
                "product": name,
                "file": f"backend/app/services/ai_service.py:{line_num}",
                "issue": (
                    f"{name} has a `chat_completion(..., cache=True, ...)` call without "
                    f"`org_id=`. The cache key includes org_id (since 2026-04-24 G5 fix); "
                    f"omitting it puts the call into the platform-wide cache pool. Pass "
                    f"`org_id=org_id` to isolate per-org cache entries."
                ),
                "severity": "high",
            })

    return issues


def _find_all_project_md(repo_root: Path) -> list[Path]:
    """Find every PROJECT.md across the repo's three valid locations.

    Per `KB § PATTERNS/project-execution.md §1` (the three-location project
    rule): root `projects/<slug>/`, `products/<product>/projects/<slug>/`,
    and `core/projects/<slug>/`. Returns sorted paths so iteration is
    deterministic across runs.
    """
    candidates: list[Path] = []
    root_projects = repo_root / "projects"
    if root_projects.exists():
        for d in sorted(root_projects.iterdir()):
            if d.is_dir() and (d / "PROJECT.md").exists():
                candidates.append(d / "PROJECT.md")
    products_dir = repo_root / "products"
    if products_dir.exists():
        for product_dir in sorted(products_dir.iterdir()):
            projects_dir = product_dir / "projects"
            if not projects_dir.exists():
                continue
            for d in sorted(projects_dir.iterdir()):
                if d.is_dir() and (d / "PROJECT.md").exists():
                    candidates.append(d / "PROJECT.md")
    core_projects = repo_root / "core" / "projects"
    if core_projects.exists():
        for d in sorted(core_projects.iterdir()):
            if d.is_dir() and (d / "PROJECT.md").exists():
                candidates.append(d / "PROJECT.md")
    return candidates


# `### Phase N` (numeric only — skips illustrative `### Phase X` placeholders
# in §5 architecture sections that aren't actual phases).
_PHASE_HEADER_RE = re.compile(r'^### Phase\s+(\d+)\b(.*)$', re.MULTILINE)
_SUBTASK_RE = re.compile(r'^[ \t]*-\s*\[([ x])\]\s', re.MULTILINE)
_IMPROVEMENTS_BLOCK_RE = re.compile(r'\*\*Improvements\b[^*]*\*\*', re.MULTILINE)
_NON_SHIPPED_ICONS = {"⏳", "❌", "🅿️"}
_SHIPPED_ICON = "✅"


def _icon_in_line(line: str) -> str | None:
    """Return the first phase-status icon found in a line, or None."""
    for icon in (_SHIPPED_ICON, "⏳", "❌", "🅿️"):
        if icon in line:
            return icon
    return None


def _split_phase_blocks(content: str) -> list[tuple[int, str, int]]:
    """Split a PROJECT.md into phase blocks.

    Returns list of `(phase_number, block_text, header_line_number)`. The
    block_text spans from one `### Phase N` header up to the next `###`
    header, `## ` section boundary, or end of file.
    """
    headers: list[tuple[int, int, int]] = []  # (number, start_offset, line_number)
    for m in _PHASE_HEADER_RE.finditer(content):
        try:
            phase_num = int(m.group(1))
        except (ValueError, TypeError) as exc:
            logger.warning("compliance: cannot parse phase number from %r (%s), skipping", m.group(0), exc)
            continue
        line_num = content.count("\n", 0, m.start()) + 1
        headers.append((phase_num, m.start(), line_num))
    blocks: list[tuple[int, str, int]] = []
    for i, (num, start, ln) in enumerate(headers):
        # Block ends at next phase header OR next ## section boundary (whichever
        # comes first). Anchor the section search AFTER this header's own line —
        # otherwise the `^## ` pattern matches the `### Phase` header itself.
        next_start = len(content)
        if i + 1 < len(headers):
            next_start = headers[i + 1][1]
        newline_after_header = content.find("\n", start)
        body_start = newline_after_header + 1 if newline_after_header >= 0 else len(content)
        section_match = re.search(
            r'^##\s', content[body_start:next_start], re.MULTILINE,
        )
        if section_match:
            next_start = min(next_start, body_start + section_match.start())
        blocks.append((num, content[start:next_start], ln))
    return blocks


def _extract_changelog_section(content: str) -> str:
    """Return the §11 Change log section text (table rows + prose), or ''."""
    m = re.search(r'^##\s*11\.\s*Change\s*log\b', content, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    return content[m.start():]


_CHANGELOG_PHASE_SHIPPED_RE = re.compile(
    r'Phase\s+(\d+)\s*(?:[—:✅\-]|.{0,40}?(?:shipped|closed|complete))',
    re.IGNORECASE,
)

# Inline code spans — single-line backtick-delimited content. Markdown
# convention: backticks mark "this is a code/identifier/reference, not
# prose." We strip them before phase-shipped detection so a §11 entry
# describing ANOTHER file's state (e.g. `Phase 0 ✅` of erp-imobiliario-
# wiring while authoring repo-state-consolidation-wave-2's §11) does NOT
# false-positive as a self-claim. Single-source convention: backtick a
# phrase = "reference, not self-claim." No new syntax; markdown already
# has it.
_INLINE_CODE_SPAN_RE = re.compile(r'`[^`\n]*`')


def _strip_code_spans(text: str) -> str:
    """Strip inline code spans (backtick-delimited, single-line) from markdown.

    Used to normalize §11 changelog text before phase-shipped detection so
    cross-file references (like ``Phase 0 ✅`` describing another project's
    state) don't trigger self-claim heuristics. Preserves all other text;
    code spans become single spaces (preserves word boundaries for downstream
    regexes).
    """
    return _INLINE_CODE_SPAN_RE.sub(" ", text)


def _shipped_phases_in_changelog(changelog: str) -> set[int]:
    """Find phase numbers THIS file's §11 changelog claims as shipped/closed.

    Heuristic: look for "Phase N ✅", "Phase N shipped", "Phase N closed",
    "Phase N complete". Only counts phases that appear with explicit
    shipped/closed markers — bare "Phase N" mentions in passing don't
    qualify (e.g. "Phase 0 audit found...").

    Cross-file references should be wrapped in backticks per the markdown
    convention; backticked spans are stripped before matching so that a §11
    entry describing another project's `Phase 0 ✅` does not false-positive
    as a self-claim. See `_strip_code_spans`.
    """
    shipped: set[int] = set()
    # Strip inline code spans first — backticked references describe other
    # files' state, not this file's claims.
    sanitized = _strip_code_spans(changelog)
    # Look for "Phase N ✅" anywhere in changelog
    for m in re.finditer(r'Phase\s+(\d+)\s*✅', sanitized):
        try:
            shipped.add(int(m.group(1)))
        except ValueError as exc:
            logger.warning("compliance: cannot parse phase number from %r (%s)", m.group(0), exc)
            continue
    # Look for "Phase N shipped" / "Phase N closed" with small lookahead
    for m in re.finditer(
        r'Phase\s+(\d+)\b[^.]{0,80}?(?:shipped|closed|complete)',
        sanitized,
        re.IGNORECASE,
    ):
        try:
            shipped.add(int(m.group(1)))
        except ValueError as exc:
            logger.warning("compliance: cannot parse phase number from %r (%s)", m.group(0), exc)
            continue
    return shipped


def check_phase_state_consistency(repo_root: Path | None = None) -> list[dict]:
    """Validate §6 ↔ §11 consistency in every PROJECT.md.

    The slip pattern this catches: an agent writes a §11 Change-Log entry
    saying "Phase N ✅ shipped" but leaves §6's checkboxes / phase header
    in their pre-close state. The user reads §6 as a real-time dashboard;
    the mismatch is functionally a lie about progress.

    Detection rules (per `KB § PATTERNS/project-execution.md § 2 Self-check
    before claiming a phase is done`):

    1. Phase header lacks ✅ icon BUT §11 says "Phase N shipped" → drift.
    2. Phase header has ✅ icon BUT some sub-tasks are `- [ ]` → drift.
    3. Phase header has ✅ icon BUT no `**Improvements:**` block → drift.
    4. §11 says "Phase N shipped" BUT sub-tasks are `- [ ]` → drift.

    Phases marked `⏳`, `❌`, or `🅿️` (partial / blocked / parked) are
    legitimate non-shipped states; not flagged.

    Per `KB § 06-AGENTS.md` (observation-only keeper rule): the detector
    REPORTS, never modifies. The fix is the agent's discipline.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for project_md in _find_all_project_md(root):
        content = project_md.read_text(encoding="utf-8")
        try:
            relative = project_md.relative_to(root)
        except ValueError:
            logger.warning("compliance: PROJECT.md outside repo root, using absolute: %s", project_md)
            relative = project_md
        product_label = "<projects>"
        # Resolve product attribution for nicer issue grouping.
        rel_str = str(relative)
        if rel_str.startswith("products/"):
            product_label = rel_str.split("/", 2)[1]
        elif rel_str.startswith("core/"):
            product_label = "core"

        phase_blocks = _split_phase_blocks(content)
        changelog = _extract_changelog_section(content)
        shipped_in_changelog = _shipped_phases_in_changelog(changelog)

        for phase_num, block, header_ln in phase_blocks:
            # First line is the header; the rest is the body.
            header_line = block.split("\n", 1)[0]
            body = block[len(header_line):]
            icon = _icon_in_line(header_line)

            # Skip non-shipped legitimate states.
            if icon in _NON_SHIPPED_ICONS:
                continue

            subtasks = _SUBTASK_RE.findall(body)
            unticked_count = sum(1 for s in subtasks if s == " ")
            has_improvements = bool(_IMPROVEMENTS_BLOCK_RE.search(body))

            is_shipped_per_changelog = phase_num in shipped_in_changelog
            header_has_check = icon == _SHIPPED_ICON

            # Rule 1: header missing ✅ but §11 says shipped.
            if is_shipped_per_changelog and not header_has_check:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) lacks the "
                        f"`✅` icon in §6 header, but §11 Change Log says it shipped. "
                        f"Either flip the header to `✅` (if truly shipped) or remove the "
                        f"shipped claim from §11 (if not). Per `KB § PATTERNS/project-"
                        f"execution.md § 2 Self-check before claiming a phase is done`."
                    ),
                    "severity": "high",
                })

            # Rule 2: header has ✅ but some sub-tasks unticked.
            if header_has_check and unticked_count > 0:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) header carries "
                        f"`✅` but {unticked_count} sub-task(s) remain `- [ ]`. Tick the "
                        f"checkboxes or revert the header to `⏳` until done."
                    ),
                    "severity": "high",
                })

            # Rule 3: header has ✅ but no Improvements block.
            if header_has_check and not has_improvements:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) header carries "
                        f"`✅` but lacks an `**Improvements:**` block. Add the block (or "
                        f"`**Improvements:** none identified.`) before flipping `✅` per the "
                        f"5-point self-check."
                    ),
                    "severity": "high",
                })

            # Rule 4: §11 says shipped but sub-tasks are unticked (covers cases
            # where header was unflipped AND tasks unticked AND §11 already claims shipped —
            # this is the dashboard-lying case, distinct from rule 1).
            if is_shipped_per_changelog and not header_has_check and unticked_count > 0:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) is claimed shipped "
                        f"in §11 but has {unticked_count} unticked sub-task(s) AND no `✅` icon "
                        f"on the header. Live state lags the narrative — fix §6 before §11 lands."
                    ),
                    "severity": "high",
                })

    return issues


# ---------------------------------------------------------------------------
# `check_no_self_monkeypatch` — enforces the no-self-monkeypatching rule
# (memory `feedback_no_monkeypatching_in_tests.md`, CLAUDE.md). Caught
# 2× this session writing `monkeypatch.setattr(ai_pipeline, "require",
# _noop)`. Documentation alone wasn't sufficient; deterministic
# enforcement closes the loop.
# ---------------------------------------------------------------------------

# Module prefixes that are "ours" (production code in this repo). Patching
# any of these in tests neuters our own logic — UNLESS the target attribute
# is a known boundary accessor (see _BOUNDARY_ACCESSOR_NAMES).
_OUR_MODULE_PREFIXES: tuple[str, ...] = (
    "app.",
    "noctusai_lib.",
    "noctusai_seed.",
)
# Boundary-accessor attribute names — patching these returns external
# resources (Supabase client, LLM SDK, network) that legitimately need
# mocking in tests. Allowed even when the module prefix is "ours".
_BOUNDARY_ACCESSOR_NAMES: set[str] = {
    # Supabase / DB client boundary
    "get_client",
    "get_admin_client",
    "get_core_client",
    "get_db_client",
    "get_supabase",
    "get_supabase_client",
    "get_session",
    "get_user",
    "get_current_user",
    "make_supabase_client",
    "create_client",
    # LLM call boundary
    "chat_completion",
    "chat_completion_stream",
    "stream_chat_completion",
    "transcribe_audio",
    "generate_embedding",
    # Audit-log boundary — `log_action` writes to the `audit_log` table.
    # Patching it in tests is the standard "skip side-effect" pattern
    # used everywhere; the alternative would require seeding RLS-coupled
    # audit-log rows for every test. Triaged 2026-04-28 from 27 hits.
    "log_action",
    # Credential/secrets boundary — `resolve_credential` /
    # `check_required_credentials` read from the secrets store; private
    # `_get_*_token` helpers wrap external auth fetches. Triaged 2026-04-28
    # from 22+6+5 hits.
    "resolve_credential",
    "check_required_credentials",
    "_get_infosimples_token",
    # External SDK getters (return Resend/etc clients).
    "_get_resend",
    "_get_resend_config",
    "_resolve_resend_config",
    # Env-config readers — return cached env state, no business logic.
    "get_whatsapp_config_from_env",
    "check_openai_configured",
    "_openai_configured",
    "YFINANCE_AVAILABLE",
    # JWT decoder boundary — wraps cryptographic verification of an
    # external token; patching skips a real signing key in tests.
    "__from_token__",
}
# Boundary-accessor patterns by suffix (for `_get_<x>_token`,
# `_get_<x>_client`, `_get_<x>_config`-style getters that wrap external
# resource access). Caught at run-time by `_is_boundary_accessor_target`.
_BOUNDARY_ACCESSOR_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^_get_[a-z][a-z0-9_]*_(?:token|client|config|key|secret|sdk)$"),
    re.compile(r"^get_[a-z][a-z0-9_]*_(?:client|config|sdk)$"),
    # `_lib_*` — convention for in-product wrappers around `noctusai_lib.*`
    # external integrations (e.g. `_lib_generate_embedding` proxies
    # `noctusai_lib.integrations.llm.generate_embedding`). Patching these mocks the
    # boundary, not our own logic.
    re.compile(r"^_lib_[a-z][a-z0-9_]*$"),
    # `send_*_email` — Resend / SMTP email boundary helpers. Mocking the
    # outbound email is the standard test pattern; the alternative is a
    # network call to a real provider.
    re.compile(r"^send_[a-z][a-z0-9_]*_email$"),
)
# External library names — when an external symbol is re-imported through
# our module (e.g. `app.routers.X.httpx.AsyncClient`), the test is
# legitimately patching the EXTERNAL lib's behavior at the import site.
# Detected by checking if any segment of the dotted path matches.
_EXTERNAL_LIB_NAMES: set[str] = {
    "httpx", "requests", "urllib", "urllib3", "openai", "anthropic",
    "google", "supabase", "redis", "stripe", "resend", "boto3",
    "smtplib", "sendgrid", "twilio", "celery", "kombu", "asyncpg",
    "psycopg2", "psycopg", "sqlalchemy", "pymongo", "elasticsearch",
    "fakeredis", "moto",
}
# Allowlist: bypass via inline comment `# self-patch-ok: <reason>` on the
# patching line itself. For genuinely-rare legitimate cases that don't
# fit the boundary-accessor pattern.
_SELF_PATCH_OK_COMMENT_RE = re.compile(r"#\s*self-patch-ok\b", re.IGNORECASE)

# Severity ratchet: products that have reached 0 self-monkeypatches get the
# detector at severity `high` so new violations block CI; the rest stay at
# `warning` while their historical debt drains. Per `KB § PATTERNS/testing.md
# § Severity ratchet`. When this set covers every product, the per-product
# carve-out is dropped and the detector goes `high` repo-wide.
_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS: frozenset[str] = frozenset({
    "therapy-platform",  # ratcheted 2026-05-01 (closed `therapy-tests-no-self-patch`)
})


def _is_boundary_accessor_target(full_target: str) -> bool:
    """True if the patched target's last component is a known boundary
    accessor (e.g. `noctusai_seed.database.DatabaseModule.get_client`).
    """
    if not full_target:
        return False
    last = full_target.rstrip(".").rsplit(".", 1)[-1]
    if last in _BOUNDARY_ACCESSOR_NAMES:
        return True
    return any(rx.match(last) for rx in _BOUNDARY_ACCESSOR_REGEXES)


def _has_external_lib_segment(full_target: str) -> bool:
    """True if any dotted segment is a known external lib name. Handles
    the `app.routers.X.httpx.AsyncClient` case (httpx re-imported via
    our module — the test is patching httpx's behavior at the import site,
    which is the standard mock pattern for external network/SDK clients).
    """
    if not full_target:
        return False
    segments = full_target.rstrip(".").split(".")
    return any(seg in _EXTERNAL_LIB_NAMES for seg in segments)


def _classify_patch_target(target: str) -> str:
    """Return 'ours' / 'boundary' / 'external' / 'external-via-ours' / 'unknown'."""
    if not any(target.startswith(p) for p in _OUR_MODULE_PREFIXES):
        return "external"
    if _is_boundary_accessor_target(target):
        return "boundary"
    if _has_external_lib_segment(target):
        return "external-via-ours"
    return "ours"


def _walk_test_files(root: Path):
    """Yield all `tests/**/*.py` files across products + seed-lib + mcp.

    Excludes vendored dependencies (`node_modules/`, `.venv/`, `venv/`,
    `dist/`) — those contain test code that's not ours and would
    false-positive every check.
    """
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache",
    }
    for base in (
        root / "products",
        root / "seed" / "lib" / "backend",
        root / "seed" / "framework" / "backend",
        root / "mcp",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            # Only test files.
            parts = path.parts
            if "tests" not in parts and "test_" not in path.name:
                continue
            if any(part in excluded_parts for part in parts):
                continue
            yield path


def _build_import_map(tree: ast.Module) -> dict[str, str]:
    """Map local-bound names to their full import paths.

    Examples:
    - `from app.services import ai_pipeline` → {"ai_pipeline": "app.services.ai_pipeline"}
    - `from app.services.ai_pipeline import require` → {"require": "app.services.ai_pipeline.require"}
    - `import noctusai_lib.domain.ai.consent as consent` → {"consent": "noctusai_lib.domain.ai.consent"}
    - `from app import services` → {"services": "app.services"}

    Used by `check_no_self_monkeypatch` to resolve `monkeypatch.setattr(X, ...)`
    where X is a local name back to its dotted module path, so we can
    classify it against `_OUR_MODULE_PREFIXES`.
    """
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local_name = alias.asname or alias.name
                full_path = f"{module}.{alias.name}" if module else alias.name
                mapping[local_name] = full_path
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                mapping[local_name] = alias.asname or alias.name
    return mapping


def _resolve_target_via_imports(target: str, import_map: dict[str, str]) -> str:
    """Resolve a `Name.attr.attr` target against the file's import map.

    `target` is expected to be the dotted path returned by `_extract_patch_target`
    (already includes the attr name when known). The first segment is the
    locally-bound name; if it's in `import_map`, prepend the resolved path.
    """
    if not target:
        return target
    segments = target.split(".")
    head = segments[0]
    if head in import_map:
        # Replace the local name with its resolved full path.
        resolved_head = import_map[head]
        return ".".join([resolved_head] + segments[1:]) if len(segments) > 1 else resolved_head
    return target


def check_no_self_monkeypatch(repo_root: Path | None = None) -> list[dict]:
    """Detect `monkeypatch.setattr(<our_module>, ...)` and
    `unittest.mock.patch.object(<our_module>, ...)` in test files —
    patterns that neuter our own logic instead of testing it.

    Per memory `feedback_no_monkeypatching_in_tests.md` + CLAUDE.md "No
    workarounds — and no monkey-patching, in production OR tests".

    Resolves local-bound names against the file's import map so that
    `from app.services import ai_pipeline` + `monkeypatch.setattr(
    ai_pipeline, "require", ...)` correctly resolves to
    `app.services.ai_pipeline.require` for classification.

    Allowlist via inline comment `# self-patch-ok: <reason>` on the
    patching line. For genuinely-rare legitimate cases (rare enough that
    they should be documented at the call site).
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_test_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("compliance: cannot read test file %s (%s), skipping", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.warning("compliance: cannot parse test file %s (%s), skipping", path, exc)
            continue
        import_map = _build_import_map(tree)
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            logger.warning("compliance: test file outside repo root, using absolute: %s", path)
            relative = str(path)
        product_label = "<seed-lib>" if "/seed/" in relative else (
            relative.split("/", 2)[1] if relative.startswith("products/") else "<mcp>"
        )

        for node in ast.walk(tree):
            raw_target = _extract_patch_target(node)
            if raw_target is None:
                continue
            target_str = _resolve_target_via_imports(raw_target, import_map)
            classification = _classify_patch_target(target_str)
            if classification != "ours":
                continue
            line_no = getattr(node, "lineno", 0) or 0
            line_text = (
                content.splitlines()[line_no - 1] if 0 < line_no <= len(content.splitlines()) else ""
            )
            if _SELF_PATCH_OK_COMMENT_RE.search(line_text):
                continue
            severity = (
                "high"
                if product_label in _NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS
                else "warning"
            )
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` patches our own symbol "
                    f"`{target_str}`. Per CLAUDE.md \"No workarounds — and no "
                    f"monkey-patching, in production OR tests\": neutering our "
                    f"own logic in tests doesn't test it. Seed real data + use "
                    f"DI; patch only external boundaries (LLM SDKs, network). "
                    f"If genuinely needed, add `# self-patch-ok: <reason>` to "
                    f"the line."
                ),
                # Severity ratchets to `high` once a product reaches 0; until
                # then, `warning` so historical debt doesn't tank score. See
                # `_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS` above + `KB §
                # PATTERNS/testing.md § Severity ratchet`.
                "severity": severity,
            })
    return issues


def _extract_patch_target(node: ast.AST) -> str | None:
    """If `node` is a self-patching call, return the FULL dotted-path target
    (module.path + attribute name). Else None.

    Examples returned:
    - `monkeypatch.setattr(ai_pipeline, "require", _noop)` → `"ai_pipeline.require"`
    - `patch.object(DatabaseModule, "get_client", ...)` → `"DatabaseModule.get_client"`
    - `patch("noctusai_seed.database.DatabaseModule.get_client", ...)` →
      `"noctusai_seed.database.DatabaseModule.get_client"`
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    target_arg: ast.expr | None = None
    attr_name: str | None = None

    # Pattern 1: monkeypatch.setattr(<target>, "attr", ...)
    if isinstance(func, ast.Attribute) and func.attr == "setattr":
        if isinstance(func.value, ast.Name) and func.value.id == "monkeypatch":
            if len(node.args) >= 1:
                target_arg = node.args[0]
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                v = node.args[1].value
                if isinstance(v, str):
                    attr_name = v
    # Pattern 2: mock.patch.object(<target>, "attr", ...) / patch.object(...)
    if isinstance(func, ast.Attribute) and func.attr == "object":
        is_patch_object = False
        if isinstance(func.value, ast.Name) and func.value.id == "patch":
            is_patch_object = True
        elif (
            isinstance(func.value, ast.Attribute)
            and func.value.attr == "patch"
        ):
            is_patch_object = True
        if is_patch_object:
            if len(node.args) >= 1:
                target_arg = node.args[0]
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                v = node.args[1].value
                if isinstance(v, str):
                    attr_name = v
    # Pattern 3: mock.patch("<dotted.string>", ...) / patch("<dotted.string>", ...)
    if isinstance(func, ast.Attribute) and func.attr == "patch":
        if node.args and isinstance(node.args[0], ast.Constant):
            val = node.args[0].value
            if isinstance(val, str):
                return val
    if isinstance(func, ast.Name) and func.id == "patch":
        if node.args and isinstance(node.args[0], ast.Constant):
            val = node.args[0].value
            if isinstance(val, str):
                return val

    if target_arg is None:
        return None
    base = _flatten_attr(target_arg)
    if base is None:
        return None
    # `_flatten_attr` returns the dotted path with a trailing `.`; append
    # the attr name when known.
    if attr_name:
        return base + attr_name
    return base.rstrip(".")


def _flatten_attr(node: ast.expr) -> str | None:
    """Convert `a.b.c` AST to `'a.b.c'`. Returns None for non-attribute exprs."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts)) + "."
    return None


# ---------------------------------------------------------------------------
# `check_silent_errors` — enforces the no-silent-errors rule
# (memory `feedback_no_silent_errors.md`, CLAUDE.md). Catches `except: pass`,
# `except Exception: return None`, and similar patterns that swallow
# errors without surfacing them.
# ---------------------------------------------------------------------------

# NOTE — there is intentionally NO escape-hatch comment for this detector.
# The previous `# silent-ok: <reason>` allowlist was retired 2026-04-28
# per user directive: "i dont want any silent-ok sign accross the
# platform". Every except handler MUST log via `logger.<level>(...)`,
# raise, or surface the error through a return value. Even bootstrap-
# time code (e.g. `noctusai_seed._version`) uses `logger.debug(...)` —
# the root logger silently drops debug by default but the call is in
# the code, the detector recognizes it, and operators can flip
# `NOCTUSAI_DEBUG=1` to see what fired during a fresh boot.


def _walk_python_files(root: Path):
    """Yield all `.py` files in product backends + seed-lib + framework + mcp.

    Excludes tests (test code legitimately uses `try/except` for assertions
    on the error paths) + vendored deps (`node_modules/`, `.venv/`, `venv/`,
    `dist/`, `__pycache__/`) + migration files (raw SQL hand-written by
    domain experts; silent-error semantics differ).
    """
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache", "tests", "migrations",
    }
    bases = [
        root / "products",
        root / "seed" / "lib" / "backend",
        root / "seed" / "framework" / "backend",
        root / "mcp" / "noctusai",
    ]
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            parts = path.parts
            if any(part in excluded_parts for part in parts):
                continue
            yield path


def _is_silent_except(handler: ast.ExceptHandler) -> tuple[bool, str]:
    """Return (is_silent, reason). A handler is "silent" if its body:
       - is just `pass`
       - is just `return None` / `return`
       - has no `raise`, no `logger.<level>`, no `log.<level>`, no `print` for the error.
    """
    body = handler.body
    if not body:
        return True, "empty body"
    # All-pass / all-return cases:
    if all(isinstance(stmt, ast.Pass) for stmt in body):
        return True, "body is just `pass`"
    if all(
        isinstance(stmt, ast.Return)
        and (stmt.value is None or (
            isinstance(stmt.value, ast.Constant) and stmt.value.value is None
        ))
        for stmt in body
    ):
        return True, "body is just `return` / `return None`"
    # Look for any signal of error-handling: raise, logger call, print.
    # Bare-name allowlist is deliberately TIGHT — only `print(...)` qualifies
    # because anything else (`warn(exc)`, `warning(exc)`) is too easy to
    # accidentally satisfy with a domain function of the same name. Logger
    # calls are recognised via the attribute-suffix pattern (`.warning`,
    # `.warn` legacy, etc.), which requires a method-call shape.
    has_signal = False
    for stmt in ast.walk(handler):
        if isinstance(stmt, ast.Raise):
            has_signal = True
            break
        if isinstance(stmt, ast.Call):
            func_name = _call_name(stmt.func)
            if func_name == "print":
                has_signal = True
                break
            if any(
                func_name.endswith(suffix) for suffix in (
                    ".warning", ".warn",  # `.warn` is the deprecated stdlib alias; some callers still use it
                    ".error", ".exception", ".critical",
                    ".info", ".debug", ".log",
                )
            ):
                has_signal = True
                break
    if not has_signal:
        return True, "no `raise` / `log` / `print` in handler body"
    return False, ""


def _call_name(func_node: ast.expr) -> str:
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        return f".{func_node.attr}"
    return ""


def check_silent_errors(repo_root: Path | None = None) -> list[dict]:
    """Detect silent-error patterns in production Python code.

    Flags `try / except:` handlers whose body neither raises, logs, nor
    surfaces the error in any way. **No escape hatch** — every handler
    must log via `logger.<level>(...)`, `raise`, or surface through a
    return value. Even bootstrap-time code uses `logger.debug(...)` so
    the call is statically present (root logger drops it by default;
    `NOCTUSAI_DEBUG=1` reveals it).

    Per memory `feedback_no_silent_errors.md` + CLAUDE.md "No silent
    errors — always explicit fix opportunities".
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_python_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.warning("compliance: cannot parse %s (%s), skipping", path, exc)
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            logger.warning("compliance: file outside repo root, using absolute: %s", path)
            relative = str(path)
        product_label = "<seed>" if relative.startswith("seed/") else (
            relative.split("/", 2)[1] if relative.startswith("products/") else "<mcp>"
        )
        lines = content.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            silent, reason = _is_silent_except(node)
            if not silent:
                continue
            line_no = node.lineno
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` swallows errors silently ({reason}). "
                    f"Per CLAUDE.md \"No silent errors\": every failure mode "
                    f"surfaces loudly. Add `logger.warning(...)` / `logger.debug(...)`, "
                    f"`raise`, or surface via a return value. Bootstrap-time code "
                    f"uses `logger.debug(...)` (silent by default; `NOCTUSAI_DEBUG=1` "
                    f"reveals it). There is no `# silent-ok` escape hatch."
                ),
                # `warning` (not `high`) so legitimate-but-historically-flagged
                # patterns don't tank the per-product score; the user can
                # tighten over time as violations are addressed.
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_clean_folder_violations` — enforces the clean-folder rule
# (CLAUDE.md). ✅-closed projects must have their folders deleted.
# ---------------------------------------------------------------------------


def check_clean_folder_violations(repo_root: Path | None = None) -> list[dict]:
    """Detect closed projects (✅ status) whose folders still exist.

    Per CLAUDE.md "Clean folder — every artifact has a home" + the
    apply-inline-then-delete rule (closed projects get deleted at close,
    audit history lives in git). Surfaced 8 violations during the
    2026-04-28 closed-folder cleanup; this check makes future drift
    visible at `--validate` time.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for project_md in _find_all_project_md(root):
        try:
            content = project_md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("compliance: cannot read PROJECT.md %s (%s), skipping", project_md, exc)
            continue
        # Look at the first `- **Status:**` line.
        m = re.search(r"^- \*\*Status:\*\*\s*(.*)$", content, re.MULTILINE)
        if not m:
            continue
        status_line = m.group(1)
        # The status icon is whatever comes FIRST on the line. A trailing
        # `Phase 0 ✅` inside narrative ("READY TO RESUME ... Phase 0 ✅
        # executed") is not the project's own status — that's drift inside
        # the prose. Only flag when ✅ is the leading icon.
        leading = re.match(r"\s*([📋⏳❌🅿️📝✅⚠️🚧🔄])", status_line)
        if not leading or leading.group(1) != "✅":
            continue
        # Mixed-status close (✅ leading but ⏳/❌/🅿️ also present) signals
        # in-flight close — don't flag.
        if any(icon in status_line for icon in ("⏳", "❌", "🅿️")):
            continue
        # Closed + folder still exists → flag.
        try:
            relative = str(project_md.relative_to(root))
        except ValueError:
            logger.warning("compliance: PROJECT.md outside repo root, using absolute: %s", project_md)
            relative = str(project_md)
        product_label = "<projects>"
        if relative.startswith("products/"):
            product_label = relative.split("/", 2)[1]
        elif relative.startswith("core/"):
            product_label = "core"
        issues.append({
            "product": product_label,
            "file": relative,
            "issue": (
                f"`{relative}` is closed (✅) but its folder still exists. "
                f"Per the clean-folder rule (CLAUDE.md): closed projects "
                f"get deleted at close — audit history lives in git + the "
                f"shipped code + KB cross-references. Run `rm -rf "
                f"{project_md.parent.relative_to(root) if project_md.parent.is_relative_to(root) else project_md.parent}/` "
                f"after confirming references are updated."
            ),
            "severity": "warning",
        })
    return issues


# ---------------------------------------------------------------------------
# `check_test_status_assertion` — every pytest test method that asserts on
# response BODY (`.text`, `.json()`, `.content`) must also assert on response
# STATUS CODE (`.status_code`) in the same method. Defends against the
# YouTube Crawler Phase 1 "false-green" slip where a substring-on-`.text`
# assertion matched the wrong of two error entries (broken `Depends(get_org_id)`
# chain) and the test went green even though the endpoint was unusable.
# Project: keeper-test-status-assertion. Per KB § PATTERNS/testing.md
# § Status-code-assertion rule.
# ---------------------------------------------------------------------------


# Attribute names that, when accessed on a response variable, indicate the
# test is asserting on the response body. Match by attribute name, not
# variable name (the test author's variable name doesn't matter).
_RESPONSE_BODY_ATTRS: frozenset[str] = frozenset({"text", "content"})
# Method names that, when called on a response variable, indicate body access.
_RESPONSE_BODY_METHODS: frozenset[str] = frozenset({"json"})
# The status-code attribute. Any comparison op against this (==, in, !=, <, >)
# satisfies the rule.
_STATUS_CODE_ATTR: str = "status_code"


# HTTP method names — any of these called as `<var>.method(...)` (or
# `await <var>.method(...)`) on the right-hand side of an assignment binds
# `<var name on left>` to a "response variable" for the rest of the method.
# Used to gate body-attr matches so non-response objects (`digest.text`,
# `result.content`) don't false-positive.
_HTTP_METHOD_NAMES: frozenset[str] = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options",
    "request",  # generic httpx/TestClient `client.request("GET", ...)`
})


def _collect_response_vars(fn: ast.AST) -> set[str]:
    """Walk a test method body and collect names that were assigned from
    an HTTP-client call.

    Examples that bind:
      - ``resp = client.get("/x")``
      - ``resp = await client.post("/x", json={})``
      - ``response = self.client.delete("/x/1")``
      - ``r = test_client.request("GET", "/x")``

    Examples that DO NOT bind (intentional false-negative bias):
      - ``digest = audit_digest_service.build_digest(...)`` — non-HTTP call
      - ``result = handler(...)`` — non-HTTP call
      - ``resp = some_helper(client)`` — opaque helper return

    Conservative on purpose: a body-attr match against a name NOT in this
    set is silently skipped, dropping false positives like `digest.text` /
    `result.content`. Cost: a test that uses a helper-returned response
    won't be flagged. PROJECT.md § 3 design principle 3 accepts that miss.
    """
    response_vars: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        # Only single-target assignments — `resp = client.get(...)`.
        # Tuple-unpack / chained assignments left as future work.
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        # Unwrap `await client.get(...)`.
        value = node.value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call):
            continue
        # Inspect the call's func — must be an Attribute access whose
        # method name is one of the HTTP verbs.
        func = value.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in _HTTP_METHOD_NAMES:
            continue
        response_vars.add(target_name)
    return response_vars


def _expr_root_name(node: ast.AST) -> str | None:
    """For an attribute / subscript / call chain, walk down to the root
    Name node and return its identifier.

    ``resp.text.lower()`` → ``"resp"``
    ``resp.json()["x"]`` → ``"resp"``
    ``self.client.get(...).text`` → ``None`` (root is `self`, but the
    walker only treats top-level local Names as response candidates).
    ``some_func().text`` → ``None``
    """
    cur = node
    while True:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        else:
            return None


def _is_body_text_assertion(node: ast.Assert, response_vars: set[str]) -> bool:
    """True iff this assert reads response BODY on a known response var.

    Catches:
      - ``assert "x" in resp.text``
      - ``assert "x" in resp.text.lower()``
      - ``assert "x" in resp.json()["error"]``
      - ``assert resp.text == "..."``
      - ``assert "..." == resp.json()["msg"]``
      - ``assert resp.content``  (truthy check on body)

    Gated by `response_vars` (names assigned from `client.<verb>(...)` in
    the same method): only flags when the body-attr access's root Name is
    in the response set. Drops false positives like `digest.text` /
    `result.content` on non-HTTP objects.

    Conservative: when the root expression isn't a simple local Name (e.g.
    `self.client.get(...).text` — fluent style), we silently skip.
    """
    test = node.test
    for sub in ast.walk(test):
        if isinstance(sub, ast.Attribute) and sub.attr in _RESPONSE_BODY_ATTRS:
            root = _expr_root_name(sub.value)
            if root is not None and root in response_vars:
                return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr in _RESPONSE_BODY_METHODS:
                root = _expr_root_name(sub.func.value)
                if root is not None and root in response_vars:
                    return True
    return False


def _is_status_code_assertion(node: ast.Assert) -> bool:
    """True iff this assert reads ``.status_code`` on something.

    Catches every comparison shape:
      - ``assert resp.status_code == 200``
      - ``assert resp.status_code in (401, 403)``
      - ``assert resp.status_code != 500``
      - ``assert 400 <= resp.status_code < 500``
      - ``assert resp.status_code``  (truthy — rare but counted)

    Note: status_code attr name is specific enough to HTTP responses that
    we don't gate it on response_vars (a non-response object asserting
    `.status_code` is exotic and we'd rather count it than miss).
    """
    for sub in ast.walk(node.test):
        if isinstance(sub, ast.Attribute) and sub.attr == _STATUS_CODE_ATTR:
            return True
    return False


def _iter_test_methods(tree: ast.Module):
    """Yield every ``def test_*`` function — module-level or class-nested.

    Only synchronous + async function defs whose name starts with ``test_``
    are returned. Helper functions (any other name) are not scanned per
    PROJECT.md § 3 design principle 1 (method-scope detection).
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield node


def _walk_test_files_in_dir(tests_dir: Path):
    """Yield every ``test_*.py`` / ``*_test.py`` file under tests_dir.

    Excludes vendored / cache / build directories (same exclusion list as
    `_walk_test_files`). conftest.py is included — it contains fixtures
    that may inadvertently mask response semantics, but no `test_*` methods
    so the detector skips them naturally.
    """
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache",
    }
    if not tests_dir.exists():
        return
    for path in tests_dir.rglob("*.py"):
        if any(part in excluded_parts for part in path.parts):
            continue
        # Match pytest's default test-file discovery pattern.
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            yield path


def check_test_status_assertion(product_path: Path) -> list[dict]:
    """Flag pytest test methods that assert on response BODY without a
    sibling assertion on response STATUS CODE in the same method.

    The slip this defends against (YouTube Crawler Phase 1):

        def test_recipient_without_channel_rejected(self, client):
            resp = client.post("/api/settings/recipients", json={"name": "x"})
            assert "at least one of" in resp.text.lower()
            # ↑ went green because 422 contained TWO error entries; the
            #   substring matched the schema-validation entry but the
            #   endpoint was actually unusable due to a broken
            #   Depends(get_org_id) chain demanding ?user= / ?token=.

    The structural fix: any test asserting on body text/JSON/content also
    pins the status code in the same method. Without that pin, a 422 / 500
    / 401 / 403 false-green is structurally possible.

    Conservative: false negatives over false positives. We do NOT walk into
    helper functions (test author's `_assert_ok(resp)` may handle status
    code there — we trust that and don't flag the test). We do NOT track
    response-variable identity — both assertions must merely exist in the
    same method body.

    Per KB § PATTERNS/testing.md § Status-code-assertion rule.
    """
    issues: list[dict] = []
    name = product_path.name
    tests_dir = product_path / "backend" / "tests"
    if not tests_dir.exists():
        return issues

    for py_file in _walk_test_files_in_dir(tests_dir):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_file, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_file, exc)
            continue

        try:
            rel = str(py_file.relative_to(product_path))
        except ValueError:
            rel = str(py_file)

        for fn in _iter_test_methods(tree):
            response_vars = _collect_response_vars(fn)
            if not response_vars:
                # No HTTP-client call assigned to a local name — skip.
                # Tests using helper-returned responses miss intentionally
                # (PROJECT.md § 3 design principle 3 — conservative).
                continue
            has_body = False
            has_status = False
            first_body_line = 0
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Assert):
                    if not has_body and _is_body_text_assertion(sub, response_vars):
                        has_body = True
                        first_body_line = sub.lineno
                    if not has_status and _is_status_code_assertion(sub):
                        has_status = True
                if has_body and has_status:
                    break
            if has_body and not has_status:
                issues.append({
                    "product": name,
                    "file": rel,
                    "method": fn.name,
                    "line": first_body_line,
                    "issue": (
                        f"{rel}:{first_body_line} `{fn.name}` asserts on "
                        f"response body (`.text` / `.json()` / `.content`) "
                        f"without a sibling `assert <resp>.status_code == "
                        f"...` in the same method. Body-only assertions can "
                        f"go green for the wrong reason — see KB § "
                        f"PATTERNS/testing.md § Status-code-assertion rule "
                        f"(YouTube Crawler Phase 1 false-green case study)."
                    ),
                    "severity": "warning",
                })
    return issues


# ---------------------------------------------------------------------------
# Production-correctness trio — surfaced by Engineer GG's therapy P4 audit
# (commit a56a39e, 2026-05-10). MockSupabase WARN+skip masked N=12 migration
# drift cases for 7+ days because tests passed silently against unknown tables.
# Two siblings — function search_path drift + admin-endpoint service_role
# bypass — are the same shape (real DB fails, tests pass). All three are
# AST-driven, observation-only, deterministic.
#
# Per KB § PATTERNS/testing.md § Production-correctness keeper detectors.
# ---------------------------------------------------------------------------


# Tables that MAY appear as `.table("X")` callsites but live OUTSIDE the
# product's own migrations — `auth.users` is Supabase-managed, `products` is
# part of core's bootstrap. Allowlist suppresses false positives at the
# unknown-table detector without weakening cross-product coverage.
_KNOWN_EXTERNAL_TABLES: set[str] = {
    "users",            # auth.users (Supabase auth)
    "products",         # core/bootstrap products registry
    "organizations",    # core/bootstrap org registry (multi-tenancy)
    "user_org_roles",   # core bootstrap RBAC pivot
}


# Files MAY hold a `.table(...)` call that is intentionally a runtime-built
# string concatenated from a variable. The detector ignores non-Constant
# arguments (it CAN'T resolve them statically); this comment is just to
# document the design choice — see `_extract_table_string_arg`.


def _extract_table_string_arg(call: ast.Call) -> str | None:
    """Return the literal string argument to a `.table("X")` call.

    Returns None when the call has no positional args or the first arg is
    not a `Constant[str]` (e.g. an f-string or a name reference — the
    detector silently skips those because it can't resolve them statically).
    """
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _walk_product_backend_python(product_path: Path):
    """Yield every `.py` under `product/backend/app/`, excluding tests + caches.

    Mirrors `_walk_python_files` exclusion set but scoped to one product's
    backend (the unknown-table + admin-bypass detectors are per-product).
    """
    backend_app = product_path / "backend" / "app"
    if not backend_app.exists():
        return
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache", "tests", "migrations",
    }
    for path in backend_app.rglob("*.py"):
        if any(part in excluded_parts for part in path.parts):
            continue
        yield path


# Pattern shared by the three production-correctness detectors. The migration
# files are raw SQL; we use regex with the `re.IGNORECASE | re.DOTALL` flags
# and document each regex's anchor strategy near its definition so future
# maintainers can verify the matched shape against real CREATE statements.

# Matches `CREATE TABLE [IF NOT EXISTS] [<schema>.]<name>` and captures the
# unqualified name. Anchored on the `(` opening the column list so we never
# false-match prose mentions of "create table foo" in a comment.
_CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*\.)?"   # optional schema
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*\(",
    re.IGNORECASE,
)


# Matches every `CREATE [OR REPLACE] FUNCTION [<schema>.]<name>` start. We
# don't try to capture the function BODY with one regex (Postgres function
# bodies can use any dollar-quoted delimiter `$tag$ ... $tag$` plus optional
# `SET` clauses outside the body). Instead the detector walks each match and
# finds the body terminator by locating the closing dollar quote — see
# `_function_block_text`.
_CREATE_FUNCTION_START_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"
    r"(?P<qualified>(?:[A-Za-z_][A-Za-z0-9_]*\.)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*))"
    r"\s*\(",
    re.IGNORECASE,
)


# Matches `CREATE POLICY "service_role_bypass" ... ON [<schema>.]<table>`
# (DOTALL so the policy clause may span lines between POLICY and ON). We
# match on the literal name `service_role_bypass` because that's the
# convention every product follows (single keeper-enforced shape — drift
# in the name itself is a separate concern and would be its own detector).
#
# Schema prefix accepts both the unquoted form (`therapy.clinics`) and the
# double-quoted form (`"personal-finance".recorrentes`) — dashed schemas
# MUST be double-quoted at DDL time per Postgres identifier rules. Before
# this teach (2026-05-11), only the unquoted prefix matched, causing the
# detector to mis-report PF / mailing / any dashed-schema product as still
# missing the policy even after it was applied. Surfaced by keeper-trio-pf
# (Engineer BBB, Wave 1) when migration 009 applied live + `pg_policies`
# confirmed the policy but the detector kept flagging the callsite.
# Table-name segment continues to be unquoted: every adopter's table name
# is a plain identifier (`recorrentes`, `clinics`, ...), never dashed.
_SERVICE_ROLE_BYPASS_POLICY_RE = re.compile(
    r'\bCREATE\s+POLICY\s+"?service_role_bypass"?\s+ON\s+'
    r'(?:(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\.)?'
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.DOTALL,
)


def _collect_known_tables(product_path: Path) -> set[str]:
    """Return unqualified table names declared by `CREATE TABLE` in any of
    the product's migrations. Includes both `IF NOT EXISTS` and bare forms.

    Returns the empty set when `backend/migrations/` is missing (the
    detectors short-circuit upstream in that case).
    """
    names: set[str] = set()
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return names
    for sql_file in migrations_dir.glob("*.sql"):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        for m in _CREATE_TABLE_RE.finditer(content):
            names.add(m.group("name").lower())
    return names


def _collect_service_role_bypass_tables(product_path: Path) -> set[str]:
    """Return unqualified table names that have a `service_role_bypass`
    policy in any of the product's migrations.
    """
    names: set[str] = set()
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return names
    for sql_file in migrations_dir.glob("*.sql"):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        for m in _SERVICE_ROLE_BYPASS_POLICY_RE.finditer(content):
            names.add(m.group("table").lower())
    return names


def _iter_table_callsites(tree: ast.AST):
    """Yield every `.table("X")` Call node within `tree`.

    Matches any attribute access named `table` regardless of receiver —
    `db.table(...)`, `admin_db.table(...)`, `get_admin_client().table(...)`,
    `self.client.table(...)`. Receiver discrimination happens at the caller
    (the admin-bypass detector uses receiver shape; the unknown-table
    detector flags any `.table(...)`).
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "table"
        ):
            yield node


def _has_schema_in_chain(call: ast.Call) -> bool:
    """True if `call` is `<receiver>.schema(...).…table(...)` — i.e. the
    `.table(...)` invocation is preceded by a `.schema(...)` call anywhere
    in the receiver chain.

    Walks backward from the `.table(...)` call's receiver looking for an
    `ast.Call` whose `.func.attr == "schema"`. Stops at the first non-Call
    receiver (`Name`/`Attribute`/`Subscript`).

    Why this matters — cross-schema lookups (canonical site:
    `products/core/backend/app/routers/admin_llm_usage.py:92`,
    `db.schema(schema).table("llm_usage")` iterating `_PRODUCT_SCHEMAS`)
    target tables in another product's migration tree. The local-schema
    detectors can't verify those without resolving `schema → product slug
    → migrations dir`, which is impossible when the `schema` arg is a
    runtime variable. **Heuristic limit (documented):** we detect the
    *presence* of the `.schema(...)` call regardless of whether its arg
    is a literal or a runtime expression, and skip the local-schema
    check. False-negative trade is acceptable — cross-schema runtime
    failures are loud (Postgres raises on missing schema), unlike the
    silent MockSupabase WARN+skip that the original detector defends
    against.

    Both production-correctness detectors (`check_unknown_table_references`
    + `check_admin_endpoint_service_role_bypass`) gate on this helper.
    The admin-bypass detector also fails its receiver-shape check on
    `db.schema(Y).table(...)` (receiver is a `Call`, not a `Name`/
    `get_admin_client()`), but the explicit skip closes the gap
    structurally so a future receiver-shape refactor doesn't reintroduce
    the false positive.
    """
    if not isinstance(call.func, ast.Attribute):
        return False
    receiver: ast.AST | None = call.func.value
    # Walk backward through call chains: `<x>.schema(...).table(...)`,
    # `<x>.schema(...).foo().table(...)` (rare but legal), etc.
    while isinstance(receiver, ast.Call):
        if (
            isinstance(receiver.func, ast.Attribute)
            and receiver.func.attr == "schema"
        ):
            return True
        # Step further back: descend into the receiver's own receiver.
        if isinstance(receiver.func, ast.Attribute):
            receiver = receiver.func.value
        else:
            # `foo()` style — no further chain.
            receiver = None
    return False


def check_unknown_table_references(product_path: Path) -> list[dict]:
    """Flag `<X>.table("name")` callsites where `name` is not declared by a
    `CREATE TABLE` in the product's migrations.

    The slip this defends against (Engineer GG therapy P4, commit a56a39e):

        # In services/admin_service.py
        db.table("commission_overrides").select(...)
        #          ^^^^^^^^^^^^^^^^^^^^
        # Real schema has `platform_commission_overrides`. MockSupabase
        # WARN+skip returns empty results silently; tests pass; production
        # fails.

    Conservative shape — false negatives over false positives:
      - Skips `.table(<non-string>)` (f-strings, names, attributes — we
        can't resolve them statically without dataflow).
      - Skips tables in :data:`_KNOWN_EXTERNAL_TABLES` (Supabase-managed
        `auth.users`, core-bootstrap `products`/`organizations`).
      - Short-circuits if the product has no `backend/migrations/` —
        scaffold-time products are not yet expected to have a schema.

    Severity `warning` (not `high`) because the cross-cutting drift cases
    surfaced by GG were genuine bugs but the false-positive risk on a
    table that lives in another product's migration tree (cross-product
    schema reference, rare but legitimate) is non-zero. Triage in
    `--review` covers the rest.
    """
    issues: list[dict] = []
    name = product_path.name
    backend_app = product_path / "backend" / "app"
    migrations = product_path / "backend" / "migrations"
    if not backend_app.exists() or not migrations.exists():
        return issues

    known = _collect_known_tables(product_path)
    if not known:
        # No CREATE TABLE found — likely a scaffold or a product whose
        # migrations live elsewhere. Avoid flagging every callsite.
        return issues

    seen_pairs: set[tuple[str, str, int, str]] = set()
    for py_file in _walk_product_backend_python(product_path):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_file, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_file, exc)
            continue

        try:
            rel = str(py_file.relative_to(product_path))
        except ValueError:
            rel = str(py_file)

        for call in _iter_table_callsites(tree):
            # Cross-schema lookup (`db.schema(X).table(Y)`) — Y lives in a
            # foreign product's migration tree. Heuristic limit: we don't
            # resolve `schema → product slug → migrations`. See
            # `_has_schema_in_chain` docstring.
            if _has_schema_in_chain(call):
                continue
            table_name = _extract_table_string_arg(call)
            if table_name is None:
                continue
            lower = table_name.lower()
            if lower in known or lower in _KNOWN_EXTERNAL_TABLES:
                continue
            key = (name, rel, call.lineno, lower)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            issues.append({
                "product": name,
                "file": rel,
                "line": call.lineno,
                "table": table_name,
                "issue": (
                    f"{rel}:{call.lineno} `.table({table_name!r})` references "
                    f"a table not declared by any `CREATE TABLE` in "
                    f"`products/{name}/backend/migrations/*.sql`. "
                    f"MockSupabase WARN+skip masks this — production fails. "
                    f"See KB § PATTERNS/testing.md § Production-correctness "
                    f"keeper detectors."
                ),
                "severity": "warning",
            })
    return issues


def _function_block_text(content: str, start: int) -> tuple[str, int]:
    """Return the text of the CREATE FUNCTION block that begins at `start`,
    plus the index where the block ends.

    The block runs from the CREATE FUNCTION match's start through the first
    statement terminator (`;`) that follows the matching dollar-quoted body
    delimiter. Supports any `$tag$ ... $tag$` form (tag may be empty).

    Falls back to "everything until the next `CREATE` keyword OR end of
    file" if no dollar quote is found (some functions use AS 'SQL_LITERAL'
    form — rare but legal).
    """
    # Find the first dollar-quote opener after `start`.
    dq_open = re.search(r"\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*)?\$", content[start:])
    if dq_open is not None:
        tag = dq_open.group("tag") or ""
        opener_idx = start + dq_open.start()
        # Find the matching closer.
        closer_pat = re.compile(rf"\${re.escape(tag)}\$")
        closer_match = closer_pat.search(content, opener_idx + len(dq_open.group(0)))
        if closer_match is not None:
            end = closer_match.end()
            # Walk forward to the next `;` to include the statement terminator.
            semi = content.find(";", end)
            if semi != -1:
                end = semi + 1
            return content[start:end], end
        # Unbalanced dollar quote — skip forward to the next CREATE/EOF.
    # Fallback: take until next CREATE keyword or EOF.
    next_create = re.search(r"\bCREATE\b", content[start + 1:], re.IGNORECASE)
    end = start + 1 + next_create.start() if next_create else len(content)
    return content[start:end], end


def check_function_search_path_pinned(product_path: Path) -> list[dict]:
    """Flag `CREATE [OR REPLACE] FUNCTION` blocks in product migrations
    that do NOT pin `SET search_path = ...`.

    The slip this defends against (Engineer GG therapy P4 / Supabase
    advisor 0011): SECURITY DEFINER functions without a pinned search_path
    can be hijacked by a caller's `search_path` settings — a public-facing
    schema can shadow the intended schema. Pin every function.

    Supabase guidance is to ALWAYS set `search_path` on SECURITY DEFINER
    functions and as a defense-in-depth on STABLE / IMMUTABLE functions
    too. The detector flags EVERY CREATE FUNCTION block missing the clause
    — calibration based on advisor 0011 catching `gcal_authorization_is_fresh`
    even though it was IMMUTABLE (no caller-search_path risk in theory; the
    advisor flags it anyway because the static guarantee is weaker than the
    pinned-clause guarantee).

    Severity `warning`. False-positive shape: a function legitimately
    relying on caller search_path (very rare in our codebase, none in any
    existing migration). Accept-with-rationale + comment would shut the
    detector up; we leave that to the product owner if the case arises.
    """
    issues: list[dict] = []
    name = product_path.name
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return issues

    seen: set[tuple[str, str, int, str]] = set()
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        try:
            rel = str(sql_file.relative_to(product_path))
        except ValueError:
            rel = str(sql_file)

        for m in _CREATE_FUNCTION_START_RE.finditer(content):
            fn_qualified = m.group("qualified")
            block_text, _end = _function_block_text(content, m.start())
            # `SET search_path = ...` can appear anywhere in the block
            # (header before AS, inside the body, after the body) — match
            # the whole text. Use a tolerant regex: any whitespace, then
            # SET, then search_path with optional schema/identifier list.
            if re.search(
                r"\bSET\s+search_path\b",
                block_text,
                re.IGNORECASE,
            ):
                continue
            # Locate line number of the CREATE FUNCTION header.
            lineno = content[:m.start()].count("\n") + 1
            key = (name, rel, lineno, fn_qualified)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "product": name,
                "file": rel,
                "line": lineno,
                "function": fn_qualified,
                "issue": (
                    f"{rel}:{lineno} `CREATE FUNCTION {fn_qualified}` "
                    f"does not pin `SET search_path = ...`. Supabase "
                    f"advisor 0011 flags this. See KB § PATTERNS/"
                    f"testing.md § Production-correctness keeper detectors."
                ),
                "severity": "warning",
            })
    return issues


def _admin_client_bindings(tree: ast.Module) -> set[str]:
    """Return the set of local variable names that hold a `get_admin_client()`
    return value within `tree`.

    Detects two assignment shapes:
        admin_db = get_admin_client()
        client: SomeType = get_admin_client()

    Plus the chained shape (`get_admin_client().table(...)`) which yields
    no binding but is matched directly by the receiver-shape walker.
    """
    bindings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is None:
                continue
            if not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "get_admin_client"
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    bindings.add(tgt.id)
    return bindings


def _is_chained_admin_table_call(call: ast.Call) -> bool:
    """True if `call` is `get_admin_client().table(...)` (chained, no
    intermediate binding).
    """
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "table"):
        return False
    receiver = call.func.value
    return (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "get_admin_client"
    )


def _is_bound_admin_table_call(call: ast.Call, bindings: set[str]) -> bool:
    """True if `call` is `<bound>.table(...)` where `<bound>` is in
    `bindings` (an admin-client variable).
    """
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "table"):
        return False
    receiver = call.func.value
    return isinstance(receiver, ast.Name) and receiver.id in bindings


def check_admin_endpoint_service_role_bypass(product_path: Path) -> list[dict]:
    """Flag admin-client `.table("T")` callsites where the target table T
    has no `service_role_bypass` policy in the product's migrations.

    The slip this defends against (Engineer GG therapy P4): an admin
    endpoint reaches for `get_admin_client()` to bypass authenticated-user
    RLS, but the target table only has `authenticated_access` policies —
    so the service_role bypass silently fails (returns empty result sets,
    or worse, succeeds against a real row by coincidence). The detector
    enforces the platform convention: every admin-accessed table ships a
    matching `CREATE POLICY "service_role_bypass" ... FOR ALL TO
    service_role USING (true)`.

    Detection shape (AST):
      - Find `admin_db = get_admin_client()` style bindings + chained
        `get_admin_client().table(...)` calls.
      - For each, extract the table-name literal arg.
      - Cross-check against `_collect_service_role_bypass_tables`.

    Severity `warning`. False-positive shape (rare): a table that's
    accessed via admin client purely for cross-tenant reads where RLS is
    intentionally not bypassed because the row visibility is enforced by
    a different mechanism (foreign-key chain to a tenant-id column the
    admin client already has). Accept-with-rationale handles those.
    """
    issues: list[dict] = []
    name = product_path.name
    backend_app = product_path / "backend" / "app"
    migrations = product_path / "backend" / "migrations"
    if not backend_app.exists() or not migrations.exists():
        return issues

    bypass_tables = _collect_service_role_bypass_tables(product_path)

    seen: set[tuple[str, str, int, str]] = set()
    for py_file in _walk_product_backend_python(product_path):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_file, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_file, exc)
            continue

        bindings = _admin_client_bindings(tree)
        if not bindings:
            # Still scan for chained `get_admin_client().table(...)`.
            pass

        try:
            rel = str(py_file.relative_to(product_path))
        except ValueError:
            rel = str(py_file)

        for call in _iter_table_callsites(tree):
            # Cross-schema lookup (`admin_db.schema(X).table(Y)`) — bypass
            # policy must live in X's migration tree, not this product's.
            # Skip explicitly so a future receiver-shape refactor (e.g.
            # extending `_is_*_admin_table_call` to follow chains) doesn't
            # reintroduce the false positive. See `_has_schema_in_chain`
            # docstring for the heuristic-limit rationale.
            if _has_schema_in_chain(call):
                continue
            is_admin = (
                _is_chained_admin_table_call(call)
                or _is_bound_admin_table_call(call, bindings)
            )
            if not is_admin:
                continue
            table_name = _extract_table_string_arg(call)
            if table_name is None:
                continue
            lower = table_name.lower()
            if lower in _KNOWN_EXTERNAL_TABLES:
                # External (auth.users etc.) — RLS not under our control.
                continue
            if lower in bypass_tables:
                continue
            key = (name, rel, call.lineno, lower)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "product": name,
                "file": rel,
                "line": call.lineno,
                "table": table_name,
                "issue": (
                    f"{rel}:{call.lineno} admin client calls "
                    f"`.table({table_name!r})` but table `{table_name}` "
                    f"has no `CREATE POLICY \"service_role_bypass\" ... ON "
                    f"<schema>.{table_name}` in "
                    f"`products/{name}/backend/migrations/*.sql`. "
                    f"Admin bypass will silently fail. See KB § "
                    f"PATTERNS/testing.md § Production-correctness keeper "
                    f"detectors."
                ),
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_detector_has_regression_test` — every keeper detector ships with a
# colocated regression test. Enforces the platform-wide testing methodology
# documented in KB § PATTERNS/testing.md § Regression-test-the-detector.
# ---------------------------------------------------------------------------


# Detector → test entry-point map. The detector is satisfied when EITHER:
#   - a `Test<CamelCase>` class exists in any `mcp/noctusai/tests/test_*.py`
#     file with a name derived from the detector (e.g. `check_silent_errors`
#     → `TestCheckSilentErrors` or `TestSilentErrors`), OR
#   - the detector is explicitly mapped here to a test file/symbol that
#     covers it (used when the natural-name heuristic doesn't hold).
#
# Adding a new detector? Add the regression test first; the test class name
# should match the detector. If the test must live somewhere else, add an
# explicit entry here so the rule stays enforced.
_DETECTOR_TEST_OVERRIDES: dict[str, str] = {
    # `check_path_references` is exercised by the underlying `find_refs`
    # tests (which the detector composes) — explicit override keeps the
    # detector classified as covered.
    "check_path_references": "tests/test_refs.py::TestFindRefs",
    "check_frontend_entrypoint": "tests/test_phase5_detectors.py",
    "check_out_of_contract_trees": "tests/test_phase5_detectors.py",
    "check_config_extends_product_settings": "tests/test_config_inheritance.py",
    "check_frontend_config_paths": "tests/test_frontend_config_paths.py",
    "check_seed_version_propagation": "tests/test_seed_version_propagation.py",
}


def _detector_function_names() -> list[str]:
    """Parse this module and return every top-level `check_*` function name.

    `check_all_products` is the dispatcher and is excluded.
    """
    here = Path(__file__).resolve()
    try:
        tree = ast.parse(here.read_text(encoding="utf-8"), filename=str(here))
    except (OSError, SyntaxError) as exc:
        logger.warning(
            "compliance: cannot self-parse %s (%s); skipping detector audit",
            here, exc,
        )
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("check_")
        and node.name != "check_all_products"
    ]


def _camel_case(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def _detector_has_regression_test(detector: str, tests_dir: Path) -> bool:
    """True if a `Test<CamelCase>` class for the detector exists somewhere
    under `tests_dir`, OR an explicit override maps the detector to a test
    target.

    Class-name matching is case-insensitive on the snake_case parts so
    acronyms like `TestAIFeatureCompleteness` (matching detector
    `check_ai_feature_completeness`) are recognized without an override.
    Both `TestCheck<...>` and `Test<...>` shapes are accepted.
    """
    if detector in _DETECTOR_TEST_OVERRIDES:
        target = _DETECTOR_TEST_OVERRIDES[detector]
        # Format: "tests/<file>.py" or "tests/<file>.py::<symbol>"
        rel_file = target.split("::", 1)[0]
        return (tests_dir.parent / rel_file).exists()

    if not tests_dir.exists():
        return False

    # Build a case-insensitive regex matching `class Test<Body>` where
    # <Body> is the joined snake_case parts (with or without leading
    # `Check`). E.g. `check_ai_feature_completeness` matches both
    # `TestCheckAIFeatureCompleteness` and `TestAIFeatureCompleteness`,
    # case-insensitively.
    body_full = detector.replace("_", "")
    body_short = detector.removeprefix("check_").replace("_", "")
    pattern = re.compile(
        rf"class\s+Test(?:{body_full}|{body_short})\b",
        re.IGNORECASE,
    )

    for test_file in tests_dir.glob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", test_file, exc)
            continue
        if pattern.search(content):
            return True
    return False


def check_detector_has_regression_test(repo_root: Path | None = None) -> list[dict]:
    """Every `check_*` keeper detector must ship with a regression test.

    The test pins the detector's true-positive and false-positive shapes so
    that a future refactor cannot silently regress it. Per KB §
    PATTERNS/testing.md § Regression-test-the-detector. Severity `high` —
    a missing detector test is the kind of gap that lets a real-world miss
    ship without being noticed.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    tests_dir = root / "mcp" / "noctusai" / "tests"

    for detector in _detector_function_names():
        if detector == "check_detector_has_regression_test":
            # Self-coverage is checked at import-time by the test file; if
            # the test doesn't import the detector, the test fails. No need
            # to flag here.
            continue
        if _detector_has_regression_test(detector, tests_dir):
            continue
        # Build hint targets so the message is actionable.
        expected = "Test" + _camel_case(detector.removeprefix("check_"))
        issues.append({
            "product": "<mcp>",
            "file": "mcp/noctusai/tools/compliance.py",
            "issue": (
                f"Keeper detector `{detector}` has no regression test. "
                f"Per KB § PATTERNS/testing.md § Regression-test-the-detector, "
                f"every detector must ship colocated with a test that pins "
                f"its true-positive and false-positive shapes. Add a "
                f"`class {expected}` (or `Test{_camel_case(detector)}`) to "
                f"`mcp/noctusai/tests/test_compliance.py` (or a dedicated "
                f"`mcp/noctusai/tests/test_<detector>.py`). If the test "
                f"covers the detector under a non-matching name, add an "
                f"override entry to `_DETECTOR_TEST_OVERRIDES` in "
                f"`mcp/noctusai/tools/compliance.py`."
            ),
            "severity": "high",
        })
    return issues


# ---------------------------------------------------------------------------


class ValidateInput(BaseModel):
    """No inputs — `validate` runs across every product unconditionally."""


class ValidateIssue(BaseModel):
    product: str | None = None
    severity: str
    issue: str
    detector: str | None = None


class ValidateOutput(BaseModel):
    score: int = Field(description="Platform-wide score 0-100. Average across products.")
    issues: list[ValidateIssue] = Field(default_factory=list)


def check_section_7_placeholder_consistency(repo_root: Path | None = None) -> list[dict]:
    """Detect PROJECT.md files where §7 says "all answered" but §2 still
    carries the unfilled `_Interrogate ..._` template placeholder.

    The bug shape this catches: a child PROJECT.md is scaffolded from
    `templates/PROJECT-TEMPLATE.md` and §7 gets filled with the template's
    default `See §2 — all answered at interrogation time.` line BEFORE
    §2 is actually filled. §7 then misleads future agents into thinking
    the §7 questions were answered, when in fact §2 is still empty.

    Surfaced 2026-05-03 by `projects/side-projects-batch/` Phase 0 audit:
    three Tier-1 children carried this exact mismatch (N=3 → triage; N≥4
    → MUST formalize). This detector formalizes the check.

    The fired rule:
      - §7 contains "See §2 — all answered" or "answered at interrogation time"
      - AND §2 still contains "_Interrogate the user before filling"
        (or similar template-default placeholder pattern)
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    answered_marker_re = re.compile(
        r"answered at interrogation time|See \xa7?2\s*[—-]\s*all answered",
        re.IGNORECASE,
    )
    placeholder_re = re.compile(
        r"_Interrogate the user before filling|"
        r"_TBD after interrogation_|"
        r"_\(filled at Phase 0 interrogation\)_",
        re.IGNORECASE,
    )
    section_2_re = re.compile(
        r"^## 2\..*?(?=^## 3\.)",
        re.MULTILINE | re.DOTALL,
    )
    section_7_re = re.compile(
        r"^## 7\..*?(?=^## 8\.)",
        re.MULTILINE | re.DOTALL,
    )

    for project_md in _find_all_project_md(root):
        try:
            content = project_md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning(
                "compliance: cannot read PROJECT.md %s (%s), skipping",
                project_md, exc,
            )
            continue

        s2 = section_2_re.search(content)
        s7 = section_7_re.search(content)
        if not s2 or not s7:
            continue

        s7_says_answered = bool(answered_marker_re.search(s7.group(0)))
        s2_still_placeholder = bool(placeholder_re.search(s2.group(0)))

        if s7_says_answered and s2_still_placeholder:
            try:
                relative = str(project_md.relative_to(root))
            except ValueError:
                relative = str(project_md)
            product_label = "<projects>"
            if relative.startswith("products/"):
                product_label = relative.split("/", 2)[1]
            elif relative.startswith("core/"):
                product_label = "core"
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}` §7 claims questions are 'answered at "
                    f"interrogation time' but §2 still carries the "
                    f"`_Interrogate the user before filling_` template "
                    f"placeholder. Either fill §2 with the actual answers "
                    f"or restore §7 to the unanswered shape (list the "
                    f"questions explicitly with recommendations). "
                    f"Misleading template-fill artifact — future agents "
                    f"will read §7 as resolved when it isn't."
                ),
                "severity": "high",
            })
    return issues


def check_all_products() -> tuple[int, list]:
    """Run all compliance checks on all products. Returns (score, issues)."""
    all_issues = []
    scores = []

    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        issues = (
            check_seed_compliance(d)
            + check_path_references(d)
            + check_standard_routers_audit(d)
            + check_frontend_entrypoint(d)
            + check_config_extends_product_settings(d)
            + check_frontend_config_paths(d)
            + check_mock_schema_validation(d)
            + check_ai_feature_completeness(d)
            + check_test_status_assertion(d)
            + check_unknown_table_references(d)
            + check_function_search_path_pinned(d)
            + check_admin_endpoint_service_role_bypass(d)
        )
        all_issues.extend(issues)
        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        scores.append(max(0, 100 - penalty))

    # Global (non-per-product) checks.
    all_issues.extend(check_out_of_contract_trees())
    all_issues.extend(check_seed_version_propagation())
    all_issues.extend(check_phase_state_consistency())
    all_issues.extend(check_no_self_monkeypatch())
    all_issues.extend(check_silent_errors())
    all_issues.extend(check_clean_folder_violations())
    all_issues.extend(check_section_7_placeholder_consistency())
    all_issues.extend(check_detector_has_regression_test())

    platform_score = round(sum(scores) / len(scores)) if scores else 100
    return platform_score, all_issues


def _check_post_scaffold(
    slug: str,
    *,
    repo_root: Path | None = None,
    products_dir: Path | None = None,
) -> list[dict]:
    """Enforce the items currently listed in `scaffold_product`'s `next_steps`.

    Each returned dict has shape `{"check": str, "ok": bool, "error": str | None}`.
    Added 2026-05-04 (sh-yt-scaffold-polish Phase 3.4) so `validate_product`
    catches scaffolded-but-not-registered products. Mirrors the next_steps
    list in `mcp/noctusai/tools/noctus/dev/scaffold.py::scaffold_product`.

    Args:
        repo_root: Override for the repository root (test seam). Defaults
            to module-level :data:`REPO_ROOT`. Tests pass tmp_path-based
            roots so they can fixture start.sh / KB / vite factory in
            isolation.
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to :data:`PRODUCTS_DIR`. Falls back to
            ``repo_root/products`` when only `repo_root` is supplied.

    Checks (5):
      1. Backend port wired in start.sh under the product's `--app-dir`.
      2. Frontend port wired in start.sh.
      3. Slug listed in `KB § CONTEXT/02-LANDSCAPE.md` Products table.
      4. INSERT INTO products row with the slug exists in any of the
         product's migration files (or core's bootstrap insert).
      5. Frontend port appears in `seed/framework/frontend/vite.config.factory.ts`
         PRODUCT_MAP (the factory looks up by frontend port — the slug never
         goes into PRODUCT_MAP, but the port does, with the slug as comment).
    """
    results: list[dict] = []

    base_repo_root = repo_root if repo_root is not None else REPO_ROOT
    if products_dir is not None:
        base_products_dir = products_dir
    elif repo_root is not None:
        base_products_dir = repo_root / "products"
    else:
        base_products_dir = PRODUCTS_DIR

    product_path = base_products_dir / slug

    # 1+2 — start.sh checks
    start_sh = base_repo_root / "start.sh"
    if not start_sh.exists():
        results.append({
            "check": "start_sh_exists",
            "ok": False,
            "error": f"start.sh missing at {start_sh}",
        })
        # Without start.sh we can't run port checks meaningfully.
        for c in ("backend_port_in_start_sh", "frontend_port_in_start_sh"):
            results.append({"check": c, "ok": False, "error": "start.sh missing"})
    else:
        sh_content = start_sh.read_text()
        # start.sh references products either via literal paths
        # (`products/<slug>/backend`) or via shell vars assigned to
        # `$ROOT_DIR/products/<slug>/backend`. Either form counts; we just
        # need to confirm a `--port N` appears within a reasonable window.
        backend_path = f"products/{slug}/backend"
        frontend_path = f"products/{slug}/frontend"

        def _has_port_near(needle: str) -> bool:
            """True iff `needle` appears in start.sh AND any `--port N`
            occurs within ±300 chars OR a shell variable assignment binds
            `needle` and that variable is referenced near a `--port`.
            """
            # Direct: literal path AND nearby --port.
            for m in re.finditer(re.escape(needle), sh_content):
                idx = m.start()
                window = sh_content[max(0, idx - 300): idx + 300]
                if re.search(r"--port\s+\d+", window):
                    return True
            # Indirect: a `VAR=...products/<slug>/(backend|frontend)`
            # assignment, then `$VAR` (or `"$VAR"`) referenced near --port.
            assign_re = re.compile(
                rf'(?P<var>[A-Z_][A-Z0-9_]*)="\$ROOT_DIR/{re.escape(needle)}"',
            )
            for m in assign_re.finditer(sh_content):
                var = m.group("var")
                # Find any usage of $var (with or without quotes) near --port.
                usage_re = re.compile(rf'"?\${re.escape(var)}"?')
                for u in usage_re.finditer(sh_content):
                    idx = u.start()
                    window = sh_content[max(0, idx - 300): idx + 300]
                    if re.search(r"--port\s+\d+", window):
                        return True
            return False

        if _has_port_near(backend_path):
            results.append({
                "check": "backend_port_in_start_sh",
                "ok": True,
                "error": None,
            })
        else:
            results.append({
                "check": "backend_port_in_start_sh",
                "ok": False,
                "error": (
                    f"start.sh has no `--port N` near `{backend_path}` — "
                    f"backend not wired into platform startup."
                ),
            })

        if _has_port_near(frontend_path):
            results.append({
                "check": "frontend_port_in_start_sh",
                "ok": True,
                "error": None,
            })
        else:
            results.append({
                "check": "frontend_port_in_start_sh",
                "ok": False,
                "error": (
                    f"start.sh has no `--port N` near `{frontend_path}` — "
                    f"frontend not wired into platform startup."
                ),
            })

    # 3 — KB § 02-LANDSCAPE.md product table
    landscape = base_repo_root / "KNOWLEDGE-BASE" / "CONTEXT" / "02-LANDSCAPE.md"
    if not landscape.exists():
        results.append({
            "check": "kb_landscape_table",
            "ok": False,
            "error": f"KB landscape file missing at {landscape}",
        })
    else:
        ls_content = landscape.read_text()
        if f"products/{slug}/" in ls_content or f"`products/{slug}/`" in ls_content:
            results.append({
                "check": "kb_landscape_table",
                "ok": True,
                "error": None,
            })
        else:
            results.append({
                "check": "kb_landscape_table",
                "ok": False,
                "error": (
                    f"KB § CONTEXT/02-LANDSCAPE.md Products table missing row "
                    f"for `products/{slug}/`."
                ),
            })

    # 4 — products-table INSERT row exists somewhere
    insert_pattern = re.compile(
        rf"INSERT\s+INTO\s+(?:public\.)?products[^\n]*\n(?:[^\n]*\n){{0,15}}[^\n]*'{re.escape(slug)}'",
        re.IGNORECASE,
    )
    found_insert = False
    insert_paths_searched = []
    for product_dir in base_products_dir.iterdir():
        if not product_dir.is_dir() or product_dir.name.startswith("."):
            continue
        migrations = product_dir / "backend" / "migrations"
        if not migrations.exists():
            continue
        for sql_file in migrations.glob("*.sql"):
            try:
                rel = str(sql_file.relative_to(base_repo_root))
            except ValueError:
                rel = str(sql_file)
            insert_paths_searched.append(rel)
            try:
                if insert_pattern.search(sql_file.read_text()):
                    found_insert = True
                    break
            except OSError:
                continue
        if found_insert:
            break
    if found_insert:
        results.append({
            "check": "products_table_insert",
            "ok": True,
            "error": None,
        })
    else:
        results.append({
            "check": "products_table_insert",
            "ok": False,
            "error": (
                f"No `INSERT INTO (public.)?products` migration row found with "
                f"slug '{slug}'. Searched {len(insert_paths_searched)} migration "
                f"file(s) under products/*/backend/migrations/."
            ),
        })

    # 5 — vite.config.factory.ts PRODUCT_MAP entry (keyed by frontend port).
    # We look for a comment line with the slug in PRODUCT_MAP — products land
    # there with their slug as a `// SlugName` trailing comment.
    factory_path = base_repo_root / "seed" / "framework" / "frontend" / "vite.config.factory.ts"
    if not factory_path.exists():
        results.append({
            "check": "vite_factory_product_map",
            "ok": False,
            "error": f"seed factory missing at {factory_path}",
        })
    else:
        fc = factory_path.read_text()
        # Look for the slug (or a CamelCased / Title variant) within the
        # PRODUCT_MAP block. Block delimited by `PRODUCT_MAP` declaration up
        # to its closing `};`.
        map_match = re.search(
            r"PRODUCT_MAP[^=]*=\s*\{(?P<body>.*?)\};",
            fc,
            re.DOTALL,
        )
        if map_match is None:
            results.append({
                "check": "vite_factory_product_map",
                "ok": False,
                "error": "Could not locate PRODUCT_MAP literal in factory.",
            })
        else:
            body = map_match.group("body")
            # The slug may appear verbatim or with hyphens replaced; allow both.
            slug_variants = {
                slug,
                slug.replace("-", " ").title(),
                slug.replace("-", "_"),
                slug.replace("-", ""),
            }
            if any(v.lower() in body.lower() for v in slug_variants):
                results.append({
                    "check": "vite_factory_product_map",
                    "ok": True,
                    "error": None,
                })
            else:
                results.append({
                    "check": "vite_factory_product_map",
                    "ok": False,
                    "error": (
                        f"PRODUCT_MAP in vite.config.factory.ts has no entry "
                        f"referencing '{slug}'. Add the frontend port row."
                    ),
                })

    return results


def validate_one_product(
    slug: str,
    *,
    repo_root: Path | None = None,
    products_dir: Path | None = None,
) -> dict:
    """Score one product against seed-compliance + path-reference rules.

    Migrated from `mcp/noctusai/server.py::_validate_one` during the FastMCP
    switch (mcp-server-fastmcp-switch Commit A) — was homeless dispatch-side
    logic; now lives next to the underlying detectors.

    Phase 3.4 (sh-yt-scaffold-polish, 2026-05-04) extended this with the
    `post_scaffold_checks` key: 5 binary registration checks mirroring
    `scaffold_product`'s next_steps. Existing `score`/`issues` shape preserved.
    Aggregate `post_scaffold_ok` is True only when every check passes.

    Args:
        repo_root, products_dir: Test seams forwarded to
            :func:`_check_post_scaffold`. The seed-compliance + path-reference
            checks still resolve from module-level :data:`PRODUCTS_DIR`
            (their refactor is not in scope for Phase 3.4); when callers
            supply `products_dir`, only the post-scaffold checks honor it.
    """
    base_products_dir = products_dir if products_dir is not None else (
        repo_root / "products" if repo_root is not None else PRODUCTS_DIR
    )
    path = base_products_dir / slug
    issues = check_seed_compliance(path) + check_path_references(path)
    penalties = {"critical": 25, "high": 10, "warning": 3}
    score = max(0, 100 - sum(penalties.get(i["severity"], 5) for i in issues))

    post_scaffold = _check_post_scaffold(
        slug, repo_root=repo_root, products_dir=products_dir,
    )
    post_ok = all(c["ok"] for c in post_scaffold)

    return {
        "product": slug,
        "score": score,
        "issues": issues,
        "post_scaffold_checks": post_scaffold,
        "post_scaffold_ok": post_ok,
    }


def register(server) -> None:
    desc_validate = "Check seed compliance for all products. Returns score 0-100."

    def _validate() -> dict:
        score, issues = check_all_products()
        return {"score": score, "issues": issues}

    server.tool(
        name="noctus.dev.validate",
        description=desc_validate,
    )(_validate)

    @server.tool(
        name="noctus.dev.validate_product",
        description="Check seed compliance for one product",
    )
    def _validate_product(slug: str) -> dict:
        return validate_one_product(slug)
