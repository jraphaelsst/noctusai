"""Deny a NEW route or table that declares no access tier, BEFORE it lands (PreToolUse, fail-closed).

The construction half of the access-tier gate (KB § PATTERNS/security/access-tiers.md): the keepers
(`check_access_tier_routes/_tables`) are the commit/CI backstop; this refuses at the first line, so a member-gated
Platform-IP route or an `authenticated`-granted definition table is never written and "found out late".

STDLIB-ONLY (runs under the hook's bare python3 via `scripts/hooks/claude-guard-access-tier.py`). It judges ONLY what
THIS call adds (diff-scoped, like `test_seam_guard`): a pre-existing undeclared route never blocks an unrelated edit.

* backend `.py` (products/*/backend, seed/**/backend; never tests/migrations): each ADDED route decorator needs tier
  evidence in its handler window -- a gate from the registry's `DEP_TIERS`, a gate-shaped helper call, a signature
  verify, `@access_tier(...)` (public needs a category from the closed allowlist), a module `ACCESS_TIER`, or a router-level `dependencies=[Depends(<gate>)]`.
* migrations `.sql`: each ADDED `CREATE TABLE` needs `COMMENT ON TABLE <t> IS 'tier:<x>'` AND an explicit
  GRANT/REVOKE naming it (no inheriting default privileges) in the same migration.

Escapes (a suppression carries its reason): `# access-tier-ok: <reason>` on/above the decorator;
`-- noc-allow: access-tier-table — <reason>` in the migration. Env `NOCTUS_ALLOW_ACCESS_TIER=1` for a human override.
"""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path
from typing import Any

ALLOW_ENV = "NOCTUS_ALLOW_ACCESS_TIER"
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
_REGISTRY = Path(__file__).resolve().parents[5] / "seed/lib/backend/noctusai_lib/api/access_tiers.py"
_ROUTE_RE = re.compile(r"^[ \t]*@\w+(?:\.\w+)*\.(?:get|post|put|patch|delete|websocket)\(", re.M)
_GATE_SHAPE = re.compile(r"\b_?(?:require|assert|ensure|authorize|authenticate)_\w+\(|\bget_current_\w+|\w+_editor\(|\w+_context\(|\w+_caller\(")
_ESCAPE_PY = re.compile(r"#\s*access-tier-ok:\s*\S+")
_ESCAPE_SQL = re.compile(r"--\s*noc-allow:\s*access-tier-table\s*[—-]\s*\S+")
_CREATE_TABLE = re.compile(r"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(?:([\w-]+)\"?\.\"?)?([\w-]+)", re.I)


def _registry():
    spec = importlib.util.spec_from_file_location("_access_tiers_registry", _REGISTRY)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _surface(path: str) -> str | None:
    p = path.replace("\\", "/")
    if re.search(r"/(tests?|migrations|node_modules)/|/conftest\.py$|/test_[^/]*\.py$", p) and not p.endswith(".sql"):
        return None
    if p.endswith(".sql") and re.search(r"products/[^/]+/backend/migrations/[^/]+\.sql$", p):
        return "sql"
    if p.endswith(".py") and re.search(r"(?:^|/)(?:products/[^/]+/backend|seed/(?:framework|lib)/backend)/", p):
        return "py"
    return None


def _added_text(tool_name: str, tool_input: dict[str, Any]) -> tuple[str, str]:
    """(added text, text of the file as it will be) -- best effort, diff-scoped."""
    path = tool_input.get("file_path", "")
    try:
        disk = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    except (OSError, UnicodeDecodeError):
        disk = ""
    if tool_name == "Write":
        new = tool_input.get("content")
        new = new if isinstance(new, str) else ""
        old_lines = set(disk.splitlines())
        return "\n".join(l for l in new.splitlines() if l not in old_lines) if disk else new, new
    edits = tool_input.get("edits") if tool_name == "MultiEdit" else [tool_input]
    added = "\n".join(e.get("new_string", "") for e in (edits or []) if isinstance(e, dict))
    return added, disk + "\n" + added


_BARE_ROUTER = re.compile(r"(?<![\w.])APIRouter\s*\(")


