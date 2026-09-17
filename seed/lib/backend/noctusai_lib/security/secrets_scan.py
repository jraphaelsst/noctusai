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
    # Stripe's REAL secret/restricted key prefixes. The `sk-` entry above
    # never matched them; they were caught only because they are mixed-case
    # (entropy) — named here so a lowercase-looking one cannot slip by.
    ("stripe_live_or_restricted_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
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
#
# `/` stays IN the character class (unlike `-`): base64's own alphabet
# uses `/`, so a real secret can legitimately contain one — stripping it
# from the tokenizer, mirroring the hyphen fix, would silently chop a
# 40+ char secret at every `/` into fragments that can each duck under
# the 28-char minimum (a worse false negative than the false positive
# below). Instead the `/`-shaped false positive (a source path like
# ``backend/app/services/agent_runner``, all-lowercase, 33 chars,
# ~3.84 bits/char once slashes are folded into the entropy calc — right
# past ``_ENTROPY_THRESHOLD``) is handled downstream in ``find_secret``
# by classifying the WHOLE already-tokenized string via
# ``_looks_like_code_path`` before the entropy check ever runs.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=]{28,}")
# bits/char. Pure hex (16 symbols) tops out at 4.0 and real hex secrets
# land a little under that (~3.9); random base64/mixed-case tokens sit
# at ~5-6. 3.5 catches both while a degenerate/repeated run (entropy
# near 0) never comes close.
_ENTROPY_THRESHOLD = 3.5
_ENTROPY_PATTERN_NAME = "high_entropy_token"

# A `/`-segment that looks like a lowercase code/path identifier:
# letters/digits/underscore only, starting with a letter — no uppercase,
# no `+`, no `=`. Requiring lowercase-only is what keeps a real
# mixed-case base64 secret (which almost always carries at least one
# uppercase char across a 28+ char run) from ever matching this branch.
_CODE_PATH_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# The last segment of a path may additionally carry a short lowercase
# file extension (`.py`, `.md`, `.sql`, `.yml`, ...).
_CODE_PATH_LAST_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9]{1,10})?$")


def _shannon_entropy(token: str) -> float:
    """Bits-per-character Shannon entropy of ``token``."""
    if not token:
        return 0.0
    counts = Counter(token)
    length = len(token)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def _looks_like_code_path(token: str) -> bool:
    """True when a `/`-containing token that cleared ``_TOKEN_RE`` is a
    source/asset path, not a secret — the `/` analogue of the hyphen
    exclusion documented above ``_TOKEN_RE``.

    Deliberate, conservative shape (a detector that MISSES a real key is
    worse than a false positive, per the brief):

    1. Every segment (split on `/`) must match the lowercase-identifier
       grammar ``_CODE_PATH_SEGMENT_RE`` — no uppercase, no `+`/`=`. A
       real base64/hex secret containing `/` (e.g. mixed-case, digits,
       `+`, `=` padding) fails this immediately and still falls through
       to the entropy check below, unaffected. This is what keeps a
       genuine ``.../ABCdef123.../...`` secret flagged.
    2. The final segment may additionally carry a short lowercase
       extension (``_CODE_PATH_LAST_SEGMENT_RE``) — real file paths
       (``.../secrets_scan.py``, ``.../docs/SPEC.md``).
    3. A MAJORITY of segments must contain no digit. Ordinary source
       trees / doc slugs are words (``backend``, ``services``,
       ``agent_runner``) with digits appearing rarely (a version
       segment like ``v2``). An adversarial random blob chopped into
       short "path-shaped" pieces to dodge detection (e.g.
       ``k3j9x/q8w2z/...``) mixes a digit into nearly EVERY segment,
       because its source alphabet is base36/base62-ish — so it fails
       this check and is deliberately left to the entropy heuristic
       below (i.e. still flaggable). This is the documented, deliberate
       call for that class: length/shape alone can't tell a short real
       path segment (``app``, 3 chars) from a short random one, but
       digit-density across segments can.

    A token with no `/` at all (a single unbroken lowercase run, no
    path structure) never reaches this function — see the call site in
    ``find_secret``, which only invokes it when ``"/" in token``. That
    class's behaviour is UNCHANGED by this fix: it is still scored by
    ``_shannon_entropy`` alone, exactly as before (documented, not
    silently altered — see
    ``TestCodePathFalsePositives::test_lowercase_only_token_with_no_slash_is_still_flagged``
    in ``mcp/noctusai/tests/test_seed_secrets_scan.py``).
    """
    segments = token.split("/")
    if len(segments) < 2:
        return False
    # 4. No segment may contain a BLOB: an `_`-free run of 16+ chars with a
    #    digit (extension stripped). Without this, a lowercase hex secret
    #    after a `/` in a URL (`com/webhook/e3b0c442…` — the tokenizer stops
    #    at `.`, so the host tail joins the token) passed rules 1-3 as one
    #    long "identifier". Judged per `_`-word so a real name like
    #    `adr_0001_agent_design` (short words) still reads as a path.
    for segment in segments:
        stem = segment.split(".", 1)[0]
        for word in stem.split("_"):
            if len(word) >= 16 and any(c.isdigit() for c in word):
                return False
    for segment in segments[:-1]:
        if not _CODE_PATH_SEGMENT_RE.match(segment):
            return False
    if not _CODE_PATH_LAST_SEGMENT_RE.match(segments[-1]):
        return False
    digit_segments = sum(1 for seg in segments if any(c.isdigit() for c in seg))
    return digit_segments * 2 <= len(segments)


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
        if "/" in token and _looks_like_code_path(token):
            continue
        if _shannon_entropy(token) >= _ENTROPY_THRESHOLD:
            return _ENTROPY_PATTERN_NAME

    return None


def has_secret(content: str) -> bool:
    """Boolean convenience wrapper over :func:`find_secret`."""
    return find_secret(content) is not None


__all__ = ["find_secret", "has_secret"]
