"""`cartao_cnpj` — a Receita Cartão CNPJ (boxed-label web printout) → typed
fields.

All names, CNPJs and dates in this file are invented. `CNPJ_VALIDO`/
`CNPJ_INVALIDO` mirror `test_cnpj.py`'s own synthetic fixtures.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from noctusai_lib.integrations.documents import (
    CartaoCnpjExtractor,
    ExtractionConfidence,
    FakeCartaoCnpjExtractor,
    TextSource,
    make_cartao_cnpj_extractor,
    parse_cartao_cnpj,
)
from noctusai_lib.integrations.documents.cartao_cnpj import (
    _TITULO_DOCUMENTO,
    LadderCartaoCnpjExtractor,
)

CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_INVALIDO = "11.222.333/0001-82"
_MASCARADO = "********"


def _cartao(
    *,
    cnpj: str = CNPJ_VALIDO,
    matriz_filial: str = "MATRIZ",
    nome_fantasia: str = "********",
    situacao_cadastral: str = "BAIXADA",
    situacao_especial: str = "********",
) -> str:
    """A full, well-formed synthetic Cartão CNPJ transcription — the
    `RÓTULO: valor` shape `DOCUMENT_PROMPT_CARTAO_CNPJ` asks for."""
    return (
        f"NUMERO DE INSCRICAO: {cnpj} {matriz_filial}\n"
        "DATA DE ABERTURA: 15/03/2010\n"
        "NOME EMPRESARIAL: RAZAO SOCIAL EXEMPLO LTDA\n"
        f"TITULO DO ESTABELECIMENTO (NOME DE FANTASIA): {nome_fantasia}\n"
        "PORTE: DEMAIS\n"
        "CODIGO E DESCRICAO DA NATUREZA JURIDICA: 206-2 - SOCIEDADE "
        "EMPRESARIA LIMITADA\n"
        "UF: SP\n"
        f"SITUACAO CADASTRAL: {situacao_cadastral}\n"
        "DATA DA SITUACAO CADASTRAL: 10/06/2021\n"
        "MOTIVO DE SITUACAO CADASTRAL: EXTINCAO POR ENCERRAMENTO "
        "LIQUIDACAO VOLUNTARIA\n"
        f"SITUACAO ESPECIAL: {situacao_especial}\n"
        "Emitido no dia 20/09/2026 as 14:33:10 (data e hora de Brasilia)\n"
    )


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_cartao_cnpj_extractor(), FakeCartaoCnpjExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(
            make_cartao_cnpj_extractor(real=True), LadderCartaoCnpjExtractor
        )

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeCartaoCnpjExtractor(), CartaoCnpjExtractor)
        assert isinstance(LadderCartaoCnpjExtractor(), CartaoCnpjExtractor)


class TestFullParse:
    def test_every_field(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.cnpj == CNPJ_VALIDO
        assert f.cnpj_valido is True
        assert f.matriz_filial == "MATRIZ"
        assert f.data_abertura == date(2010, 3, 15)
        assert f.razao_social == "RAZAO SOCIAL EXEMPLO LTDA"
        assert f.porte == "DEMAIS"
        assert f.natureza_juridica == "206-2 - SOCIEDADE EMPRESARIA LIMITADA"
        assert f.situacao_cadastral == "baixada"
        assert f.data_situacao_cadastral == date(2021, 6, 10)
        assert f.motivo_situacao == "EXTINCAO POR ENCERRAMENTO LIQUIDACAO VOLUNTARIA"
        assert f.emitido_em == datetime(2026, 9, 20, 14, 33, 10)
        assert f.error is None
        # This fixture's default is `baixada` — its `UF: SP` line is
        # POLICY-DISCARDED, not read. See `TestBaixadaAddressDiscard` for
        # the dedicated coverage; `TestAddressBlock` covers a full address
        # parse against an `ativa`-shaped (non-discarding) document.
        assert f.uf is None
        assert f.endereco_mascarado is True

    def test_confiancas_and_rotulos(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        for campo in (
            "cnpj", "data_abertura", "razao_social", "porte",
            "natureza_juridica", "situacao_cadastral",
            "data_situacao_cadastral", "motivo_situacao", "emitido_em",
        ):
            assert f.confiancas[campo] is ExtractionConfidence.ALTA
        # `uf` is policy-discarded on this `baixada` fixture — see above.
        assert f.confiancas["uf"] is ExtractionConfidence.NENHUMA
        assert f.rotulos["cnpj"] == "NUMERO DE INSCRICAO"
        assert f.rotulos["situacao_cadastral"] == "SITUACAO CADASTRAL"
        assert f.rotulos["emitido_em"] == "EMITIDO NO DIA"

    def test_filial(self):
        f = parse_cartao_cnpj(_cartao(matriz_filial="FILIAL"), TextSource.TEXT_LAYER)
        assert f.matriz_filial == "FILIAL"

    def test_matriz_filial_carries_confianca_and_the_cnpj_boxs_own_rotulo(self):
        """🔴 `matriz_filial` has no box of its own on the real document — it
        prints beside the CNPJ. It must still land in `confiancas`/`rotulos`
        like every other field, not be a silent exception to the shape."""
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.confiancas["matriz_filial"] is ExtractionConfidence.ALTA
        assert f.rotulos["matriz_filial"] == f.rotulos["cnpj"] == "NUMERO DE INSCRICAO"

    def test_matriz_filial_absent_when_the_cnpj_box_itself_is_never_found(self):
        texto = _cartao().replace("NUMERO DE INSCRICAO:", "OUTRO ROTULO:")
        f = parse_cartao_cnpj(texto, TextSource.TEXT_LAYER)
        assert f.matriz_filial is None
        assert f.confiancas["matriz_filial"] is ExtractionConfidence.NENHUMA
        assert f.rotulos["matriz_filial"] is None


class TestMaskedFields:
    """`********` → `None`, never the literal asterisks — and the label
    still lands in `rotulos` so a human can see the box was present."""

    def test_a_masked_field_is_none_not_the_literal_asterisks(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.nome_fantasia is None
        assert "*" not in (f.nome_fantasia or "")

    def test_the_masked_label_still_registers(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.rotulos["nome_fantasia"] == "TITULO DO ESTABELECIMENTO (NOME DE FANTASIA)"
        assert f.confiancas["nome_fantasia"] is ExtractionConfidence.NENHUMA

    def test_an_unmasked_field_is_read_normally(self):
        f = parse_cartao_cnpj(
            _cartao(nome_fantasia="FANTASIA EXEMPLO"), TextSource.TEXT_LAYER
        )
        assert f.nome_fantasia == "FANTASIA EXEMPLO"


class TestSituacaoCadastralClosedVocabulary:
    """Migration 167's CHECK constraint: `ativa`/`baixada`/`inapta`/
    `suspensa`/`nula`, else `None` — with the raw text preserved."""

    @pytest.mark.parametrize(
        "impresso,esperado",
        [("ATIVA", "ativa"), ("BAIXADA", "baixada"), ("INAPTA", "inapta"),
         ("SUSPENSA", "suspensa"), ("NULA", "nula")],
    )
    def test_every_vocabulary_word_normalises(self, impresso, esperado):
        f = parse_cartao_cnpj(
            _cartao(situacao_cadastral=impresso), TextSource.TEXT_LAYER
        )
        assert f.situacao_cadastral == esperado

    def test_an_unrecognised_value_is_none_but_the_raw_text_survives(self):
        f = parse_cartao_cnpj(
            _cartao(situacao_cadastral="PENDENTE DE REGULARIZACAO"),
            TextSource.TEXT_LAYER,
        )
        assert f.situacao_cadastral is None
        assert f.rotulos["situacao_cadastral"] == "PENDENTE DE REGULARIZACAO"
        assert f.confiancas["situacao_cadastral"] is ExtractionConfidence.NENHUMA


class TestSituacaoCadastralTitleHazard:
    """🔴 "SITUACAO CADASTRAL" is also a literal substring of the
    document's own printed title ("COMPROVANTE DE INSCRICAO E DE
    SITUACAO CADASTRAL") — `TestPipeTableTranscription` covers the fused
    -pipe-cell shape that surfaced this first; these cover the OTHER
    shapes a real re-read of the same document measured live
    (2026-09-25): the title echoed as its OWN standalone line ahead of
    the real box, and the title fused as a same-line PREFIX onto the
    real box, in an otherwise clean `RÓTULO: valor` transcription (no
    pipe table at all)."""

    def test_title_on_its_own_line_does_not_starve_a_later_real_box(self):
        """The model echoes the title as its own line, ahead of the real
        "SITUACAO CADASTRAL: BAIXADA" box — a first-occurrence-wins scan
        commits to the title's own embedded match and never reaches the
        real box below it (measured live as `rotulos.situacao_cadastral`
        carrying the title text)."""
        texto = (
            f"{_TITULO_DOCUMENTO}\n"
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "NOME EMPRESARIAL: RAZAO SOCIAL EXEMPLO LTDA\n"
            "LOGRADOURO: RUA EXEMPLO\n"
            "NUMERO: 123\n"
            "COMPLEMENTO: SALA 4\n"
            "CEP: 01310-100\n"
            "BAIRRO/DISTRITO: PINHEIROS\n"
            "MUNICIPIO: SAO PAULO\n"
            "UF: SP\n"
            "SITUACAO CADASTRAL: BAIXADA\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.situacao_cadastral == "baixada"
        assert f.rotulos["situacao_cadastral"] == "SITUACAO CADASTRAL"
        assert f.endereco_mascarado is True
        for campo in ("logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf"):
            assert getattr(f, campo) is None, campo

    def test_title_fused_as_a_same_line_prefix_onto_the_real_box(self):
        """The prompt's own `RÓTULO: valor` shape, but the model prefixed
        the document's title onto the SAME line as the real box instead
        of giving it its own line — the "prefix" shape, distinct from
        "own line" above and the fused pipe-cell shape."""
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "LOGRADOURO: ********\n"
            "UF: ********\n"
            f"{_TITULO_DOCUMENTO} SITUACAO CADASTRAL: BAIXADA\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.situacao_cadastral == "baixada"
        assert f.endereco_mascarado is True
        assert f.uf is None

    def test_a_title_only_document_with_no_real_box_is_never_guessed(self):
        """Every occurrence of the label anywhere in the document sits
        inside the title — there is no real box at all.
        `situacao_cadastral` stays `None`, never the title's own text."""
        texto = f"{_TITULO_DOCUMENTO}\nNUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.situacao_cadastral is None
        assert f.rotulos["situacao_cadastral"] is None


