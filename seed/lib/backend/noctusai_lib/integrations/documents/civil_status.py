"""`find_estado_civil` / `find_regime_bens` — marital status off a Brazilian
identity document or certidão.

Sixth and seventh siblings of `birthdate.py`, `name.py`, `gender.py`,
`cpf.py` and `rg.py`, but the first of the family whose own truth CHANGES
after the document was issued: a certidão de casamento (or de nascimento)
carries its original REGISTRO on page one and, further in, the AVERBAÇÕES —
divórcio, separação judicial, óbito, conversão de união estável — that amend
it. See social-wiring migration 103's header for why truncating such a
document does not lose detail; it inverts the answer.

🔴 WHY THIS FIELD IS NORMALISED TO A CODE, UNLIKE `genero`
------------------------------------------------------------
`gender.py` returns the document's own word ("Masculino") because the
consuming column is unconstrained TEXT holding exactly that word.
`social_wiring.clientes.estado_civil` / `.regime_bens` (migration 097) are
ALSO unconstrained TEXT — deliberately, so the vocabulary can grow without a
migration (see that migration's header) — but this extractor still
normalises to a closed snake_case vocabulary rather than echoing the
document's prose.

The reason is what this field is FOR, not how it is stored. `estado_civil`
decides whether a spouse must sign an instrument (CC art. 1.647), so a
downstream consumer branches on the VALUE, not on its spelling. Free-text
pass-through would make "casado", "Casado(a)" and "... sob o regime da
comunhão parcial ..." three different strings to that branch. A closed
vocabulary is this extractor's OWN contract; a consumer remains free to keep
the document's literal wording too — that is what `*_rotulo` is for.

🔴 DISAGREEMENT IS NOT ALWAYS ABSENCE, HERE
---------------------------------------------
Every sibling parser treats two conflicting readings as a misread and
reports nothing (`gender.py`'s "disagreement is absence"). That rule is
wrong for a field whose whole point is to change over the life of the
document: a registro reading "casado" and an averbação reading "divorciado"
are not a disagreement, they are a timeline, and the later one is the truth.

So both functions here distinguish the two cases by POSITION: a conflict
that straddles an AVERBAÇÃO marker resolves to the later (post-marker)
reading; a conflict with no averbação between the two readings falls back to
the family's usual rule — `nenhuma`, because that shape really is OCR noise
or a misread, not an update.

🔴 NEVER GUESS
----------------
`estado_civil` is inferred from a bare `regime_bens` reading ONLY because
that phrase has no other reason to appear in Brazilian legal prose — the
same structural-evidence argument `cpf.py` makes for a check digit. Every
other case requires an explicit `ESTADO CIVIL` label or an AVERBAÇÃO event
keyword. There is deliberately no unlabelled-whole-word fallback (unlike
`gender.py`'s `MASCULINO`/`FEMININO`): "casado" and "solteiro" are ordinary
Portuguese words with far more reasons to appear loose in prose than a sex
word does, so accepting them unlabelled would be a guess wearing a
confidence score. A document that simply does not carry the field returns
`(None, "nenhuma", None)`.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.labels import Achado, label_before

#: Same window every sibling parser uses — these are the same document
#: layouts.
_LABEL_WINDOW = 48

# ─── Closed vocabulary ───────────────────────────────────────────────────
#: `social_wiring.clientes.estado_civil` is unconstrained TEXT (migration
#: 097) — the taxonomy lives HERE, in the extractor, not in a database
#: CHECK, for the reason that migration's header gives. Snake_case because
#: this is the extractor's own token, not the document's wording — see the
#: module docstring.
ESTADO_CIVIL_VALORES: tuple[str, ...] = (
    "solteiro",
    "casado",
    "divorciado",
    "separado_judicialmente",
    "viuvo",
    "uniao_estavel",
)

#: `social_wiring.clientes.regime_bens` — same unconstrained-TEXT column,
#: same reasoning.
REGIME_BENS_VALORES: tuple[str, ...] = (
    "comunhao_parcial",
    "comunhao_universal",
    "separacao_total",
    "separacao_obrigatoria",
    "participacao_final_aquestos",
)

_ESTADO_CIVIL_LABELS = ("ESTADO CIVIL", "EST CIVIL")

#: Same block-opener discipline every sibling applies: a value sitting
#: inside a FILIACAO/CONJUGE block may be a different person's.
_BLOCO_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
    "RESPONSAVEL",
)

#: Whole word/phrase -> canonical token. Requires an `ESTADO CIVIL` label —
#: see the module docstring's "never guess" note.
_ESTADO_CIVIL_PALAVRAS: dict[str, str] = {
    "SOLTEIRO": "solteiro",
    "SOLTEIRA": "solteiro",
    "CASADO": "casado",
    "CASADA": "casado",
    "DIVORCIADO": "divorciado",
    "DIVORCIADA": "divorciado",
    "SEPARADO JUDICIALMENTE": "separado_judicialmente",
    "SEPARADA JUDICIALMENTE": "separado_judicialmente",
    "VIUVO": "viuvo",
    "VIUVA": "viuvo",
    "UNIAO ESTAVEL": "uniao_estavel",
}
_ESTADO_CIVIL_VALOR_RE = re.compile(
    r"\b("
    + "|".join(sorted(_ESTADO_CIVIL_PALAVRAS, key=len, reverse=True))
    + r")\b"
)

#: Regime phrases are matched UNLABELLED, on purpose — see the module
#: docstring's structural-evidence note. Each pattern tolerates the "DE
#: BENS" suffix being present or elided (a certidão often states it once
#: and a later averbação restates only the regime name).
_REGIME_BENS_PADROES: tuple[tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"COMUNHAO\s+PARCIAL(?:\s+DE\s+BENS)?"), "comunhao_parcial"),
    (re.compile(r"COMUNHAO\s+UNIVERSAL(?:\s+DE\s+BENS)?"), "comunhao_universal"),
    (
        re.compile(r"SEPARACAO\s+(?:TOTAL|CONVENCIONAL)(?:\s+DE\s+BENS)?"),
        "separacao_total",
    ),
    (
        re.compile(r"SEPARACAO\s+(?:OBRIGATORIA|LEGAL)(?:\s+DE\s+BENS)?"),
        "separacao_obrigatoria",
    ),
    (
        re.compile(r"PARTICIPACAO\s+FINAL\s+(?:NOS|DE)\s+AQUESTOS"),
        "participacao_final_aquestos",
    ),
)

#: Marks the start of an AVERBAÇÃO zone. `normalize()` strips accents first,
#: so this bare prefix alone matches AVERBAÇÃO / AVERBAÇÕES / AVERBADO /
#: AVERBADA.
_AVERBACAO_RE = re.compile(r"AVERBA\w*")

#: Event keyword -> the `estado_civil` it establishes. Order is not a
#: priority list — `find_estado_civil` treats more than one DISTINCT match
#: inside the same AVERBAÇÃO zone as a disagreement, not a ranking.
_AVERBACAO_EVENTOS: tuple[tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"DIVORCIO"), "divorciado"),
    (re.compile(r"SEPARACAO\s+JUDICIAL"), "separado_judicialmente"),
    (re.compile(r"OBITO|FALECIMENTO"), "viuvo"),
    (re.compile(r"CONVERSAO\s+DE\s+UNIAO\s+ESTAVEL"), "casado"),
    (re.compile(r"RECONHECIMENTO\s+DE\s+UNIAO\s+ESTAVEL"), "uniao_estavel"),
)


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As every sibling
    parser in this package does."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def _label_before(haystack: str, at: int) -> Achado:
    """Delegate to the shared label window — see `labels.py`."""
    return label_before(
        haystack,
        at,
        labels=_ESTADO_CIVIL_LABELS,
        blocos=_BLOCO_LABELS,
        window=_LABEL_WINDOW,
    )


def _averbacao_start(norm: str) -> Optional[int]:
    """Where the first AVERBAÇÃO marker begins in already-normalised text,
    or `None` when the document carries no averbação section at all."""
    m = _AVERBACAO_RE.search(norm)
    return m.start() if m else None


def find_regime_bens(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the marital property regime.

    Returns `(value, confidence, matched_label)` — value one of
    :data:`REGIME_BENS_VALORES`, confidence one of `"alta"` / `"nenhuma"`
    (the string values of `types.ExtractionConfidence`, kept as plain
    strings so this module stays import-free of the rest of the package —
    same shape as every sibling parser).

    Deliberately unlabelled: unlike every other field in this package, the
    phrase ITSELF ("comunhão parcial de bens") is the structural evidence —
    it has no other reason to appear in Brazilian legal prose. See the
    module docstring.

    - **alta** — exactly one distinct phrase found, OR two (or more) that
      differ but straddle an AVERBAÇÃO marker — the later reading is an
      update, not a misread. The matched label is `AVERBACAO: <phrase>` in
      that case, so an auditor can see the override happened.
    - **nenhuma** — nothing, or two distinct phrases with no AVERBAÇÃO
      between them (indistinguishable from a misread).
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    achados: list[tuple[int, str, str]] = []  # (start, canonical, phrase)
    for padrao, canonico in _REGIME_BENS_PADROES:
        for m in padrao.finditer(norm):
            achados.append((m.start(), canonico, m.group(0)))
    if not achados:
        return (None, "nenhuma", None)

    achados.sort(key=lambda a: a[0])
    distintos = {c for _, c, _ in achados}
    if len(distintos) == 1:
        return (achados[0][1], "alta", achados[0][2])

    # More than one distinct reading. An AVERBAÇÃO strictly between the
    # FIRST and the LAST is what turns "disagreement" into "the document
    # was updated" — the later reading is then the current truth.
    averbacao_pos = _averbacao_start(norm)
    if averbacao_pos is not None and achados[0][0] < averbacao_pos < achados[-1][0]:
        ultimo = achados[-1]
        return (ultimo[1], "alta", f"AVERBACAO: {ultimo[2]}")

    return (None, "nenhuma", None)


def find_estado_civil(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's marital status.

    Returns `(value, confidence, matched_label)` — value one of
    :data:`ESTADO_CIVIL_VALORES`.

    Resolution order:

    1. **An AVERBAÇÃO event** (divórcio, separação judicial, óbito,
       conversão de união estável, reconhecimento de união estável) — the
       most recent fact on the document, so it OVERRIDES everything before
       it. More than one DISTINCT event inside the AVERBAÇÃO zone reports
       `nenhuma`, not a guess at which one is real.
    2. **An explicit `ESTADO CIVIL` label.**
    3. **A bare `regime_bens` reading**, with no averbação event resolved
       in step 1 — the presence of a matrimonial-regime phrase is itself
       structural evidence of "casado" (see the module docstring). This
       step never overrides a step-1 result.

    A document carrying none of the three is legible with the field simply
    absent — `(None, "nenhuma", None)`, never a guess.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    averbacao_pos = _averbacao_start(norm)
    if averbacao_pos is not None:
        zona = norm[averbacao_pos:]
        eventos = {
            canonico
            for padrao, canonico in _AVERBACAO_EVENTOS
            if padrao.search(zona)
        }
        if len(eventos) > 1:
            # Conflicting amendments — cannot tell which is real.
            return (None, "nenhuma", None)
        if len(eventos) == 1:
            canonico = next(iter(eventos))
            padrao = next(p for p, c in _AVERBACAO_EVENTOS if c == canonico)
            m = padrao.search(zona)
            assert m is not None  # canonico came from a match in `zona`
            return (canonico, "alta", f"AVERBACAO: {m.group(0)}")
        # An averbação zone exists but carries none of the known events —
        # fall through to the registro reading below, unresolved by this
        # document's amendments.

    rotulados: list[tuple[str, str]] = []
    for m in _ESTADO_CIVIL_VALOR_RE.finditer(norm):
        valor = _ESTADO_CIVIL_PALAVRAS[m.group(1)]
        achado = _label_before(norm, m.start())
        if achado.rejeitado:
            continue
        if achado.rotulo and not achado.rebaixado:
            rotulados.append((valor, achado.rotulo))
        # An unlabelled or block-demoted reading is dropped, not queued at
        # low confidence — see the module docstring's "never guess" note.

    if rotulados:
        distintos = {v for v, _ in rotulados}
        if len(distintos) == 1:
            valor, rotulo = rotulados[0]
            return (valor, "alta", rotulo)
        return (None, "nenhuma", None)

    # No explicit label, no averbação event. The one structural inference
    # this module makes: a matrimonial-regime phrase has no reason to be on
    # the page unless the document is recording a marriage.
    regime, regime_conf, regime_rotulo = find_regime_bens(text)
    if regime is not None and regime_conf == "alta":
        return ("casado", "alta", regime_rotulo)

    return (None, "nenhuma", None)


__all__ = [
    "ESTADO_CIVIL_VALORES",
    "REGIME_BENS_VALORES",
    "find_estado_civil",
    "find_regime_bens",
    "normalize",
]
