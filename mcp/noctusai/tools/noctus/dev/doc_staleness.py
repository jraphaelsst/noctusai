"""`noctus.dev.doc_staleness` — the deterministic, CI-blocking doc-staleness gate.

WHY (owner order 2026-10-19: "gate stale docs, so CI lets us know and we update
docs and don't leave them stale never"). Three docs were found stale at once:
`products/agents/README.md` + `MASTER-PROMPT.md` ("scaffold only / PLANNED" over a
live studio + channels API), the `02-LANDSCAPE.md` agents row (missing the SDR
agent), and `products/social-wiring/projects/maya-blocks/CONTRACT.md` ("nothing
implemented yet" after S2-S4 shipped). `doc_to_code_drift` (embedding cosine,
advisory) could not have caught any of them; line-diffs never do — only ONE side
changes at a time.

Four deterministic legs, ONE mechanism (extends — does not replace — the existing
pieces: the `check_product_guide_cochange` range-keeper idiom + `Docs-Reviewed:`
trailer escape, `commit-range-keepers` CI job, `kb_sync`'s "pointer must resolve"
principle widened to every living doc, `doc_to_code_drift` stays the semantic
advisory layer):

  1. COUPLING   (range)  code under a doc's coverage changed MATERIALLY in
                         `<base>..<tip>` and none of its covering docs changed ->
                         fail, naming the docs. Ack: `Docs-Reviewed: <doc|glob> —
                         <reason>` trailer on any commit of the range.
  2. CLAIMS     (tree)   repo paths a living doc cites must exist; "scaffold only /
                         nothing implemented / NOT applied" claims are cross-checked
                         against the code (route count, resolved contract paths,
                         `migrations-applied.json`).
  3. RATCHET    (tree)   the stale set that existed when the gate shipped lives in
                         `mcp/noctusai/tests/doc_staleness_baseline.json` — it may only
                         SHRINK; only NEW staleness fails.
  4. AGE        (tree)   warning list: docs whose covered code moved >= N commits
                         and >= D days after the doc's last touch.

Coverage ("which code does this doc describe?") is declared, never guessed:
frontmatter `covers: [globs]`, plus derived defaults (`products/<slug>/README.md` and
`MASTER-PROMPT.md` cover that product's app code + migrations; a `CONTRACT.md` covers
the code paths it cites) plus `STRUCTURAL_RULES` for cross-cutting inventories
(the `02-LANDSCAPE.md` roster).

Depth: `KB § PATTERNS/common/doc-staleness-gate.md`.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

BASELINE_REL = "mcp/noctusai/tests/doc_staleness_baseline.json"

#: Commit-message trailer: `Docs-Reviewed: <doc path | glob> — <reason>` (reason mandatory).
DOCS_REVIEWED_RE = re.compile(
    r"^Docs-Reviewed:[ \t]*(\S+)[ \t]*(?:—|--|-|:)[ \t]*(\S.*)$", re.MULTILINE
)

CODE_EXTS = (".py", ".ts", ".tsx", ".sql")
#: A modified file is MATERIAL only if a changed line adds/removes one of these
#: shapes (route, table, public symbol) -- not every line (owner: "not every line").
SIGNATURE_RE = re.compile(
    r"^\s*(@(?:\w+\.)?(?:get|post|put|patch|delete|route|websocket)\b"
    r"|(?:async\s+)?def\s+[a-zA-Z]\w*\s*\("      # public def (a leading _ is private)
    r"|class\s+[A-Za-z]\w*"
    r"|export\s+(?:default\s+|async\s+)?(?:function|const|class|interface|type)\b"
    r"|create\s+table\b|alter\s+table\b|create\s+(?:or\s+replace\s+)?function\b"
    r"|<Route\b)",
    re.IGNORECASE,
)

#: Cross-cutting inventories: (docs, covers, material-kind). `added_removed` = only a
#: file ADDED/DELETED/RENAMED in the covered glob counts (not edits).
STRUCTURAL_RULES: tuple[dict[str, Any], ...] = (
    {
        "name": "landscape-roster",
        "docs": ["KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md"],
        "covers": [
            "products/*/backend/app/routers/*.py",
            "products/*/backend/app/studio/*.py",
            "products/*/backend/app/channels/*.py",
        ],
        "material": "added_removed",
    },
)

#: Living-doc discovery. Historical/point-in-time files are NOT living docs.
_EXCLUDED_PARTS = frozenset({
    "node_modules", "archive", "proposals", ".venv", "venv", "fixtures",
    "templates", "__pycache__", "dist", "contract-fixtures", "packages",
})
_EXCLUDED_NAMES = frozenset({
    "findings.md", "improvements.md", "CHANGELOG.md", "PROJECT-HISTORY.md",
    "LEARNINGS.md", "SKILL.md",
})
_LIVING_ROOTS = ("products/", "projects/", "KNOWLEDGE-BASE/", "CLAUDE/", "core/")

# claim regexes -----------------------------------------------------------------
_TICK_RE = re.compile(r"`([^`\n]{3,200})`")
_PATH_ROOTS = (
    "products/", "seed/", "mcp/", "scripts/", "deploy/", ".github/", ".claude/",
    "KNOWLEDGE-BASE/", "projects/", "core/", "docs/", "templates/",
)
_PLACEHOLDER = frozenset("<>{}*$|()[]!?, ")
_SCAFFOLD_CLAIM_RE = re.compile(
    r"scaffold(?:ed)?\s+only|only\s+scaffold|domain code is planned,?\s+not built"
    r"|every\s+domain\s+item\s+below\s+is\s+PLANNED|not\s+(?:yet\s+)?built\b",
    re.IGNORECASE,
)
_NOT_IMPL_CLAIM_RE = re.compile(
    r"nothing\s+(?:is\s+)?implemented(?:\s+yet)?|nothing\s+is\s+built"
    r"|not\s+implemented\s+yet|no\s+code\s+yet",
    re.IGNORECASE,
)
_MIG_NOT_APPLIED_RE = re.compile(
    r"(\d{2,4}_[\w-]+\.sql)[^\n]{0,80}?\b(NOT\s+applied|unapplied|not\s+yet\s+applied|pending\s+apply)\b",
    re.IGNORECASE,
)
_ROUTE_DECORATOR_RE = re.compile(r"^\s*@\w+\.(?:get|post|put|patch|delete)\(", re.MULTILINE)


@dataclass
class Doc:
    rel: str
    text: str
    covers: list[str] = field(default_factory=list)


def _git(root: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


# ── discovery ───────────────────────────────────────────────────────────────────
def _tracked(root: Path) -> list[str]:
    r = _git(root, "ls-files", "-z")
    if r is not None and r.returncode == 0 and r.stdout:
        return [p for p in r.stdout.split("\0") if p]
    return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


def _active_slugs(root: Path) -> set[str]:
    from .compliance import _active_product_dirs
    pdir = root / "products"
    return {p.name for p in _active_product_dirs(pdir)} if pdir.is_dir() else set()


def is_living_doc(rel: str, active: set[str]) -> bool:
    if not rel.endswith(".md") or not rel.startswith(_LIVING_ROOTS):
        return False
    parts = rel.split("/")
    if any(p in _EXCLUDED_PARTS for p in parts) or parts[-1] in _EXCLUDED_NAMES:
        return False
    if rel.startswith("products/"):
        # asleep products get no gate (product-working-scope); products/seed ships templates
        return len(parts) > 2 and parts[1] in active
    return True


def parse_covers(text: str) -> list[str]:
    """`covers:` from a leading YAML frontmatter block (inline list or `- item` list)."""
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---", 4)
    if end < 0:
        return []
    out: list[str] = []
    in_list = False
    for line in text[4:end].splitlines():
        m = re.match(r"^covers:\s*(.*)$", line)
        if m:
            rest = m.group(1).strip()
            if rest.startswith("["):
                out += [x.strip().strip("'\"") for x in rest.strip("[]").split(",") if x.strip()]
                in_list = False
            else:
                in_list = rest == ""
            continue
        if in_list:
            li = re.match(r"^\s+-\s+(.+?)\s*$", line)
            if li:
                out.append(li.group(1).strip("'\""))
            elif line.strip() and not line.startswith(" "):
                in_list = False
    return out


def load_docs(root: Path) -> list[Doc]:
    active = _active_slugs(root)
    docs: list[Doc] = []
    for rel in sorted(_tracked(root)):
        if not is_living_doc(rel, active):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        docs.append(Doc(rel=rel, text=text, covers=parse_covers(text)))
    return docs


# ── coverage ────────────────────────────────────────────────────────────────────
def _cited_code_paths(root: Path, doc: Doc) -> tuple[list[str], list[str]]:
    """(existing, missing) repo-relative code paths cited in backticks."""
    found: list[str] = []
    for m in _TICK_RE.finditer(doc.text):
        tok = _normalise_path_token(m.group(1))
        if tok and tok not in found:
            found.append(tok)
    existing = [t for t in found if (root / t).exists()]
    missing = [t for t in found if t not in existing]
    return existing, missing


def _normalise_path_token(tok: str) -> str | None:
    tok = tok.strip()
    if any(c in _PLACEHOLDER for c in tok) or not tok.startswith(_PATH_ROOTS):
        return None
    tok = re.sub(r"(::[\w.]+|:\d+(?:-\d+)?)$", "", tok).rstrip("/.,;")
    if "/" not in tok or not re.search(r"[\w]$", tok):
        return None
    return tok


def doc_coverage(root: Path, doc: Doc) -> list[str]:
    """Glob list of the code a doc is accountable for (declared + derived)."""
    cov = list(doc.covers)
    parts = doc.rel.split("/")
    name = parts[-1]
    if parts[0] == "products" and len(parts) == 3 and name in ("README.md", "MASTER-PROMPT.md"):
        slug = parts[1]
        cov += [f"products/{slug}/backend/app/**", f"products/{slug}/frontend/src/**",
                f"products/{slug}/backend/migrations/*.sql"]
    if name == "CONTRACT.md":
        existing, _ = _cited_code_paths(root, doc)
        for p in existing:
            if p.endswith(".md"):
                continue
            cov.append(f"{p}/**" if (root / p).is_dir() else p)
    return cov


def _glob_match(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/") or fnmatch.fnmatch(path, pattern[:-3] + "/*")
    return fnmatch.fnmatch(path, pattern)


# ── change classification ──────────────────────────────────────────────────────
@dataclass
class Change:
    path: str
    status: str  # A | D | M | R
    reason: str


def material_changes(root: Path, rev_range: str) -> tuple[list[Change], list[str], str | None]:
    """(material code changes, ALL changed paths, error) for the NET diff of the range."""
    from .compliance import _TEST_FILE_RE
    ns = _git(root, "diff", "--name-status", "-M", "--no-renames", rev_range)
    if ns is None or ns.returncode != 0:
        return [], [], f"cannot diff {rev_range!r}: {(ns.stderr if ns else 'git unavailable').strip()}"
    all_paths: list[str] = []
    cand: dict[str, str] = {}
    for line in ns.stdout.splitlines():
        bits = line.split("\t")
        if len(bits) < 2:
            continue
        st, p = bits[0][0], bits[-1]
        all_paths.append(p)
        if p.endswith(CODE_EXTS) and not _TEST_FILE_RE.search(p) and not p.endswith("__init__.py"):
            cand[p] = st
    changes = [Change(p, st, "added" if st == "A" else "removed") for p, st in cand.items() if st in "AD"]
    modified = [p for p, st in cand.items() if st == "M"]
    for p in modified:
        d = _git(root, "diff", "-U0", rev_range, "--", p)
        if d is None or d.returncode != 0:
            changes.append(Change(p, "M", "diff unreadable (treated as material)"))
            continue
        plus, minus = set(), set()
        for ln in d.stdout.splitlines():
            if ln[:1] in "+-" and not ln.startswith(("+++", "---")) and SIGNATURE_RE.match(ln[1:]):
                (plus if ln[0] == "+" else minus).add(_signature_identity(ln[1:]))
        sig = sorted(plus ^ minus)  # a re-formatted/moved signature is not a change
        if sig:
            changes.append(Change(p, "M", f"signature change: {sig[0][:70]}"))
    return changes, all_paths, None


def _signature_identity(line: str) -> str:
    """Name-level identity of a signature line: `def f(a, b)` and `def f(a)` differ only
    in args -> same identity (arg churn is not a documented-surface change); a decorator
    keeps its full text (the route path IS the surface)."""
    t = line.strip()
    m = re.match(r"(?:async\s+)?(def|class)\s+(\w+)", t) or re.match(
        r"export\s+(?:default\s+|async\s+)?(function|const|class|interface|type)\s+(\w+)", t)
    return f"{m.group(1)} {m.group(2)}" if m else re.sub(r"\s+", " ", t)


def range_trailers(root: Path, rev_range: str) -> list[tuple[str, str]]:
    r = _git(root, "log", "--format=%B%x1e", rev_range)
    if r is None or r.returncode != 0:
        return []
    return [(m.group(1), m.group(2)) for m in DOCS_REVIEWED_RE.finditer(r.stdout)]


def check_range(root: Path, rev_range: str) -> list[dict]:
    """Leg 1 -- change-coupling over `<base>..<tip>` (net diff)."""
    if ".." not in rev_range or "..." in rev_range:
        return [_issue("<range>", f"needs a `<base>..<tip>` range, got {rev_range!r}")]
    changes, all_paths, err = material_changes(root, rev_range)
    if err:
        return [_issue(rev_range, err + "; fail-closed")]
    if not changes:
        return []
    changed = set(all_paths)
    acks = range_trailers(root, rev_range)
    docs = load_docs(root)
    issues: list[dict] = []
    # per-doc: material changes inside its coverage, doc itself untouched
    for doc in docs:
        if doc.rel in changed:
            continue
        cov = doc_coverage(root, doc)
        hits = [c for c in changes if any(_glob_match(c.path, g) for g in cov)]
        if not hits or _acked(doc.rel, acks):
            continue
        issues.append(_coupling_issue(doc.rel, hits))
    for rule in STRUCTURAL_RULES:
        hits = [c for c in changes if c.status in "AD"
                and any(_glob_match(c.path, g) for g in rule["covers"])]
        for dpath in rule["docs"]:
            if not hits or dpath in changed or _acked(dpath, acks) or not (root / dpath).is_file():
                continue
            issues.append(_coupling_issue(dpath, hits, rule["name"]))
    return issues


def _acked(doc_rel: str, acks: list[tuple[str, str]]) -> bool:
    return any(fnmatch.fnmatch(doc_rel, spec) for spec, _reason in acks)


def _coupling_issue(doc_rel: str, hits: list[Change], rule: str | None = None) -> dict:
    sample = "; ".join(f"{c.path} ({c.reason})" for c in hits[:3]) + (" ..." if len(hits) > 3 else "")
    return {
        "kind": "coupling", "doc": doc_rel, "severity": "high",
        "id": f"coupling::{doc_rel}",
        "issue": (f"`{doc_rel}` documents code that changed materially in this range "
                  f"({len(hits)} change(s): {sample}) but the doc was not touched. Update it "
                  f"to match the code, or acknowledge with a commit trailer "
                  f"`Docs-Reviewed: {doc_rel} — <why it is still accurate>`."
                  + (f" [rule {rule}]" if rule else "")),
    }


def _issue(doc: str, msg: str, kind: str = "range", severity: str = "high", detail: str = "") -> dict:
    return {"kind": kind, "doc": doc, "severity": severity, "id": f"{kind}::{doc}::{detail}" if detail else f"{kind}::{doc}",
            "issue": msg}


# ── claims ──────────────────────────────────────────────────────────────────────
def _product_of(rel: str) -> str | None:
    p = rel.split("/")
    return p[1] if p[0] == "products" and len(p) > 2 else None


def _route_count(root: Path, slug: str) -> int:
    app = root / "products" / slug / "backend" / "app"
    n = 0
    if app.is_dir():
        for f in app.rglob("*.py"):
            if "tests" in f.parts:
                continue
            try:
                n += len(_ROUTE_DECORATOR_RE.findall(f.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    return n


def _applied_migrations(root: Path) -> set[str]:
    out: set[str] = set()
    for f in (root / "products").glob("*/backend/migrations-applied.json"):
        try:
            out |= set((json.loads(f.read_text(encoding="utf-8")).get("applied") or {}))
        except (OSError, ValueError):
            continue
    return out


def check_claims(root: Path, docs: list[Doc] | None = None) -> list[dict]:
    """Leg 2 -- deterministic claim checks over every living doc."""
    docs = docs if docs is not None else load_docs(root)
    applied = _applied_migrations(root)
    issues: list[dict] = []
    for doc in docs:
        name = doc.rel.rsplit("/", 1)[-1]
        slug = _product_of(doc.rel)
        # (a) cited repo paths must exist (reality docs only -- project docs legitimately
        #     describe code that is not built yet; those are judged by (b)/(c))
        if not doc.rel.startswith("projects/") and "/projects/" not in doc.rel:
            _, missing = _cited_code_paths(root, doc)
            for p in missing:
                if _rel_exists(root, doc.rel, p):
                    continue
                issues.append(_issue(doc.rel, f"`{doc.rel}` cites `{p}`, which does not exist in the tree "
                                     f"(renamed/deleted?). Fix the reference.", "missing_path", detail=p))
        # (b) "scaffold only / planned" product docs vs the live routes
        if slug and name in ("README.md", "MASTER-PROMPT.md") and doc.rel.count("/") == 2:
            m = _SCAFFOLD_CLAIM_RE.search(doc.text)
            if m:
                routes = _route_count(root, slug)
                if routes >= 3:
                    issues.append(_issue(
                        doc.rel, f"`{doc.rel}` says \"{m.group(0)}\" but `products/{slug}/backend/app` "
                        f"declares {routes} route handlers -- the product is built. Rewrite the status.",
                        "status_contradiction", detail=m.group(0).lower()))
        # (c) "nothing implemented" contracts vs the paths they cite
        if name in ("CONTRACT.md", "PROJECT.md"):
            m = _NOT_IMPL_CLAIM_RE.search(doc.text)
            if m:
                existing, missing = _cited_code_paths(root, doc)
                code_ok = [p for p in existing if not p.endswith(".md")]
                code_all = len(code_ok) + len([p for p in missing if not p.endswith(".md")])
                landed = _impl_commits(root, doc.rel)
                if (len(code_ok) >= 3 and code_all and len(code_ok) / code_all >= 0.5) or landed >= 2:
                    why = (f"{landed} implementation commit(s) naming `{doc.rel.split('/')[-2]}` touched code"
                           if landed >= 2 else
                           f"{len(code_ok)} of the {code_all} code paths it cites already exist (e.g. `{code_ok[0]}`)")
                    issues.append(_issue(
                        doc.rel, f"`{doc.rel}` says \"{m.group(0)}\" but {why}. Update the status header.",
                        "status_contradiction", detail=m.group(0).lower()))
        # (d) "migration X NOT applied" vs migrations-applied.json
        for mm in _MIG_NOT_APPLIED_RE.finditer(doc.text):
            if mm.group(1) in applied:
                issues.append(_issue(
                    doc.rel, f"`{doc.rel}` says migration `{mm.group(1)}` is \"{mm.group(2)}\" but it is "
                    f"recorded in a product's migrations-applied.json.",
                    "migration_state", detail=mm.group(1)))
    return issues


def _impl_commits(root: Path, doc_rel: str) -> int:
    """Non-merge commits that name the doc's project slug AND touched code (not docs)."""
    slug = doc_rel.rsplit("/", 2)[-2]
    prod = _product_of(doc_rel)
    specs = ([f"products/{prod}/backend/app", f"products/{prod}/frontend/src"] if prod
             else ["seed", "products", "mcp"])
    r = _git(root, "log", "--no-merges", "-i", f"--grep={slug}", "--format=%H", "--", *specs)
    return len(r.stdout.split()) if r is not None and r.returncode == 0 else 0


