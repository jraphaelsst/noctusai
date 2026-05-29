"""doc_to_code_drift — surface KB patterns whose code referent drifted.

Why this exists
    A KB pattern doc that names a tool / keeper / function (e.g.
    "`check_eight_way_sync` enforces...") is an implicit contract: the
    code with that name implements what the doc describes. Over time
    the code evolves (refactors, renames, new logic) and the doc lags.
    The drift is invisible in line-diffs because the LINKS don't change
    — only the SEMANTICS of what each side describes does.

What it does
    For each KB pattern doc:
      1. Extract referenced code symbols (function / keeper / class names
         mentioned in backticks or with explicit "`check_*`" patterns).
      2. For each symbol, find the on-disk code embedding chunk.
      3. Compute cosine similarity: doc_chunk vector  ↔  code_chunk vector.
      4. Flag when similarity drops below a threshold (default 0.5) —
         signals "the doc no longer describes what the code does."

Status: structural sensor. Advisory (warning severity if promoted to
a keeper) because doc-text and code-text are NEVER going to be highly
similar (they're different prose registers). The signal is in the DELTA
over time — same symbol pair, score dropping run-over-run = drift.

KB § CONTEXT/PATTERNS/common/doc-to-code-drift.md.
"""
from __future__ import annotations

import re
from typing import Any

# Canonical cosine — single source at _embedding_corpus (N=7 consolidation).
from . import _embedding_corpus as _ec

_cosine = _ec.cosine


# Regex for the canonical referent shapes in KB docs:
# - `check_<name>` (keeper names)
# - `noctus.dev.<name>` (MCP tool fully qualified)
# - `<name>.py` (module references)
# Extracted from backtick-quoted spans.
_REFERENT_PATTERNS = [
    re.compile(r"`(check_[a-z][a-z0-9_]+)`"),
    re.compile(r"`noctus\.dev\.([a-z][a-z0-9_]+)`"),
    re.compile(r"`([a-z][a-z0-9_]+)\.py`"),
]


def _extract_referents(doc_text: str) -> set[str]:
    """Pull every code-shaped backtick token from a doc body.

    Returns deduped names (no qualifier; just the leaf symbol).
    """
    out: set[str] = set()
    for pat in _REFERENT_PATTERNS:
        for match in pat.finditer(doc_text):
            out.add(match.group(1))
    return out


def scan(
    threshold: float = 0.5,
    kb_path_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Walk KB docs, extract code referents, score doc↔code similarity.

    Args:
      threshold: minimum cosine score; pairs BELOW this surface as drift.
        Default 0.5 reflects empirical doc-vs-code distance (they're
        different registers; perfect match never reached).
      kb_path_filter: substring filter on KB doc paths (e.g. "common/").
      limit: cap returned drift findings.

    Returns:
      {
        ok: bool,
        threshold: float,
        scanned_docs: int,
        scanned_referents: int,
        drift_findings: [
          {
            kb_path: str,
            referent: str,
            code_path: str | None,    # None if referent not found in code corpus
            score: float | None,
            severity: "below_threshold" | "referent_not_found",
          },
        ],
      }
    """
    try:
        from . import kb_embeddings as kbe
        from . import code_embeddings as ce
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"required modules unavailable: {e}"}

    kb_rows = kbe._load_all_chunk_vectors()
    code_rows = ce._load_all_chunk_vectors()
    if not kb_rows or not code_rows:
        return {
            "ok": True,
            "threshold": threshold,
            "scanned_docs": 0,
            "scanned_referents": 0,
            "drift_findings": [],
            "message": (
                "either kb-embeddings or code-embeddings cache is empty — "
                "run their respective refresh tools first."
            ),
        }

    # Index code corpus by symbol name → first chunk vector.
    # `code_chunks` carries symbol_name; key by symbol_name OR derive
    # from module name when file-level.
    code_by_symbol: dict[str, tuple[str, list[float]]] = {}
    code_by_module: dict[str, tuple[str, list[float]]] = {}
    for c_path, _idx, sym, _kind, _txt, vec in code_rows:
        if sym and sym not in code_by_symbol:
            code_by_symbol[sym] = (c_path, vec)
        # Module-level lookup: foo/bar.py → "bar"
        leaf = c_path.rsplit("/", 1)[-1]
        if leaf.endswith(".py"):
            stem = leaf[:-3]
            if stem not in code_by_module:
                code_by_module[stem] = (c_path, vec)

    # Group KB chunks by path so we get one vector per doc (first chunk).
    kb_by_path: dict[str, list[float]] = {}
    for path, _idx, _txt, vec in kb_rows:
        if path not in kb_by_path:
            kb_by_path[path] = vec

    drift_findings: list[dict[str, Any]] = []
    scanned_docs = 0
    scanned_referents = 0

    # We need the doc body text to extract referents (the vector tuples
    # don't carry it directly in our schema). Re-read KB markdown.
    from settings import REPO_ROOT
    kb_dir = REPO_ROOT / "KNOWLEDGE-BASE"
    for kb_path, kb_vec in kb_by_path.items():
        if kb_path_filter and kb_path_filter not in kb_path:
            continue
        md_file = kb_dir / kb_path
        if not md_file.is_file():
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned_docs += 1
        referents = _extract_referents(text)
        for referent in referents:
            scanned_referents += 1
            code_info = code_by_symbol.get(referent) or code_by_module.get(referent)
            if code_info is None:
                drift_findings.append({
                    "kb_path": kb_path,
                    "referent": referent,
                    "code_path": None,
                    "score": None,
                    "severity": "referent_not_found",
                })
                continue
            code_path, code_vec = code_info
            score = _cosine(kb_vec, code_vec)
            if score < threshold:
                drift_findings.append({
                    "kb_path": kb_path,
                    "referent": referent,
                    "code_path": code_path,
                    "score": score,
                    "severity": "below_threshold",
                })
            if len(drift_findings) >= limit:
                break
        if len(drift_findings) >= limit:
            break

    return {
        "ok": True,
        "threshold": threshold,
        "scanned_docs": scanned_docs,
        "scanned_referents": scanned_referents,
        "drift_findings": drift_findings,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.doc_to_code_drift",
        description=(
            "Scan KB pattern docs for referenced code symbols (check_*, "
            "noctus.dev.*, *.py) and score doc↔code semantic similarity. "
            "Surfaces drift when a referent doesn't exist in the code "
            "corpus (renamed/deleted) or when the doc-vs-code cosine is "
            "below threshold (the doc no longer describes what the code "
            "does). Advisory layer — different prose registers will never "
            "perfectly match; signal is in the DELTA over time. "
            "KB § CONTEXT/PATTERNS/common/doc-to-code-drift.md."
        ),
    )
    def _scan(threshold: float = 0.5, kb_path_filter: str | None = None,
              limit: int = 100) -> dict:
        return scan(threshold=threshold, kb_path_filter=kb_path_filter, limit=limit)


__all__ = ["scan", "register"]