class TestAddressBlock:
    """Each of the seven address fields is its OWN box (the vision-prompt
    `RÓTULO: valor` shape) — never scraped out of a neighbour's value. A
    real Cartão CNPJ (2026-09-24) turned out to mask the WHOLE address
    block far more often than not; `uf=None` on that file was correct
    masking, not a parser gap — an earlier "scan the merged row for a
    trailing UF code" heuristic was removed for exactly that reason (see
    the module header)."""

    def _endereco(self, *, mascarado: bool = False) -> str:
        valores = (
            ("LOGRADOURO", "RUA EXEMPLO"),
            ("NUMERO", "123"),
            ("COMPLEMENTO", "SALA 4"),
            ("CEP", "01310-100"),
            ("BAIRRO/DISTRITO", "PINHEIROS"),
            ("MUNICIPIO", "SAO PAULO"),
            ("UF", "SP"),
        )
        linhas = [
            f"{rotulo}: {_MASCARADO if mascarado else valor}"
            for rotulo, valor in valores
        ]
        return (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "NOME EMPRESARIAL: RAZAO SOCIAL EXEMPLO LTDA\n" + "\n".join(linhas) + "\n"
            "SITUACAO CADASTRAL: ATIVA\n"
        )

    def test_an_unmasked_block_parses_every_field(self):
        f = parse_cartao_cnpj(self._endereco(), TextSource.TEXT_LAYER)
        assert f.logradouro == "RUA EXEMPLO"
        assert f.numero == "123"
        assert f.complemento == "SALA 4"
        assert f.cep == "01310-100"
        assert f.bairro == "PINHEIROS"
        assert f.municipio == "SAO PAULO"
        assert f.uf == "SP"
        assert f.endereco_mascarado is False

    def test_numero_is_never_confused_with_numero_de_inscricao(self):
        """🔴 "NUMERO" (the address box) is a literal PREFIX of "NUMERO DE
        INSCRICAO" (the CNPJ box) — the embedding guard must keep them
        apart in both directions."""
        f = parse_cartao_cnpj(self._endereco(), TextSource.TEXT_LAYER)
        assert f.numero == "123"
        assert f.cnpj == CNPJ_VALIDO

    def test_a_fully_masked_block_is_every_field_none_and_the_flag_is_set(self):
        f = parse_cartao_cnpj(self._endereco(mascarado=True), TextSource.TEXT_LAYER)
        for campo in ("logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf"):
            assert getattr(f, campo) is None, campo
        assert f.endereco_mascarado is True

    def test_masking_does_not_leak_into_unrelated_fields(self):
        f = parse_cartao_cnpj(self._endereco(mascarado=True), TextSource.TEXT_LAYER)
        assert f.endereco_mascarado is True
        assert f.cnpj == CNPJ_VALIDO
        assert f.razao_social == "RAZAO SOCIAL EXEMPLO LTDA"

    def test_a_non_uf_token_is_never_guessed(self):
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "MUNICIPIO: SAO PAULO\n"
            "UF: ZZ\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.TEXT_LAYER)
        assert f.uf is None
        assert f.confiancas["uf"] is ExtractionConfidence.NENHUMA


