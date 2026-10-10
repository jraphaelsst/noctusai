"""Parity: `_slugify_kebab` on the seed `fold_accents_ascii` returns the
byte-identical slug the private NFKD/ascii fold produced (stored slugs must
not move). `_old_slugify_kebab` is the pre-migration body, verbatim."""
from __future__ import annotations

import re
import unicodedata

from app.routers.kb_router import _slugify_kebab

CORPUS = [
    "", " ", "Domínio Regulatório", "Domínio Regulatório — PNRS",
    "Ação / Cobrança: revisão", "nº 1ª 2º", "ＰＮＲＳ ﬁnal x²",
    "Straße Øresund", "emoji 😀 ç", "日本", "--já--",
]


def _old_slugify_kebab(label: str) -> str:
    """Kebab-case slug derivation (§B.1: "slug is derived from titulo
    when omitted"). Accent-folds so "Domínio Regulatório" -> "dominio-
    regulatorio", matching the sibling's own slug shape (§0's example:
    `dominio-regulatorio-pnrs`)."""
    folded = unicodedata.normalize("NFKD", label or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "entrada"


def test_slug_unchanged():
    for text in CORPUS:
        assert _slugify_kebab(text) == _old_slugify_kebab(text), text
