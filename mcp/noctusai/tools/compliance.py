"""Seed compliance checks — migrated from agents/keeper/checks/.

Validates that products follow the seed framework pattern.
All checks are deterministic, fast, zero AI.
"""
import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


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
    except SyntaxError:
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
        if "seed/backend/framework" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/backend/framework", "severity": "high"})
        if "seed/backend/lib" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/backend/lib", "severity": "high"})

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
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return issues

    for package_name, attr_name, stamp_hint in (
        ("noctusai_seed", "__seed_version__", "seed/backend/framework"),
        ("noctusai_lib", "__lib_version__", "seed/backend/lib"),
    ):
        try:
            module = __import__(package_name)
            reported = getattr(module, attr_name, None)
        except ImportError as exc:
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/",
                "issue": (
                    f"Cannot import `{package_name}` to check version "
                    f"propagation: {exc}. Run `pip install -e {stamp_hint}` "
                    f"to install the package."
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
        except (ValueError, TypeError):
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


def _shipped_phases_in_changelog(changelog: str) -> set[int]:
    """Find phase numbers the §11 changelog claims as shipped/closed.

    Heuristic: look for "Phase N ✅", "Phase N shipped", "Phase N closed",
    "Phase N complete". Only counts phases that appear with explicit
    shipped/closed markers — bare "Phase N" mentions in passing don't
    qualify (e.g. "Phase 0 audit found...").
    """
    shipped: set[int] = set()
    # Look for "Phase N ✅" anywhere in changelog
    for m in re.finditer(r'Phase\s+(\d+)\s*✅', changelog):
        try:
            shipped.add(int(m.group(1)))
        except ValueError:
            continue
    # Look for "Phase N shipped" / "Phase N closed" with small lookahead
    for m in re.finditer(
        r'Phase\s+(\d+)\b[^.]{0,80}?(?:shipped|closed|complete)',
        changelog,
        re.IGNORECASE,
    ):
        try:
            shipped.add(int(m.group(1)))
        except ValueError:
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
        )
        all_issues.extend(issues)
        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        scores.append(max(0, 100 - penalty))

    # Global (non-per-product) checks.
    all_issues.extend(check_out_of_contract_trees())
    all_issues.extend(check_seed_version_propagation())
    all_issues.extend(check_phase_state_consistency())

    platform_score = round(sum(scores) / len(scores)) if scores else 100
    return platform_score, all_issues