class TestBaixadaAddressDiscard:
    """🔴 The Receita masks the address block of EVERY `baixada` company
    (verified 5/5 real Cartões, 2026-09-24). A vision transcription that
    reports address VALUES on a `baixada` document anyway is the model
    FABRICATING a plausible address, not a legitimate read — measured
    live: 6/7 address fields came back "found" on a real REALIZA Cartão
    whose boxes are ALL `********`. `parse_cartao_cnpj` enforces this as a
    POLICY, independent of what any single transcription claims."""

    def _cartao_com_endereco(self, *, situacao: str) -> str:
        return (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "NOME EMPRESARIAL: RAZAO SOCIAL EXEMPLO LTDA\n"
            "LOGRADOURO: RUA EXEMPLO\n"
            "NUMERO: 123\n"
            "COMPLEMENTO: SALA 4\n"
            "CEP: 01310-100\n"
            "BAIRRO/DISTRITO: PINHEIROS\n"
            "MUNICIPIO: SAO PAULO\n"
            "UF: SP\n"
            f"SITUACAO CADASTRAL: {situacao}\n"
        )

    def test_baixada_with_transcribed_address_values_forces_every_field_none(self):
        f = parse_cartao_cnpj(
            self._cartao_com_endereco(situacao="BAIXADA"), TextSource.OCR
        )
        assert f.situacao_cadastral == "baixada"
        for campo in ("logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf"):
            assert getattr(f, campo) is None, campo
            assert f.confiancas[campo] is ExtractionConfidence.NENHUMA

    def test_baixada_with_transcribed_address_values_sets_endereco_mascarado(self):
        f = parse_cartao_cnpj(
            self._cartao_com_endereco(situacao="BAIXADA"), TextSource.OCR
        )
        assert f.endereco_mascarado is True

    def test_baixada_with_fabricated_values_carries_the_aviso(self):
        f = parse_cartao_cnpj(
            self._cartao_com_endereco(situacao="BAIXADA"), TextSource.OCR
        )
        assert f.aviso is not None
        assert "endereco_descartado_baixada" in f.aviso

    def test_baixada_with_already_masked_address_carries_no_fabrication_aviso(self):
        """The discard fires either way (policy, not a fabrication
        detector) — but there is nothing to FLAG as fabricated when the
        transcription was already honest about the mask."""
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "LOGRADOURO: ********\n"
            "UF: ********\n"
            "SITUACAO CADASTRAL: BAIXADA\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.uf is None
        assert f.endereco_mascarado is True
        assert f.aviso is None

    def test_ativa_with_the_same_address_values_keeps_them_capped_at_baixa(self):
        """The discard is `baixada`-specific — an `ativa` company's
        (unmasked, per the module's own real-corpus evidence) address is
        NOT policy-discarded, only tempered like every other vision-read
        field."""
        f = parse_cartao_cnpj(
            self._cartao_com_endereco(situacao="ATIVA"), TextSource.OCR
        )
        assert f.situacao_cadastral == "ativa"
        assert f.logradouro == "RUA EXEMPLO"
        assert f.municipio == "SAO PAULO"
        assert f.uf == "SP"
        assert f.endereco_mascarado is False
        assert f.aviso is None
        for campo in ("logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf"):
            assert f.confiancas[campo] is ExtractionConfidence.BAIXA, campo

    def test_ativa_with_the_same_address_values_off_a_text_layer_reaches_alta(self):
        """Tempering, not discarding — a TEXT_LAYER source is untouched."""
        f = parse_cartao_cnpj(
            self._cartao_com_endereco(situacao="ATIVA"), TextSource.TEXT_LAYER
        )
        for campo in ("logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf"):
            assert f.confiancas[campo] is ExtractionConfidence.ALTA, campo


