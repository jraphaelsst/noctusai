"""Anonymization guard for pt-BR social-media methodology content.

Scans text (or files) for content that violates the privacy/atemporality
policy defined in methodology_service._POLICY:
  - No person names / @handles / brands / clients.
  - No result/performance numbers (views, seguidores, faturamento, etc.).
  - Examples must be converted to templates (not detected here — that's an
    LLM-generation concern; this guard catches residual leakage in outputs).

Intrinsic-method numbers ("3 segundos", "7 gatilhos", "primeiros 5 segundos",
"32 templates") are explicitly allowed — they describe the mechanism, not a result.

Design goal: PRECISION FIRST.  False positives block commits; false negatives
are caught in review.  Each pattern is conservative and documented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    kind: str       # category label (e.g. "handle", "currency_result", …)
    match: str      # the matched text substring
    line: int       # 1-based line number in the scanned text
    context: str    # the full line (stripped) for human-readable output


# ---------------------------------------------------------------------------
# Default brand/name denylist
# ---------------------------------------------------------------------------

_DEFAULT_DENYLIST: list[str] = [
    "CORE Educação",
    "CORE Educacao",
]

# ---------------------------------------------------------------------------
# Allowlist: intrinsic-method patterns that must NOT be flagged even though
# they contain numbers adjacent to "result-like" nouns.
#
# Rationale: the policy explicitly permits numbers that are part of the
# method itself ("3 segundos", "7 gatilhos", "32 templates", etc.).  We
# pre-compile these so the result-number detector can skip matching spans.
# ---------------------------------------------------------------------------

_INTRINSIC_METHOD_PATTERNS: list[re.Pattern[str]] = [
    # Time units: "3 segundos", "primeiros 3s", "5 segundos", "10s"
    re.compile(r"\b\d+\s*s(?:egundos?)?\b", re.IGNORECASE),
    # "7 gatilhos", "3 gatilhos"
    re.compile(r"\b\d+\s+gatilhos?\b", re.IGNORECASE),
    # "32 templates", "10 templates"
    re.compile(r"\b\d+\s+templates?\b", re.IGNORECASE),
    # "3 pilares", "5 pilares"
    re.compile(r"\b\d+\s+pilares?\b", re.IGNORECASE),
    # "3 passos", "5 passos", "7 etapas"
    re.compile(r"\b\d+\s+(?:passos?|etapas?|fases?)\b", re.IGNORECASE),
    # "3 elementos", "5 elementos"
    re.compile(r"\b\d+\s+elementos?\b", re.IGNORECASE),
    # "3 princípios", "5 princípios"
    re.compile(r"\b\d+\s+princ[íi]pios?\b", re.IGNORECASE),
    # "3 técnicas", "5 técnicas"
    re.compile(r"\b\d+\s+t[eé]cnicas?\b", re.IGNORECASE),
    # "3 regras", "5 regras"
    re.compile(r"\b\d+\s+regras?\b", re.IGNORECASE),
    # "3 tipos", "5 tipos"
    re.compile(r"\b\d+\s+tipos?\b", re.IGNORECASE),
    # ordinal "1º", "2º", "3ª" etc. — structural enumeration, not results
    re.compile(r"\b\d+[ºª°]\b", re.IGNORECASE),
]


def _is_intrinsic(span_text: str) -> bool:
    """Return True if the number-containing span matches any intrinsic-method pattern."""
    for pat in _INTRINSIC_METHOD_PATTERNS:
        if pat.search(span_text):
            return True
    return False


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# 1. @handles — @word with optional internal ".word" segments (never a trailing dot,
#    so "@nome_perfil." yields "@nome_perfil" and sentence punctuation is excluded).
#    Rationale: the policy forbids @handles; "@" in normal prose is rare in pt-BR.
_HANDLE_RE = re.compile(r"(?<!\w)@\w+(?:\.\w+)*")  # (?<!\w) excludes emails like nome@dominio.com

# 2. Currency results — "R$" followed by a number (integer or decimal, with optional
#    thousand-separators).  Even "R$ 0" is a result claim.
#    Rationale: any R$ figure is a faturamento/result signal.
_CURRENCY_RE = re.compile(r"R\$\s*[\d.,]+")

# 3. Result-number patterns — a number (with optional "mil"/"k"/"M"/"bilhão" suffix)
#    directly adjacent to a result-oriented noun.  We keep the number+noun together
#    so we can run the intrinsic-method exemption on the full span.
#
#    Result nouns (pt-BR social-media context):
#      seguidores, inscritos, views, visualizações/visualizacoes,
#      faturamento, faturei, vendas, crescimento,
#      "de N vídeos"/"de N videos" pattern, "%"
#
#    Number form: digits optionally followed by "mil", "k", "M", "bi", "bilhão",
#    or a decimal/comma number.
#
#    Rationale: "10 mil seguidores", "500k views", "1,5 M de faturamento",
#    "crescimento de 200%", "de 30 vídeos no mês" are all forbidden.
#    We use word-boundary anchors and require the noun to be on the same "phrase"
#    (within ~5 words) to avoid catching e.g. "2 exemplos de visualizações".

# Must START with a digit — a bare "," or "." is punctuation, not a number
# (otherwise prose like "..., vendas somem" false-positives as a result number).
_NUMBER_PART = r"\d[\d.,]*(?:\s*(?:mil|k|M|bi|bilh[aã]o))?"

# Note: "vídeos" is a content count (method), not a performance metric — excluded
# to avoid flagging "~50 vídeos" / "vídeo 9". Real metrics: views/seguidores/etc.
_RESULT_NOUN_AFTER_RE = re.compile(
    r"(?P<num>" + _NUMBER_PART + r")"
    r"(?:\s+(?:de|dos?|das?|em|com|no|na|nos|nas)\s+)?"
    r"\s*"
    r"(?P<noun>seguidores?|inscritos?|views?|visualiza[çc][oõ]es?|"
    r"faturamento|faturei|vendas?|crescimento)",
    re.IGNORECASE,
)

_RESULT_NOUN_BEFORE_RE = re.compile(
    r"(?P<noun>seguidores?|inscritos?|views?|visualiza[çc][oõ]es?|"
    r"faturamento|faturei|vendas?|crescimento)"
    r"\s+(?:de\s+)?"
    r"(?P<num>" + _NUMBER_PART + r")",
    re.IGNORECASE,
)

# Growth-result percentage: a growth verb DIRECTLY followed by a "%" number, e.g.
# "cresceu 300%", "aumentei em 50%", "caiu 20%". A bare threshold ("15–20%") or a
# verb not followed by a number ("aumenta a probabilidade") is NOT a result.
_GROWTH_PERCENT_RE = re.compile(
    r"(?:cresc\w*|aument\w*|dobr\w*|tripl\w*|multiplic\w*|despenc\w*|redu\w*|subiu|caiu)"
    r"\s+(?:em\s+|para\s+|de\s+|a\s+)?"
    r"\d[\d.,]*\s*%",
    re.IGNORECASE,
)

# "X de Y vídeos" — "de N vídeos" already covered above; this catches bare
# "X de Y" when Y is a video count written differently, but the _RESULT_NOUN_AFTER_RE
# covers it.  Keep only the % pattern as a separate check for standalone percentages.


# ---------------------------------------------------------------------------
# Core scanning logic
# ---------------------------------------------------------------------------

def _findings_for_line(
    line_text: str,
    line_no: int,
    denylist_patterns: list[re.Pattern[str]],
) -> list[Finding]:
    """Return all findings for a single line of text."""
    findings: list[Finding] = []
    ctx = line_text.strip()

    # 1. @handles
    for m in _HANDLE_RE.finditer(line_text):
        findings.append(Finding(kind="handle", match=m.group(), line=line_no, context=ctx))

    # 2. Currency results
    for m in _CURRENCY_RE.finditer(line_text):
        findings.append(Finding(kind="currency_result", match=m.group(), line=line_no, context=ctx))

    # 3. Result-number patterns (number THEN noun)
    for m in _RESULT_NOUN_AFTER_RE.finditer(line_text):
        span = m.group()
        if not _is_intrinsic(span):
            findings.append(Finding(kind="result_number", match=span, line=line_no, context=ctx))

    # 4. Result-number patterns (noun THEN number)
    for m in _RESULT_NOUN_BEFORE_RE.finditer(line_text):
        span = m.group()
        if not _is_intrinsic(span):
            findings.append(Finding(kind="result_number", match=span, line=line_no, context=ctx))

    # 5. Growth-result percentage — a growth verb DIRECTLY followed by a "%" number.
    #    Method thresholds ("15–20%", "Acima de 50%") and "aumenta a probabilidade"
    #    (verb not followed by a number) deliberately pass; "cresceu 50%" is caught.
    for m in _GROWTH_PERCENT_RE.finditer(line_text):
        findings.append(Finding(kind="result_percent", match=m.group().strip(), line=line_no, context=ctx))

    # 6. Denylist brands/names
    for pat in denylist_patterns:
        for m in pat.finditer(line_text):
            findings.append(Finding(kind="denylist_brand", match=m.group(), line=line_no, context=ctx))

    return findings


def _build_denylist_patterns(denylist: list[str]) -> list[re.Pattern[str]]:
    """Compile denylist strings into case-insensitive regex patterns."""
    return [re.compile(re.escape(term), re.IGNORECASE) for term in denylist]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_text(
    text: str,
    *,
    denylist: list[str] | None = None,
) -> list[Finding]:
    """Scan *text* for policy violations and return all findings.

    Parameters
    ----------
    text:
        Raw string content to scan (markdown, plain text, etc.).
    denylist:
        Optional list of additional brand/name strings to flag (exact match,
        case-insensitive).  The default denylist ("CORE Educação", etc.) is
        always included and cannot be removed by the caller.

    Returns
    -------
    list[Finding]
        One Finding per matched violation.  Empty list means the text is clean.
    """
    effective_denylist = list(_DEFAULT_DENYLIST)
    if denylist:
        effective_denylist.extend(denylist)
    denylist_patterns = _build_denylist_patterns(effective_denylist)

    findings: list[Finding] = []
    for line_no, line_text in enumerate(text.splitlines(), start=1):
        findings.extend(_findings_for_line(line_text, line_no, denylist_patterns))
    return findings


# Binary-file magic bytes prefix check (covers common formats)
_BINARY_MAGIC = [
    b"\x50\x4b",       # ZIP / DOCX / XLSX / PPTX (PK header)
    b"\x89PNG",        # PNG
    b"\xff\xd8\xff",   # JPEG
    b"\x47\x49\x46",   # GIF
    b"\x25\x50\x44\x46",  # PDF
    b"\x00\x00\x00",   # MP4/MOV (ftyp starts with 0-bytes)
    b"\x1a\x45\xdf\xa3",  # MKV/WEBM
    b"ID3",            # MP3
    b"fLaC",           # FLAC
    b"OggS",           # OGG
]

_SCANNABLE_SUFFIXES = {".md", ".txt", ".rst"}


def _is_binary(path: Path) -> bool:
    """Heuristic binary-file check: peek at the first 8 bytes for known magic headers."""
    try:
        with path.open("rb") as fh:
            header = fh.read(8)
    except OSError:
        return True  # unreadable → skip
    for magic in _BINARY_MAGIC:
        if header.startswith(magic):
            return True
    return False


def scan_paths(
    paths: Iterable[str | Path],
    *,
    denylist: list[str] | None = None,
) -> dict[str, list[Finding]]:
    """Scan a collection of files, returning a map of path → findings.

    Skips files that are binary, have a non-scannable suffix (.docx, .pdf, …),
    or cannot be read.  Only .md / .txt / .rst files are scanned.

    Parameters
    ----------
    paths:
        An iterable of file paths (str or Path).
    denylist:
        Optional extra brand/name strings (see scan_text).

    Returns
    -------
    dict[str, list[Finding]]
        Keys are str(path); value is the list of findings (may be empty,
        meaning the file is clean — the key is still present).
    """
    result: dict[str, list[Finding]] = {}
    for raw_path in paths:
        p = Path(raw_path)
        key = str(p)
        if p.suffix.lower() not in _SCANNABLE_SUFFIXES:
            continue
        if _is_binary(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        result[key] = scan_text(text, denylist=denylist)
    return result


__all__ = ["Finding", "scan_text", "scan_paths"]
