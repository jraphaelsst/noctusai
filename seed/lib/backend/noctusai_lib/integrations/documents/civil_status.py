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

🔴 CONTRACT F6 — TWO DATES, NEITHER OF THEM `birthdate.py`'S PROBLEM
----------------------------------------------------------------------
`find_data_casamento` / `find_data_emissao` (social-wiring migration 117)
answer questions `birthdate.py` never had to: the office's generated
instrument cites Lei 6.515/77 differently depending on which side of
26/12/1977 the marriage CELEBRATION fell, and a certidão de estado civil
must be under 90 days old AS OF SIGNING — which needs the certidão's own
ISSUANCE date, not the marriage date.

They are label-anchored the same way every function above is, with the
same "never guess" discipline: `find_data_casamento` accepts a REGISTRO
date only when it is itself explicitly labelled (never inferred from an
unlabelled date the way `find_estado_civil` infers "casado" from a bare
regime phrase — a wrong marriage date changes which law an instrument
cites, so the bar here is higher, not the same). `find_data_emissao`
falls back to the document's LAST dated line (the cartório's closing
signature) only when no explicit "emitida em" label exists, and types
that fallback `baixa` — a position-based guess, same posture
`birthdate.find_birthdate` takes for its own single unlabelled candidate.

🔴 WHY THE DATE PARSING IS NOT SHARED WITH `birthdate.py`
------------------------------------------------------------
The two numeric/semi-extenso regexes below overlap what `birthdate.py`
already has. Not extracted into a shared `documents/dates.py` here: this
slice's scope is `types.py` + `civil_status.py` only (social-wiring
migration 117's dispatch), and factoring a shared module means editing
`birthdate.py`, which is out of scope for it. Recurrence is at N=2 —
`KB § PATTERNS/architect/project-execution.md`'s own threshold for
"triage", not yet "must formalize" — surfaced as a scoped-improvement
rather than silently duplicated.

What genuinely IS new here, because no certidão-adjacent parser needed it
before: a certidão frequently spells the WHOLE date in words — "doze de
março de dois mil e dez" — not just the month the way `birthdate.py`'s
semi-extenso form does. `_extenso_prefixo` is a small additive Portuguese
cardinal-number parser, bounded to what a date needs (a day 1-31, a year
in the low thousands), not a general-purpose number-to-words module.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional, Sequence

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


# ─── Dates (contract F6) ──────────────────────────────────────────────────
#
# See the module docstring's "CONTRACT F6" and "WHY THE DATE PARSING IS NOT
# SHARED WITH birthdate.py" sections for what these answer and why the
# numeric/semi-extenso forms below are a deliberate, flagged N=2 with
# `birthdate.py` rather than a shared primitives module.

_MESES: dict[str, int] = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

#: Portuguese cardinal-number tables, additive: UNIDADES/DEZENAS/CENTENAS sum
#: into a running total, MIL multiplies whatever precedes it. Bounded to what
#: a day (1-31) and a year (low thousands) need — not a general number-to-
#: words module.
_UNIDADES: dict[str, int] = {
    "UM": 1, "UMA": 1, "DOIS": 2, "DUAS": 2, "TRES": 3, "QUATRO": 4,
    "CINCO": 5, "SEIS": 6, "SETE": 7, "OITO": 8, "NOVE": 9,
    "DEZ": 10, "ONZE": 11, "DOZE": 12, "TREZE": 13,
    "CATORZE": 14, "QUATORZE": 14, "QUINZE": 15,
    "DEZESSEIS": 16, "DEZESSETE": 17, "DEZOITO": 18, "DEZENOVE": 19,
}
_DEZENAS: dict[str, int] = {
    "VINTE": 20, "TRINTA": 30, "QUARENTA": 40, "CINQUENTA": 50,
    "SESSENTA": 60, "SETENTA": 70, "OITENTA": 80, "NOVENTA": 90,
}
_CENTENAS: dict[str, int] = {
    "CEM": 100, "CENTO": 100, "DUZENTOS": 200, "TREZENTOS": 300,
    "QUATROCENTOS": 400, "QUINHENTOS": 500, "SEISCENTOS": 600,
    "SETECENTOS": 700, "OITOCENTOS": 800, "NOVECENTOS": 900,
}


