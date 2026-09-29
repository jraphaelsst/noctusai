"""Pure tests for `documents.releitura` — `deve_escalar` (the trigger table)
and `mesclar` (the merge policy). See that module's own docstring for the
measured run-to-run-variance this closes.
"""
from __future__ import annotations

from dataclasses import replace

from noctusai_lib.integrations.documents.releitura import (
    AVISO_RELEITURA,
    deve_escalar,
    mesclar,
)
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

_CPF_A = "412.954.238-98"
_CPF_B = "111.444.777-35"


class TestDeveEscalar:
    """The declarative trigger table + the two independent signals
    (`leitura_comprometida`, `source is not OCR`)."""

    def test_no_trigger_on_a_complete_clean_read(self):
        fields = IdentityFields(
            nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.BAIXA,
            cpf=_CPF_A, cpf_confianca=ExtractionConfidence.ALTA,
            source=TextSource.OCR,
        )
        assert deve_escalar(fields, "cin") is False

    def test_trigger_on_missing_core_field_cpf_card(self):
        fields = IdentityFields(nome="JOAO CARLOS PEREIRA", source=TextSource.OCR)
        assert deve_escalar(fields, "cin") is True

    def test_rg_and_cnh_additionally_require_rg(self):
        completo_sem_rg = IdentityFields(
            nome="JOAO CARLOS PEREIRA", cpf=_CPF_A, source=TextSource.OCR,
        )
        assert deve_escalar(completo_sem_rg, "rg") is True
        assert deve_escalar(completo_sem_rg, "cnh") is True
        # CIN/CPF cards carry no RG number of their own — the SAME reading
        # is already complete for those two types.
        assert deve_escalar(completo_sem_rg, "cin") is False
        assert deve_escalar(completo_sem_rg, "cpf") is False

    def test_trigger_on_comprometida(self):
        fields = IdentityFields(
            nome="JOAO", cpf=_CPF_A, rg="1.234.567-8",
            aviso="leitura_comprometida", source=TextSource.OCR,
        )
        assert deve_escalar(fields, "rg") is True

    def test_no_trigger_when_source_is_text_layer_even_if_comprometida(self):
        """An exact PDF text layer is not model-dependent — a stronger
        VISION model reads the identical bytes no better."""
        fields = IdentityFields(
            aviso="leitura_comprometida", source=TextSource.TEXT_LAYER,
        )
        assert deve_escalar(fields, "rg") is False

    def test_no_trigger_when_source_is_text_layer_even_if_fields_missing(self):
        fields = IdentityFields(source=TextSource.TEXT_LAYER)
        assert deve_escalar(fields, "rg") is False

    def test_comprovante_missing_endereco_triggers(self):
        fields = IdentityFields(source=TextSource.OCR, endereco=None)
        assert deve_escalar(fields, "comprovante_endereco") is True

    def test_comprovante_with_endereco_does_not_trigger(self):
        from noctusai_lib.integrations.documents.address import EnderecoLido

        fields = IdentityFields(
            source=TextSource.OCR,
            endereco=EnderecoLido(cep="12345-678", logradouro="RUA DAS FLORES"),
        )
        assert deve_escalar(fields, "comprovante_endereco") is False

    def test_certidao_casamento_missing_estado_civil_triggers(self):
        fields = IdentityFields(source=TextSource.OCR)
        assert deve_escalar(fields, "certidao_casamento") is True

    def test_certidao_casamento_missing_second_conjuge_triggers(self):
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        fields = IdentityFields(
            estado_civil="casado", source=TextSource.OCR,
            conjuges=(ConjugeLido(nome="ANA", titular=True),),
        )
        assert deve_escalar(fields, "certidao_casamento") is True

    def test_certidao_casamento_complete_does_not_trigger(self):
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        fields = IdentityFields(
            estado_civil="casado", source=TextSource.OCR,
            conjuges=(
                ConjugeLido(nome="ANA", titular=True),
                ConjugeLido(nome="JOAO"),
            ),
        )
        assert deve_escalar(fields, "certidao_casamento") is False

    def test_certidao_nascimento_has_no_conjuge_expectation(self):
        fields = IdentityFields(estado_civil="casado", source=TextSource.OCR)
        assert deve_escalar(fields, "certidao_nascimento") is False

    def test_unlisted_tipo_never_triggers_on_missing_fields(self):
        fields = IdentityFields(source=TextSource.OCR)
        assert deve_escalar(fields, "guia_itbi") is False
        assert deve_escalar(fields, None) is False