class TestColumnAlignedTextLayer:
    """🔴 Some Cartões are Chrome-printed PDFs with a genuine text layer
    (`Producer: Skia/PDF`), read by rung 1 — no vision call, `alta`
    reachable. `pdftotext -layout` renders a short label row (address
    fields especially) as one line, its values column-aligned on the very
    next line, separated by 2+ spaces — a different shape from the vision
    prompt's `RÓTULO: valor` convention, and NOT collapsed by
    `normalize_lines` (which only case/accent-folds — see the module
    header)."""

    def _texto_colunas(self, *, mascarado: bool = False) -> str:
        valores = "01310-100  PINHEIROS  SAO PAULO  SP"
        if mascarado:
            valores = "  ".join([_MASCARADO] * 4)
        return (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "NOME EMPRESARIAL: RAZAO SOCIAL EXEMPLO LTDA\n"
            "CEP  BAIRRO/DISTRITO  MUNICIPIO  UF\n"
            f"{valores}\n"
            "SITUACAO CADASTRAL: ATIVA\n"
        )

    def test_an_unmasked_column_aligned_row_parses_every_column(self):
        f = parse_cartao_cnpj(self._texto_colunas(), TextSource.TEXT_LAYER)
        assert f.cep == "01310-100"
        assert f.bairro == "PINHEIROS"
        assert f.municipio == "SAO PAULO"
        assert f.uf == "SP"
        assert f.endereco_mascarado is False

    def test_confianca_alta_is_reachable_off_a_text_layer_column_read(self):
        f = parse_cartao_cnpj(self._texto_colunas(), TextSource.TEXT_LAYER)
        for campo in ("cep", "bairro", "municipio", "uf"):
            assert f.confiancas[campo] is ExtractionConfidence.ALTA

    def test_a_masked_column_aligned_row_is_every_column_none_flag_set(self):
        f = parse_cartao_cnpj(self._texto_colunas(mascarado=True), TextSource.TEXT_LAYER)
        assert f.cep is None
        assert f.bairro is None
        assert f.municipio is None
        assert f.uf is None
        assert f.endereco_mascarado is True

    def test_a_mismatched_column_count_is_never_positionally_guessed(self):
        """A garbled value row (wrong column count vs. its header) is
        skipped outright rather than zipped against the wrong labels."""
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "CEP  BAIRRO/DISTRITO  MUNICIPIO  UF\n"
            "01310-100  PINHEIROS\n"  # only 2 of 4 columns
        )
        f = parse_cartao_cnpj(texto, TextSource.TEXT_LAYER)
        assert f.cep is None
        assert f.municipio is None
        assert f.uf is None

    def test_a_multi_word_value_does_not_split_on_its_own_internal_space(self):
        """"SAO PAULO" carries a single space — only a run of 2+ spaces is
        a column boundary."""
        f = parse_cartao_cnpj(self._texto_colunas(), TextSource.TEXT_LAYER)
        assert f.municipio == "SAO PAULO"