def _extenso_prefixo(tokens: Sequence[str]) -> tuple[Optional[int], int]:
    """Parse the number-word PREFIX of `tokens` (already normalised, split on
    whitespace). Returns `(valor, quantidade_consumida)` — `valor` is `None`
    when `tokens` does not begin with a recognised number word at all.

    `E` is consumed only when it genuinely connects two number words —
    peeked, never swallowed speculatively — so "TRES E MEIA HORAS DEPOIS"
    (unrelated prose following a year) does not eat the "E" and then stop
    with `visto=True` on a value that never included it.
    """
    total = 0
    atual = 0
    i = 0
    visto = False
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "E":
            proximo = tokens[i + 1] if i + 1 < n else ""
            if proximo in _UNIDADES or proximo in _DEZENAS or proximo in _CENTENAS or proximo == "MIL":
                i += 1
                continue
            break
        if tok == "MIL":
            atual = atual or 1
            total += atual * 1000
            atual = 0
            visto = True
            i += 1
            continue
        if tok in _CENTENAS:
            atual += _CENTENAS[tok]
            visto = True
            i += 1
            continue
        if tok in _DEZENAS:
            atual += _DEZENAS[tok]
            visto = True
            i += 1
            continue
        if tok in _UNIDADES:
            atual += _UNIDADES[tok]
            visto = True
            i += 1
            continue
        break
    if not visto:
        return (None, 0)
    return (total + atual, i)


def _gerar_dias_por_extenso() -> dict[str, int]:
    """Every spelled-out day 1-31, built from the same UNIDADES/DEZENAS
    tables the year parser uses, rather than 31 hand-written entries."""
    dias: dict[str, int] = {}
    for palavra, valor in _UNIDADES.items():
        if 1 <= valor <= 19:
            dias.setdefault(palavra, valor)
    for palavra, valor in _DEZENAS.items():
        if valor not in (20, 30):
            continue
        dias[palavra] = valor
        for u_palavra, u_valor in _UNIDADES.items():
            if 1 <= u_valor <= 9:
                dias[f"{palavra} E {u_palavra}"] = valor + u_valor
    return dias


_DIAS_POR_EXTENSO: dict[str, int] = _gerar_dias_por_extenso()

_NUMERIC_DATE = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
_SEMI_EXTENSO_DATE = re.compile(
    r"\b(\d{1,2})\s+DE\s+(" + "|".join(_MESES) + r")\s+DE\s+(\d{4})\b"
)
_EXTENSO_DATE = re.compile(
    r"\b(" + "|".join(sorted(_DIAS_POR_EXTENSO, key=len, reverse=True)) + r")"
    r"\s+DE\s+(" + "|".join(_MESES) + r")\s+DE\s+"
    r"([A-Z]+(?:\s+[A-Z]+){0,6})"
)

#: No client's marriage or certidão plausibly predates this — the same role
#: `birthdate.MIN_AGE` plays, guarding against an OCR digit confusion
#: producing a well-formed but wrong year.
_ANO_MINIMO = 1900


def _iter_datas(norm: str):
    """Every parseable date in `norm` (already `normalize()`d) as
    `(offset, date)`, across the three forms a certidão uses: numeric
    (`12/03/2010`), semi-extenso (`12 DE MARCO DE 2010`) and fully extenso
    (`DOZE DE MARCO DE DOIS MIL E DEZ`). Malformed values (day 32, a year
    word sequence that fails to parse at all) are skipped, not raised — the
    same posture `birthdate._iter_dates` takes."""
    for m in _NUMERIC_DATE.finditer(norm):
        dia, mes, ano = (int(g) for g in m.groups())
        try:
            yield (m.start(), date(ano, mes, dia))
        except ValueError:
            continue
    for m in _SEMI_EXTENSO_DATE.finditer(norm):
        dia, mes_nome, ano = int(m.group(1)), m.group(2), int(m.group(3))
        try:
            yield (m.start(), date(ano, _MESES[mes_nome], dia))
        except ValueError:
            continue
    for m in _EXTENSO_DATE.finditer(norm):
        dia = _DIAS_POR_EXTENSO[m.group(1)]
        mes = _MESES[m.group(2)]
        ano, _consumidos = _extenso_prefixo(m.group(3).split())
        if ano is None:
            continue
        try:
            yield (m.start(), date(ano, mes, dia))
        except ValueError:
            continue