def _rel_exists(root: Path, doc_rel: str, p: str) -> bool:
    d = (root / doc_rel).parent
    return (d / p).exists() or ((root / "products" / (_product_of(doc_rel) or "_") / p).exists())


# ── age backstop ────────────────────────────────────────────────────────────────
def age_report(root: Path, docs: list[Doc] | None = None, min_commits: int = 40,
               min_days: int = 14) -> list[dict]:
    """Leg 4 -- warnings: covered code moved >= min_commits and >= min_days after the doc."""
    docs = docs if docs is not None else load_docs(root)
    acks = _reviewed_times(root)
    out: list[dict] = []
    for doc in docs:
        cov = doc_coverage(root, doc)
        dirs = sorted({_cov_pathspec(g) for g in cov if g})
        if not dirs:
            continue
        last = _git(root, "log", "-1", "--format=%H %ct", "--", doc.rel)
        if last is None or last.returncode != 0 or not last.stdout.strip():
            continue
        sha, ts = last.stdout.split()
        ts_i = max(int(ts), acks.get(doc.rel, 0))
        cnt = _git(root, "rev-list", "--count", "--no-merges", f"--since={ts_i + 1}", "HEAD", "--", *dirs)
        if cnt is None or cnt.returncode != 0:
            continue
        n = int(cnt.stdout.strip() or 0)
        head = _git(root, "log", "-1", "--format=%ct")
        days = (int(head.stdout.strip()) - ts_i) / 86400 if head and head.stdout.strip() else 0
        if n >= min_commits and days >= min_days:
            out.append({"doc": doc.rel, "code_commits_since": n, "days_behind": int(days)})
    return sorted(out, key=lambda r: -r["code_commits_since"])


