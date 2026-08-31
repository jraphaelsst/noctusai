"""noctus.dev.scan_remediation_markers — batch-sweep the NOC-REMEDIATE deferral markers.

KB § PATTERNS/remediation-markers.md. The marker
``NOC-REMEDIATE[<class>]: <what + why> — <YYYY-MM-DD>`` is the sanctioned *non-silent*
deferral channel — the marker IS the named destination. This tool operationalizes the
batch sweep + triage the doc prescribes: find every marker, parse its class + age, group
by class, flag the malformed ones (no `[class]` / no date) and the **forbidden** ones (on
an ``except`` line — a marker must never suppress an error), and surface any class at
**N≥3** (the recurrence threshold ⇒ promote to a project / seed lift).

A *scan/query* tool (advisory) — recurrence gates enforcement, not querying — so it ships
ahead of the N≥3 a keeper would need. Exit 1 only on malformed/on-except markers (genuine
defects); a clean catalog of well-formed markers is exit 0.

Declaration vs. citation (2026-08-31 rewrite)
----------------------------------------------
A naive "any line containing the literal string" scan conflates two very different
things: a genuine **declaration** (a marker actually left in the code / a doc's "Known
debt" section) vs. a **citation** — prose *about* a marker that lives elsewhere (a
roadmap bullet, a KB doc pointing back at the code comment, a test's ``assert "...
NOC-REMEDIATE[x]..." in some_string`` checking that ANOTHER module emits the text). Only
a declaration is a real deferral; a citation is not a marker at all and must not be
counted, dated, or flagged malformed.

The discriminator is **structural, not path-based** — CLAUDE.md's own doc-sync
philosophy: a real declaration's ``[class]`` is followed (directly, or via one of the
handful of shapes real code actually uses) by explanatory text; a citation's is not.
Concretely, per file kind:

- **Python (``.py``)** — AST + ``tokenize`` first (the file's *own* comment/docstring
  structure is unambiguous ground truth; no regex could reconstruct it reliably from a
  single grepped line). A ``NOC-REMEDIATE[...]`` occurrence counts only when the physical
  line is a ``#`` COMMENT token (via ``tokenize``) or falls inside a module/class/function
  DOCSTRING (the AST node's own ``lineno``/``end_lineno`` range — ``ast.get_docstring``
  doesn't give ranges, so the docstring ``Expr`` node is read directly). Any other
  occurrence — an ``assert "..." in x``, an f-string, a ``.write_text("...")`` test
  fixture, a ``logger.warning(...)`` format-string literal — is inside an *ordinary*
  string literal, which is where every verified Python false-positive lived (test
  assertions checking that some OTHER function emits the marker text; the
  ``validation_signal`` test fixtures constructing synthetic marker content as test
  input). Within a comment/docstring, one of three real shapes is required (see
  ``_declaration_span`` below) — a docstring CAN also merely *cite* a marker declared
  elsewhere ("See the ``NOC-REMEDIATE[x]`` marker at the handling site") and the shape
  check catches that too.
- **Markdown (``.md``)** — no lexical comment concept, so the shape check is the *only*
  signal, and it is intentionally the STRICT canonical shape only: ``[class]:`` with a
  colon immediately following the bracket (optionally through a closing backtick/paren).
  This is the shape the two genuine doc-hosted deferrals in this corpus
  (``corpus-embeddings.md`` / ``memory-embeddings.md`` "## Known debt" sections) actually
  use. The reversed bullet shape (``<text> — NOC-REMEDIATE[class]``, no colon) that DOES
  count as a declaration in code comments turned out, in every verified instance, to be a
  roadmap/PROJECT.md line citing the marker that actually lives in the referenced source
  file (e.g. ``igig-2026-08.md`` citing the markers in ``comercial_router.py`` /
  ``contrato_documento.py`` / ``publicacao_publisher.py``) — so it is deliberately NOT
  accepted for ``.md``. This is not a blanket ``.md`` skip: a well-formed ``[class]:
  text`` declaration in a KB doc or PROJECT.md still counts.
- **Other code (``.ts``/``.tsx``/``.sql``/``.yml``/``.yaml``)** — no full lexer available
  here without a new dependency; a comment-leader heuristic stands in for the AST gate
  (does a recognized leader — ``#``, ``//``, ``--``, or a JSDoc ``*`` continuation —
  appear before the marker on the line, or does the strict ``.md``-style colon-shape
  match, for YAML "knowledge journal" prose fields that don't use a ``#`` leader at all).
  No false positive of this shape was found in the verified corpus, so this stays a
  documented simplification rather than a full lexer.

Real shapes (declaration, once the context gate above passes):
  (a) ``[class]: text`` — colon immediately after ``]`` (through an optional closing
      backtick / quote / paren).
  (b) ``text — NOC-REMEDIATE[class]`` — an em-dash (or ``--``) immediately before the
      token, with nothing substantive after ``]`` (the reversed bullet-list form; code
      files only, per above).
  (c) bare-standalone — nothing but whitespace/comment-leader/backtick precedes the token
      on its physical line (the marker opens a fresh comment/docstring line, with the
      "what" continuing on the next lines — e.g. ``financial_service.py``'s
      ``NOC-REMEDIATE[orbity-finance-fiscal]`` followed by an indented explanation).

Placeholders (documentation *teaching* the format, never a real class): an angle-bracket
class (``[<class>]``, pre-existing rule) OR a class that is a bare ellipsis (``...`` /
``…`` — the "some class" notation seen in ``validation_signal.py``'s own docstring) OR
descriptive text that is itself an angle-bracket / ellipsis placeholder (``<rationale> —
<date>``, `` …)`` `` inside a quoted worked-example commit message) are never counted.

Multi-line markers: the "what" text and the trailing ``— <date>`` frequently continue
past the marker's own physical line (a wrapped sentence, an indented explanation block).
Once a declaration is found, the surrounding block is read forward — the rest of the
docstring's own line range for a docstring hit, the contiguous run of comment lines for a
comment hit, a capped run of non-blank lines for ``.md`` — and the date pattern is
searched across that WHOLE block (text strictly after the marker's own ``]``, never
before it — the bug that made a bullet's leading ``2026-05-29 (W5): …`` timestamp read as
the marker's own date).
"""
from __future__ import annotations

