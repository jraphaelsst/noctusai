"""Identity-document extraction value objects + Protocol.

The seam turns an identity document (RG / CPF / CNH — bytes plus a
mimetype) into a small set of **typed fields**, not prose. That is the
whole reason this module exists next to `integrations.media` rather than
inside it: `media.ResolvedMedia.text` is a narrative rendering built for
a chatbot to read, and a narrative is not something a database column can
consume without a second, lossy parse at every call site.

WHY CONFIDENCE IS PART OF THE CONTRACT
--------------------------------------
OCR on a photographed ID confuses `0/O`, `1/I`, `5/S` and `8/B`, which
produces dates that are *well-formed and wrong* — `12/05/1980` reading as
`12/05/1930`. A caller that receives a bare `date` has no way to tell that
apart from a date lifted cleanly off a digital PDF's text layer, so it
either writes both (storing guesses as facts) or writes neither (making
the extractor useless).

So `confidence` is mandatory, and the contract is that only `ALTA` is safe
to persist unattended. `BAIXA` is a suggestion for a human to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:  # the carriers below are imported lazily to keep this module leaf-level
    from noctusai_lib.integrations.documents.address import EnderecoLido
    from noctusai_lib.integrations.documents.conjuges import ConjugeLido


class IdentityDocumentKind(str, Enum):
    """Classified identity-document category."""

    RG = "rg"
    CPF = "cpf"
    CNH = "cnh"
    UNKNOWN = "unknown"


class ExtractionConfidence(str, Enum):
    """How much the caller may trust a extracted field.

    ALTA — the value sat next to its own label (`DATA DE NASCIMENTO: …`)
        and passed every plausibility gate. Safe to persist unattended.
    MEDIA — 🔴 a narrow, money-field-only tier (added for
        `documents.money.ler_valor` / `documents.guia_itbi` /
        `documents.financiamento_imobiliario`, per the negociação/
        financiamento extraction contract §D.5). A money value is never
        `alta` off a vision read — a model's self-reported confidence is
        exactly what this whole extractor family refuses to trust for
        currency — but a value corroborated by a DETERMINISTIC check (its
        own printed "valor por extenso" agreeing, or a Quadro Resumo's
        arithmetic summing correctly) is more trustworthy than an
        uncorroborated `baixa` read, without being the "safe to persist
        unattended" claim `alta` makes. Every OTHER extractor in this
        package still uses only `alta`/`baixa`/`nenhuma` — a `media`
        appearing outside a money field is a bug, not a new convention.
    BAIXA — a plausible value was found, but not label-anchored (or the
        text came off a rasterize→vision pass, where digit confusion is
        real). Surface it for a human to confirm; do NOT persist silently.
    NENHUMA — nothing usable. Not an error: a legible document may simply
        not carry the field.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"
    NENHUMA = "nenhuma"


class TextSource(str, Enum):
    """Which rung of the extraction ladder produced the text.

    Recorded because it is the single best predictor of transcription
    error: a PDF text layer is exact, a vision pass over a phone photo is
    not. `confidence` is derived partly from this.
    """

    TEXT_LAYER = "texto"        # PDF's own text layer — exact
    OCR = "ocr"                 # rasterize → vision — approximate
    NENHUMA = "nenhuma"         # no text could be obtained at all


#: Every field the extractor can lift, by attribute name.
#:
#: THE single declaration. `persistable` / `sugestao` derive from it, the
#: product's `CampoExtraido` table mirrors it, and adding a field means adding
#: one entry here plus its three attributes below. Hand-written per-field
#: predicates were what this replaced — see the class docstring's N=3 note.
#:
CAMPOS: tuple[str, ...] = (
    "data_nascimento", "nome", "genero", "cpf", "rg",
    "estado_civil", "regime_bens", "data_casamento", "nacionalidade",
    "profissao",
)