def _cov_pathspec(glob: str) -> str:
    cut = re.split(r"[*?\[]", glob, 1)[0]
    return cut.rsplit("/", 1)[0] if "/" in cut and not cut.endswith("/") else cut.rstrip("/")


def _reviewed_times(root: Path) -> dict[str, int]:
    r = _git(root, "log", "--grep=^Docs-Reviewed:", "--format=%ct%x1f%B%x1e")
    out: dict[str, int] = {}
    if r is None or r.returncode != 0:
        return out
    for rec in r.stdout.split("\x1e"):
        if "\x1f" not in rec:
            continue
        ts, body = rec.split("\x1f", 1)
        for m in DOCS_REVIEWED_RE.finditer(body):
            if "*" not in m.group(1):
                out[m.group(1)] = max(out.get(m.group(1), 0), int(ts.strip() or 0))
    return out


# ── ratchet ─────────────────────────────────────────────────────────────────────
def load_baseline(root: Path) -> dict[str, str]:
    p = root / BASELINE_REL
    if not p.is_file():
        return {}
    try:
        return dict((json.loads(p.read_text(encoding="utf-8")).get("entries") or {}))
    except (OSError, ValueError):
        return {}


def write_baseline(root: Path, findings: list[dict], mode: str) -> dict:
    """mode 'init' = snapshot the current stale set (only when no baseline exists);
    mode 'shrink' = drop entries no longer found, NEVER add."""
    existing = load_baseline(root)
    current = {f["id"]: f["issue"][:160] for f in findings}
    if mode == "init":
        if existing:
            return {"ok": False, "error": "baseline exists; use mode='shrink' (the ratchet may only shrink)"}
        entries = current
    elif mode == "shrink":
        entries = {k: v for k, v in existing.items() if k in current}
    else:
        return {"ok": False, "error": f"unknown mode {mode!r}"}
    doc = {"_doc": ("Ratchet of doc-staleness findings that existed when the gate shipped (2026-10-19). "
                    "It may only SHRINK: fix a doc, then `--doc-baseline shrink`. New staleness fails CI. "
                    "KB § PATTERNS/common/doc-staleness-gate.md."),
           "entries": dict(sorted(entries.items()))}
    (root / BASELINE_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / BASELINE_REL).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "entries": len(entries), "dropped": len(existing) - len(entries) if mode == "shrink" else 0}