import ast
import io
import re
import subprocess
import tokenize
from datetime import date, datetime
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

# The class token itself: no angle brackets (the placeholder shape), non-empty,
# first char not whitespace. Extraction only — real-vs-citation is decided below
# by `_declaration_span`, not by this regex alone (that was the old, insufficient
# discriminator).
_MARKER_RE = re.compile(r"NOC-REMEDIATE\[(?P<cls>[^\]<>\s][^\]<>]*)\]")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_EXCEPT_RE = re.compile(r"^\s*except\b")  # the line's CODE is an except clause (precise)

# A class token that is itself a placeholder notation, never a real class.
_PLACEHOLDER_CLASSES = frozenset({"...", "…"})  # "..." and the "…" glyph
# Descriptive text that is itself elided/placeholder content — never a real "what".
_PLACEHOLDER_TEXT_RE = re.compile(r"^(?:<[^>]*>|\.\.\.|…)")

# Characters trimmed off the ends of the "before"/"after" spans when testing the
# three declaration shapes — closing/opening quote & bracket punctuation that
# wraps the token in prose (`` `NOC-REMEDIATE[x]` ``, "(NOC-REMEDIATE[x])").
_WRAP_CHARS = " \t`'\"()[]"

# Comment leaders recognized for non-Python code files (no full lexer available;
# see module docstring "Other code" — a documented simplification).
_OTHER_CODE_LEADERS = ("#", "//", "--")

# Docs that DEFINE the marker convention are self-reference — never scanned
# (the placeholder-exclusion lesson: a scanner must not trip on the docs that
# spell out its own token, even when they show a concrete ``[codify]`` example).
_DEFINING_DOCS = (
    "remediation-markers.md",                # the token definition
    "methodology-codification-pipeline.md",  # the pipeline meta-doc
    "codify.md",                             # the /codify command
    "dev/compliance.py",                     # the check_codification_debt keeper (handles [codify])
)


