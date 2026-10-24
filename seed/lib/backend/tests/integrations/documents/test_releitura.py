"""Pure tests for `documents.releitura` — `deve_escalar` (the trigger table)
and `mesclar` (the merge policy). See that module's own docstring for the
measured run-to-run-variance this closes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from noctusai_lib.integrations.documents.ancora import ancora_falhou
from noctusai_lib.integrations.documents.releitura import (
    AVISO_CAMPOS_NUCLEO_AUSENTES,
    AVISO_DIVERGENCIA,
    AVISO_RELEITURA,
    campos_nucleo_faltando,
    deve_escalar,
    marcar_campos_ausentes,
    mesclar,
    sem_corroboracao,
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

    def test_a_complete_clean_ocr_read_STILL_escalates_for_critical_fields(self):
        """Owner decision 2026-10-13: the agreement gate needs a second
        independent read of EVERY document that carries critical identity
        fields — a complete, clean first read is not an exemption."""
        fields = IdentityFields(
            nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.BAIXA,
            cpf=_CPF_A, cpf_confianca=ExtractionConfidence.ALTA,
            source=TextSource.OCR,
        )
        for tipo in ("cin", "rg", "cnh", "certidao_casamento", "certidao_nascimento"):
            assert deve_escalar(fields, tipo) is True, tipo

    def test_trigger_on_missing_core_field_cpf_card(self):
        fields = IdentityFields(nome="JOAO CARLOS PEREIRA", source=TextSource.OCR)
        assert deve_escalar(fields, "cin") is True

    def test_rg_and_cnh_additionally_require_rg_for_completeness(self):
        completo_sem_rg = IdentityFields(
            nome="JOAO CARLOS PEREIRA", cpf=_CPF_A, source=TextSource.OCR,
        )
        assert campos_nucleo_faltando(completo_sem_rg, "rg") == ("rg",)
        assert campos_nucleo_faltando(completo_sem_rg, "cnh") == ("rg",)
        # CIN/CPF cards carry no RG number of their own.
        assert campos_nucleo_faltando(completo_sem_rg, "cin") == ()
        assert campos_nucleo_faltando(completo_sem_rg, "cpf") == ()

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

    def test_certidao_casamento_complete_still_escalates(self):
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        fields = IdentityFields(
            estado_civil="casado", source=TextSource.OCR,
            conjuges=(
                ConjugeLido(nome="ANA", titular=True),
                ConjugeLido(nome="JOAO"),
            ),
        )
        assert campos_nucleo_faltando(fields, "certidao_casamento") == ()
        assert deve_escalar(fields, "certidao_casamento") is True

    def test_certidao_nascimento_has_no_conjuge_expectation(self):
        fields = IdentityFields(
            nome="FULANO EXEMPLO", data_nascimento=date(1990, 10, 4), source=TextSource.OCR
        )
        assert campos_nucleo_faltando(fields, "certidao_nascimento") == ()

    def test_certidao_nascimento_without_estado_civil_is_complete(self):
        """Never-married registrado: no averbação, so no estado civil."""
        fields = IdentityFields(
            nome="FULANO EXEMPLO", data_nascimento=date(1990, 10, 4), source=TextSource.OCR
        )
        assert fields.estado_civil is None
        assert campos_nucleo_faltando(fields, "certidao_nascimento") == ()
        vazio = IdentityFields(source=TextSource.OCR)
        assert campos_nucleo_faltando(vazio, "certidao_nascimento") == ("nome", "data_nascimento")

    def test_unlisted_tipo_never_triggers_on_missing_fields(self):
        fields = IdentityFields(source=TextSource.OCR)
        assert deve_escalar(fields, "guia_itbi") is False
        assert deve_escalar(fields, None) is False


class TestCamposNucleoFaltando:
    """The completeness query `deve_escalar` now delegates to — usable on
    ANY `IdentityFields`, regardless of `source` (see `real.py`'s own
    text-layer-fallthrough and post-read-completeness callers, neither of
    which wants `deve_escalar`'s OCR-only gating)."""

    def test_complete_rg_reports_nothing_missing(self):
        fields = IdentityFields(
            nome="JOAO CARLOS PEREIRA", cpf=_CPF_A, rg="1.234.567-8",
            source=TextSource.TEXT_LAYER,
        )
        assert campos_nucleo_faltando(fields, "rg") == ()

    def test_rg_missing_cpf_and_rg_reports_both(self):
        fields = IdentityFields(nome="JOAO CARLOS PEREIRA", source=TextSource.TEXT_LAYER)
        faltando = campos_nucleo_faltando(fields, "rg")
        assert set(faltando) == {"cpf", "rg"}

    def test_runs_regardless_of_source_unlike_deve_escalar(self):
        """`deve_escalar` refuses to fire on a TEXT_LAYER read (a stronger
        model reads identical bytes no better) — but the read is still
        genuinely INCOMPLETE, and a caller asking about completeness alone
        (not "should I re-read") must see that."""
        fields = IdentityFields(nome="JOAO CARLOS PEREIRA", source=TextSource.TEXT_LAYER)
        assert deve_escalar(fields, "rg") is False
        assert campos_nucleo_faltando(fields, "rg") != ()

    def test_unlisted_tipo_reports_nothing_missing(self):
        fields = IdentityFields(source=TextSource.OCR)
        assert campos_nucleo_faltando(fields, "guia_itbi") == ()
        assert campos_nucleo_faltando(fields, None) == ()

    def test_comprovante_missing_endereco_reports_it(self):
        fields = IdentityFields(source=TextSource.OCR, endereco=None)
        assert campos_nucleo_faltando(fields, "comprovante_endereco") == ("endereco",)


class TestMarcarCamposAusentes:
    def test_no_op_when_nothing_is_missing(self):
        fields = IdentityFields(nome="JOAO", cpf=_CPF_A, source=TextSource.OCR)
        assert marcar_campos_ausentes(fields, ()) is fields

    def test_appends_the_aviso_naming_the_missing_fields(self):
        fields = IdentityFields(
            nome="JOAO", data_nascimento_confianca=ExtractionConfidence.ALTA,
            source=TextSource.OCR,
        )
        marcado = marcar_campos_ausentes(fields, ("cpf", "rg"), tipo_documento="rg")

        assert AVISO_CAMPOS_NUCLEO_AUSENTES in marcado.aviso.split("+")
        assert "CPF" in marcado.aviso_mensagem
        assert "RG" in marcado.aviso_mensagem
        # Never blocks what WAS found — unlike `leitura_comprometida`, this
        # is informational, not a persistence gate.
        assert marcado.nome == "JOAO"

    def test_stacks_with_an_existing_aviso_rather_than_replacing_it(self):
        fields = replace(
            IdentityFields(source=TextSource.OCR),
            aviso=AVISO_RELEITURA,
            aviso_mensagem="releitura com claude-opus preencheu: nome",
        )
        marcado = marcar_campos_ausentes(fields, ("cpf",), tipo_documento="cin")

        codigos = marcado.aviso.split("+")
        assert AVISO_RELEITURA in codigos
        assert AVISO_CAMPOS_NUCLEO_AUSENTES in codigos
        assert "releitura com claude-opus" in marcado.aviso_mensagem
        assert "CPF" in marcado.aviso_mensagem


def _matricula(dv_ok: bool = True) -> str:
    """A structurally valid 32-digit RCPN matrícula (CNS 123456, acervo 01,
    '55', ano 2001, livro tipo 2 = casamento) with a correct — or broken — DV."""
    from noctusai_lib.primitives.identificador import _rcpn_dv

    corpo = "123456" + "01" + "55" + "2001" + "2" + "00012" + "034" + "0001234"
    dv = _rcpn_dv(corpo)
    if not dv_ok:
        dv = "00" if dv != "00" else "11"
    return corpo + dv


class TestMesclar:
    """`mesclar` is the AGREEMENT GATE (owner decision 2026-10-13): a critical
    identity field is stored only when two independent reads agree. A
    disagreement yields NO value plus both readings — never a winner."""

    def _original(self, **kwargs) -> IdentityFields:
        base = IdentityFields(
            nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.BAIXA,
            cpf=_CPF_A, cpf_confianca=ExtractionConfidence.BAIXA,
            source=TextSource.OCR,
        )
        return replace(base, **kwargs)

    # ── agree ───────────────────────────────────────────────────────────

    def test_two_agreeing_reads_store_the_field_and_promote_one_step(self):
        out = mesclar(
            self._original(),
            IdentityFields(nome="Joao Carlos Pereira", nome_confianca=ExtractionConfidence.BAIXA),
            escalation_model="m",
        )
        assert out.nome == "JOAO CARLOS PEREIRA"
        assert out.nome_confianca is ExtractionConfidence.MEDIA
        assert out.divergencias == ()
        assert AVISO_DIVERGENCIA not in (out.aviso or "").split("+")

    def test_agreement_never_promotes_past_media(self):
        original = self._original(nome_confianca=ExtractionConfidence.MEDIA)
        escalada = IdentityFields(nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.MEDIA)
        assert mesclar(original, escalada, escalation_model="m").nome_confianca is ExtractionConfidence.MEDIA

    def test_cpf_in_two_spellings_agrees(self):
        out = mesclar(
            self._original(cpf="41295423898"),
            IdentityFields(nome="JOAO CARLOS PEREIRA", cpf=_CPF_A, cpf_confianca=ExtractionConfidence.BAIXA),
            escalation_model="m",
        )
        assert out.cpf is not None and out.divergencias == ()

    def test_a_cnh_rg_without_dv_and_the_full_rg_agree(self):
        """`30128742` (a CNH prints no check digit) and `30.128.742-9` are
        ONE RG (`canonical-identifiers`): an agreement, not a divergence."""
        original = self._original(
            rg="30128742", rg_confianca=ExtractionConfidence.BAIXA, rg_orgao="SSP/SP",
            rg_orgao_confianca=ExtractionConfidence.BAIXA,
        )
        escalada = IdentityFields(nome="JOAO CARLOS PEREIRA", rg="30.128.742-9", rg_confianca=ExtractionConfidence.MEDIA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.rg == "30.128.742-9"  # the fuller of the two agreeing values
        assert out.rg_orgao == "SSP/SP"
        assert out.divergencias == ()

    def test_all_three_reads_two_agree_one_differs(self):
        original = self._original(nome="ANA EXEMPLO SILVA")
        escalada = IdentityFields(nome="ANA EXEMPLO SILVEIRA")
        terceira = IdentityFields(nome="ANA EXEMPLO SILVA")
        out = mesclar(original, escalada, escalation_model="m", extras=(terceira,))
        assert out.nome == "ANA EXEMPLO SILVA"
        assert ("nome", "ANA EXEMPLO SILVEIRA") in out.leituras_alternativas

    # ── disagree ────────────────────────────────────────────────────────

    def test_disagreement_yields_no_value_and_both_readings(self):
        original = self._original(nome="JOSE FORTUNATO DA SILVA")
        escalada = IdentityFields(nome="JOSE FORTUNATO DA SILVEIRA", nome_confianca=ExtractionConfidence.BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome is None
        assert out.nome_confianca is ExtractionConfidence.NENHUMA
        assert not out.sugestao("nome") and not out.persistable("nome")
        assert out.leituras_alternativas == (
            ("nome", "JOSE FORTUNATO DA SILVA"), ("nome", "JOSE FORTUNATO DA SILVEIRA"),
        )
        assert out.divergencias == (
            ("nome", ("JOSE FORTUNATO DA SILVA", "JOSE FORTUNATO DA SILVEIRA")),
        )
        codigos = out.aviso.split("+")
        assert AVISO_DIVERGENCIA in codigos and AVISO_RELEITURA in codigos
        assert "nome" in out.aviso_mensagem

    def test_other_fields_still_agree_when_one_diverges(self):
        out = mesclar(
            self._original(nome="ANA SILVA"),
            IdentityFields(nome="ANA SOUZA", cpf=_CPF_A, cpf_confianca=ExtractionConfidence.BAIXA),
            escalation_model="m",
        )
        assert out.nome is None and out.cpf == _CPF_A

    @pytest.mark.parametrize("ordem", ["a_primeiro", "b_primeiro"])
    def test_no_heuristic_picks_a_winner_for_estado_civil(self, ordem):
        """Was 'averbação wins': a divorce read and a bare 'casado' read of
        the same certidão now give NO estado civil — the order is irrelevant."""
        divorciado = IdentityFields(
            estado_civil="divorciado", estado_civil_rotulo="AVERBACAO DE DIVORCIO",
            estado_civil_confianca=ExtractionConfidence.BAIXA,
        )
        casado = IdentityFields(estado_civil="casado", estado_civil_confianca=ExtractionConfidence.BAIXA)
        a, b = (divorciado, casado) if ordem == "a_primeiro" else (casado, divorciado)
        out = mesclar(replace(a, source=TextSource.OCR), b, escalation_model="m")
        assert out.estado_civil is None
        assert {v for c, v in out.leituras_alternativas if c == "estado_civil"} == {"divorciado", "casado"}

    @pytest.mark.parametrize("ordem", ["truncado_primeiro", "truncado_depois"])
    def test_no_heuristic_picks_a_winner_for_a_truncated_rg(self, ordem):
        ruim = IdentityFields(rg="1656536", rg_confianca=ExtractionConfidence.BAIXA, rg_orgao="SSP/SP",
                              source=TextSource.OCR)
        bom = IdentityFields(rg="18568536", rg_confianca=ExtractionConfidence.BAIXA, rg_orgao="SSP/SP")
        a, b = (ruim, bom) if ordem == "truncado_primeiro" else (replace(bom, source=TextSource.OCR), ruim)
        out = mesclar(a, b, escalation_model="m")
        assert out.rg is None and out.rg_orgao is None
        assert {v for c, v in out.leituras_alternativas if c == "rg"} == {"1656536", "18568536"}

    def test_a_compromised_first_read_no_longer_wins_or_loses_by_rule(self):
        """Was 'compromised-first-read-loses': now it simply does not count,
        so a single clean read corroborates nothing."""
        original = self._original(
            nome="CLELIER BASSO MERY", aviso="leitura_comprometida", aviso_mensagem="x",
        )
        escalada = IdentityFields(nome="CILENE AFRA EXEMPLO NERY", nome_confianca=ExtractionConfidence.BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.nome is None
        assert {v for c, v in out.leituras_alternativas if c == "nome"} == {
            "CLELIER BASSO MERY", "CILENE AFRA EXEMPLO NERY",
        }
        assert AVISO_DIVERGENCIA in out.aviso.split("+")

    def test_a_third_read_lets_two_valid_reads_agree_around_a_compromised_one(self):
        original = self._original(nome="CLELIER BASSO MERY", aviso="leitura_comprometida")
        e1 = IdentityFields(nome="CILENE AFRA EXEMPLO NERY")
        e2 = IdentityFields(nome="Cilene Afra Exemplo Nery")
        out = mesclar(original, e1, escalation_model="m", extras=(e2,))
        assert out.nome == "CILENE AFRA EXEMPLO NERY"
        assert not out.leitura_comprometida  # built from a clean read

    def test_a_field_only_one_read_has_is_not_stored(self):
        """A gap the re-read fills is NOT agreement: one transcription alone
        is exactly what invents content."""
        out = mesclar(
            self._original(rg=None, rg_confianca=ExtractionConfidence.NENHUMA),
            IdentityFields(nome="JOAO CARLOS PEREIRA", rg="52.179.965-X",
                           rg_confianca=ExtractionConfidence.BAIXA, rg_orgao="SSP/SP"),
            escalation_model="m",
        )
        assert out.rg is None and out.rg_orgao is None
        assert ("rg", "52.179.965-X") in out.leituras_alternativas
        assert out.divergencias == (("rg", ("52.179.965-X",)),)

    def test_spouse_names_must_agree(self):
        from noctusai_lib.integrations.documents.conjuges import ConjugeLido

        a = (ConjugeLido(nome="ANA EXEMPLO"), ConjugeLido(nome="JOAO EXEMPLO"))
        b = (ConjugeLido(nome="ANA EXEMPLO"), ConjugeLido(nome="JOAO EXEMPLAR"))
        c = (ConjugeLido(nome="JOAO EXEMPLO"), ConjugeLido(nome="ANA EXEMPLO"))
        ok = mesclar(self._original(conjuges=a), IdentityFields(nome="JOAO CARLOS PEREIRA", conjuges=c),
                     escalation_model="m")
        assert len(ok.conjuges) == 2
        # By IDENTITY, not list equality (F96, 2026-10-24): ANA is named by
        # both reads and stays; only the spouse the reads disagree on goes to
        # review — never the whole list.
        ruim = mesclar(self._original(conjuges=a), IdentityFields(nome="JOAO CARLOS PEREIRA", conjuges=b),
                       escalation_model="m")
        assert [c.nome for c in ruim.conjuges] == ["ANA EXEMPLO"]
        assert ruim.divergencias == (("conjuges", ("JOAO EXEMPLO", "JOAO EXEMPLAR")),)

    # ── DV anchor ───────────────────────────────────────────────────────

    def test_disagreeing_cpf_only_one_verifies_that_one_stands(self):
        """The one DV-based tie-break kept: a CPF whose check digit verifies
        is strong evidence on its own (a slip passes mod-11 ~1 in 100)."""
        out = mesclar(
            self._original(cpf="412.954.238-99"),  # DV fails
            IdentityFields(cpf=_CPF_A, cpf_confianca=ExtractionConfidence.MEDIA),
            escalation_model="m",
        )
        assert out.cpf == _CPF_A
        assert ("cpf", "412.954.238-99") in out.leituras_alternativas

    def test_two_disagreeing_cpfs_both_verifying_yield_no_value(self):
        out = mesclar(
            self._original(),
            IdentityFields(cpf=_CPF_B, cpf_confianca=ExtractionConfidence.MEDIA),
            escalation_model="m",
        )
        assert out.cpf is None
        assert {v for c, v in out.leituras_alternativas if c == "cpf"} == {_CPF_A, _CPF_B}

    def test_a_transcription_with_a_failed_anchor_never_counts(self):
        original = self._original(ancora_falhou=True)
        escalada = IdentityFields(
            nome="JOAO CARLOS PEREIRA", nome_confianca=ExtractionConfidence.BAIXA,
            cpf=_CPF_A, cpf_confianca=ExtractionConfidence.BAIXA,
        )
        out = mesclar(original, escalada, escalation_model="m")
        # Agreement on nome is impossible (one valid read); the lone valid
        # read's CPF verifies, so it stands by itself.
        assert out.nome is None
        assert out.cpf == _CPF_A

    # ── single read with a valid DV ─────────────────────────────────────

    def test_escalation_error_leaves_a_single_read_where_only_dv_verified_values_stand(self):
        original = self._original(
            rg="52.179.965-X", rg_confianca=ExtractionConfidence.BAIXA,
            data_nascimento=date(1980, 5, 12),
            data_nascimento_confianca=ExtractionConfidence.ALTA,
        )
        escalada = IdentityFields(error="resolver_failed", error_message="boom")
        out = mesclar(original, escalada, escalation_model="m")
        assert out.cpf == _CPF_A  # DV verifies: stands alone
        assert out.nome is None and out.rg is None and out.data_nascimento is None
        assert [c for c, _ in out.divergencias] == ["nome", "rg", "data_nascimento"]

    def test_single_read_with_an_invalid_cpf_dv_is_withheld(self):
        out = sem_corroboracao(self._original(cpf="412.954.238-99"))
        assert out.cpf is None
        assert ("cpf", "412.954.238-99") in out.leituras_alternativas

    def test_matricula_certidao_single_read_stands_only_with_a_valid_dv(self):
        ok = sem_corroboracao(self._original(
            matricula_certidao=_matricula(True), matricula_certidao_confianca=ExtractionConfidence.ALTA))
        assert ok.matricula_certidao == _matricula(True)
        ruim = sem_corroboracao(self._original(
            matricula_certidao=_matricula(False), matricula_certidao_confianca=ExtractionConfidence.ALTA))
        assert ruim.matricula_certidao is None
        assert ("matricula_certidao", _matricula(False)) in ruim.leituras_alternativas

    def test_a_text_layer_read_is_never_gated(self):
        original = self._original(source=TextSource.TEXT_LAYER)
        assert sem_corroboracao(original) is original

    # ── rg / rne exclusivity survives the gate ──────────────────────────

    def test_rne_and_rg_never_both_stand(self):
        original = self._original(rg="52.179.965-X", rg_confianca=ExtractionConfidence.BAIXA,
                                  rne="W573678Z", rne_confianca=ExtractionConfidence.BAIXA)
        escalada = IdentityFields(rg="52.179.965-X", rg_confianca=ExtractionConfidence.BAIXA,
                                  rne="W573678Z", rne_confianca=ExtractionConfidence.BAIXA)
        out = mesclar(original, escalada, escalation_model="m")
        assert out.rne == "W573678Z" and out.rg is None


class TestAncora:
    def test_a_cpf_whose_dv_fails_marks_the_transcription(self):
        assert ancora_falhou("NOME ANA\nCPF: 412.954.238-99\n") is True
        assert ancora_falhou("NOME ANA\nCPF: 41295423899\n") is True

    def test_a_valid_cpf_does_not(self):
        assert ancora_falhou("NOME ANA\nCPF: 412.954.238-98\n") is False

    def test_a_bare_eleven_digit_run_without_a_cpf_label_is_not_a_cpf(self):
        assert ancora_falhou("REGISTRO: 12346581446") is False

    def test_a_32_digit_matricula_with_a_broken_dv_marks_the_transcription(self):
        assert ancora_falhou(f"MATRICULA {_matricula(False)}") is True
        assert ancora_falhou(f"MATRICULA {_matricula(True)}") is False

    def test_the_matricula_is_found_through_spacing(self):
        m = _matricula(False)
        espacada = " ".join(m[i:i + 4] for i in range(0, 32, 4))
        assert ancora_falhou(f"Matrícula: {espacada}") is True