@dataclass(frozen=True)
class IdentityFields:
    """Typed fields lifted from one identity document.

    Every value is Optional: a document that is legible but simply does
    not carry a birthdate is a successful extraction with
    `data_nascimento=None`, not a failure. Failures are carried in
    `error`, so a caller can distinguish "read it, wasn't there" from
    "couldn't read it" — a distinction that decides whether retrying is
    worth anything.

    🔴 CONFIDENCE IS PER FIELD, AND THE NAMES SAY SO
    ------------------------------------------------
    This started with a single `confidence` + `matched_label` pair, which
    was unambiguous only while exactly one field was extracted. With a
    second field the pair becomes a trap: `fields.confidence` reads as if
    it describes the whole result, and every call site that used it for
    the name would silently be asserting the BIRTHDATE's trust level.

    So each extracted value carries its own confidence and its own matched
    label, and the attribute names are prefixed with the field they belong
    to. There is no bare `confidence` — not for tidiness, but so that the
    mistake cannot be spelled.

    **N=3 REACHED, AND FORMALIZED — read this before adding a fourth.**
    `genero` arrived with social-wiring's migration 073 and tripped the
    trigger the N=2 note here left behind. What got formalized is
    deliberately NOT the whole shape:

    - The ATTRIBUTES stay flat (`genero`, `genero_confianca`,
      `genero_rotulo`). The original reason still holds at three and would
      hold at six — the database columns are flat, every consumer is flat,
      and wrapping them in `ExtractedField[T]` would buy indirection at
      every call site in exchange for no safety.
    - The PREDICATES no longer are. `persistable_x` / `sugestao_x` were
      hand-written per field, which is the half that actually multiplies
      and the half that actually goes wrong: adding a field and forgetting
      its `persistable_` property yields a value that is never written and
      never suggested, silently. They now derive from :data:`CAMPOS`,
      declared once, so a new field is a single tuple entry.

    The named properties survive as thin aliases over the generic ones so
    no consumer had to change. Adding a fourth field (RG number and CPF
    number remain the obvious next ones) means: one `CAMPOS` entry, one
    triple of attributes, and nothing else.

    **AND THAT PREDICTION HELD — `cpf` AND `rg` ARRIVED, AT EXACTLY THAT
    COST.** Both landed for the contract-generation work (social-wiring
    migration 093): one `CAMPOS` entry each, one triple of attributes
    each, two aliases each, and no change to `presente` / `persistable` /
    `sugestao`. Recorded because a design note that predicted its own
    next change is worth more once it has been tested than it was as a
    prediction — the derivation is now load-bearing at five fields, and
    the next one costs the same.

    **AND `estado_civil` / `regime_bens` ARRIVED, ON THE SAME TERMS —
    with one twist.** Contract automation F3 (social-wiring migration
    097/103) needed both: two `CAMPOS` entries, two triples, two alias
    pairs, no change to the derivation. The twist is that their finder
    (`civil_status.py`) is the first in the family whose "two labelled
    readings disagree" case is not always a misread — a certidão's
    AVERBAÇÃO (divórcio, óbito, conversão de união estável) amends the
    original registro, so a later reading straddling an AVERBAÇÃO marker
    is a timeline, not noise, and wins instead of collapsing to
    `nenhuma`. That resolution rule lives entirely in the finder; it did
    not need a change here.

    The one thing five fields DID teach: not every extracted value is a
    CAMPO. `rg_orgao` is an attribute here and deliberately absent from
    `CAMPOS`, because it is not independently persistable — see its own
    comment below. A future field should ask that question before adding
    its tuple entry.

    **AND `data_casamento` ARRIVED (contract F6, social-wiring migration
    117), ON THE SAME TERMS `data_nascimento` DID** — one `CAMPOS` entry,
    one triple, two aliases, `sobrescreve=False`: it is "a date is a
    date" in exactly the way `data_nascimento`'s own note argues, with no
    registration-vs-document tension to preserve.

    `data_emissao` arrived alongside it and answers the SAME question
    `rg_orgao` already answered once: not every extracted value is a
    CAMPO. It is the certidão's OWN issuance date (when the cartório
    closed the document — "emitida em" / the closing signature line), not
    a fact about the holder at all, so there is no `clientes` column it
    could promote to — a person does not have one "certidão emission
    date", their certidões each have their own, and the office's
    90-day-freshness rule (a certidão de estado civil must be recent as
    of SIGNING, not as of upload) is answered by asking the DOCUMENT row,
    not the client. `data_emissao` therefore lives here as a plain triple
    and stays deliberately absent from `CAMPOS`, exactly as `rg_orgao`
    does — see that field's own comment.

    **AND `nacionalidade` ARRIVED, RESOLVING THE `NOC-REMEDIATE` THIS
    DOCSTRING USED TO CARRY** — one `CAMPOS` entry, one triple, two
    aliases, `sobrescreve=False`: a REGISTRATION field like `genero` and
    `estado_civil`, not a document-owned one like `nome_oficial`, for the
    same reason those two give — no second column holds an operator's own
    spelling, so a first typed value should not be silently overwritten by
    a later document read. See `nacionalidade.py` for why this is the
    first field in the family whose "two labelled readings disagree"
    check runs over a CANONICALISED value rather than the raw string —
    grammatical gender ("brasileiro"/"brasileira") is not the same kind of
    disagreement `estado_civil`'s AVERBAÇÃO timeline is, and collapsing
    both spouses' readings to the same token BEFORE comparing them is what
    makes a same-nationality couple's certidão resolve at `alta` instead
    of `nenhuma`.
    """

    kind: IdentityDocumentKind = IdentityDocumentKind.UNKNOWN

    # ─── Birthdate ────────────────────────────────────────────────────
    data_nascimento: Optional[date] = None
    data_nascimento_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    #: The label the date was found next to, verbatim. Kept for audit —
    #: it is what lets a human check the extractor's reasoning later
    #: without re-reading the document (which would be another LGPD
    #: content access).
    data_nascimento_rotulo: Optional[str] = None

    # ─── Full name ────────────────────────────────────────────────────
    nome: Optional[str] = None
    nome_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    nome_rotulo: Optional[str] = None

    # ─── Gender ───────────────────────────────────────────────────────
    #: Normalised to the document's own vocabulary — "Masculino" /
    #: "Feminino" — rather than to a code, because the consuming column
    #: (`social_wiring.clientes.genero`) is unconstrained TEXT holding
    #: exactly those words, and a code would need decoding at every reader.
    genero: Optional[str] = None
    genero_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    genero_rotulo: Optional[str] = None

    # ─── CPF ──────────────────────────────────────────────────────────
    #: Always the canonical `412.954.238-98` form, whatever punctuation the
    #: document used — `cpf.find_cpf` normalises, so no consumer has to.
    #: Unlike every other field here, its confidence is driven by a CHECK
    #: DIGIT as much as by a label; see `cpf.py`.
    cpf: Optional[str] = None
    cpf_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    cpf_rotulo: Optional[str] = None

    # ─── RG ───────────────────────────────────────────────────────────
    #: Verbatim as printed (`52.179.965-X`) — there is no national RG format
    #: to normalise to, so imposing one would invent punctuation. Compare via
    #: `rg.only_alnum`.
    rg: Optional[str] = None
    rg_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    rg_rotulo: Optional[str] = None

    #: 🔴 The issuing body, and deliberately NOT a member of :data:`CAMPOS`.
    #:
    #: `CAMPOS` enumerates fields that are independently persistable — each
    #: gets its own `persistable()` decision. The issuer is not one: an
    #: `SSP/SP` with no RG number beside it identifies nothing, and an RG
    #: number stored without its issuer is an incomplete qualification on a
    #: contract. So it TRAVELS WITH `rg` — a consumer writes both or neither,
    #: under the `rg` field's decision. Making it a CAMPO would offer a
    #: `persistable_rg_orgao` that no correct consumer should ever consult.
    rg_orgao: Optional[str] = None
    rg_orgao_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA

    # ─── Estado civil (marital status) ─────────────────────────────────
    #: Normalised to a closed snake_case vocabulary (`civil_status.
    #: ESTADO_CIVIL_VALORES`) rather than to the document's own wording —
    #: unlike `genero`, this field gates whether a spouse must sign an
    #: instrument (CC art. 1.647), so a consumer branches on the VALUE,
    #: not on its spelling. See `civil_status.py` for why.
    estado_civil: Optional[str] = None
    estado_civil_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    estado_civil_rotulo: Optional[str] = None

    # ─── Regime de bens ─────────────────────────────────────────────────
    #: Only meaningful when `estado_civil` is a married state (migration
    #: 097's own comment on the consuming column). Read from the
    #: registro unless a later AVERBAÇÃO changes it — see
    #: `civil_status.find_regime_bens`. Vocabulary: `civil_status.
    #: REGIME_BENS_VALORES`.
    regime_bens: Optional[str] = None
    regime_bens_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    regime_bens_rotulo: Optional[str] = None

    # ─── Data do casamento (contract F6) ───────────────────────────────
    #: The CELEBRATION date — "casaram-se em" / "data do casamento" — off a
    #: certidão de casamento. `sobrescreve=False`: no registration-vs-document
    #: tension to preserve, same reasoning as `data_nascimento`. Why it
    #: matters: the office's Lei 6.515/77 citation in a generated instrument
    #: depends on which side of 26/12/1977 this date falls.
    data_casamento: Optional[date] = None
    data_casamento_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    data_casamento_rotulo: Optional[str] = None

    # ─── Data de emissão da certidão (contract F6) ─────────────────────
    #: 🔴 Deliberately NOT a member of :data:`CAMPOS` — see the class
    #: docstring's note on `data_emissao`. The certidão's OWN issuance date
    #: ("emitida em" / the cartório's closing signature line), read off
    #: `certidao_casamento` AND `certidao_nascimento` alike (both carry
    #: averbações and both close the same way). Answers the office's
    #: 90-day-freshness rule, which is a question about ONE document, not
    #: about the client.
    data_emissao: Optional[date] = None
    data_emissao_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    data_emissao_rotulo: Optional[str] = None

    # ─── Nacionalidade ──────────────────────────────────────────────────
    #: Normalised to the closed gentílico vocabulary
    #: (`nacionalidade.NACIONALIDADE_VALORES`), always the CANONICAL
    #: MASCULINE spelling regardless of which grammatical gender the
    #: document printed — see `nacionalidade.py`'s module docstring for
    #: why that canonicalisation is what makes a same-nationality couple's
    #: certidão resolve instead of colliding with the family's usual
    #: "two labelled readings disagree" rule. `social_wiring.clientes.
    #: nacionalidade` is unconstrained TEXT, like `estado_civil` — the
    #: taxonomy lives in the extractor, not in a database CHECK.
    nacionalidade: Optional[str] = None
    nacionalidade_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    nacionalidade_rotulo: Optional[str] = None

    # ─── Profissão ───────────────────────────────────────────────────────
    #: Label-anchored only (`profession.py`) — there is no closed vocabulary,
    #: so an unlabelled word is never read as a profissão. Lower-cased, with
    #: the document's accents. Printed by a certidão de casamento (per
    #: spouse) and by fichas; never by an RG/CIN/CNH.
    profissao: Optional[str] = None
    profissao_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    profissao_rotulo: Optional[str] = None

    # ─── Endereço (comprovante de endereço) ─────────────────────────────
    #: 🔴 Deliberately NOT a member of :data:`CAMPOS` — it is a GROUP of seven
    #: parts that must be written together or not at all (a CEP from one bill
    #: with a street from another is an address nobody lives at), and it
    #: carries the bill's printed holder, which a consumer must check against
    #: the person before trusting it. `None` when no address was read. See
    #: `address.EnderecoLido`.
    endereco: Optional["EnderecoLido"] = None

    # ─── Both spouses (certidão de casamento) ────────────────────────────
    #: Every spouse `conjuges.find_conjuges` could attribute facts to, in
    #: document order — `()` for any document that does not name exactly two.
    #: When the caller's `titular` hint picked one, that entry has
    #: `titular=True` and its per-person facts ALSO populate this result's own
    #: `nome`/`cpf`/`data_nascimento`/`nacionalidade`/`profissao`/`genero`.
    #: The OTHER entry is what lets a consumer fill the second spouse's
    #: record from the same document instead of dropping it.
    conjuges: tuple["ConjugeLido", ...] = ()

    # ─── Provenance, shared by every field on this result ─────────────
    source: TextSource = TextSource.NENHUMA
    error: Optional[str] = None
    error_message: Optional[str] = None
    #: 🔴 A NOTICE, NOT A FAILURE. `error` means "could not read this
    #: document" and a consumer discards the result. `aviso` means "read it;
    #: some per-person fields were withheld" — today only
    #: `"titulares_multiplos"`: a certidão de casamento names two spouses
    #: with equal prominence and no `titular` hint picked one. The
    #: couple-level facts on the same result (estado_civil, regime_bens,
    #: data_casamento, data_emissao) are valid regardless of whose card it
    #: is, and carrying the ambiguity in `error` made every consumer throw
    #: them away (live, 2026-09-21: a divorced seller's certidão extracted
    #: nothing at all).
    aviso: Optional[str] = None
    aviso_mensagem: Optional[str] = None

    #: 🔴 A CONTENT SIGNAL, NOT A VERDICT. `misfile.classificar_tipo_
    #: provavel`'s best-effort read of what `tipo_documento` this text's
    #: OWN markers suggest — independent of, and never compared against,
    #: whatever the caller declared this document to be (this extractor is
    #: type-agnostic by design — see the class docstring on the family's
    #: other fields). `None` means no marker phrase was recognised, not
    #: "this is not an identity document" — see that module's own
    #: docstring. A consumer that DOES know the declared `tipo_documento`
    #: (the product layer, never this seed module) is the one place a
    #: mismatch becomes an `aviso` — this module never retypes, never
    #: writes `tipo_documento`, and is not itself part of `CAMPOS` (it is
    #: not a persistable per-person fact, it is a diagnostic).
    tipo_provavel: Optional[str] = None

    def _valor(self, campo: str) -> object:
        return getattr(self, campo)

    def _confianca(self, campo: str) -> ExtractionConfidence:
        return getattr(self, f"{campo}_confianca")

    def presente(self, campo: str) -> bool:
        """Did the extractor find anything at all for this field?

        `bool(value)` rather than `is not None`, so an empty-string name
        counts as absent — a name of `""` is a failed read wearing a
        success, and every downstream check would have to repeat that
        thought.
        """
        if campo not in CAMPOS:
            raise KeyError(campo)
        return bool(self._valor(campo))

    def persistable(self, campo: str) -> bool:
        """May this field be written to a record UNATTENDED?

        ALTA only, for every field. The bar is uniform on purpose: what
        varies between fields is how conservatively their confidence is
        SET upstream (see `real.LadderIdentityExtractor`, which tempers a
        vision-read name), not what confidence means once set. Encoding
        per-field leniency here would hide that asymmetry in two places.
        """
        return (
            self.presente(campo)
            and self._confianca(campo) is ExtractionConfidence.ALTA
        )

    def sugestao(self, campo: str) -> bool:
        """Found, but not trusted enough to write without a human."""
        return (
            self.presente(campo)
            and self._confianca(campo) is ExtractionConfidence.BAIXA
        )

    # ─── Named aliases ────────────────────────────────────────────────
    #
    # Kept so existing callers read the same as they always did, and so a
    # typo like `persistable_nomee` is an AttributeError at import rather
    # than a string that quietly misses at runtime — which is the one real
    # cost of the generic form.

    @property
    def persistable_data_nascimento(self) -> bool:
        return self.persistable("data_nascimento")

    @property
    def persistable_nome(self) -> bool:
        return self.persistable("nome")

    @property
    def persistable_genero(self) -> bool:
        return self.persistable("genero")

    @property
    def persistable_cpf(self) -> bool:
        return self.persistable("cpf")

    @property
    def persistable_rg(self) -> bool:
        return self.persistable("rg")

    @property
    def persistable_estado_civil(self) -> bool:
        return self.persistable("estado_civil")

    @property
    def persistable_regime_bens(self) -> bool:
        return self.persistable("regime_bens")

    @property
    def persistable_data_casamento(self) -> bool:
        return self.persistable("data_casamento")

    @property
    def persistable_nacionalidade(self) -> bool:
        return self.persistable("nacionalidade")

    @property
    def persistable_profissao(self) -> bool:
        return self.persistable("profissao")

    @property
    def sugestao_data_nascimento(self) -> bool:
        return self.sugestao("data_nascimento")

    @property
    def sugestao_nome(self) -> bool:
        return self.sugestao("nome")

    @property
    def sugestao_genero(self) -> bool:
        return self.sugestao("genero")

    @property
    def sugestao_cpf(self) -> bool:
        return self.sugestao("cpf")

    @property
    def sugestao_rg(self) -> bool:
        return self.sugestao("rg")

    @property
    def sugestao_estado_civil(self) -> bool:
        return self.sugestao("estado_civil")

    @property
    def sugestao_regime_bens(self) -> bool:
        return self.sugestao("regime_bens")

    @property
    def sugestao_data_casamento(self) -> bool:
        return self.sugestao("data_casamento")

    @property
    def sugestao_nacionalidade(self) -> bool:
        return self.sugestao("nacionalidade")

    @property
    def sugestao_profissao(self) -> bool:
        return self.sugestao("profissao")


@dataclass(frozen=True)
class TitularEsperado:
    """Who the caller already knows this document belongs to.

    A certidão de casamento names two people; the extractor cannot tell
    which one is "the" holder, but the caller can — it uploaded the document
    onto one person's card. Passing that person's registered name and/or
    CPF lets the extractor pick the matching spouse instead of declining.

    It is a SELECTOR, never a source: a hinted value is only ever returned
    when the document itself printed it. A hint that matches nothing on the
    document changes nothing.
    """

    nome: Optional[str] = None
    cpf: Optional[str] = None


@runtime_checkable
class IdentityExtractor(Protocol):
    """Bytes + mimetype → typed identity fields.

    Implementations MUST NOT raise for an unreadable/corrupt document —
    they return `IdentityFields` with `error` set. An extractor that
    raises into a background job turns a bad upload into a lost job.
    """

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
        titular: Optional[TitularEsperado] = None,
    ) -> IdentityFields:
        ...


__all__ = [
    "ExtractionConfidence",
    "IdentityDocumentKind",
    "IdentityExtractor",
    "IdentityFields",
    "TextSource",
    "TitularEsperado",
]