def _is_frozen_history(path: str) -> bool:
    """A verbatim RECORD of past code, not live code.

    `git format-patch` output archived by `salvage_before_delete` embeds whole
    source files as `+` lines — markers and all. Scanning them asks "is this
    deferral still open?" of a snapshot that is, by construction, immutable:
    the marker cannot be fixed, because editing an archived patch would falsify
    the record it exists to preserve.

    Found 2026-08-11, in CI, on `main`: archiving `feat/harness-audit-refit`
    for deletion carried a `NOC-REMEDIATE[codify]` line inside the patch, and
    `check_codification_debt` reported it as a NEW high-severity malformed
    marker — a compliance regression manufactured purely by recording history.
    A gate that fires on its own archive is a scope error, not debt.
    """
    return path.startswith("project-history/") and path.endswith(".patch")


def _is_event_log(path: str) -> bool:
    """An append-only NDJSON event log is a RECORD of a past agent action, not
    live code or prose. `auto-improvement.ndjson` rows quote whatever text an
    agent wrote at the time (including, verbatim, a mention of a marker) —
    scanning it asks the same falsify-the-record question `_is_frozen_history`
    asks of an archived patch. Same reasoning, different artifact shape.
    """
    return path.endswith(".ndjson")


def _is_defining_doc(path: str) -> bool:
    # The marker-machinery's own source + test files are self-reference: their
    # tests carry fixture markers (true/false-positive shapes) that must not
    # count as real deferrals. Substring matches both `<tool>.py` and
    # `tests/test_<tool>.py`.
    return (
        path.endswith(_DEFINING_DOCS)
        or "scan_remediation_markers" in path
        or "codification_debt" in path
    )


