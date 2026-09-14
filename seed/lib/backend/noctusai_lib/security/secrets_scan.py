"""Content secret scan — shared by every consumer that must refuse to
persist a plaintext secret (contract §B.6,
``project-history/roadmaps/julia-agents-academia-2026-09.md``).

Hoisted (A1c) from two independent copies that had drifted apart only
in NAME, never in behaviour:

  - ``products/academia-de-reciclagem/backend/app/importer/secrets.py``
    (``scan_content``, boolean-only)
  - ``mcp/noctusai/tools/noctus/dev/knowledge_bundle_export.py``
    (``_content_has_secret``, boolean-only, explicitly documented as a
    "small duplicate, not an import" because the MCP toolkit process
    cannot import a product package)

Both copies used the IDENTICAL known-pattern list, the identical
hyphen-excluded token regex, and the identical entropy threshold — so
this hoist is a pure move, not a reconciliation of diverging logic.
``noctusai_lib`` is on both processes' Python path (the product via its
normal dependency, the MCP toolkit via its own editable install — see
``mcp/noctusai/tests/test_seed_secrets_scan.py`` for the CI-gating leg
of THIS module, since ``seed/lib/backend/tests/`` itself is not run by
CI), so the "can't import across the product/toolkit boundary" reason
for the duplicate no longer applies to either call site.

Two independent detectors, either one is enough to flag a line:

1. **Known token patterns** — literal prefixes/markers used by common
   secret shapes: Stripe publishable (``pk_``) / secret (``sk-``) keys
   — narrowed with a length guard so plain PT-BR words like
   ``pesquisa`` never match — GitHub PATs (``ghp_``), AWS access key
   ids (``AKIA``), and PEM private-key headers (``-----BEGIN``).
2. **Shannon-entropy heuristic** — any sufficiently long unbroken token
   of base64/hex/url-safe characters whose per-character entropy clears
   a threshold. Ordinary prose (PT-BR included) breaks into short,
   space-separated, low-entropy words and never trips this; a real
   secret is one long high-entropy blob.

``find_secret`` returns the matched pattern NAME (never the value) so a
caller can report *which kind* of secret tripped the scan without ever
being able to leak the value itself — the contract's "naming the path
but never the value" applies one level up, at the caller (the path is
known to the caller, not to this module).
"""
from __future__ import annotations

import math
import re
from collections import Counter

# Fixed-prefix secret shapes. Each pattern requires enough trailing
# characters that an incidental substring match (e.g. someone writing
# the literal word "sk-learning" in prose) can't trip it. Order matters
# only for which NAME is reported when multiple patterns could match
# the same content — the first hit wins.
_KNOWN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("stripe_publishable_key", re.compile(r"pk_[A-Za-z0-9]{16,}")),
    ("stripe_secret_key", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("aws_access_key_id", re.compile(r"AKIA[A-Z0-9]{12,}")),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
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
_ENTROPY_PATTERN_NAME = "high_entropy_token"


def _shannon_entropy(token: str) -> float:
    """Bits-per-character Shannon entropy of ``token``."""
    if not token:
        return 0.0
    counts = Counter(token)
    length = len(token)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def find_secret(content: str) -> str | None:
    """Return the NAME of the first secret pattern ``content`` trips, or
    ``None`` if it looks clean.

    Checked in order: known token-prefix patterns first (cheap, exact),
    then the entropy heuristic over any long unbroken token found in the
    text. Never returns or logs the matched VALUE — only the pattern
    name (e.g. ``"github_pat"``, ``"high_entropy_token"``) — so a
    caller can always safely surface the return value in an error
    detail or a log line.
    """
    for name, pattern in _KNOWN_PATTERNS:
        if pattern.search(content):
            return name

    for token in _TOKEN_RE.findall(content):
        if _shannon_entropy(token) >= _ENTROPY_THRESHOLD:
            return _ENTROPY_PATTERN_NAME

    return None


def has_secret(content: str) -> bool:
    """Boolean convenience wrapper over :func:`find_secret`."""
    return find_secret(content) is not None


__all__ = ["find_secret", "has_secret"]
