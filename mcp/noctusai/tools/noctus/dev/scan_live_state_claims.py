"""noctus.dev.scan_live_state_claims — resolve LIVE-STATE claims in our docs
against the live source of truth (advisory, read-only, non-gating).

THE RULE (owner, 2026-10-07): org and product state must never go stale —
when an org or product changes, docs (memory, KB, product guide, catalog) and
code are aligned in the same change and VERIFIED against the live source
before the work counts as done. The commit-time half is the keeper
``check_product_guide_cochange``; THIS tool is the verification half: it
extracts claims a doc makes about live state and checks each one.

Claim kinds (heuristic, deliberately conservative — an advisory query, not a
gate; it needs no N>=3 recurrence):

* ``org``   — an org UUID (full) or 8-hex prefix written NEAR the word "org"
  → resolved against ``public.organizations``; a name from the same line is
  cross-checked against the resolved row.
* ``email`` — an email → resolved against ``public.noctus_users`` (a role word
  on the same line is cross-checked against ``org_role``).
* ``prod_sha`` — a 7-40 hex SHA near ``prod``/``production``/``deployed``/``live``
  → compared with the ``origin/prod`` tip. Lines that read as HISTORY (dated,
  "shipped", "released"...) are ``unverifiable`` — history is not a claim of
  current state.

Statuses: ``ok`` | ``mismatch`` | ``unknown`` (live source answered, nothing
matched / ambiguous) | ``unverifiable`` (could not ask: no credentials, query
failed, historical line, unresolvable SHA).

IO seams: the Supabase side reuses ``migrate_product``'s ``SqlExecutor``
(Fake + Real + ``make_sql_executor`` factory); the prod tip is an injectable
``prod_sha_resolver``. Read-only by construction (two SELECTs + ``git
rev-parse``/``merge-base``). KB § PATTERNS/common/live-state-alignment.md.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from . import migrate_product as _mp

logger = logging.getLogger(__name__)

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_HEX8 = r"(?<![0-9a-zA-Z-])[0-9a-fA-F]{8}(?![0-9a-zA-Z])"
_ORG_RE = re.compile(
    r"\b(?:org(?:s|anization|aniza[cç][aã]o)?|org_id)\b[^\n]{0,40}?(?P<id>" + _UUID + "|" + _HEX8 + ")",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_EMAIL_IGNORE = re.compile(
    r"(^noreply@|^no-reply@|@(?:c|g)\.us$|@s\.whatsapp\.net$|@lid$|@example\.|@anthropic\.com$|noreply\.github\.com$|@localhost$|@test\.|@domain\.)",
    re.IGNORECASE,
)
_SHA_RE = re.compile(
    r"\b(?:prod|production|deployed|live)\b[^\n]{0,40}?(?<![0-9a-zA-Z])(?P<sha>[0-9a-f]{7,40})(?![0-9a-zA-Z])",
    re.IGNORECASE,
)
_HISTORY_RE = re.compile(
    r"\b20\d\d-\d\d-\d\d\b|\b(?:shipped|released?|promoted|was|were|landed|merged|since|incident)\b",
    re.IGNORECASE,
)
_ROLE_RE = re.compile(r"\b(superadmin|owner|admin|member|membro|viewer)\b", re.IGNORECASE)

_ORGS_SQL = "SELECT id::text AS id, nome FROM public.organizations;"
_USERS_SQL = "SELECT email, org_id::text AS org_id, org_role FROM public.noctus_users;"

ProdShaResolver = Callable[[], "tuple[str | None, str]"]
IsAncestor = Callable[[str, str], bool]


def _has_letter_and_digit(s: str) -> bool:
    return any(c.isdigit() for c in s) and any(c.isalpha() for c in s)


def default_memory_dir(root: Path) -> Path:
    """The auto-memory dir of the PRIMARY checkout (`~/.claude/projects/<path-with-dashes>/memory`)."""
    primary = root
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root, capture_output=True, text=True, timeout=15, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            primary = Path(out.stdout.strip()).parent
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("scan_live_state_claims: cannot resolve primary checkout (%s)", exc)
    return Path.home() / ".claude" / "projects" / str(primary).replace("/", "-") / "memory"


def _git_prod_tip(root: Path, ref: str = "origin/prod") -> "tuple[str | None, str]":
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=root, capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git rev-parse failed: {exc}"
    sha = out.stdout.strip()
    return (sha, f"{ref} = {sha[:12]}") if out.returncode == 0 and sha else (None, f"cannot resolve {ref}")


def _collect_files(root: Path, memory_dir: Path) -> list[Path]:
    files: list[Path] = []
    if memory_dir.is_dir():
        files += sorted(memory_dir.glob("*.md"))
    landscape = root / "KNOWLEDGE-BASE" / "CONTEXT" / "02-LANDSCAPE.md"
    if landscape.is_file():
        files.append(landscape)
    products = root / "products"
    if products.is_dir():
        for pdir in sorted(d for d in products.iterdir() if d.is_dir() and not d.name.startswith(".")):
            readme = pdir / "README.md"
            if readme.is_file():
                files.append(readme)
    try:
        from .compliance import derive_help_chat_guides
        guides, _unresolved = derive_help_chat_guides(root)
    except Exception as exc:  # advisory tool: a derivation failure must not hide the rest
        logger.warning("scan_live_state_claims: guide derivation failed (%s)", exc)
        guides = {}
    for rels in guides.values():
        for rel in rels:
            p = root / rel
            if p.is_file() and p not in files:
                files.append(p)
    return files


def scan_live_state_claims(
    *,
    root: Path | None = None,
    memory_dir: Path | None = None,
    executor: "_mp.SqlExecutor | None" = None,
    prod_sha_resolver: ProdShaResolver | None = None,
    is_ancestor: IsAncestor | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    include_ok: bool = False,
    files: list[Path] | None = None,
) -> dict[str, Any]:
    """Scan docs for live-state claims and resolve each against the live source."""
    from settings import REPO_ROOT

    root = root or REPO_ROOT
    memory_dir = memory_dir if memory_dir is not None else default_memory_dir(root)
    errors: list[str] = []

    if executor is None:
        executor = _mp.make_sql_executor(project_ref=project_ref)
    orgs: dict[str, str] | None = None
    users: dict[str, dict[str, str]] | None = None
    db_reason = ""
    if executor is None:
        db_reason = "not_configured: no supabase_access_token resolved (NOC-REMEDIATE[credentials])"
        errors.append(db_reason)
    else:
        r = executor.execute(_ORGS_SQL)
        if r.get("ok"):
            orgs = {str(row["id"]).lower(): str(row.get("nome") or "") for row in (r.get("rows") or [])}
        else:
            db_reason = f"organizations query failed: {r.get('error')}"
            errors.append(db_reason)
        r = executor.execute(_USERS_SQL)
        if r.get("ok"):
            users = {
                str(row["email"]).lower(): {"org_id": str(row.get("org_id") or "").lower(),
                                            "org_role": str(row.get("org_role") or "")}
                for row in (r.get("rows") or []) if row.get("email")
            }
        else:
            errors.append(f"noctus_users query failed: {r.get('error')}")
            db_reason = db_reason or errors[-1]

    tip, tip_detail = (prod_sha_resolver or (lambda: _git_prod_tip(root)))()
    if tip is None:
        errors.append(f"prod tip unresolved: {tip_detail}")

    def _anc(claim: str, tip_sha: str) -> bool:
        if is_ancestor is not None:
            return is_ancestor(claim, tip_sha)
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", claim, tip_sha],
            cwd=root, capture_output=True, timeout=15, check=False,
        )
        return out.returncode == 0

    rows: list[dict[str, Any]] = []

    def _row(path: Path, line_no: int, kind: str, claim: str, live: str, status: str, note: str = "") -> None:
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        rows.append({"file": rel, "line": line_no, "kind": kind, "claim": claim,
                     "live": live, "status": status, "note": note})

    file_list = files if files is not None else _collect_files(root, memory_dir)
    for path in file_list:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("scan_live_state_claims: cannot read %s (%s)", path, exc)
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            for m in _ORG_RE.finditer(line):
                cid = m.group("id").lower()
                if len(cid) == 8 and not _has_letter_and_digit(cid):
                    continue
                if orgs is None:
                    _row(path, n, "org", cid, "", "unverifiable", db_reason)
                    continue
                hits = [(oid, nome) for oid, nome in orgs.items() if oid == cid or (len(cid) == 8 and oid.startswith(cid))]
                if not hits:
                    _row(path, n, "org", cid, "", "mismatch", "no organization with this id")
                elif len(hits) > 1:
                    _row(path, n, "org", cid, f"{len(hits)} orgs match prefix", "unknown", "ambiguous prefix")
                else:
                    oid, nome = hits[0]
                    named = [nm for nm in orgs.values() if len(nm) >= 5 and re.search(r"\b" + re.escape(nm) + r"\b", line, re.IGNORECASE)]
                    if named and nome not in named:
                        _row(path, n, "org", cid, f"{oid} ({nome})", "unknown",
                             f"line names org(s) {named} but the id resolves to '{nome}' "
                             f"(may be a cliente/product name, not an org)")
                    else:
                        _row(path, n, "org", cid, f"{oid} ({nome})", "ok")
            for m in _EMAIL_RE.finditer(line):
                email = m.group(0).lower().rstrip(".")
                if _EMAIL_IGNORE.search(email) or not any(ch.isalpha() for ch in email.split("@")[0]):
                    continue
                if users is None:
                    _row(path, n, "email", email, "", "unverifiable", db_reason or "noctus_users unavailable")
                    continue
                u = users.get(email)
                if u is None:
                    _row(path, n, "email", email, "", "unknown", "not a noctus_users row")
                    continue
                said = {r.lower() for r in _ROLE_RE.findall(line)}
                live = f"org {u['org_id'][:8]} role={u['org_role']}"
                if said and u["org_role"].lower() not in said:
                    _row(path, n, "email", email, live, "mismatch", f"line says {sorted(said)}")
                else:
                    _row(path, n, "email", email, live, "ok")
            for m in _SHA_RE.finditer(line):
                sha = m.group("sha").lower()
                if not _has_letter_and_digit(sha) and len(sha) < 40:
                    continue
                if _HISTORY_RE.search(line):
                    _row(path, n, "prod_sha", sha, tip or "", "unverifiable", "historical line, not a current-state claim")
                elif tip is None:
                    _row(path, n, "prod_sha", sha, "", "unverifiable", tip_detail)
                elif tip.startswith(sha):
                    _row(path, n, "prod_sha", sha, tip[:12], "ok")
                else:
                    try:
                        behind = _anc(sha, tip)
                    except (OSError, subprocess.SubprocessError):
                        behind = False
                    _row(path, n, "prod_sha", sha, tip[:12], "mismatch" if behind else "unverifiable",
                         "prod has moved past this sha" if behind else "sha not an ancestor of the prod tip / not in repo")

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    order = {"mismatch": 0, "unknown": 1, "unverifiable": 2, "ok": 3}
    shown = sorted((r for r in rows if include_ok or r["status"] != "ok"), key=lambda r: order[r["status"]])
    return {
        "ok": counts.get("mismatch", 0) == 0,
        "status": "mismatch" if counts.get("mismatch") else ("partial" if errors else "clean"),
        "files_scanned": len(file_list),
        "claims_total": len(rows),
        "counts": counts,
        "claims": shown,
        "errors": errors,
        "prod_tip": tip_detail,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_live_state_claims",
        description=(
            "Advisory, read-only. Scans auto-memory, KB 02-LANDSCAPE, product READMEs and "
            "help-chat guides for live-state claims — org UUIDs / 8-hex prefixes near 'org', "
            "emails, prod SHAs — and resolves each against the live source (Supabase "
            "public.organizations + public.noctus_users, origin/prod tip). Output per claim: "
            "file:line, claim, live value, status ok|mismatch|unknown|unverifiable (non-ok rows "
            "only unless include_ok). Run it before calling any org/product state change done "
            "(KB § PATTERNS/common/live-state-alignment.md). No credentials ⇒ org/email claims "
            "report unverifiable, never a faked ok."
        ),
    )
    def _scan_live_state_claims(include_ok: bool = False,
                                project_ref: str = "nyplttplcoyiiqjrvtiw") -> dict:
        return scan_live_state_claims(include_ok=include_ok, project_ref=project_ref)


__all__ = ["scan_live_state_claims", "default_memory_dir", "register"]
