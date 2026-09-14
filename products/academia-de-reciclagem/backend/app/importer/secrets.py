"""Content secret scan for the knowledge-bundle importer (contract §B.6).

Two independent detectors, either one is enough to flag a line:

1. **Known token patterns** — literal prefixes/markers used by common
   secret shapes: Stripe (``pk_``/``sk-``... — narrowed with a length
   guard so plain PT-BR words like ``pesquisa`` never match), GitHub PATs
   (``ghp_``), AWS access key ids (``AKIA``), and PEM key headers
   (``-----BEGIN``).
2. **Shannon-entropy heuristic** — any sufficiently long unbroken token
   of base64/hex/url-safe characters whose per-character entropy clears
   a threshold. Ordinary prose (PT-BR included) breaks into short,
   space-separated, low-entropy words and never trips this; a real
   secret is one long high-entropy blob.

Returns booleans / the offending pattern only — **never** the value that
matched, so a scan result is always safe to log or return to a caller
(contract: "returns the offending path, never the value").
"""
from __future__ import annotations

import math
import re
from collections import Counter

# Fixed-prefix secret shapes. Each pattern requires enough trailing
# characters that an incidental substring match (e.g. someone writing
# the literal word "sk-learning" in prose) can't trip it.
_KNOWN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"pk_[A-Za-z0-9]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

# A "long token" for the entropy heuristic: an unbroken run of base64 /
# hex characters. Deliberately EXCLUDES the hyphen: PT-BR knowledge-base
# prose is full of long hyphenated compound slugs/phrases
# ("conforme-a-politica-nacional-de-residuos-solidos-...") that measure
# 3.7-4.0 bits/char once hyphens are counted as token characters — right
# at a naive threshold, and a guaranteed false positive at N=3+ of them
# per KB page. Dropping the hyphen makes the tokenizer itself break every
# such phrase into short (<28 char) words, so it never reaches the
# entropy check at all; real secrets (base64, hex, JWT segments, AWS
# keys) essentially never rely on a literal hyphen to encode information.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=]{28,}")
# bits/char. Pure hex (16 symbols) tops out at 4.0 and real hex secrets
# land a little under that (~3.9); random base64/mixed-case tokens sit
# at ~5-6. 3.5 catches both while a degenerate/repeated run (entropy
# near 0) never comes close.
_ENTROPY_THRESHOLD = 3.5


def _shannon_entropy(token: str) -> float:
    """Bits-per-character Shannon entropy of ``token``."""
    if not token:
        return 0.0
    counts = Counter(token)
    length = len(token)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def scan_content(content: str) -> bool:
    """Return True if ``content`` contains a likely secret.

    Checked in order: known token-prefix patterns first (cheap, exact),
    then the entropy heuristic over any long unbroken token found in the
    text. The caller (``bundle.py`` / the MCP export tool) is
    responsible for turning a True result into a ``SecretDetected(path)``
    — this function never sees or reports the path.
    """
    for pattern in _KNOWN_PATTERNS:
        if pattern.search(content):
            return True

    for token in _TOKEN_RE.findall(content):
        if _shannon_entropy(token) >= _ENTROPY_THRESHOLD:
            return True

    return False
