"""The canonical `Imovel` domain model.

**What this is.** The typed, coerced, app-facing shape of a real-estate
listing. `PropertyData` (this package's other value object) is an 8-field
YouTube-metadata carrier and deliberately stays that; `Imovel` is the full
property.

**Why the wire never reaches the app layer.** Vista returns every scalar as
a string, uses three different spellings of "absent", and overloads ``"0"``
to mean two incompatible things depending on the field. Those are wire
concerns, and they are absorbed here — at the boundary — so no consumer ever
branches on ``payload.get("ValorLocacao") == "0"``.

Every coercion rule below is measured, not assumed. A 2026-08-03 census of
all 1919 imóveis on tenant ``oneconsu-rest`` (roadmap
``social-wiring-imoveis-vista-2026-08``) produced the counts cited in each
docstring. Where the census contradicted an earlier single-sample belief,
the docstring says so — those are the rules most likely to be "corrected"
back into bugs by someone reading only the Vista docs.

Layering::

    Vista wire payload   all strings, preserved verbatim in `vista_raw`
    Imovel               this module — typed, coerced, app-facing
    <product>.imoveis    persistence (product-owned)
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date, datetime
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─── Wire coercion — one helper per measured quirk ────────────────────────


def _clean(value: Any) -> Optional[str]:
    """Collapse Vista's three spellings of "absent" to ``None``.

    Vista uses ``""`` for almost everything — but NOT always. The census
    found ``CodigoImobiliaria`` is JSON ``null`` on 38/1919 rows, which
    disproves the earlier "empty is always ``''``, never null" reading. A
    rule that only handles ``""`` raises ``AttributeError`` on those 38.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _money(value: Any) -> Optional[float]:
    """Money, where ``"0"`` means *not applicable* rather than *free*.

    ``ValorLocacao`` is ``"0"`` on 1488/1919 rows (every one of them a
    ``Venda`` listing — the imóvel is not for rent) and ``""`` on a further
    199. ``ValorVenda`` is ``"0"`` on 64, of which 63 are the ``Aluguel``
    listings — the same fact with the fields inverted.

    Both states mean "no price of this kind", so both collapse to ``None``.
    Returning ``0.0`` is what renders "R$ 0" on ~78% of the catalog.
    """
    text = _clean(value)
    if text is None:
        return None
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        logger.debug("imovel: non-numeric money value %r → None", value)
        return None
    return None if amount == 0 else amount


def _area(value: Any) -> Optional[float]:
    """Area, where ``"0"`` means *unknown* rather than *zero square metres*.

    A property with no floor area does not exist; ``"0"`` is Vista's
    not-filled-in. ``AreaConstruida`` is ``"0"`` on 1918/1919 rows — the
    field is effectively unpopulated on this tenant, so consumers should
    treat a present value as the exception.
    """
    text = _clean(value)
    if text is None:
        return None
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        logger.debug("imovel: non-numeric area value %r → None", value)
        return None
    return None if amount == 0 else amount


def _count(value: Any) -> Optional[int]:
    """Room/space counts, where ``0`` is a REAL value and must survive.

    This is the rule most likely to be "fixed" into a bug. The ``"0" → None``
    treatment applied to money and area is **wrong** here: a Terreno
    genuinely has 0 dormitórios, 0 suítes and 0 vagas, and the census counts
    (`Vagas` 512, `Suites` 477, `Dormitorios` 405 rows at ``"0"``) are
    dominated by land and commercial listings where zero is the truth.

    Only a missing/blank value is unknown.
    """
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        logger.debug("imovel: non-numeric count value %r → None", value)
        return None


