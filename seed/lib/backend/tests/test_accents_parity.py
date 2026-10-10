"""Parity: every accent fold migrated onto `noctusai_lib.primitives.accents`
returns byte-identical output to the private copy it replaced.

The `_old_*` functions below are VERBATIM copies of each call site's body as it
stood before the migration (frozen by AST extraction, renamed only). They stay
here as the reference; a future edit that changes a site's output fails this
test instead of silently re-keying stored slugs / match keys.
"""
from __future__ import annotations

import hashlib
import importlib
import re
import unicodedata
from typing import Optional

import pytest

from noctusai_lib.primitives.accents import fold_accents, fold_accents_ascii

# pt-BR text, OCR noise, and the characters where fold variants diverge:
# compatibility forms (º ª ﬁ ² full-width), non-decomposable letters (ß ø æ ł),
# dashes, emoji, mixed whitespace, empty.
CORPUS = [
    "",
    " ",
    "São Paulo/SP",
    "FILIAÇÃO",
    "Ação  de   Cobrança\n\tJoão",
    "Gilson Tangerino — CoreStudio",
    "Nós no Limiar",
    "Qualificação",
    "Domínio Regulatório: revisão/ajuste",
    "Rua Três, nº 81 – 1ª andar, apto 2º",
    "Ｒｕａ １２３ ﬁnal x²",
    "Straße Øresund Æble Łódź",
    "CARTÓRIO DO 2º OFÍCIO | CNS 12.345-6",
    "  trinta e cinco mil reais  ",
    "naïve café crème brûlée",
    "emoji 😀 e ç",
    "MARIA DA CONCEIÇÃO\r\nJOSÉ",
    "\u00a0nbsp\u2003em-space",
]

# frozen from seed/lib/backend/noctusai_lib/integrations/documents/text.py::strip_accents_upper
def _old_strip_accents_upper(text: str) -> str:
    """NFKD-decompose, drop combining marks, uppercase.

    Accents go because OCR is unreliable about them and a label written
    `FILIAÇÃO` must match `FILIACAO`. Uppercasing follows because Brazilian
    ID layouts are already uppercase and case carries no signal here.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/civil_status.py::normalize
def _old_civil_status_normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As every sibling
    parser in this package does."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/cpf.py::normalize
def _old_cpf_normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed.

    Same normalisation the sibling parsers apply, for the same reason: an OCR
    pass produces `C.P.F.` and `Cpf` in equal measure.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/gender.py::normalize
def _old_gender_normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed.

    Same normalisation the sibling parsers apply, for the same reason: an OCR
    pass over a photographed card produces `SÉXO` and `Masculino` in equal
    measure, and matching against every casing/accent variant is a losing game.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/matricula.py::normalize
def _old_matricula_normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/nacionalidade.py::normalize
def _old_nacionalidade_normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As every sibling
    parser in this package does."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/rg.py::normalize
def _old_rg_normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As the siblings do."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/nacionalidade_civil.py::_normalize
def _old_nacionalidade_civil_normalize(value: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed — same shape every
    sibling parser in this package uses."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper()).strip()


# frozen from seed/lib/backend/noctusai_lib/integrations/cnpj_registry/real.py::_sem_acento
def _old_cnpj_sem_acento(texto: str) -> str:
    """Unicode NFKD accent fold (drop every combining mark) — the standard
    library's own primitive, not a hand-rolled translation table (an
    earlier draft of this function used `str.maketrans` with two
    same-length literals and got the alignment wrong; this is the
    boring-and-correct version)."""

    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/money.py::_chave_extenso
def _old_money_chave_extenso(txt: str) -> str:
    """Case/accent/whitespace-insensitive comparison key — a document's own
    typography (capitalisation, an extra space, a line-wrap) must never
    register as a disagreement `reais_por_extenso` itself would never
    produce either."""
    decomposed = unicodedata.normalize("NFKD", txt or "")
    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.strip().lower())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/name.py::chave_nome
def _old_chave_nome(valor: Optional[str]) -> str:
    """Accent-stripped, upper-cased, whitespace-collapsed — for MATCHING."""
    decomposto = unicodedata.normalize("NFKD", valor or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


# frozen from seed/lib/backend/noctusai_lib/integrations/documents/pacto_antenupcial.py::_dobrar
def _old_pacto_dobrar(texto: str) -> str:
    """Upper-case, accent-stripped, LENGTH-PRESERVING — every offset in the
    result is the same offset in `texto`, so a match can be sliced back out
    of the original (accents and case intact)."""
    saida = []
    for c in texto:
        base = "".join(
            ch for ch in unicodedata.normalize("NFKD", c) if not unicodedata.combining(ch)
        )
        saida.append(base.upper() if len(base) == 1 else c.upper()[:1] or " ")
    return "".join(saida)


# frozen from seed/lib/backend/noctusai_lib/integrations/risk_classifier/fake.py::normalized_text_hash
def _old_normalized_text_hash(text: str) -> str:
    """sha256 of the text lower-cased, accent-stripped, whitespace-collapsed."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    norm = re.sub(r"\s+", " ", stripped.lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# frozen from seed/lib/backend/noctusai_lib/primitives/identificador.py::_deaccent_upper
