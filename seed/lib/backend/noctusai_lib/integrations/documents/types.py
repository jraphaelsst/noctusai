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
from typing import Optional, Protocol, runtime_checkable


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
    BAIXA — a plausible value was found, but not label-anchored (or the
        text came off a rasterize→vision pass, where digit confusion is
        real). Surface it for a human to confirm; do NOT persist silently.
    NENHUMA — nothing usable. Not an error: a legible document may simply
        not carry the field.
    """

    ALTA = "alta"
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
CAMPOS: tuple[str, ...] = ("data_nascimento", "nome", "genero", "cpf", "rg")


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

    The one thing five fields DID teach: not every extracted value is a
    CAMPO. `rg_orgao` is an attribute here and deliberately absent from
    `CAMPOS`, because it is not independently persistable — see its own
    comment below. A future field should ask that question before adding
    its tuple entry.
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

    # ─── Provenance, shared by every field on this result ─────────────
    source: TextSource = TextSource.NENHUMA
    error: Optional[str] = None
    error_message: Optional[str] = None

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
    ) -> IdentityFields:
        ...


__all__ = [
    "ExtractionConfidence",
    "IdentityDocumentKind",
    "IdentityExtractor",
    "IdentityFields",
    "TextSource",
]