def _py_findings(added: str, whole: str, reg) -> list[str]:
    out_bare: list[str] = []
    if _BARE_ROUTER.search(added) and not _ESCAPE_PY.search(added):
        out_bare.append("a bare `APIRouter(...)` is the restricted API: create it with `make_router(tier=...)` "
                        "(noctusai_lib.api.access_tiers; `tier` is a required argument)")
    names = set(reg.DEP_TIERS) | set(reg.SIGNATURE_CALLS)
    name_re = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b")
    module_declared = bool(re.search(r"^ACCESS_TIER\s*=", whole, re.M))
    router_gated = bool(re.search(r"(?:APIRouter|include_router)\([^)]*dependencies\s*=", whole, re.S))
    out: list[str] = []
    lines = added.splitlines()
    starts = [m.start() for m in _ROUTE_RE.finditer(added)]
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(added)
        window = added[st:end]
        head = added[max(0, st - 200):st]
        if module_declared or router_gated or _ESCAPE_PY.search(head + window[:200]):
            continue
        if re.search(r"access_tier\(\s*[\"']public[\"']", window) and not re.search(r"category\s*=\s*[\"'](?:landing|auth|pricing-checkout|legal-consent|lead-capture|token-link)[\"']", window):
            out.append("public route without a category from the closed allowlist (landing|auth|pricing-checkout|legal-consent|lead-capture|token-link): " + window.strip().splitlines()[0][:80])
            continue
        if name_re.search(window) or "access_tier(" in window or _GATE_SHAPE.search(window):
            continue
        out.append(window.strip().splitlines()[0][:100])
    return out_bare + out


def _sql_findings(added: str, whole: str) -> list[str]:
    if _ESCAPE_SQL.search(whole):
        return []
    out: list[str] = []
    for m in _CREATE_TABLE.finditer(added):
        schema, table = m.group(1), m.group(2)
        qual = f"{schema}.{table}" if schema else table
        tbl = re.escape(table)
        has_tier = re.search(r"COMMENT\s+ON\s+TABLE\s+[^;]*\b" + tbl + r"\b[^;]*IS\s+'tier:(?:platform|org|service|public)'", whole, re.I | re.S)
        has_grant = re.search(r"\b(?:GRANT|REVOKE)\b[^;]*\bON\b[^;]*\b" + tbl + r"\b", whole, re.I | re.S)
        if not has_tier or not has_grant:
            miss = ([] if has_tier else ["`COMMENT ON TABLE " + qual + " IS 'tier:platform|org|service|public';`"]) + \
                   ([] if has_grant else ["an explicit GRANT/REVOKE on it (Platform IP: `REVOKE ALL ON " + qual + " FROM authenticated, anon;`)"])
            out.append(f"table `{qual}` is missing " + " and ".join(miss))
    return out


def decide(tool_name: str, tool_input: dict[str, Any] | None = None, cwd: str | None = None,
           allow_override: bool | None = None) -> dict[str, Any] | None:
    """None to allow; a dict with `reason` to deny."""
    if allow_override is None:
        allow_override = os.environ.get(ALLOW_ENV, "") == "1"
    if allow_override or tool_name not in _WRITE_TOOLS:
        return None
    tool_input = tool_input or {}
    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return None
    kind = _surface(path)
    if kind is None:
        return None
    added, whole = _added_text(tool_name, tool_input)
    if not added.strip():
        return None
    reg = _registry()
    findings = _py_findings(added, whole, reg) if kind == "py" else _sql_findings(added, whole)
    if not findings:
        return None
    what = "route" if kind == "py" else "table"
    fix = ("put it behind a gate dependency (`require_platform_admin` for Platform IP: prompts, evals, config; "
           "`get_current_user_org`/`require_member` for a customer's own data), or declare "
           "`@access_tier(\"public\", reason=..., category=...)` (noctusai_lib.api.access_tiers)") if kind == "py" else \
          "declare the tier and the grants in the migration"
    return {"reason": (
        f"{path}: new {what} without a declared access tier (default deny). "
        + "; ".join(findings[:5]) + f". Fix: {fix}. Whose data is this -- platform | org | service | public? "
        "KB § PATTERNS/security/access-tiers.md. A reviewed exception: `# access-tier-ok: <reason>` "
        "(or `-- noc-allow: access-tier-table — <reason>`)."
    )}
