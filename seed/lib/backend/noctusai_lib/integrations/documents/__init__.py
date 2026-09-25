"""Identity documents → typed fields. Protocol + Fake + Real + factory.

**What ships**

- `IdentityFields` / `IdentityDocumentKind` / `ExtractionConfidence` /
  `TextSource` value objects, and the `IdentityExtractor` Protocol.
- `find_birthdate(text)` / `find_name(text)` / `find_gender(text)` — the pure,
  label-anchored Brazilian parsers. Usable on their own wherever text is
  already in hand.
- `FakeIdentityExtractor` — deterministic; the dev/test default.
- `LadderIdentityExtractor` — identity documents → `IdentityFields`.
  Imported lazily.
- `make_identity_extractor(real=...)` — factory.
- `find_matricula(text)` + `MatriculaFields` / `FakeMatriculaExtractor` /
  `LadderMatriculaExtractor` / `make_matricula_extractor(real=...)` — the
  same shape for a certidão de matrícula. See `matricula_extractor.py` for
  why it tempers a vision read harder than anything else here.
- `DocumentTextLadder` — the shared "bytes → cheapest readable text" rung
  chooser both real extractors compose.
- `DEFAULT_DOCUMENT_PROVIDER` / `OCR_MODELS` / `DOCUMENT_ANALYSIS_MODELS` —
  the ONE place the document-read vendor default and per-rung model pins
  live (`providers.py`, with the measurement behind them).

**Why this is a seed module and not product code.** RG/CPF extraction is
requested as *the canonical procedure*, and the platform already has the
counter-example of what happens otherwise:
`erp-imobiliario/app/services/matricula_service.py` is a product-local
PDF extractor that predates `integrations.media` and now duplicates it
(OCR-only — it pays for a vision call per page even when the PDF has a
text layer). A second product-local copy would make that a pattern rather
than an accident.

**Relationship to `integrations.media`.** `media` answers "bytes → text
a model can read". This answers "document → fields a column can store".
They are different questions: `ResolvedMedia.text` is deliberately
narrative, and every consumer that needed a typed value out of it would
otherwise re-parse that prose itself, differently, at each call site.

🔴 **Consumer contract.** Confidence is PER FIELD. Only a value whose
`persistable_<field>` property is true may be written unattended as a
CONFIRMED fact (`<field>_confianca == ALTA`); anything else needs a human.
A consumer with its own downstream human gate may write lower-confidence
values UNCONFIRMED (social-wiring's D1, migration 153: machine-pending until
its contract validation gate accepts them) — the confidence must then travel
with the value so that gate can show it. Persist `source` and the field's `_rotulo` alongside any
stored value — reading an identity document is a logged, LGPD-relevant
access, and an unattributed value cannot be audited or corrected later.

**The two fields have deliberately different write semantics**, and a
consumer must honour both:

- `data_nascimento` — FIRST WRITER WINS. Only ever written into an empty
  column; a value already present, from any source, is left alone.
- `nome` — THE OFFICIAL DOCUMENT WINS. Written even over an existing
  value, because a name typed into a lead form is a convenience spelling
  and the one on the RG/CPF is the legal one. This is why its confidence
  is tempered by text source (`real._temper_name_confidence`): an
  overwrite must not be driven by a vision-pass guess.
"""
from noctusai_lib.integrations.documents.abnt import (
    UnsupportedGlyphError,
    paragraphs_from_docx,
    paragraphs_from_text,
    render_abnt_pdf,
    render_word_html,
)
from noctusai_lib.integrations.documents.html_pdf import (
    HtmlPdfError,
    cp1252_safe,
    render_html_pdf,
)
from noctusai_lib.integrations.documents.birthdate import find_birthdate, normalize
from noctusai_lib.integrations.documents.civil_status import (
    ESTADO_CIVIL_VALORES,
    REGIME_BENS_VALORES,
    find_data_casamento,
    find_data_emissao,
    find_estado_civil,
    find_regime_bens,
)
from noctusai_lib.integrations.documents.factory import make_identity_extractor
from noctusai_lib.integrations.documents.cpf import find_cpf
from noctusai_lib.integrations.documents.gender import canonical_gender, find_gender
from noctusai_lib.integrations.documents.address import EnderecoLido, UFS, find_endereco
from noctusai_lib.integrations.documents.conjuges import ConjugeLido, find_conjuges
from noctusai_lib.integrations.documents.profession import find_profissao, find_profissoes
from noctusai_lib.integrations.documents.name import chave_nome, nomes_compativeis
from noctusai_lib.integrations.documents.nacionalidade import (
    NACIONALIDADE_VALORES,
    find_nacionalidade,
)
from noctusai_lib.integrations.documents.rg import find_rg, find_rg_orgao, is_same_as_cpf
from noctusai_lib.integrations.documents.misfile import classificar_tipo_provavel
from noctusai_lib.integrations.documents.ladder import (
    DocumentTextLadder,
    looks_like_pdf,
)
from noctusai_lib.integrations.documents.matricula import find_matricula
from noctusai_lib.integrations.documents.matricula_abertura import (
    BlocoAbertura,
    CampoAbertura,
    segmentar_abertura,
)
from noctusai_lib.integrations.documents.matricula_atos import (
    AtoKind,
    MatriculaAto,
    ato_hint_span,
    segment_matricula_atos,
)
from noctusai_lib.integrations.documents.matricula_endereco import (
    EnderecoMatricula,
    derivar_endereco,
)
from noctusai_lib.integrations.documents.matricula_ato_detalhes import (
    NATUREZAS_ATO,
    NATUREZAS_COM_CREDOR,
    NATUREZAS_TRANSFERENCIA,
    AtoDetalhes,
    AtoReferido,
    Instrumento,
    NaturezaAto,
    Parte,
    cpf_cnpj_valido,
    extrair_detalhes_ato,
    formatar_cpf_cnpj,
    frase_titulo_aquisitivo,
    parse_detalhes_json,
)
from noctusai_lib.integrations.documents.matricula_extractor import (
    FakeMatriculaExtractor,
    MatriculaExtractor,
    MatriculaFields,
    make_matricula_extractor,
)
from noctusai_lib.integrations.documents.serasa_crednet import (
    CrednetExtractor,
    CrednetFields,
    FakeCrednetExtractor,
    OcorrenciaCrednet,
    ParticipacaoCrednet,
    make_crednet_extractor,
    parse_crednet,
)
from noctusai_lib.integrations.documents.cartao_cnpj import (
    CartaoCnpjExtractor,
    CartaoCnpjFields,
    FakeCartaoCnpjExtractor,
    make_cartao_cnpj_extractor,
    parse_cartao_cnpj,
)
from noctusai_lib.integrations.documents.money import ValorLido, ler_valor
from noctusai_lib.integrations.documents.guia_itbi import (
    DOCUMENT_PROMPT_GUIA_ITBI,
    FakeGuiaItbiExtractor,
    GuiaItbiExtractor,
    GuiaItbiFields,
    PessoaItbi,
    make_guia_itbi_extractor,
    parse_guia_itbi,
)
from noctusai_lib.integrations.documents.financiamento_imobiliario import (
    DOCUMENT_PROMPT_FINANCIAMENTO,
    ContaCreditoVendedor,
    FakeContratoFinanciamentoExtractor,
    FakePropostaFinanciamentoExtractor,
    FinanciamentoImobiliarioExtractor,
    FinanciamentoImobiliarioFields,
    PessoaFinanciamento,
    make_contrato_financiamento_extractor,
    make_proposta_financiamento_extractor,
    parse_financiamento_imobiliario,
)
from noctusai_lib.integrations.documents.matricula_qualificacao import (
    Qualificacao,
    QualificacaoConsolidada,
    extrair_qualificacoes,
    mesclar_qualificacoes,
)
from noctusai_lib.integrations.documents.matricula_ruido import (
    RuidoKind,
    RuidoSpan,
    detectar_ruido,
    subtrair_ruido,
)
from noctusai_lib.integrations.documents.name import find_name, looks_like_a_name
from noctusai_lib.integrations.documents.fake import (
    FakeIdentityExtractor,
    classify_kind,
)
from noctusai_lib.integrations.documents.providers import (
    DEFAULT_DOCUMENT_PROVIDER,
    DOCUMENT_ANALYSIS_MODELS,
    DOCUMENT_PROVIDERS,
    OCR_MODELS,
)
from noctusai_lib.integrations.documents.transcription import (
    DocumentTranscriber,
    FakeDocumentTranscriber,
    RenderDpiPolicy,
    TranscribedPage,
    Transcription,
    has_raw_markup,
    identity_document_render_dpi_policy,
    make_document_transcriber,
)
from noctusai_lib.integrations.documents.text import (
    normalize_lines,
    strip_accents_upper,
)
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityDocumentKind,
    IdentityExtractor,
    IdentityFields,
    TextSource,
    TitularEsperado,
)
from noctusai_lib.integrations.documents.formatting import (
    FormatRange,
    FormattedDocument,
    Paragraph,
    ParagraphKind,
    Run,
    ranges_from_json,
    ranges_to_json,
)