def _old_deaccent_upper(s: str) -> str:
    dec = unicodedata.normalize("NFKD", s)
    return "".join(c for c in dec if not unicodedata.combining(c)).upper()


# frozen from seed/lib/backend/noctusai_lib/domain/pipeline/stages.py::slugify
def _old_stages_slugify(label: str) -> str:
    """Derive a stable machine key from a human label.

    Accent-folding matters here: "Qualificação" must yield `qualificacao`, not
    `qualifica_o`, because the seeded defaults use the unaccented forms and a
    consumer re-creating a deleted stage should land on the same slug.
    """
    folded = unicodedata.normalize("NFKD", label or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "etapa"



CASES = [
    ("strip_accents_upper", "noctusai_lib.integrations.documents.text", "strip_accents_upper", _old_strip_accents_upper),
    ("civil_status_normalize", "noctusai_lib.integrations.documents.civil_status", "normalize", _old_civil_status_normalize),
    ("cpf_normalize", "noctusai_lib.integrations.documents.cpf", "normalize", _old_cpf_normalize),
    ("gender_normalize", "noctusai_lib.integrations.documents.gender", "normalize", _old_gender_normalize),
    ("matricula_normalize", "noctusai_lib.integrations.documents.matricula", "normalize", _old_matricula_normalize),
    ("nacionalidade_normalize", "noctusai_lib.integrations.documents.nacionalidade", "normalize", _old_nacionalidade_normalize),
    ("rg_normalize", "noctusai_lib.integrations.documents.rg", "normalize", _old_rg_normalize),
    ("nacionalidade_civil_normalize", "noctusai_lib.integrations.documents.nacionalidade_civil", "_normalize", _old_nacionalidade_civil_normalize),
    ("cnpj_sem_acento", "noctusai_lib.integrations.cnpj_registry.real", "_sem_acento", _old_cnpj_sem_acento),
    ("money_chave_extenso", "noctusai_lib.integrations.documents.money", "_chave_extenso", _old_money_chave_extenso),
    ("chave_nome", "noctusai_lib.integrations.documents.name", "chave_nome", _old_chave_nome),
    ("pacto_dobrar", "noctusai_lib.integrations.documents.pacto_antenupcial", "_dobrar", _old_pacto_dobrar),
    ("normalized_text_hash", "noctusai_lib.integrations.risk_classifier.fake", "normalized_text_hash", _old_normalized_text_hash),
    ("deaccent_upper", "noctusai_lib.primitives.identificador", "_deaccent_upper", _old_deaccent_upper),
    ("stages_slugify", "noctusai_lib.domain.pipeline.stages", "slugify", _old_stages_slugify)
]


@pytest.mark.parametrize("alias,mod,func,old", CASES, ids=[c[0] for c in CASES])
def test_site_output_unchanged(alias, mod, func, old):
    new = getattr(importlib.import_module(mod), func)
    for text in CORPUS:
        assert new(text) == old(text), (alias, text)


def test_fold_accents_is_nfkd_minus_combining():
    for text in CORPUS:
        dec = unicodedata.normalize("NFKD", text)
        assert fold_accents(text) == "".join(c for c in dec if not unicodedata.combining(c))
        assert fold_accents_ascii(text) == dec.encode("ascii", "ignore").decode("ascii")
    assert fold_accents(None) == "" and fold_accents_ascii(None) == ""
