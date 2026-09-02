"""Self-patch detection — the predicate, with NO heavy dependencies.

Extracted from `compliance.py` so that TWO enforcement points can share ONE
definition of "is this test patching our own code":

  * `compliance.check_no_self_monkeypatch` — the commit/CI-time keeper;
  * `test_seam_guard.decide`               — the PreToolUse write-time guard.

WHY IT LIVES IN ITS OWN MODULE
==============================
The write-time guard runs inside a PreToolUse hook, under whatever `python3`
is on PATH — NOT the repo venv. `compliance.py` imports pydantic at module
scope, so importing it from the hook raised `No module named 'pydantic'`, the
hook failed OPEN by design, and the guard silently never fired. It was caught
only by exercising the hook end-to-end; every module-level unit test passed,
because those run under the venv.

That is the same false-green shape this repo keeps paying for: a check that
cannot go red proves nothing. So the predicate lives here, importing stdlib
only (`ast`, `re`, `pathlib`) — which is now a CONSTRAINT on this file, not a
coincidence. Adding a third-party import here re-breaks the guard silently.

`compliance.py` re-exports every name below, so existing references and the
keeper's own tests are unaffected.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


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


# Directory names under `mcp/` that are never a vendor-connector "ours"
# namespace: `noctusai` is the platform MCP toolkit itself (this very
# module), not a connector client — it imports as `tools.*`, not
# `noctusai.*`, so it's a non-issue either way, but the exclusion documents
# intent. `__pycache__` is build noise.
_MCP_NON_CONNECTOR_DIR_NAMES: frozenset[str] = frozenset({"noctusai", "__pycache__"})


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


# Module prefixes that are "ours" (production code in this repo). Patching
# any of these in tests neuters our own logic — UNLESS the target attribute
# is a known boundary accessor (see _BOUNDARY_ACCESSOR_NAMES).
#
# NOTE: this fixed tuple does NOT cover the in-repo `mcp/<vendor>` connector
# clients (`n8n.*`, `waha.*`, `github.*`, ...) — those are namespace-rooted
# at their own top-level package name, not under `app.`/`noctusai_lib.`/
# `noctusai_seed.`. See `_discover_connector_module_prefixes` below, which
# extends this set per-call with the DERIVED connector-package prefixes
# (found `mcp/n8n/build` Wave 1 — `n8n.tools.credential.credential_create`
# monkeypatched in a test slipped past this detector entirely because the
# `n8n.` namespace wasn't "ours").
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
    # Connector-MCP env-config boundary — every `mcp/<vendor>` connector's
    # `get_settings()` is the `_kit.settings.make_get_settings`-built,
    # `lru_cache`-wrapped env/.env reader (base_url/api_key/token, no
    # business logic). Same category as `get_whatsapp_config_from_env`
    # above. Shared name across ALL connectors (n8n/waha/cloudflare/
    # hostinger/github/meta/vista/supabase) — see `mcp/_kit/settings.py`.
    "get_settings",
    # Connector-MCP subprocess boundary — GitHub connector shells out to
    # the `gh` CLI instead of an HTTP client; `run_gh` is the subprocess
    # boundary, `gh_available` a PATH-presence check. Mirrors `request_json`
    # below for the HTTP-based connectors.
    "run_gh",
    "gh_available",
    # Shared connector transport primitive — `_kit.transport.urlopen` is
    # stdlib `urllib.request.urlopen` re-exported into the shared seam;
    # `mcp/hostinger` + `mcp/supabase` test_smoke.py patch it directly
    # (one level below the per-vendor `request_json`).
    "urlopen",
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
    # Connector-MCP HTTP boundary — every `mcp/<vendor>/api.py` exposes the
    # SAME single-HTTP-seam shape: `request_json` (n8n/waha/cloudflare/
    # hostinger/supabase) or `request_envelope` (cloudflare's pagination
    # variant), both wrapping the shared `_kit.transport.request_json` +
    # stdlib `urllib`. Mocking it is the sanctioned "skip the real network
    # call" pattern documented identically in every connector's api.py
    # docstring.
    re.compile(r"^request_(?:json|envelope)$"),
)


# Allowlist: bypass via inline comment `# self-patch-ok: <reason>` on the
# patching line itself. For genuinely-rare legitimate cases that don't
# fit the boundary-accessor pattern.
_SELF_PATCH_OK_COMMENT_RE = re.compile(r"#\s*self-patch-ok\b", re.IGNORECASE)


def _discover_connector_module_prefixes(root: Path) -> tuple[str, ...]:
    """Return the top-level import-name prefixes for every in-repo
    `mcp/<vendor>` connector package (e.g. `("n8n.", "waha.", "_kit.", ...)`).

    DERIVED from the `mcp/` directory listing rather than hand-maintained —
    a silently-missed new connector would otherwise reopen the exact blind
    spot this closes (found `mcp/n8n/build`: `n8n.tools.credential.
    credential_create` monkeypatched in a test was invisible to
    `check_no_self_monkeypatch` because no `mcp/<vendor>` namespace was
    ever "ours"). Per the "hand-maintained lists drift" rule (CLAUDE.md §1
    / `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`).

    Two exclusions, both deliberate:
    - `_MCP_NON_CONNECTOR_DIR_NAMES` (the platform toolkit itself).
    - any dir name that collides with a known EXTERNAL SDK top-level
      import name in `_EXTERNAL_LIB_NAMES` — e.g. `mcp/google` and
      `mcp/supabase` share their vendor's REAL PyPI top-level import name
      (`google.*` / `supabase.*`). Classifying those as "ours" would
      misroute genuine external-SDK patches (the real `supabase-py` /
      `google-auth` clients used all over `products/*/backend`) into
      false-positive self-monkeypatch flags — the exact over-flagging
      failure mode this fix must avoid. `mcp/google` already dodges the
      collision itself (imports its own modules as bare `tools`/
      `settings`, never `google.*` — see `mcp/google/conftest.py`);
      `mcp/supabase`'s tests DO use `supabase.tools.*.get_settings`
      (covered anyway via the `get_settings` boundary-accessor exemption
      above, so excluding the prefix costs no real coverage today) —
      tracked, not silently absorbed: `NOC-REMEDIATE[connector-namespace-collision]`
      would apply if `mcp/supabase` grows non-boundary business-logic
      patches that need catching.
    """
    mcp_dir = root / "mcp"
    if not mcp_dir.is_dir():
        return ()
    prefixes: list[str] = []
    for child in sorted(mcp_dir.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name in _MCP_NON_CONNECTOR_DIR_NAMES:
            continue
        if name in _EXTERNAL_LIB_NAMES:
            continue
        if not (child / "__init__.py").exists():
            continue
        prefixes.append(f"{name}.")
    return tuple(prefixes)


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


def _classify_patch_target(
    target: str, extra_our_prefixes: tuple[str, ...] = ()
) -> str:
    """Return 'ours' / 'boundary' / 'external' / 'external-via-ours' / 'unknown'.

    `extra_our_prefixes` extends `_OUR_MODULE_PREFIXES` for this call — used
    by `check_no_self_monkeypatch` to fold in the per-repo-root DERIVED
    `mcp/<vendor>` connector prefixes (`_discover_connector_module_prefixes`)
    without baking a specific worktree's connector roster into the module
    constant.
    """
    if not any(
        target.startswith(p) for p in (*_OUR_MODULE_PREFIXES, *extra_our_prefixes)
    ):
        return "external"
    if _is_boundary_accessor_target(target):
        return "boundary"
    if _has_external_lib_segment(target):
        return "external-via-ours"
    return "ours"


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