def check_tree(root: Path, with_age: bool = True) -> dict[str, Any]:
    """Legs 2+3+4: claims against the ratchet, plus the age warning list."""
    docs = load_docs(root)
    findings = check_claims(root, docs)
    base = load_baseline(root)
    new = [f for f in findings if f["id"] not in base]
    fixed = sorted(set(base) - {f["id"] for f in findings})
    return {"findings": findings, "new": new, "baselined": len(findings) - len(new),
            "fixed_in_baseline": fixed, "age_warnings": age_report(root, docs) if with_age else [], "docs_scanned": len(docs)}


def suggest(result: dict[str, Any]) -> str:
    """The exact docs to update + the claims that are false (compliance-by-construction)."""
    lines: list[str] = []
    by_doc: dict[str, list[dict]] = {}
    for f in result.get("new", []) + result.get("range", []):
        by_doc.setdefault(f["doc"], []).append(f)
    for doc, fs in sorted(by_doc.items()):
        lines.append(f"UPDATE {doc}")
        lines += [f"    - [{f['kind']}] {f['issue']}" for f in fs]
    return "\n".join(lines) or "nothing to update"


# ── keeper wrapper + MCP ────────────────────────────────────────────────────────
def check_doc_staleness(repo_root: Path | None = None, rev_range: str | None = None) -> list[dict]:
    """Keeper entrypoint: range given -> coupling; else -> NEW claim staleness vs the ratchet."""
    root = repo_root or REPO_ROOT
    if rev_range:
        return check_range(root, rev_range)
    return check_tree(root, with_age=False)["new"]