def _plausivel(d: date, today: date) -> bool:
    return _ANO_MINIMO <= d.year and d <= today


def _rotulo_data(
    haystack: str, at: int, *, labels: Sequence[str], decoys: Sequence[str] = ()
) -> Achado:
    """Same shared label-window mechanism every function above uses —
    `labels.label_before`, not a bespoke copy. `decoys` are passed as
    `valores`: a different KIND of date (an emission date competing with a
    celebration date, or vice-versa) is rejected outright, not demoted —
    there is no "different person" block-ambiguity for a document-level
    date the way there is for `estado_civil`."""
    return label_before(haystack, at, labels=labels, blocos=(), valores=decoys, window=_LABEL_WINDOW)


#: Celebration-date labels. Longest/most-specific alternatives listed first
#: is not required here (unlike `birthdate._BIRTH_LABELS`) since
#: `label_before` itself already prefers the label that ends latest, then the
#: longest, on a tie.
_CASAMENTO_LABELS = (
    "CASARAM-SE EM", "CASARAM SE EM", "DATA DO CASAMENTO", "DATA DE CASAMENTO",
    "CASADOS EM", "CONTRAIRAM CASAMENTO EM", "CONTRAIU CASAMENTO EM",
)
#: Used ONLY when no celebration-date label exists anywhere in the document —
#: see `find_data_casamento`'s "never guess" note. Still requires an explicit
#: label of its own; an unlabelled date is never accepted as the registro.
_CASAMENTO_LABELS_FALLBACK = (
    "DATA DE REGISTRO", "DATA DO REGISTRO", "REGISTRADO EM", "REGISTRO EM",
)
_CASAMENTO_DECOYS = (
    "DATA DE NASCIMENTO", "DATA NASCIMENTO",
    "EMITIDA EM", "EMITIDO EM", "DATA DE EMISSAO", "DATA EMISSAO",
)

_EMISSAO_LABELS = ("EMITIDA EM", "EMITIDO EM", "DATA DE EMISSAO", "DATA EMISSAO")
_EMISSAO_DECOYS = (
    "DATA DE NASCIMENTO", "DATA NASCIMENTO",
    "DATA DO CASAMENTO", "DATA DE CASAMENTO", "CASARAM-SE EM", "CASARAM SE EM",
)