class TestPipeTableTranscription:
    """🔴 A real vision transcription sometimes emits a markdown PIPE TABLE
    instead of one box per line (measured against a real Cartão CNPJ,
    2026-09-25, a BAIXADA company) — several boxes' `RÓTULO valor` pairs
    fused into pipe-delimited cells of ONE row, a `| --- | --- | --- |`
    separator row, and the document's own TITLE landing in a "column" as
    a table-flattening artifact. See the module header."""

    def _tabela_fundida(
        self,
        *,
        situacao: str = "BAIXADA",
        nome_fantasia_valor: str = "*",
    ) -> str:
        """The FUSED-CELL shape actually measured: `RÓTULO valor` glued
        together inside each pipe cell, no colon. The document title
        ("COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL") is placed as
        the MIDDLE cell of the first row — it contains the literal
        `situacao_cadastral` label as a substring, and must NOT be read as
        that field's box."""
        return (
            f"| NUMERO DE INSCRICAO {CNPJ_VALIDO} MATRIZ "
            "| COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL "
            "| DATA DE ABERTURA 15/03/2010 |\n"
            "| --- | --- | --- |\n"
            "| NOME EMPRESARIAL RAZAO SOCIAL EXEMPLO LTDA |\n"
            f"| TITULO DO ESTABELECIMENTO (NOME DE FANTASIA) {nome_fantasia_valor} "
            "| PORTE ME |\n"
            "| CODIGO E DESCRICAO DA NATUREZA JURIDICA 206-2 - SOCIEDADE "
            "EMPRESARIA LIMITADA |\n"
            "| CEP * | BAIRRO/DISTRITO * | MUNICIPIO * | UF * |\n"
            f"| SITUACAO CADASTRAL {situacao} "
            "| DATA DA SITUACAO CADASTRAL 10/06/2021 |\n"
            "| MOTIVO DE SITUACAO CADASTRAL EXTINCAO POR ENCERRAMENTO "
            "LIQUIDACAO VOLUNTARIA |\n"
            "Emitido no dia 20/09/2026 as 14:33:10 (data e hora de Brasilia)\n"
        )

    def test_situacao_resolves_despite_the_titles_embedded_label_substring(self):
        """🔴 Regression: the document title cell contains "...E DE
        SITUACAO CADASTRAL" as a literal substring of `situacao_cadastral`'s
        own label, sitting BEFORE the real box in the transcription. A
        naive scan finds that false match first, with nothing after it —
        measured live as `rotulos.situacao_cadastral == "|"`."""
        f = parse_cartao_cnpj(self._tabela_fundida(), TextSource.OCR)
        assert f.situacao_cadastral == "baixada"
        assert f.rotulos["situacao_cadastral"] == "SITUACAO CADASTRAL"

    def test_baixada_guard_fires_end_to_end_off_the_pipe_table_shape(self):
        f = parse_cartao_cnpj(self._tabela_fundida(), TextSource.OCR)
        assert f.endereco_mascarado is True
        for campo in ("logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf"):
            assert getattr(f, campo) is None

    def test_no_trailing_pipe_residue_survives_in_any_value(self):
        """🔴 Regression: measured live as `porte == "ME |"`,
        `razao_social == "<NAME> LTDA | | |"`."""
        f = parse_cartao_cnpj(self._tabela_fundida(), TextSource.OCR)
        for campo in ("razao_social", "natureza_juridica", "motivo_situacao", "porte"):
            valor = getattr(f, campo)
            assert valor is not None
            assert "|" not in valor
            assert not valor.endswith(" ")

    def test_a_single_asterisk_value_is_masked_not_a_literal_value(self):
        """🔴 Regression: measured live as `nome_fantasia == "* |"` — the
        model transcribed the mask as ONE `*`, not the prompt's literal
        `********`."""
        f = parse_cartao_cnpj(self._tabela_fundida(), TextSource.OCR)
        assert f.nome_fantasia is None
        assert f.confiancas["nome_fantasia"] is ExtractionConfidence.NENHUMA

    def test_an_unmasked_eight_asterisk_value_is_still_masked(self):
        f = parse_cartao_cnpj(self._tabela_fundida(nome_fantasia_valor=_MASCARADO), TextSource.OCR)
        assert f.nome_fantasia is None

    def test_a_non_baixada_situacao_leaves_the_address_untouched(self):
        f = parse_cartao_cnpj(self._tabela_fundida(situacao="ATIVA"), TextSource.OCR)
        assert f.situacao_cadastral == "ativa"
        # The address boxes are still ALL "*" in this fixture — masked, but
        # NOT discarded-by-baixada (situação is ATIVA here).
        assert f.endereco_mascarado is True

    def test_the_cnpj_and_matriz_filial_box_reads_through_the_fused_cell(self):
        f = parse_cartao_cnpj(self._tabela_fundida(), TextSource.OCR)
        assert f.cnpj == CNPJ_VALIDO
        assert f.cnpj_valido is True
        assert f.matriz_filial == "MATRIZ"
        assert f.data_abertura == date(2010, 3, 15)

    def test_header_row_of_labels_then_a_separate_value_row(self):
        """A SEPARATE header-row-of-pure-labels shape, values on the very
        next row — the pipe-table analogue of `TestColumnAlignedTextLayer`,
        for a model that chooses this layout instead of fusing label+value
        into one cell."""
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "| CEP | BAIRRO/DISTRITO | MUNICIPIO | UF |\n"
            "| --- | --- | --- | --- |\n"
            "| 01310-100 | PINHEIROS | SAO PAULO | SP |\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.cep == "01310-100"
        assert f.bairro == "PINHEIROS"
        assert f.municipio == "SAO PAULO"
        assert f.uf == "SP"

    def test_header_row_value_row_count_mismatch_is_never_guessed(self):
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "| CEP | BAIRRO/DISTRITO | MUNICIPIO | UF |\n"
            "| 01310-100 | PINHEIROS |\n"  # only 2 of 4 columns
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.cep is None
        assert f.municipio is None
        assert f.uf is None

    def test_alternating_label_pipe_value_pipe_row(self):
        """`LABEL | valor |` — one or more fields fused onto a SINGLE row,
        label and value each their OWN cell (distinct from the fused
        `LABEL valor` single-cell shape above)."""
        texto = (
            f"| NUMERO DE INSCRICAO | {CNPJ_VALIDO} MATRIZ |\n"
            "| SITUACAO CADASTRAL | BAIXADA |\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.cnpj == CNPJ_VALIDO
        assert f.situacao_cadastral == "baixada"

    def test_a_two_label_row_is_a_header_row_not_label_value(self):
        """`| LABEL1 | LABEL2 |` (both cells ARE labels) must be treated as
        a pure header row awaiting its OWN value row — never mistaken for
        `LABEL1 | valor=LABEL2`."""
        texto = (
            f"NUMERO DE INSCRICAO: {CNPJ_VALIDO} MATRIZ\n"
            "| CEP | UF |\n"
            "| 01310-100 | SP |\n"
        )
        f = parse_cartao_cnpj(texto, TextSource.OCR)
        assert f.cep == "01310-100"
        assert f.uf == "SP"


class TestCheckDigitDiscipline:
    def test_an_invalid_cnpj_is_flagged_never_corrected(self):
        # `situacao_cadastral="ATIVA"` — isolates the CNPJ check-digit
        # aviso from the `baixada` address-discard aviso (see
        # `TestBaixadaAddressDiscard` for that one's own coverage).
        f = parse_cartao_cnpj(
            _cartao(cnpj=CNPJ_INVALIDO, situacao_cadastral="ATIVA"),
            TextSource.TEXT_LAYER,
        )
        assert f.cnpj == CNPJ_INVALIDO
        assert f.cnpj_valido is False
        assert f.confiancas["cnpj"] is ExtractionConfidence.BAIXA
        assert f.aviso == "cnpj_digito_invalido"

    def test_a_valid_cnpj_never_carries_an_aviso(self):
        f = parse_cartao_cnpj(
            _cartao(situacao_cadastral="ATIVA"), TextSource.TEXT_LAYER
        )
        assert f.aviso is None


class TestOcrNeverAlta:
    def test_a_clean_ocr_read_still_caps_every_field_at_baixa(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.OCR)
        for campo, confianca in f.confiancas.items():
            assert confianca is not ExtractionConfidence.ALTA, campo

    def test_a_text_layer_read_reaches_alta(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.confiancas["cnpj"] is ExtractionConfidence.ALTA


class TestFailuresAreReturnedNotRaised:
    @pytest.mark.asyncio
    async def test_empty_bytes_are_an_error_not_a_crash(self):
        got = await LadderCartaoCnpjExtractor(resolver=None).extract(b"")
        assert got.error == "empty_document"

    @pytest.mark.asyncio
    async def test_a_resolver_exception_becomes_a_recorded_error(self):
        class _Boom:
            async def resolve(self, media):
                raise RuntimeError("vision down")

        got = await LadderCartaoCnpjExtractor(resolver=_Boom()).extract(
            b"\xff\xd8", mimetype="image/jpeg"
        )
        assert got.error == "resolver_failed"

    @pytest.mark.asyncio
    async def test_legible_but_empty_is_not_an_error(self):
        class _Stub:
            async def resolve(self, media):
                class _R:
                    text, error, error_message = "   \n  ", None, None

                return _R()

        got = await LadderCartaoCnpjExtractor(resolver=_Stub()).extract(
            b"\xff\xd8", mimetype="image/jpeg"
        )
        assert got.error is None
        assert got.cnpj is None


class TestLadderReadsThroughTheProvidedProvider:
    """🔴 Never monkeypatch our own code — drive the Ladder through its own
    injectable `resolver` seam instead."""

    @pytest.mark.asyncio
    async def test_a_pdf_with_a_text_layer_never_reaches_vision(self, monkeypatch):
        from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

        texto = _cartao()

        class _Resolver:
            calls = 0

            async def resolve(self, media):
                self.calls += 1
                raise AssertionError("should never reach vision")

        resolver = _Resolver()
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda content: PdfTextLayer(
                pages=(PdfPage(number=1, text=texto, is_substantive=True, reason="stub"),),
                tooling_available=True,
            ),
        )
        got = await LadderCartaoCnpjExtractor(resolver=resolver).extract(
            b"%PDF-1.7", mimetype="application/pdf"
        )
        assert resolver.calls == 0
        assert got.source is TextSource.TEXT_LAYER
        assert got.cnpj == CNPJ_VALIDO


class TestTheFake:
    @pytest.mark.asyncio
    async def test_it_returns_obviously_synthetic_but_valid_values(self):
        got = await FakeCartaoCnpjExtractor().extract(b"x", mimetype="application/pdf")
        assert got.cnpj == CNPJ_VALIDO
        assert got.cnpj_valido is True
        assert got.razao_social == "EMPRESA FAKE SINTETICA LTDA"
        assert got.situacao_cadastral == "ativa"

    @pytest.mark.asyncio
    async def test_it_still_refuses_empty_bytes(self):
        got = await FakeCartaoCnpjExtractor().extract(b"")
        assert got.error == "empty_document"