def register(server) -> None:
    @server.tool(
        name="noctus.dev.doc_staleness",
        description=(
            "Deterministic doc-staleness gate (the CI-blocking sibling of doc_to_code_drift). "
            "rev_range='<base>..<tip>' -> change-coupling (covered code changed materially, covering docs "
            "untouched; ack via `Docs-Reviewed: <doc> — <reason>` trailer). No range -> claim checks over every "
            "living doc (cited paths exist; 'scaffold only/nothing implemented/NOT applied' vs the code) judged "
            "against the shrink-only ratchet, plus age warnings. suggest=True returns the exact docs to update. "
            "baseline='init'|'shrink' rewrites the ratchet (never grows it). "
            "KB § PATTERNS/common/doc-staleness-gate.md."
        ),
    )
    def _doc_staleness(rev_range: str | None = None, suggest_updates: bool = True,
                       baseline: str | None = None) -> dict:
        root = REPO_ROOT
        if baseline:
            return write_baseline(root, check_claims(root), baseline)
        if rev_range:
            rng = check_range(root, rev_range)
            res: dict[str, Any] = {"ok": not rng, "range": rng}
        else:
            res = check_tree(root)
            res["ok"] = not res["new"]
        if suggest_updates:
            res["suggest"] = suggest(res)
        return res


__all__ = ["check_doc_staleness", "check_range", "check_claims", "check_tree", "age_report",
           "write_baseline", "load_baseline", "parse_covers", "register"]