class TestMesclar:
    """`mesclar`'s merge policy — fill / confirm / conflict, never a guess."""

    def _original(self, **kwargs) -> IdentityFields:
        base = IdentityFields(
            nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.BAIXA,
            cpf=_CPF_A, cpf_confianca=ExtractionConfidence.BAIXA,
            source=TextSource.OCR,
        )
        return replace(base, **kwargs)

    def test_escalation_error_returns_original_unchanged(self):
        original = self._original()
        escalada = IdentityFields(error="resolver_failed", error_message="boom")
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out is original

    def test_original_comprometida_escalada_clean_lifts_the_gate(self):
        """The brief's own condition: "if the escalated read is not
        comprometida ... use it" — a clean stronger-model read resolves the
        human-review reason the FIRST read carried, so the CODE that gates
        `aplicar_campos_ao_cliente` (`IdentityFields.leitura_comprometida`)
        is lifted. The full history — including the original comprometida
        sentence — survives in `aviso_mensagem` for audit."""
        original = self._original(
            aviso="leitura_comprometida",
            aviso_mensagem="leitura comprometida: algo — conferencia humana obrigatoria",
        )
        escalada = IdentityFields(nome="JOAO CARLOS PEREIRA", cpf=_CPF_A)
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.leitura_comprometida is False
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert "leitura_comprometida" not in out.aviso.split("+")
        # the ORIGINAL sentence is preserved for audit, plus the new one:
        assert "conferencia humana obrigatoria" in out.aviso_mensagem
        assert "liberada" in out.aviso_mensagem

    def test_escalated_also_comprometida_keeps_withheld_and_records_both(self):
        original = self._original(
            aviso="leitura_comprometida",
            aviso_mensagem="leitura comprometida: algo — conferencia humana obrigatoria",
        )
        escalada = IdentityFields(aviso="leitura_comprometida")
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.leitura_comprometida is True
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert "tambem comprometida" in out.aviso_mensagem.replace("é", "e").replace("á", "a")
        # The ORIGINAL fields are untouched — nothing was applied unattended.
        assert out.nome == original.nome
        assert out.cpf == original.cpf

    def test_fill_gap_adopts_the_escalated_value(self):
        original = self._original(rg=None, rg_confianca=ExtractionConfidence.NENHUMA)
        escalada = IdentityFields(
            rg="52.179.965-X", rg_confianca=ExtractionConfidence.BAIXA,
            rg_rotulo="REGISTRO GERAL", rg_orgao="SSP/SP",
            rg_orgao_confianca=ExtractionConfidence.BAIXA,
        )
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.rg == "52.179.965-X"
        assert out.rg_confianca == ExtractionConfidence.BAIXA
        assert out.rg_orgao == "SSP/SP"
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert "preencheu" in out.aviso_mensagem
        assert "rg" in out.aviso_mensagem

    def test_agreement_promotes_confidence_one_step_never_past_media(self):
        original = self._original()  # cpf at BAIXA
        escalada = IdentityFields(cpf=_CPF_A, cpf_confianca=ExtractionConfidence.BAIXA)
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.cpf == _CPF_A
        assert out.cpf_confianca == ExtractionConfidence.MEDIA
        assert "confirmou" in out.aviso_mensagem

    def test_agreement_never_promotes_past_media(self):
        original = self._original(cpf_confianca=ExtractionConfidence.MEDIA)
        escalada = IdentityFields(cpf=_CPF_A, cpf_confianca=ExtractionConfidence.MEDIA)
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.cpf_confianca == ExtractionConfidence.MEDIA

    def test_disagreement_reports_absent_never_guesses(self):
        original = self._original()  # cpf = _CPF_A
        escalada = IdentityFields(cpf=_CPF_B, cpf_confianca=ExtractionConfidence.BAIXA)
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.cpf is None
        assert out.cpf_confianca is ExtractionConfidence.NENHUMA
        assert AVISO_RELEITURA in out.aviso.split("+")
        assert "divergiu" in out.aviso_mensagem
        assert "cpf" in out.aviso_mensagem

    def test_disagreement_on_rg_adopts_escalated_value_as_baixa(self):
        """Measured (P2): on RG disagreements the escalated read was right
        3/3, so it is kept — as a baixa suggestion with a divergence note —
        instead of blanking the field."""
        original = self._original(
            rg="52.179.965-X", rg_confianca=ExtractionConfidence.BAIXA,
            rg_orgao="SSP/SP", rg_orgao_confianca=ExtractionConfidence.BAIXA,
        )
        escalada = IdentityFields(
            rg="99.999.999-0", rg_confianca=ExtractionConfidence.MEDIA,
            rg_orgao="SSP/SP", rg_orgao_confianca=ExtractionConfidence.MEDIA,
        )
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.rg == "99.999.999-0"
        assert out.rg_confianca is ExtractionConfidence.BAIXA
        assert out.rg_orgao == "SSP/SP"
        assert out.rg_orgao_confianca is ExtractionConfidence.BAIXA
        assert "adotado o valor do modelo superior" in out.aviso_mensagem

    def test_disagreement_on_rg_without_escalated_issuer_clears_issuer(self):
        original = self._original(
            rg="52.179.965-X", rg_confianca=ExtractionConfidence.BAIXA,
            rg_orgao="SSP/SP", rg_orgao_confianca=ExtractionConfidence.BAIXA,
        )
        escalada = IdentityFields(rg="99.999.999-0", rg_confianca=ExtractionConfidence.BAIXA)
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.rg == "99.999.999-0"
        assert out.rg_orgao is None
        assert out.rg_orgao_confianca is ExtractionConfidence.NENHUMA

    def test_disagreement_on_cpf_still_blanks(self):
        original = self._original()
        escalada = IdentityFields(cpf=_CPF_B, cpf_confianca=ExtractionConfidence.MEDIA)
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out.cpf is None

    def test_no_change_when_escalation_agrees_at_the_ceiling_and_finds_nothing_new(self):
        original = self._original(
            cpf_confianca=ExtractionConfidence.ALTA,
            nome_confianca=ExtractionConfidence.ALTA,
        )
        escalada = IdentityFields(
            nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.ALTA,
            cpf=_CPF_A, cpf_confianca=ExtractionConfidence.ALTA,
        )
        out = mesclar(original, escalada, escalation_model="claude-sonnet-5")
        assert out is original