def find_data_casamento(
    text: str, *, today: Optional[date] = None
) -> tuple[Optional[date], str, Optional[str]]:
    """Extract the marriage CELEBRATION date off a certidão de casamento.

    Returns `(value, confidence, matched_label)` — value one of the three
    date forms `_iter_datas` recognises, confidence one of `"alta"` /
    `"nenhuma"` (never `"baixa"`: unlike a birthdate, a wrong marriage date
    changes which side of Lei 6.515/77's 26/12/1977 line the office's
    generated instrument cites, so there is no unlabelled-guess tier here —
    see the module docstring).

    Resolution order:

    1. **A celebration-date label** ("casaram-se em", "data do casamento", …).
       Several labelled dates that agree are still `alta`; several that
       disagree report `nenhuma` — the layout was misread, not updated (a
       marriage date does not change over time the way `estado_civil` does,
       so there is no averbação-precedence rule to apply here).
    2. **A registro-date label**, used ONLY when step 1 found nothing. Still
       requires its OWN explicit label — "registro date fallback only if
       clearly labelled": an unlabelled date is never promoted to the
       registro date by position alone.

    A document carrying neither is legible with the field simply absent —
    `(None, "nenhuma", None)`, never a guess.
    """
    today = today or date.today()
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    def _rotuladas(
        labels: Sequence[str], *, extra_decoys: Sequence[str] = ()
    ) -> list[tuple[date, str]]:
        # `extra_decoys` is the OTHER label set — a nearer, more-specific
        # label (e.g. "DATA DE REGISTRO" sitting right next to its own date)
        # must block a farther, merely-in-window primary label from claiming
        # that date too. Same "different KIND of value" rejection
        # `_CASAMENTO_DECOYS` already does for emission-date labels.
        decoys = tuple(_CASAMENTO_DECOYS) + tuple(extra_decoys)
        achadas: list[tuple[date, str]] = []
        for offset, valor in _iter_datas(norm):
            if not _plausivel(valor, today):
                continue
            achado = _rotulo_data(norm, offset, labels=labels, decoys=decoys)
            if achado.rejeitado or achado.rotulo is None:
                continue
            achadas.append((valor, achado.rotulo))
        return achadas

    primarias = _rotuladas(_CASAMENTO_LABELS, extra_decoys=_CASAMENTO_LABELS_FALLBACK)
    if primarias:
        distintas = {v for v, _ in primarias}
        if len(distintas) == 1:
            return (primarias[0][0], "alta", primarias[0][1])
        return (None, "nenhuma", None)

    secundarias = _rotuladas(_CASAMENTO_LABELS_FALLBACK, extra_decoys=_CASAMENTO_LABELS)
    if secundarias:
        distintas = {v for v, _ in secundarias}
        if len(distintas) == 1:
            return (secundarias[0][0], "alta", secundarias[0][1])
        return (None, "nenhuma", None)

    return (None, "nenhuma", None)


def find_data_emissao(
    text: str, *, today: Optional[date] = None
) -> tuple[Optional[date], str, Optional[str]]:
    """Extract the certidão's OWN issuance date — when the cartório closed
    it, not a fact about the holder. Read off `certidao_casamento` AND
    `certidao_nascimento` alike; see `types.IdentityFields.data_emissao` for
    why this rides on the document rather than promoting to `clientes`.

    Resolution order:

    1. **An explicit label** ("emitida em", "emitido em", "data de emissão").
       Several that agree are `alta`; several that disagree are `nenhuma`.
    2. **The document's LAST dated line** — the cartório's closing signature,
       used only when step 1 found nothing. Genuinely a guess by position,
       so it is typed `baixa` and never written unattended — the same
       posture `birthdate.find_birthdate` takes for a single unlabelled
       candidate.

    A document carrying no date at all is `(None, "nenhuma", None)`.
    """
    today = today or date.today()
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    candidatas = [
        (offset, valor) for offset, valor in _iter_datas(norm) if _plausivel(valor, today)
    ]
    if not candidatas:
        return (None, "nenhuma", None)

    rotuladas: list[tuple[date, str]] = []
    for offset, valor in candidatas:
        achado = _rotulo_data(norm, offset, labels=_EMISSAO_LABELS, decoys=_EMISSAO_DECOYS)
        if achado.rotulo is not None and not achado.rejeitado:
            rotuladas.append((valor, achado.rotulo))

    if rotuladas:
        distintas = {v for v, _ in rotuladas}
        if len(distintas) == 1:
            return (rotuladas[0][0], "alta", rotuladas[0][1])
        return (None, "nenhuma", None)

    _ultimo_offset, ultimo_valor = max(candidatas, key=lambda c: c[0])
    return (ultimo_valor, "baixa", "FECHAMENTO_CARTORIO")


__all__ = [
    "ESTADO_CIVIL_VALORES",
    "REGIME_BENS_VALORES",
    "find_data_casamento",
    "find_data_emissao",
    "find_estado_civil",
    "find_regime_bens",
    "normalize",
]