def _sim_nao(value: Any) -> Optional[bool]:
    """Vista's yes/no flag → a real bool.

    ``BanheiroSocial`` carries ``"Sim"``/``"Nao"``. It was previously fed to
    an int coercion via ``_to_int(Banheiros or BanheiroSocial)``, which threw
    internally and returned ``None`` — so ``banheiros`` was ``None`` on
    1919/1919 rows, silently, forever. The two fields are different types
    (a count vs a flag) and the canonical model keeps them apart.

    Note ``Banheiros`` itself is permission-denied on ``oneconsu-rest``:
    calibration drops it from both field sets, so ``banheiro_social`` is the
    only bathroom signal this tenant exposes at all.
    """
    text = _clean(value)
    if text is None:
        return None
    folded = _fold_accents(text).lower()
    if folded in {"sim", "s", "true", "1"}:
        return True
    if folded in {"nao", "n", "false", "0"}:
        return False
    return None


def _to_date(value: Any) -> Optional[date]:
    text = _clean(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[: len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    logger.debug("imovel: unparseable date %r → None", value)
    return None


def _fold_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


# ─── Place names — the `cidade`/`empreendimento` casing collision ─────────
#
# Measured live 2026-08-03/13 on `oneconsu-rest`: `Cidade` carries both
# `"Embu das Artes"` (57 rows) and `"Embu Das Artes"` (19 rows) — a quarter
# of that city's inventory hidden from a filter keyed on the other spelling.
# `Empreendimento` carries the same defect shape twice: `"Granja Viana II -
# Gleba 1 e 2 - Km 26"` / `"...Ii..."` (18 rows) and `"Paisagem Renoir II e
# III - Km 26"` / `"...Ii e Iii..."` (8 rows). Same root cause as
# `CARACTERISTICA_COLLISIONS` above (Q4 of the
# `social-wiring-imoveis-vista-2026-08` roadmap): a tenant-side data-entry
# inconsistency, not a modelling choice — merge, don't pick a winner.
#
# **The trap that makes this non-trivial.** The two classes pull in OPPOSITE
# directions: `"Embu Das Artes"` needs its connective LOWERED to match
# `"Embu das Artes"`; `"Granja Viana Ii"` needs its numeral UPPERCASED to
# match `"Granja Viana II"`. A blind `str.title()` fixes the first and
# CAUSES the second — the `Ii`/`Iii` spellings already look exactly like a
# naive title-case was applied upstream, so shipping one here would deepen
# the bug rather than close it. This function classifies each word instead
# of blanket-casing the string: a pt-BR connective (not in first position)
# lowercases, a Roman numeral I-X uppercases, everything else title-cases —
# and title-casing an already-correct word (accented or not) is a no-op, so
# running this over the whole catalog is safe, not just over the 3 rows
# known to be broken.

# Connectives that stay lowercase mid-name — but NOT in first position,
# where a leading connective is still the start of how the name is written
# ("Do Carmo" is a place; nobody writes "do Carmo" at the start of a
# sentence-less proper noun). Scoped to the connectives actually observed
# on this tenant's `Cidade`/`Empreendimento` values (Q4); extend by
# measurement, not by guessing at Portuguese grammar in general.
_PLACE_NAME_CONNECTIVES = frozenset({"de", "da", "do", "das", "dos", "e"})

# Roman numerals I-X, canonical uppercase form. An explicit whitelist
# (rather than a general Roman-numeral regex) is deliberate: it matches
# exactly what's measured live (`II`, `III`) and can never misfire on a
# longer letter sequence that happens to be Roman-numeral-shaped (e.g. a
# regex would treat `"MIL"` as ambiguous input worth scrutinizing; this
# whitelist simply never looks at it).
_ROMAN_NUMERALS_I_TO_X = frozenset(
    {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
)


def _normalize_place_name(value: Any) -> Optional[str]:
    """Canonicalize a Vista place name — collapses the casing-only
    duplicates measured on `Cidade` and `Empreendimento` into one spelling.

    Per-word classification, in order: (1) a connective past the first word
    lowercases: (2) a Roman numeral I-X uppercases; (3) everything else
    title-cases (accent-safe — `"ARTES"` → `"Artes"`, `"SÃO"` → `"São"`,
    already-correct words are a no-op). Non-letter tokens (`"-"`, digits
    like `"26"`) pass through `str.capitalize()` unchanged.

    Idempotent by construction: every branch's output is already the fixed
    point of that same branch, so normalizing an already-normalized value
    changes nothing — required because this runs both at sync time (fresh
    Vista reads) and, via the once-off migration, over rows already in the
    mirror.
    """
    text = _clean(value)
    if text is None:
        return None

    words: list[str] = []
    for index, word in enumerate(text.split()):
        folded = _fold_accents(word).lower()
        if index > 0 and folded in _PLACE_NAME_CONNECTIVES:
            words.append(folded)
        elif word.upper() in _ROMAN_NUMERALS_I_TO_X:
            words.append(word.upper())
        else:
            words.append(word.capitalize())
    return " ".join(words)


# ─── Caracteristicas — the 76-key amenity schema ──────────────────────────

# The one real slug collision on this tenant, measured over the full 76-key
# space: both spellings are the same amenity with a tenant-side typo, and
# both are `"Sim"` on overlapping-but-different imóveis. Merging with OR is
# the ratified answer (roadmap Q4) — dropping either loses real amenities.
CARACTERISTICA_COLLISIONS: dict[str, tuple[str, ...]] = {
    "dependenciadeempregada": ("Dependenciade Empregada", "Dependencia De Empregada"),
}


def caracteristica_slug(key: str) -> str:
    """Normalize a Vista amenity key to a stable slug.

    Vista de-camelizes its own keys and inserts spaces mid-acronym, so the
    wire carries ``"Sala T V"``, ``"T V Cabo"`` and ``"W C Empregada"``.
    Collapsing all whitespace is what makes those stable, and it is also
    what creates the single known collision above — which is handled, not
    silently absorbed.
    """
    return "".join(_fold_accents(key).lower().split())


def parse_caracteristicas(raw: Any) -> frozenset[str]:
    """Return the slug set of amenities the imóvel actually HAS.

    The census measured this dict as a fixed tenant-wide schema: **exactly
    76 keys on all 75 sampled imóveis**, spanning all 20 categorias, with a
    value vocabulary of exactly ``{"Sim", "Nao"}`` — no third value, no
    blanks. So per-row variance is zero; only per-tenant drift is real,
    which is why this is a slug set rather than 76 boolean columns (a
    column set would need a migration per amenity the tenant adds).

    Only the ``"Sim"`` keys are returned — 48 of the 76 are `Sim` on at
    least one sampled imóvel; the other 28 are dead weight on this tenant.
    """
    if not isinstance(raw, dict):
        return frozenset()
    present: set[str] = set()
    for key, value in raw.items():
        if _sim_nao(value) is True:
            present.add(caracteristica_slug(key))
    return frozenset(present)


# ─── Finalidade ───────────────────────────────────────────────────────────


def derive_finalidades(
    *, finalidade_status: Any = None, status: Any = None, finalidade: Any = None
) -> frozenset[str]:
    """Resolve what the imóvel is FOR: ``{"venda"}``, ``{"aluguel"}``, or both.

    Three sources, in descending reliability:

    1. ``FinalidadeStatus`` — a clean 2-key enum (``VENDA`` / ``ALUGUEL``),
       populated on 75/75 sampled. **But it is detalhes-only**, so a
       listar-only row cannot use it.
    2. ``Status`` — 100% populated on all 1919 rows, 3 values
       (``Venda`` 89.4%, ``Venda e Aluguel`` 7.2%, ``Aluguel`` 3.4%). This
       is the list-view answer.
    3. ``Finalidade`` — the field whose name suggests it should be first,
       and is the least useful: non-empty on only 287/1919 (15.0%), and it
       carries the *audience* (``Residencial``/``Comercial``), not the
       transaction. Kept only as a last resort.

    A single-sample reading once concluded ``Finalidade`` was always empty
    and ``FinalidadeStatus`` was the sole signal. Both halves were wrong at
    catalog scale, which is why this reads all three.
    """
    out: set[str] = set()

    if isinstance(finalidade_status, dict):
        for key, value in finalidade_status.items():
            if value in (True, "true", "Sim", 1, "1"):
                folded = _fold_accents(str(key)).lower()
                if "venda" in folded:
                    out.add("venda")
                if "aluguel" in folded or "locacao" in folded:
                    out.add("aluguel")
    if out:
        return frozenset(out)

    text = _clean(status)
    if text:
        folded = _fold_accents(text).lower()
        if "venda" in folded:
            out.add("venda")
        if "aluguel" in folded or "locacao" in folded:
            out.add("aluguel")
    if out:
        return frozenset(out)

    text = _clean(finalidade)
    if text:
        folded = _fold_accents(text).lower()
        if "venda" in folded:
            out.add("venda")
        if "aluguel" in folded or "locacao" in folded:
            out.add("aluguel")
    return frozenset(out)


# ─── Value objects ────────────────────────────────────────────────────────


class Corretor(BaseModel):
    """One broker assigned to an imóvel."""

    codigo: Optional[str] = None
    nome: Optional[str] = None
    email: Optional[str] = None
    fone: Optional[str] = None


def parse_corretores(raw: Any) -> list[Corretor]:
    """Return EVERY assigned broker, not just the first.

    ``Corretor`` is polymorphic on the wire: a dict keyed by broker code on
    1903/1919 rows, and an empty list on the other 16 (Vista's way of saying
    "nobody assigned"). A reader that assumes one shape breaks on the other.

    Multi-broker is not an edge case — the census found **252 imóveis
    (13.1%) with 2–3 corretores**. The previous helper returned only the
    first name, so it was silently discarding a co-broker on one imóvel in
    eight. That is why this returns a list and the model stores a list.
    """
    if isinstance(raw, dict):
        entries: Iterable[Any] = raw.values()
    elif isinstance(raw, list):
        entries = raw
    else:
        return []

    out: list[Corretor] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        corretor = Corretor(
            codigo=_clean(entry.get("Codigo")),
            nome=_clean(entry.get("Nome")),
            email=_clean(entry.get("Email")),
            fone=_clean(entry.get("Fone")),
        )
        if any((corretor.codigo, corretor.nome, corretor.email)):
            out.append(corretor)
    return out


# ─── The model ────────────────────────────────────────────────────────────


class Imovel(BaseModel):
    """A real-estate listing, coerced off the Vista wire.

    Field groups mirror the ratified design in the
    ``social-wiring-imoveis-vista-2026-08`` roadmap.

    There is deliberately **no** ``origem`` field. An earlier draft carried
    ``origem`` (``vista``/``manual``) as a provenance discriminator; that was
    a category error twice over. Vista is the source of truth for imóveis, so
    there is nothing to discriminate — and ``origem`` already means something
    else in this domain: the marketing portal a *lead* arrived from
    (``lead_sources`` / ``leads.origem_id``). Two different ``origem``s in one
    product would be worse than a redundant column.
    """

    # Identidade
    codigo: str = Field(..., description="Vista primary id, e.g. 'ONE10640' or 'CA0190'.")
    codigo_imobiliaria: Optional[str] = Field(
        None, description="Agency code. JSON null on 38/1919 rows — genuinely optional."
    )

    # Classificação
    titulo: Optional[str] = None
    categoria: Optional[str] = Field(None, description="20 distinct values on this tenant.")
    status: Optional[str] = Field(None, description="Venda | Aluguel | Venda e Aluguel.")
    finalidades: frozenset[str] = Field(
        default_factory=frozenset,
        description="Derived transaction set: {'venda'}, {'aluguel'} or both.",
    )

    # Localização
    cep: Optional[str] = None
    logradouro: Optional[str] = Field(None, description="Unprefixed — 'Fernando Nobre', no 'Rua'.")
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    empreendimento: Optional[str] = Field(
        None, description="May duplicate `bairro` — don't render both blindly."
    )
    latitude: Optional[float] = Field(None, description="Absent on 36.8% — UI needs a no-geo branch.")
    longitude: Optional[float] = None

    # Comercial
    valor_venda: Optional[float] = None
    valor_locacao: Optional[float] = None

    # Dimensões
    area_total: Optional[float] = None
    area_privativa: Optional[float] = None
    area_construida: Optional[float] = Field(
        None, description="'0' on 99.9% of this tenant's catalog — effectively unpopulated."
    )

    # Cômodos
    dormitorios: Optional[int] = None
    suites: Optional[int] = None
    vagas: Optional[int] = None
    banheiro_social: Optional[bool] = Field(
        None, description="A flag, not a count. The only bathroom signal this tenant exposes."
    )

    # Mídia
    foto_destaque: Optional[str] = None
    fotos: list[str] = Field(default_factory=list)

    # Atribuição
    corretores: list[Corretor] = Field(default_factory=list)
    construtora: Optional[str] = Field(None, description="Populated on only ~9% — too sparse to feature.")

    # Datas
    data_cadastro: Optional[date] = None
    data_atualizacao: Optional[date] = None
    data_atualizacao_dias: Optional[int] = Field(
        None, description="Detalhes-only; the sole int on the wire. Derived — display, don't key on it."
    )

    # Características
    caracteristicas: frozenset[str] = Field(
        default_factory=frozenset, description="Slugs of amenities present ('Sim' only)."
    )
    caracteristicas_raw: dict = Field(
        default_factory=dict, description="The full 76-key dict, preserved for re-slugging."
    )

    # Auditoria
    vista_raw: dict = Field(
        default_factory=dict, description="Merged listar+detalhes payload, verbatim."
    )

    model_config = {"frozen": False}

    # ── derived conveniences (no storage) ──

    @property
    def endereco_completo(self) -> Optional[str]:
        """Compose the split address parts for display.

        Vista stores `Endereco` unprefixed and splits `Numero` /
        `Complemento` out, so display has to reassemble them.
        """
        parts = [p for p in (self.logradouro, self.numero, self.complemento) if p]
        return ", ".join(parts) if parts else None

    @property
    def tem_geo(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def para_venda(self) -> bool:
        return "venda" in self.finalidades

    @property
    def para_aluguel(self) -> bool:
        return "aluguel" in self.finalidades

    def tem_caracteristica(self, key: str) -> bool:
        """Membership test that accepts a raw Vista key or an already-slugged one."""
        return caracteristica_slug(key) in self.caracteristicas


class ImovelPage(BaseModel):
    """One page of a catalog read.

    Cross-CRM by design — Vista's pagination envelope (``total`` /
    ``paginas`` / ``pagina`` / ``quantidade``) is translated into this at the
    adapter boundary, so consumers paginate without knowing whose CRM it is.
    """

    items: list[Imovel] = Field(default_factory=list)
    total: int = Field(0, description="Total imóveis matching the query, across all pages.")
    page: int = 1
    pages: int = Field(1, description="Total page count at the requested page_size.")

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


# ─── Public names for the coercion helpers ────────────────────────────────
#
# The rules above are the contract, not an implementation detail: an adapter
# for a second CRM has to make the same "0"-vs-null decisions to produce a
# comparable `Imovel`, and `imovel_normalizer` needs them by name. Exporting
# them beats having consumers reach for the underscore-prefixed originals.

clean_text = _clean
parse_money = _money
parse_area = _area
parse_count = _count
parse_sim_nao = _sim_nao
parse_date = _to_date
fold_accents = _fold_accents
normalize_place_name = _normalize_place_name


__all__ = [
    "CARACTERISTICA_COLLISIONS",
    "Corretor",
    "Imovel",
    "ImovelPage",
    "caracteristica_slug",
    "clean_text",
    "derive_finalidades",
    "fold_accents",
    "normalize_place_name",
    "parse_area",
    "parse_caracteristicas",
    "parse_corretores",
    "parse_count",
    "parse_date",
    "parse_money",
    "parse_sim_nao",
]