def _git_grep(root: Path) -> list[tuple[str, int, str]]:
    """(path, lineno, content) for every NOC-REMEDIATE occurrence in tracked files."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "grep", "-n", "--no-color", "NOC-REMEDIATE"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    out: list[tuple[str, int, str]] = []
    for ln in r.stdout.splitlines():
        parts = ln.split(":", 2)  # path:lineno:content
        if len(parts) == 3 and parts[1].isdigit():
            out.append((parts[0], int(parts[1]), parts[2]))
    return out


def _resolve_root(repo_root: Path | None, worktree_path: str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    if worktree_path:
        return Path(resolve_caller_root(worktree_path))
    return REPO_ROOT


# ---------------------------------------------------------------------------
# Python context classification — AST + tokenize (see module docstring).
# ---------------------------------------------------------------------------

def _py_context_lines(source: str) -> tuple[set[int], dict[int, int]]:
    """Return (comment_lines, docstring_line_to_end) for a Python source string.

    ``comment_lines`` — 1-indexed physical lines carrying a ``#`` COMMENT token.
    ``docstring_line_to_end`` — maps every 1-indexed line inside a module/class/
    function docstring to that docstring's ``end_lineno`` (so a hit anywhere in
    the docstring knows how far the block extends for multi-line date lookup).

    Best-effort: a file that fails to tokenize/parse (rare, e.g. a WIP syntax
    error) yields empty sets rather than raising — the caller then has no
    comment/docstring evidence and correctly treats any hit in that file as
    unclassifiable (dropped, not miscounted).
    """
    comment_lines: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                comment_lines.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass

    docstring_line_to_end: dict[int, int] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return comment_lines, docstring_line_to_end

    nodes: list[ast.AST] = [tree]
    nodes.extend(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    )
    for node in nodes:
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(getattr(first, "value", None), ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start = first.value.lineno
            end = getattr(first.value, "end_lineno", start) or start
            for ln in range(start, end + 1):
                docstring_line_to_end[ln] = end
    return comment_lines, docstring_line_to_end


# ---------------------------------------------------------------------------
# Declaration-shape check — the real-vs-citation discriminator.
# ---------------------------------------------------------------------------

def _strip_wrap(s: str, *, from_end: bool) -> str:
    return s.rstrip(_WRAP_CHARS) if from_end else s.lstrip(_WRAP_CHARS)


def _leading_leader_stripped(before: str) -> str:
    """Strip a single leading comment-leader (`` // `` / ``--`` / ``#`` / ``*``)
    plus surrounding whitespace off `before`, so the leader itself never
    masquerades as "real preceding text" for the bare/shape-b checks below.
    Without this, a SQL ``--`` line with nothing else before the marker
    (`` --     NOC-REMEDIATE[x] — attach real cron trigger``) reads its own
    ``--`` leader as "text ending in a hyphen" — shape (b) — and the
    extracted "what" becomes the literal string ``"--"`` (garbage). Applying
    it once collapses that case to genuine bare-standalone (shape c) instead,
    which correctly captures the real trailing text.
    """
    stripped = before.lstrip()
    for leader in ("//", "--", "#", "*"):
        if stripped.startswith(leader):
            stripped = stripped[len(leader):]
            break
    return stripped.strip()


def _declaration_span(
    line: str, m: re.Match, *, allow_reversed_bullet: bool
) -> tuple[str, str] | None:
    """Return `(kind, text)` if `line` is a real declaration start, else None
    (citation). `kind` is ``"a"`` (colon-shape) / ``"b"`` (reversed bullet) /
    ``"c"`` (bare-standalone) — the caller uses it to decide whether the
    marker's text/date may continue onto later lines (a/c can; b is a single
    complete bullet item, never multi-line — see ``_block_end_index``).

    The bare-standalone check (``c``) strips a leading comment-leader (see
    ``_leading_leader_stripped``) but never backtick/quote/paren WRAP
    punctuation: `` `NOC-REMEDIATE[x]` — prose`` (an inline-code-quoted token
    followed by a citation) must NOT read as "nothing precedes it" just
    because the backtick itself is punctuation — that was the false-positive
    shape in `auth-boundary-false-green.md` / `roteiros-visitas-PROJECT.md` /
    `APPLIED.md` (all: a marker cited inside backticks, with real prose
    *about* the marker following, not fresh deferral text).
    """
    raw_before = line[:m.start()]
    after = _strip_wrap(line[m.end():], from_end=False)

    # Shape (a): colon immediately after `]` (through wrap chars).
    if after.startswith(":"):
        return "a", after[1:].strip()

    before_content = _leading_leader_stripped(raw_before)

    # Shape (c): bare-standalone — truly nothing (beyond this line's own
    # comment leader) precedes the token on its physical line.
    if before_content == "":
        return "c", after  # possibly empty; continuation lines carry the "what"

    # Shape (b): reversed bullet — em-dash immediately before the token
    # (code files only; see module docstring). A complete, atomic bullet
    # item — its "what" is the `before` text, never continuation lines.
    if allow_reversed_bullet and before_content[-1:] in ("—", "-"):
        return "b", before_content

    return None


def _other_code_leader_present(line: str, marker_pos: int) -> bool:
    """Comment-leader heuristic for non-Python, non-Markdown files (no lexer
    available here — see module docstring). Recognizes a leading `//`/`--`/`#`
    (comment-only or inline-trailing) or a JSDoc `*` continuation line."""
    prefix = line[:marker_pos]
    if any(leader in prefix for leader in _OTHER_CODE_LEADERS):
        return True
    return line.lstrip().startswith("*")


def _is_placeholder(cls: str, text: str) -> bool:
    if cls in _PLACEHOLDER_CLASSES:
        return True
    return bool(_PLACEHOLDER_TEXT_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Multi-line block extraction (text + date), per file-kind block rule.
# ---------------------------------------------------------------------------

def _block_end_index(
    lines: list[str], start_idx: int, *, comment_lines: set[int] | None,
    docstring_end: int | None, prose_cap: int,
) -> int:
    """0-indexed inclusive end line of the block starting at `start_idx`."""
    if docstring_end is not None:
        return min(len(lines) - 1, docstring_end - 1)
    if comment_lines is not None:
        end_idx = start_idx
        for i in range(start_idx + 1, min(len(lines), start_idx + 1 + prose_cap)):
            if (i + 1) not in comment_lines or not lines[i].strip():
                break
            end_idx = i
        return end_idx
    # Generic prose continuation (md / other-code, comment-leader unknown ahead):
    # extend while non-blank, capped.
    end_idx = start_idx
    for i in range(start_idx + 1, min(len(lines), start_idx + 1 + prose_cap)):
        if not lines[i].strip():
            break
        end_idx = i
    return end_idx


def _find_date_after(lines: list[str], start_idx: int, start_col: int, end_idx: int) -> str | None:
    """Search for a `YYYY-MM-DD` date in the block, restricted to text AFTER
    the marker's own `]` on its line (never before — the bug that read a
    bullet's leading timestamp as the marker's date)."""
    first = lines[start_idx][start_col:]
    rest = "\n".join(lines[start_idx + 1:end_idx + 1])
    dm = _DATE_RE.search(first) or _DATE_RE.search(rest)
    return dm.group(1) if dm else None


def _first_line_text(lines: list[str], idx: int, span_text: str, end_idx: int, *, extend: bool) -> str:
    """Assemble the "what" text. `extend=False` (shape "b") is a single,
    complete bullet item — never pull in the next line (that next line is
    very likely a SIBLING bullet with its own separate marker, not a
    continuation — the bug that concatenated 3 distinct
    `meta_ads_service.py` seam bullets into one garbled record)."""
    parts = [span_text.strip()] if span_text.strip() else []
    if extend:
        for i in range(idx + 1, min(end_idx + 1, idx + 4)):
            parts.append(lines[i].strip())
    return " ".join(p for p in parts if p)[:160]


# ---------------------------------------------------------------------------
# Per-file classification.
# ---------------------------------------------------------------------------

def _classify_file_hits(
    root: Path, path: str, hits: list[tuple[int, str]],
) -> list[dict]:
    """`hits` = [(lineno, content), ...] for one file. Returns parsed real-marker
    records (declarations only — citations are silently dropped, not counted)."""
    try:
        full_text = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = full_text.splitlines()

    is_py = path.endswith(".py")
    is_md = path.endswith(".md")

    comment_lines: set[int] = set()
    docstring_map: dict[int, int] = {}
    if is_py:
        comment_lines, docstring_map = _py_context_lines(full_text)

    out: list[dict] = []
    for lineno, content in hits:
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            continue
        line = lines[idx]
        m = _MARKER_RE.search(line)
        if not m:
            continue
        cls = m.group("cls").strip()

        if is_py:
            in_comment = lineno in comment_lines
            in_docstring = lineno in docstring_map
            if not in_comment and not in_docstring:
                continue  # ordinary string literal — citation, per module docstring
            result = _declaration_span(line, m, allow_reversed_bullet=True)
            if result is None:
                continue
            kind, span = result
            docstring_end = docstring_map.get(lineno) if in_docstring else None
            block_comment_lines = comment_lines if in_comment else None
            end_idx = idx if kind == "b" else _block_end_index(
                lines, idx, comment_lines=block_comment_lines,
                docstring_end=docstring_end, prose_cap=20,
            )
        elif is_md:
            result = _declaration_span(line, m, allow_reversed_bullet=False)
            if result is None:
                continue
            kind, span = result
            end_idx = idx if kind == "b" else _block_end_index(
                lines, idx, comment_lines=None, docstring_end=None, prose_cap=6,
            )
        else:
            if not _other_code_leader_present(line, m.start()):
                # Still allow the strict md-style colon shape for prose-data
                # files (YAML knowledge-journal fields) with no leader at all.
                result = _declaration_span(line, m, allow_reversed_bullet=False)
            else:
                result = _declaration_span(line, m, allow_reversed_bullet=True)
            if result is None:
                continue
            kind, span = result
            end_idx = idx if kind == "b" else _block_end_index(
                lines, idx, comment_lines=None, docstring_end=None, prose_cap=20,
            )

        text = _first_line_text(lines, idx, span, end_idx, extend=(kind != "b"))
        if _is_placeholder(cls, span):
            continue

        marker_date = _find_date_after(lines, idx, m.end(), end_idx)
        age_days = None
        if marker_date:
            try:
                age_days = (date.today() - datetime.strptime(marker_date, "%Y-%m-%d").date()).days
            except ValueError:
                marker_date = None

        out.append({
            "path": path, "line": lineno, "class": cls,
            "date": marker_date, "age_days": age_days, "text": text,
            "on_except": bool(_EXCEPT_RE.match(content)),  # FORBIDDEN — suppresses an error
        })
    return out


def _iter_markers(root: Path) -> list[dict]:
    """Parsed record for every well-formed NOC-REMEDIATE marker (real ``[class]``).

    One parser, two surfaces: ``scan_remediation_markers`` (all classes,
    advisory CLI/MCP) + ``markers_of_class`` / the ``check_codification_debt``
    keeper (one class, in the compliance gate). Each record carries the
    ``on_except`` flag so both surfaces classify defects identically.
    """
    by_file: dict[str, list[tuple[int, str]]] = {}
    for path, lineno, content in _git_grep(root):
        if _is_defining_doc(path) or _is_frozen_history(path) or _is_event_log(path):
            continue
        by_file.setdefault(path, []).append((lineno, content))

    out: list[dict] = []
    for path, hits in by_file.items():
        out.extend(_classify_file_hits(root, path, hits))
    out.sort(key=lambda m: (m["path"], m["line"]))
    return out


def scan_remediation_markers(
    repo_root: Path | None = None, worktree_path: str | None = None
) -> dict:
    """Sweep + triage NOC-REMEDIATE markers. See module docstring."""
    root = _resolve_root(repo_root, worktree_path)
    markers = _iter_markers(root)
    malformed = [m for m in markers if not m["date"]]
    on_except = [m for m in markers if m["on_except"]]
    by_class: dict[str, int] = {}
    for m in markers:
        by_class[m["class"]] = by_class.get(m["class"], 0) + 1

    promote = sorted(c for c, n in by_class.items() if n >= 3)
    defects = len(malformed) + len(on_except)
    return {
        "ok": True,
        "total": len(markers),
        "by_class": dict(sorted(by_class.items(), key=lambda kv: -kv[1])),
        "promote_candidates": promote,   # class at N≥3 ⇒ promote to project / seed lift
        "malformed": malformed,          # missing [class] or — <date>
        "on_except": on_except,          # FORBIDDEN: a marker on an `except` line
        "oldest": sorted(
            (m for m in markers if m["age_days"] is not None),
            key=lambda m: -(m["age_days"] or 0),
        )[:10],
        "status": "defects" if defects else ("markers" if markers else "clean"),
        "exit_code": 1 if defects else 0,
    }


def markers_of_class(
    repo_root: Path | None = None, cls: str = "", worktree_path: str | None = None
) -> list[dict]:
    """Marker records for ONE class (e.g. ``"codify"``), or all if ``cls`` is empty.

    Shares ``_iter_markers`` with ``scan_remediation_markers`` — one parser,
    two surfaces. Backs the ``check_codification_debt`` keeper
    (KB § PATTERNS/methodology-codification-pipeline.md) — the always-on
    compliance-gate form of the ``/codify`` command's *detection* half.
    """
    root = _resolve_root(repo_root, worktree_path)
    return [m for m in _iter_markers(root) if not cls or m["class"] == cls]


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_remediation_markers",
        description=(
            "Batch-sweep + triage the NOC-REMEDIATE deferral markers "
            "(KB § PATTERNS/remediation-markers.md). Finds every "
            "`NOC-REMEDIATE[<class>]: … — <YYYY-MM-DD>`, distinguishes a real "
            "declaration from prose merely CITING one (AST/tokenize for Python "
            "comment-vs-docstring-vs-string context; a strict colon-shape for "
            "Markdown; a comment-leader heuristic elsewhere), parses class + "
            "age (multi-line-aware), groups by class, flags malformed (no "
            "class/date) + FORBIDDEN on-`except` markers, and surfaces any "
            "class at N≥3 (promote to a project / seed lift). Advisory query "
            "— exit 1 only on defects. Pass worktree_path when called from "
            "inside a git worktree."
        ),
    )
    def _scan(worktree_path: str | None = None) -> dict:
        return scan_remediation_markers(worktree_path=worktree_path)


__all__ = ["scan_remediation_markers", "markers_of_class", "register"]