#: Attribute name → the module it lives in, for the lazy proxy below. Both
#: real extractors are listed: neither may be imported eagerly, since each
#: pulls `integrations.media` (PyMuPDF / the LLM stack) on its ladder's first
#: use, and a slim image must still be able to import this package.
_LAZY: dict[str, str] = {
    "LadderIdentityExtractor": "noctusai_lib.integrations.documents.real",
    "LadderMatriculaExtractor": (
        "noctusai_lib.integrations.documents.matricula_extractor"
    ),
    "LadderDocumentTranscriber": (
        "noctusai_lib.integrations.documents.transcription"
    ),
    "LadderCrednetExtractor": (
        "noctusai_lib.integrations.documents.serasa_crednet"
    ),
    "LadderCartaoCnpjExtractor": (
        "noctusai_lib.integrations.documents.cartao_cnpj"
    ),
    "LadderGuiaItbiExtractor": (
        "noctusai_lib.integrations.documents.guia_itbi"
    ),
    "LadderContratoFinanciamentoExtractor": (
        "noctusai_lib.integrations.documents.financiamento_imobiliario"
    ),
    "LadderPropostaFinanciamentoExtractor": (
        "noctusai_lib.integrations.documents.financiamento_imobiliario"
    ),
}


def __getattr__(name: str):  # pragma: no cover - lazy proxy
    """Lazy-load the real extractors on first access, so importing this
    package never requires PyMuPDF / the LLM stack."""
    modulo = _LAZY.get(name)
    if modulo is not None:
        import importlib

        return getattr(importlib.import_module(modulo), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "HtmlPdfError",
    "cp1252_safe",
    "render_html_pdf",
    "DEFAULT_DOCUMENT_PROVIDER",
    "DOCUMENT_ANALYSIS_MODELS",
    "DOCUMENT_PROVIDERS",
    "OCR_MODELS",
    "AtoKind",
    "BlocoAbertura",
    "CartaoCnpjExtractor",
    "CartaoCnpjFields",
    "ConjugeLido",
    "EnderecoLido",
    "UFS",
    "canonical_gender",
    "chave_nome",
    "nomes_compativeis",
    "find_conjuges",
    "find_endereco",
    "find_profissao",
    "find_profissoes",
    "CampoAbertura",
    "ContaCreditoVendedor",
    "CrednetExtractor",
    "CrednetFields",
    "DOCUMENT_PROMPT_FINANCIAMENTO",
    "DOCUMENT_PROMPT_GUIA_ITBI",
    "DocumentTextLadder",
    "DocumentTranscriber",
    "ESTADO_CIVIL_VALORES",
    "EnderecoMatricula",
    "ExtractionConfidence",
    "FakeCartaoCnpjExtractor",
    "FakeContratoFinanciamentoExtractor",
    "FakeCrednetExtractor",
    "FakeDocumentTranscriber",
    "FakeGuiaItbiExtractor",
    "FakeIdentityExtractor",
    "FakeMatriculaExtractor",
    "FakePropostaFinanciamentoExtractor",
    "FinanciamentoImobiliarioExtractor",
    "FinanciamentoImobiliarioFields",
    "FormatRange",
    "FormattedDocument",
    "GuiaItbiExtractor",
    "GuiaItbiFields",
    "IdentityDocumentKind",
    "IdentityExtractor",
    "IdentityFields",
    "LadderCartaoCnpjExtractor",
    "LadderContratoFinanciamentoExtractor",
    "LadderCrednetExtractor",
    "LadderDocumentTranscriber",
    "LadderGuiaItbiExtractor",
    "LadderIdentityExtractor",
    "LadderMatriculaExtractor",
    "LadderPropostaFinanciamentoExtractor",
    "MatriculaAto",
    "MatriculaExtractor",
    "MatriculaFields",
    "NACIONALIDADE_VALORES",
    "OcorrenciaCrednet",
    "Paragraph",
    "ParagraphKind",
    "ParticipacaoCrednet",
    "PessoaFinanciamento",
    "PessoaItbi",
    "Qualificacao",
    "QualificacaoConsolidada",
    "REGIME_BENS_VALORES",
    "RenderDpiPolicy",
    "RuidoKind",
    "RuidoSpan",
    "Run",
    "TextSource",
    "TitularEsperado",
    "TranscribedPage",
    "Transcription",
    "UnsupportedGlyphError",
    "ValorLido",
    "ato_hint_span",
    "classify_kind",
    "derivar_endereco",
    "detectar_ruido",
    "extrair_qualificacoes",
    "find_birthdate",
    "has_raw_markup",
    "find_cpf",
    "find_data_casamento",
    "find_data_emissao",
    "find_estado_civil",
    "find_gender",
    "find_matricula",
    "find_nacionalidade",
    "find_name",
    "find_regime_bens",
    "find_rg",
    "find_rg_orgao",
    "identity_document_render_dpi_policy",
    "is_same_as_cpf",
    "classificar_tipo_provavel",
    "ler_valor",
    "looks_like_a_name",
    "looks_like_pdf",
    "make_cartao_cnpj_extractor",
    "make_contrato_financiamento_extractor",
    "make_crednet_extractor",
    "make_document_transcriber",
    "make_guia_itbi_extractor",
    "make_identity_extractor",
    "make_matricula_extractor",
    "make_proposta_financiamento_extractor",
    "mesclar_qualificacoes",
    "normalize",
    "normalize_lines",
    "paragraphs_from_docx",
    "paragraphs_from_text",
    "parse_cartao_cnpj",
    "parse_crednet",
    "parse_financiamento_imobiliario",
    "parse_guia_itbi",
    "ranges_from_json",
    "ranges_to_json",
    "render_abnt_pdf",
    "render_word_html",
    "segment_matricula_atos",
    "segmentar_abertura",
    "strip_accents_upper",
    "subtrair_ruido",
]
