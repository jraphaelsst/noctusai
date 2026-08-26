"""Identity resolution — the pure algorithm behind `clientes` (person layer).

`project-history/roadmaps/lead-card-hub-2026-08.md` §2/§4 (P1.3) +
`products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §2/§3 are the
contract this module implements. Read §3 first — the C1-C6 predicate table
is reproduced here as code, not re-derived.

**Deliberately I/O-free.** Every function here takes plain data in and
returns plain data out — no Supabase client, no network. `clientes_service`
is the layer that fetches rows and writes results; this module is the part
that can be unit-tested with a handful of dicts and no database at all,
which matters because this migration cannot be applied or run against any
database before a human decides to (`PROJECT.md` §7) — the tests against
THIS module are the only pre-apply verification the classification logic
gets.

THE C1-C6 PREDICATE
--------------------
Two source rows (a `leads` row or a `meta_ads_leads` row) are the same
person iff their canonical contact key (`chave_canonica` — E.164 phone or
lowercased email) is equal AND non-null, AND their names are compatible.
Name compatibility is evaluated on the SAME normalization the DB predicate
would use: lower(unaccent(trim(collapse_whitespace(name)))).

Within a (org_id, chave_canonica) group, classification looks only at the
DISTINCT normalized names among rows that HAVE a name (nameless rows are
tracked separately — `has_nameless` — and never contribute a "distinct
name" of their own):

    0 or 1 distinct name                       -> C1 (or C3 if has_nameless)
    2 distinct names, one a token-prefix of     -> C2 (or C3 if has_nameless)
      the other ("Maria Silva" / "Maria")
    2 distinct names, same first token,         -> C4 (review)
      diverging after that ("Maria Silva" /
      "Maria Souza")
    2 distinct names, no relationship at all    -> C5 (review)
    3 or more distinct names                    -> C6 (review)

C1/C2/C3 auto-merge; C4/C5/C6 land in the review queue. This is a literal
transcription of the contract's §3 table — the "0 distinct names" arm
(every row in the group is nameless, despite sharing a real key) is not
itself named in the table because the live census found zero such groups;
it is handled here as a degenerate C1 (auto-merge — there is no name
information to disagree about, so nothing blocks folding the rows
together) rather than left unhandled, in case a future group hits it.
This is a genuine interpretation call, not something the contract states
explicitly — flagged in the Slice A delivery note, not hidden here.

WHY "C3" DOESN'T MEAN "1 MERGE"
--------------------------------
C3 covers BOTH "one named cluster + nameless rows riding along" (needs no
merge at all — there was only ever one identity) AND "two prefix-compatible
named clusters + nameless rows" (needs exactly one merge, same as a bare
C2). `classify_group` returns the actual `named_clusters` mapping so the
caller can tell these apart by `len(named_clusters)`, rather than inferring
merge count from the motivo string.

THE clientes.chave_canonica UNIQUE CONSTRAINT, AND WHAT THAT MEANS FOR
REVIEW GROUPS
------------------------------------------------------------------------
`clientes` carries `UNIQUE (org_id, chave_canonica) WHERE chave_canonica
IS NOT NULL` (contract §4, 🔴). At most ONE cliente may ever hold a given
real phone/email. A C4-C6 (review) group therefore CANNOT be represented
as multiple clientes that all provisionally claim the same key — that
would violate the constraint the day the backfill runs, not eventually.

So for a review group, `clientes_service` (the caller of this module)
creates one cliente per distinct name-cluster exactly as for an
auto-merge, but leaves EVERY one of them `chave_canonica = NULL,
identidade_incerta = true` — none of them claims the shared key until a
human resolves the ambiguity (Slice B's `POST .../revisao/{grupo}/merge`).
This is a deliberate generalisation of `identidade_incerta`'s contract
definition (§2: "no key at all") to also cover "a key that is real but is
demonstrably shared with someone else, and therefore cannot serve as this
cliente's unique key yet." The real key is never lost — it survives on
every `cliente_touches.chave_canonica` row (and, losslessly, on the source
`leads`/`meta_ads_leads` row itself) — so a human resolving the group can
recover it and assign it to whichever cliente is confirmed correct.
`identidade_incerta` therefore does not ONLY mean "the 399 keyless leads"
in the implementation, though that remains its most common cause. This
interpretation is surfaced explicitly in the Slice A delivery note as a
candidate contract clarification.

Carmen Real Dias / Luana Batista (the shared-household-phone example in
the roadmap, §3 🔴) is exactly the case this protects: two real people
cannot both hold `+5511974781330` as their canonical key simultaneously,
so until an operator decides who (if anyone) keeps it, neither does.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

__all__ = [
    "SourceRow",
    "GroupClassification",
    "AUTO_MERGE_CODES",
    "REVIEW_CODES",
    "normalize_name",
    "leads_row_to_source",
    "meta_lead_row_to_source",
    "classify_group",
    "classify_names",
    "build_clusters",
    "longest_raw_name",
    "span",
]

AUTO_MERGE_CODES = frozenset({"C1", "C2", "C3"})
REVIEW_CODES = frozenset({"C4", "C5", "C6"})


# ─── source-row normalization ───────────────────────────────────────────


@dataclass(frozen=True)
class SourceRow:
    """One `leads` or `meta_ads_leads` row, reduced to what identity
    resolution needs. `chave_canonica`/`chave_tipo` are already-canonical —
    `leads.contato_norm`/`contato_tipo` (migration 037's trigger) and
    `meta_ads_leads.phone` (same trigger) arrive pre-normalized; this
    module never re-derives a phone/email, it only reads what the DB
    already guarantees."""

    origem_tabela: str  # "leads" | "meta_ads_leads"
    origem_id: str
    org_id: str
    nome: Optional[str]
    chave_canonica: Optional[str]
    chave_tipo: Optional[str]  # "telefone" | "email" | None
    ocorreu_em: str  # ISO-8601, whatever precision the source column has
    origem_label: Optional[str] = None


def _clean_str(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_iso(value: object) -> str:
    """Coerce a date/datetime/str source value to an ISO-8601 string.

    `leads.data_entrada` is a bare DATE; `meta_ads_leads.created_time` is a
    full timestamptz. Both round-trip through `str()`/`.isoformat()`
    cleanly; a bare date string sorts correctly against a same-format
    date string, and `span()` below parses either shape back into a
    real `datetime` before comparing, so mixed granularity never produces
    a wrong min/max.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    return str(value)


def leads_row_to_source(row: dict) -> SourceRow:
    """`social_wiring.leads` row -> `SourceRow`.

    `chave_tipo` is read straight off `contato_tipo`, EXCEPT when
    `contato_norm` is null — `leads.contato_tipo` can still say
    'telefone' for an unparseable-but-phone-shaped value (see
    `leads_service._derive_contato_fields`), and that is not a usable
    key: a row with no `contato_norm` is exactly the §2 keyless case and
    must carry `chave_canonica = chave_tipo = None`, never a type with no
    key behind it.
    """
    chave = row.get("contato_norm") or None
    return SourceRow(
        origem_tabela="leads",
        origem_id=str(row["id"]),
        org_id=str(row["org_id"]),
        nome=_clean_str(row.get("cliente_nome")),
        chave_canonica=chave,
        chave_tipo=(row.get("contato_tipo") if chave else None),
        ocorreu_em=_as_iso(row.get("data_entrada")),
        origem_label=_clean_str(row.get("origem_raw")),
    )


def meta_lead_row_to_source(row: dict) -> SourceRow:
    """`social_wiring.meta_ads_leads` row -> `SourceRow`.

    No `contato_norm`/`contato_tipo` split exists on this table (033's
    header: "no norm/raw split... `raw` already holds the original
    payload"). `phone` is already E.164 (037's trigger); `email` is used
    lowercased when there is no phone, matching the same
    phone-before-email precedence `leads_service._derive_contato_fields`
    uses for a row that could be either.
    """
    phone = _clean_str(row.get("phone"))
    email = _clean_str(row.get("email"))
    if phone:
        chave, tipo = phone, "telefone"
    elif email:
        chave, tipo = email.lower(), "email"
    else:
        chave, tipo = None, None
    return SourceRow(
        origem_tabela="meta_ads_leads",
        origem_id=str(row["id"]),
        org_id=str(row["org_id"]),
        nome=_clean_str(row.get("full_name")),
        chave_canonica=chave,
        chave_tipo=tipo,
        ocorreu_em=_as_iso(row.get("created_time") or row.get("synced_at")),
        origem_label=_clean_str(row.get("campaign_name") or row.get("form_name")),
    )


# ─── name normalization + compatibility ─────────────────────────────────


#: Leading/trailing tokens that are NOT part of anyone's name — they are how a
#: lead's ORIGIN got typed into the name field. Derived from the live review
#: queue on 2026-08-25, not invented: `hp luiza`/`luiza`,
#: `de lead luiz alberto`/`luis alberto`, `retono morgana`/`morgana`,
#: `v4 adilaine pavan`/`adilaine`, `rebelo insta`/`wildo rebello`.
#:
#: 🔴 A token here is stripped ONLY when something survives it. "Lead" alone
#: stays "lead" rather than becoming nameless — a nameless row rides along with
#: whatever else is in its group (the C3 rule), which is a much bigger claim
#: than "this name has a prefix on it".
MARCADORES_DE_ORIGEM: frozenset[str] = frozenset(
    {"hp", "lead", "leads", "de", "retono", "retorno", "v4", "vv", "prof", "insta"}
)


def _strip_marcadores(tokens: list[str]) -> list[str]:
    """Drop origin markers from BOTH ends, never from the middle.

    Both ends because the live data has them both ways (`v4 adilaine pavan`,
    `rebelo insta`). Never the middle, because a token surrounded by name
    tokens is overwhelmingly likely to BE one — "Ana de Souza" must not lose
    its "de".
    """
    out = list(tokens)
    while len(out) > 1 and out[0] in MARCADORES_DE_ORIGEM:
        out = out[1:]
    while len(out) > 1 and out[-1] in MARCADORES_DE_ORIGEM:
        out = out[:-1]
    return out


def normalize_name(raw: Optional[str]) -> str:
    """`lower(unaccent(trim(collapse_whitespace(name))))`, plus punctuation and
    origin-marker folding — the Python mirror of the §3 predicate's
    normalization. Returns `""` (never `None`) for a nameless input, so
    callers can test truthiness directly.

    🔴 WIDENED 2026-08-25, FROM THE LIVE QUEUE, NOT FROM THEORY
    ------------------------------------------------------------
    351 groups were sitting in the review queue. Reading them showed that a
    large share were not disagreements about WHO the person is at all:

      `alex sandro` / `alex sandro*`        — a trailing asterisk
      `nei nunes`   / `nei_nunes`           — an underscore for a space
      `ricardo`     / `ricardo.santos`      — a dot for a space
      `hp luiza`    / `luiza`               — the source pasted onto the name
      `morgana`     / `retono morgana`      — same
      `ju cantowitz +` / `juliana cantowitz`

    Every one of those is the same letters with something non-alphabetic
    around them, and every one cost a human two clicks. Punctuation now folds
    to whitespace and origin markers are dropped from the ends, which moved
    106 of the 351 groups into the auto-mergeable classes (C1/C2) — measured
    against the live database, not estimated.

    WHAT THIS DELIBERATELY DOES NOT DO
    ----------------------------------
    No fuzzy matching, no edit distance, no phonetics. `elisabeth`/`elizabeth`
    and `erick`/`erik` are almost certainly the same person, and
    `fernanda`/`lucilene ferreira alves` is almost certainly two people
    sharing a phone — and NOTHING in the letters distinguishes those two cases
    from each other. Guessing there merges strangers' records. Those 245 stay
    with a human, which is what the review queue is for.
    """
    if not raw:
        return ""
    # A social handle's tagline is not part of the name: "Rose Oliveira |
    # Nutricionista Oncológica" and "Silas Brito | Estilo inglês Móveis" are
    # the same people as "Rose Oliveira" and "Silas". Keep what precedes the
    # bar — but ONLY when something precedes it, or "|Maria Veiga" would
    # normalize to nothing and turn a named row into a nameless one.
    if "|" in raw and raw.split("|", 1)[0].strip():
        raw = raw.split("|", 1)[0]
    collapsed = " ".join(raw.split())
    decomposed = unicodedata.normalize("NFKD", collapsed)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    # Punctuation to whitespace, not to nothing: `nei_nunes` must become two
    # tokens, matching `nei nunes`, rather than one glued `neinunes`.
    folded = "".join(c if (c.isalnum() or c.isspace()) else " " for c in stripped)
    tokens = _strip_marcadores(folded.lower().split())
    return " ".join(tokens)


def _tokens(name_norm: str) -> list[str]:
    return name_norm.split()


def _prefix_compatible(a: str, b: str) -> bool:
    """"Maria Silva" / "Maria" -> True (token-prefix, not raw substring —
    "Mari" is never a prefix of "Maria" under this rule, only whole
    tokens count)."""
    ta, tb = _tokens(a), _tokens(b)
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if not shorter:
        return False
    return longer[: len(shorter)] == shorter


def _same_first_token(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta) and bool(tb) and ta[0] == tb[0]


def longest_raw_name(rows: list[SourceRow]) -> Optional[str]:
    """The longest AS-ENTERED name string among `rows` (ties keep the
    first-encountered, for determinism). "Adopt the longest name" is the
    contract's explicit rule for C3 (§4); applied uniformly here to every
    auto-merge case, since it is the only sane general policy once two
    spellings of one person's name are folded together."""
    candidates = [r.nome.strip() for r in rows if r.nome and r.nome.strip()]
    if not candidates:
        return None
    return max(candidates, key=len)


def span(times: list[str]) -> tuple[str, str]:
    """(earliest, latest) among `times` (a list of `ocorreu_em`-shaped ISO
    strings), returned as ISO strings — `primeiro_contato_em`/
    `ultimo_contato_em` (§4). Parses every value to a real `datetime`
    before comparing so a bare-date value ("2026-08-01") never mis-sorts
    against a full-timestamp value from the same day purely from
    string-length differences. Takes plain strings rather than
    `SourceRow`s so `clientes_service` can call it both when building a
    NEW cliente (from its members' `ocorreu_em`) and when recomputing an
    EXISTING cliente's span after a merge/undo (from `cliente_touches`
    rows it already fetched, no `SourceRow` reconstruction needed)."""
    if not times:
        raise ValueError("span() of an empty list")
    parsed = [(_parse_dt(t), t) for t in times]
    earliest = min(parsed, key=lambda p: p[0])
    latest = max(parsed, key=lambda p: p[0])
    return earliest[1], latest[1]


def _parse_dt(value: str) -> datetime:
    if len(value) <= 10:  # bare "YYYY-MM-DD"
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ─── classification (the C1-C6 predicate) ───────────────────────────────


@dataclass(frozen=True)
class GroupClassification:
    motivo: str  # "C1".."C6"
    auto_merge: bool
    named_clusters: dict[str, list["SourceRow"]] = field(default_factory=dict)
    has_nameless: bool = False


def classify_names(names: list[Optional[str]]) -> tuple[str, bool]:
    """Pure C1-C6 decision over a bag of (possibly-None) name strings —
    the core predicate, with no `SourceRow` dependency. Used both by
    `classify_group` (backfill, needs the row lists too) and by
    `clientes_service.list_review_groups` (re-classifying an already-
    resolved review group from its clientes' `nome` values alone, with
    no touches to re-read). Returns `(motivo, auto_merge)`.
    """
    named_norms = sorted({normalize_name(n) for n in names if normalize_name(n)})
    has_nameless = any(not normalize_name(n) for n in names)

    if len(named_norms) <= 1:
        motivo = "C3" if (has_nameless and named_norms) else "C1"
    elif len(named_norms) == 2:
        a, b = named_norms
        if _prefix_compatible(a, b):
            motivo = "C3" if has_nameless else "C2"
        elif _same_first_token(a, b):
            motivo = "C4"
        else:
            motivo = "C5"
    else:
        motivo = "C6"

    return motivo, motivo in AUTO_MERGE_CODES


def classify_group(rows: list[SourceRow]) -> GroupClassification:
    """Classify a (org_id, chave_canonica) group of `SourceRow`s.

    `rows` MUST already share one `chave_canonica` — grouping is the
    caller's job (`clientes_service` groups by `(org_id, chave_canonica)`
    before calling this); this function only decides what to do WITHIN
    one such group.
    """
    if not rows:
        raise ValueError("classify_group() of an empty group")

    named_clusters: dict[str, list[SourceRow]] = {}
    for r in rows:
        norm = normalize_name(r.nome)
        if norm:
            named_clusters.setdefault(norm, []).append(r)

    has_nameless = any(not normalize_name(r.nome) for r in rows)
    motivo, auto_merge = classify_names([r.nome for r in rows])

    return GroupClassification(
        motivo=motivo,
        auto_merge=auto_merge,
        named_clusters=named_clusters,
        has_nameless=has_nameless,
    )


def build_clusters(
    rows: list[SourceRow], classification: GroupClassification
) -> dict[Optional[str], list[SourceRow]]:
    """Row-assignment step, separate from classification.

    Auto-merge (C1/C2/C3): everything — including nameless rows — folds
    into ONE cluster (key `None`), because after folding there is exactly
    one identity and nothing left to distinguish.

    Review (C4/C5/C6): one cluster per distinct normalized name (real
    string keys), PLUS — if any rows are nameless — a `None`-keyed
    cluster holding them. A nameless row cannot be safely assigned to any
    one of 2+ conflicting named candidates (that is precisely what makes
    the group a review case), so it becomes its own review-visible
    cliente rather than a silent guess.
    """
    if classification.auto_merge:
        return {None: list(rows)}

    clusters: dict[Optional[str], list[SourceRow]] = {
        name: list(members) for name, members in classification.named_clusters.items()
    }
    nameless = [r for r in rows if not normalize_name(r.nome)]
    if nameless:
        clusters[None] = nameless
    return clusters
