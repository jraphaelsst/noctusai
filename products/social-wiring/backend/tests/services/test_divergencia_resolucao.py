"""The automatic divergence resolver (owner directive, 2026-09-29):

    "Those data divergencies we've been having on extractions, i need you to
    reason on how to solve this and resolve divergencies without the need of
    a human. You are to do this using docs and done contracts."

WHAT THESE PIN
--------------
- equivalence: format-only differences (an RG read without its check digit,
  a CPF with and without punctuation) are not a disagreement at all;
- type routing: a CPF sitting in the RG field is not an RG (CIN excepted);
- validators: an invalid CPF/CNPJ/RG-DV or unparseable date loses outright,
  whatever its tier;
- corroboration: >=2 distinct origins agreeing outranks a lone dissenter,
  regardless of either side's tier; an unresolved 2-vs-2 split falls
  through to tier, then to a human;
- source tier: the higher MEASURED precision wins; equal/unmeasured
  precision on both sides still needs a human;
- `normalizar_logradouro` collapses AV/AVENIDA-shaped format differences;
- `valido_para_contrato_sem_revisao` is the validation-gate predicate
  (>=95% precision with n>=10, or corroborated).

Pure module — no DB, no mocks. `app.services.campo_conflitos`'s own tests
cover the DB-aware `historico_valores`/`resolver_e_registrar` wrapper.
"""
from __future__ import annotations

from app.services import divergencia_resolucao as dr


def _mesmo_valor_simples(campo: str, a, b) -> bool:
    """A minimal field-equality stand-in for these pure tests — the real
    `identidade_extracao_service._mesmo_valor` is exercised end to end in
    `tests/modules/card_hub/test_identidade_d1_contrato.py`."""
    if a is None or b is None:
        return False
    if campo == "cpf":
        return dr.only_digits(str(a)) == dr.only_digits(str(b))
    return str(a).strip().upper() == str(b).strip().upper()


class TestValidadorCpf:
    def test_an_invalid_cpf_loses_to_a_valid_one(self):
        decisao = dr.resolver_divergencia(
            "cpf",
            valor_atual="111.111.111-11",  # repdigit — fails the check digit
            origem_atual="certidao_casamento",
            valor_proposto="412.954.238-98",  # a real, valid CPF
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao == dr.Decisao(
            vencedor="proposto", regra="validador", motivo=decisao.motivo,
            requer_humano=False,
        )

    def test_a_valid_cpf_already_on_file_beats_an_invalid_proposal(self):
        decisao = dr.resolver_divergencia(
            "cpf",
            valor_atual="412.954.238-98",
            origem_atual="cnh",
            valor_proposto="111.111.111-11",
            origem_proposto="certidao_casamento",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "validador"
        assert not decisao.requer_humano

    def test_two_invalid_cpfs_fall_through_to_tier_not_a_free_pass(self):
        # Neither side is refused BY THE VALIDATOR when both fail it (the
        # validator only breaks a tie between a good and a bad reading) —
        # source tier still applies underneath, exactly as it would for any
        # other disagreement.
        decisao = dr.resolver_divergencia(
            "cpf",
            valor_atual="111.111.111-11",
            origem_atual="cnh",
            valor_proposto="222.222.222-22",
            origem_proposto="certidao_casamento",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.regra == "tier"
        assert decisao.vencedor == "atual"


class TestValidadorData:
    def test_an_unparseable_date_loses(self):
        decisao = dr.resolver_divergencia(
            "data_nascimento",
            valor_atual="not-a-date",
            origem_atual="matricula",
            valor_proposto="1980-05-12",
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "proposto"
        assert decisao.regra == "validador"


class TestRgEquivalenciaEValidador:
    """Owner rule 2026-10-01 (`canonical-identifiers`) — prod examples."""

    def test_a_cnh_rg_without_its_dv_is_the_same_rg_as_the_full_one_proposed(self):
        # CNH prints `30128742`; the matrícula/card carries `30.128.742-9`.
        # Same identifier -> never a conflict (rule `equivalencia`, the
        # on-file provenance untouched).
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="30128742",
            origem_atual="cnh",
            valor_proposto="30.128.742-9",
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "equivalencia"
        assert not decisao.requer_humano

    def test_equivalence_holds_when_the_full_rg_is_the_value_on_file(self):
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="30.128.742-9",
            origem_atual="matricula",
            valor_proposto="30128742",
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert (decisao.vencedor, decisao.regra) == ("atual", "equivalencia")

    def test_a_cnh_rg_whose_dv_is_wrong_loses_to_the_completed_one(self):
        # `30.128.742-5` carries a DV that FAILS (the right one is 9).
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="30128742",
            origem_atual="cnh",
            valor_proposto="30.128.742-5",
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "validador"

    def test_an_ocr_digit_swap_loses_to_the_reading_whose_dv_verifies(self):
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="15.668.564-3",  # DV fails
            origem_atual="cnh",
            valor_proposto="16.669.554-3",  # DV verifies
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "proposto"
        assert decisao.regra == "validador"

    def test_a_cpf_sitting_in_the_rg_field_loses_to_a_real_rg(self):
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="297.556.088-50",  # a valid CPF, not an RG
            origem_atual="matricula",
            valor_proposto="30.128.742-9",
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "proposto"
        assert decisao.regra == "tipo_detectado"

    def test_a_cin_rg_equal_to_the_holders_own_cpf_is_not_misrouted(self):
        # The CIN prints the CPF number AS the identity number.
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="297.556.088-50",
            origem_atual="rg",
            valor_proposto="30.128.742-9",
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
            cpf_proprio="297.556.088-50",
        )
        assert decisao.regra != "tipo_detectado"

    def test_format_only_cpf_difference_is_equivalent(self):
        decisao = dr.resolver_divergencia(
            "cpf",
            valor_atual="41295423898",
            origem_atual="cnh",
            valor_proposto="412.954.238-98",
            origem_proposto="serasa_crednet",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert (decisao.vencedor, decisao.regra) == ("atual", "equivalencia")

    def test_two_genuinely_different_valid_rgs_fall_through_to_tier(self):
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="30.128.742-9",
            origem_atual="cnh",
            valor_proposto="52.179.965-X",
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        # matricula (0.38) < cnh (0.39) — cnh wins on tier.
        assert decisao.regra == "tier"
        assert decisao.vencedor == "atual"


class TestCorroboracao:
    def test_two_independent_sources_outrank_a_lone_dissenter(self):
        # `nome_oficial`: matricula (84%) alone would beat a lone cnh (100%)
        # read on... no, cnh is HIGHER tier — use a case where corroboration
        # actually overrides tier: two independent sources (rg + serasa)
        # agree with the ON-FILE value against a single higher-tier cnh
        # proposal that, for THIS pair, happens to disagree.
        decisao = dr.resolver_divergencia(
            "nome_oficial",
            valor_atual="ANA PAULA SOUZA",
            origem_atual="rg",
            valor_proposto="ANA PAULA SOUZA COSTA",
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
            historico=[("ANA PAULA SOUZA", "serasa_crednet")],
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "corroboracao"

    def test_corroboration_for_the_proposed_side_wins_too(self):
        # Both sides carry the SAME tier (cnh/rg = 100% each) — a tier call
        # alone would tie and need a human; three independent sources
        # (rg + serasa_crednet + matricula) agreeing with the PROPOSED value
        # against the lone `cnh` reading decides it BEFORE tier is reached.
        decisao = dr.resolver_divergencia(
            "nome_oficial",
            valor_atual="ANA PAULA SOUZA COSTA",
            origem_atual="cnh",
            valor_proposto="ANA PAULA SOUZA",
            origem_proposto="rg",
            mesmo_valor=_mesmo_valor_simples,
            historico=[
                ("ANA PAULA SOUZA", "serasa_crednet"),
                ("ANA PAULA SOUZA", "matricula"),
            ],
        )
        assert decisao.vencedor == "proposto"
        assert decisao.regra == "corroboracao"

    def test_a_third_disagreeing_value_in_history_is_ignored(self):
        decisao = dr.resolver_divergencia(
            "genero",
            valor_atual="Masculino",
            origem_atual="cnh",
            valor_proposto="Feminino",
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
            historico=[("Indefinido", "certidao_casamento")],
        )
        # Neither side corroborated (the third value matches neither) —
        # falls through to tier: cnh (100%) beats matricula (95%).
        assert decisao.regra == "tier"
        assert decisao.vencedor == "atual"


class TestTier:
    def test_the_higher_measured_precision_wins(self):
        decisao = dr.resolver_divergencia(
            "cpf",
            valor_atual="412.954.238-98",
            origem_atual="cnh",  # 100%, n=19
            valor_proposto="303.102.653-55",
            origem_proposto="certidao_casamento",  # 67%, n=3
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "tier"
        assert "cnh" in decisao.motivo

    def test_equal_precision_on_both_sides_needs_a_human(self):
        decisao = dr.resolver_divergencia(
            "nacionalidade",
            valor_atual="brasileiro",
            origem_atual="cnh",  # 100%
            valor_proposto="brasileira",  # a different fact per this stub
            origem_proposto="matricula",  # also 100%
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.requer_humano
        assert decisao.vencedor is None

    def test_one_side_unmeasured_cannot_be_decided_on_tier_either(self):
        # A tier call compares TWO measured cells — one side with no
        # PRECISAO entry at all is not "worse than measured", it is
        # UNKNOWN, and unknown never loses automatically either.
        decisao = dr.resolver_divergencia(
            "profissao",
            valor_atual="engenheiro",
            origem_atual="matricula",  # measured, 100%
            valor_proposto="advogado",
            origem_proposto="whatsapp_bot",  # not in PRECISAO at all
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.requer_humano
        assert decisao.vencedor is None

    def test_two_unmeasured_sources_need_a_human(self):
        decisao = dr.resolver_divergencia(
            "profissao",
            valor_atual="engenheiro",
            origem_atual="whatsapp_bot",
            valor_proposto="advogado",
            origem_proposto="chat_manual",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.requer_humano


class TestNormalizarLogradouro:
    def test_abbreviation_and_spelled_out_form_collapse_to_one_string(self):
        assert dr.normalizar_logradouro("AV Paulista") == dr.normalizar_logradouro(
            "Avenida Paulista"
        )

    def test_every_listed_abbreviation_maps_to_its_canonical_form(self):
        pares = [
            ("R", "RUA"), ("AL", "ALAMEDA"), ("EST", "ESTRADA"),
            ("TV", "TRAVESSA"), ("ROD", "RODOVIA"), ("PC", "PRACA"),
        ]
        for abreviado, canonico in pares:
            assert dr.normalizar_logradouro(f"{abreviado} das Flores").startswith(
                canonico
            )

    def test_accent_case_and_spacing_are_also_normalised(self):
        assert dr.normalizar_logradouro("  praça   da Sé  ") == "PRACA DA SE"

    def test_a_street_type_not_in_the_map_is_left_alone_but_still_normalised(self):
        assert dr.normalizar_logradouro("Alameda Santos") == dr.normalizar_logradouro(
            "AL Santos"
        )

    def test_empty_normalises_to_empty(self):
        assert dr.normalizar_logradouro(None) == ""
        assert dr.normalizar_logradouro("") == ""


class TestValidoParaContratoSemRevisao:
    def test_a_95_percent_n_10_plus_source_auto_validates(self):
        assert dr.valido_para_contrato_sem_revisao("cpf", "cnh") is True

    def test_a_39_percent_source_does_not(self):
        assert dr.valido_para_contrato_sem_revisao("rg", "cnh") is False

    def test_a_thin_sample_does_not_auto_validate_on_tier_alone(self):
        # rg/rg is 100% but n=2 — below N_MINIMO_VALIDACAO.
        assert dr.valido_para_contrato_sem_revisao("rg", "rg") is False

    def test_corroborated_always_qualifies_whatever_the_tier(self):
        assert dr.valido_para_contrato_sem_revisao(
            "rg", "cnh", corroborado=True
        ) is True

    def test_an_unmeasured_source_does_not_auto_validate(self):
        assert dr.valido_para_contrato_sem_revisao("profissao", "whatsapp_bot") is False

    def test_unknown_origem_does_not_auto_validate(self):
        assert dr.valido_para_contrato_sem_revisao("cpf", None) is False


class TestEvidenciaViva:
    """Step 1b (2026-09-29 second pass): a side whose own document no longer
    asserts it has been RETRACTED — positive evidence only."""

    def test_a_retracted_on_file_value_loses_to_a_supported_proposal(self):
        # 897's shape: both sources measure 100% on names, but the CNH pass
        # that wrote the on-file name was re-read and no longer carries it.
        decisao = dr.resolver_divergencia(
            "nome_oficial",
            valor_atual="JOAO SILVA", origem_atual="cnh",
            valor_proposto="MARIA SOUZA", origem_proposto="serasa_crednet",
            mesmo_valor=_mesmo_valor_simples,
            evidencia=dr.EvidenciaViva(atual_sustentado=False, proposto_sustentado=True),
        )
        assert (decisao.vencedor, decisao.regra) == ("proposto", "retratado")

    def test_a_retracted_proposal_loses_even_to_an_unknown_on_file_value(self):
        # 882's shape: the certidão "RG" names no spouse in particular.
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="12345678", origem_atual="cnh",
            valor_proposto="9876543210", origem_proposto="certidao_casamento",
            mesmo_valor=_mesmo_valor_simples,
            evidencia=dr.EvidenciaViva(atual_sustentado=None, proposto_sustentado=False),
        )
        assert (decisao.vencedor, decisao.regra) == ("atual", "retratado")

    def test_both_retracted_is_not_decided_by_retraction(self):
        decisao = dr.resolver_divergencia(
            "profissao",
            valor_atual="engenheiro", origem_atual="rg",
            valor_proposto="advogado", origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
            evidencia=dr.EvidenciaViva(atual_sustentado=False, proposto_sustentado=False),
        )
        assert decisao.requer_humano

    def test_unknown_support_on_both_sides_changes_nothing(self):
        sem = dr.resolver_divergencia(
            "genero", valor_atual="Masculino", origem_atual="cnh",
            valor_proposto="Feminino", origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        com = dr.resolver_divergencia(
            "genero", valor_atual="Masculino", origem_atual="cnh",
            valor_proposto="Feminino", origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples, evidencia=dr.EvidenciaViva(),
        )
        assert (sem.vencedor, sem.regra) == (com.vencedor, com.regra)

    def test_a_validator_still_outranks_retraction(self):
        decisao = dr.resolver_divergencia(
            "cpf",
            valor_atual="111.111.111-11", origem_atual="cnh",
            valor_proposto="412.954.238-98", origem_proposto="certidao_casamento",
            mesmo_valor=_mesmo_valor_simples,
            evidencia=dr.EvidenciaViva(atual_sustentado=True, proposto_sustentado=False),
        )
        assert (decisao.vencedor, decisao.regra) == ("proposto", "validador")

    def test_live_document_assertions_corroborate(self):
        # f2a4e739's shape: a typed name, an RG that agrees with it (applied
        # without a conflict, so never "proposed"), a lone matrícula against.
        decisao = dr.resolver_divergencia(
            "nome_oficial",
            valor_atual="ANA PAULA SOUZA", origem_atual="manual",
            valor_proposto="ANA P SOUZA", origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
            evidencia=dr.EvidenciaViva(afirmacoes=(("ANA PAULA SOUZA", "rg"),)),
        )
        assert (decisao.vencedor, decisao.regra) == ("atual", "corroboracao")


class TestDecisaoOutraPessoa:
    """R4 (owner directive, 2026-09-30, live-test evidence): a proposed
    identity value that equals another PARTY's own value in the same
    negotiation is not this person's fact — auto-rejected, never left
    pending for a human. Pure — the caller
    (`identidade_extracao_service._valores_outras_pessoas`) gathers the
    other parties' own values; this function only compares."""

    def test_a_name_matching_another_party_is_rejected(self):
        decisao = dr.decisao_outra_pessoa(
            "nome_oficial", "JOAO PEREIRA SILVA",
            mesmo_valor=_mesmo_valor_simples,
            valores_outras_pessoas=[("JOAO PEREIRA SILVA", "comprador")],
        )
        assert decisao is not None
        assert (decisao.vencedor, decisao.regra, decisao.requer_humano) == (
            "atual", "outra_pessoa", False,
        )
        assert "comprador" in decisao.motivo

    def test_a_cpf_matching_another_partys_cpf_is_rejected(self):
        decisao = dr.decisao_outra_pessoa(
            "cpf", "412.954.238-98",
            mesmo_valor=_mesmo_valor_simples,
            valores_outras_pessoas=[("41295423898", "vendedor")],
        )
        assert decisao is not None
        assert decisao.regra == "outra_pessoa"

    def test_no_match_among_other_parties_is_none(self):
        decisao = dr.decisao_outra_pessoa(
            "nome_oficial", "MARIA SOUZA",
            mesmo_valor=_mesmo_valor_simples,
            valores_outras_pessoas=[("JOAO PEREIRA SILVA", "comprador")],
        )
        assert decisao is None

    def test_no_other_parties_at_all_is_none(self):
        decisao = dr.decisao_outra_pessoa(
            "nome_oficial", "MARIA SOUZA",
            mesmo_valor=_mesmo_valor_simples, valores_outras_pessoas=[],
        )
        assert decisao is None

    def test_an_empty_proposal_is_never_rejected(self):
        decisao = dr.decisao_outra_pessoa(
            "cpf", None, mesmo_valor=_mesmo_valor_simples,
            valores_outras_pessoas=[("41295423898", "vendedor")],
        )
        assert decisao is None

    def test_endereco_is_out_of_scope_a_shared_household_address_is_not_misfiling(self):
        # A couple legitimately shares the SAME address — never a rejection.
        decisao = dr.decisao_outra_pessoa(
            "endereco", "RUA A, 100",
            mesmo_valor=_mesmo_valor_simples,
            valores_outras_pessoas=[("RUA A, 100", "conjuge")],
        )
        assert decisao is None

    def test_an_empty_other_partys_value_never_matches(self):
        decisao = dr.decisao_outra_pessoa(
            "rg", "12.345.678-9",
            mesmo_valor=_mesmo_valor_simples,
            valores_outras_pessoas=[(None, "comprador"), ("", "vendedor")],
        )
        assert decisao is None


class TestRefinamentoOrgaoExpedidor:
    """2026-10-03, P3/P4 test loop: a bank form (`ficha_cadastral`) prints the
    issuer as `SSP` with no state, the CNH as `SSP/SP`. Same órgão, one
    reading stated completely — measured as the single largest class of
    blocking conflicts. Pre-fix: `requer_humano` (no ficha cell in PRECISAO)."""

    def _decidir(self, atual, origem_atual, proposto, origem_proposto, **kw):
        return dr.resolver_divergencia(
            "rg_orgao_expedidor",
            valor_atual=atual, origem_atual=origem_atual,
            valor_proposto=proposto, origem_proposto=origem_proposto,
            mesmo_valor=_mesmo_valor_simples, **kw,
        )

    def test_the_reading_with_the_uf_is_kept(self):
        d = self._decidir("SSP/SP", "cnh", "SSP", "ficha_cadastral")
        assert (d.vencedor, d.regra, d.requer_humano) == ("atual", "refinamento", False)

    def test_the_proposed_reading_with_the_uf_wins_over_a_bare_one(self):
        d = self._decidir("SSP", "ficha_cadastral", "SSP/SP", "cnh")
        assert (d.vencedor, d.regra) == ("proposto", "refinamento")

    def test_a_different_orgao_still_needs_a_human(self):
        d = self._decidir("SERRA/SP", "rg", "SSP", "ficha_cadastral")
        assert d.requer_humano is True

    def test_a_human_typed_bare_orgao_is_never_replaced(self):
        d = self._decidir("SSP", "manual", "SSP/SP", "cnh", atual_humano=True)
        assert (d.requer_humano, d.regra) == (True, "valor_humano")

    def test_a_human_value_still_wins_when_the_rule_keeps_it(self):
        d = self._decidir("SSP/SP", "manual", "SSP", "ficha_cadastral", atual_humano=True)
        assert (d.vencedor, d.regra) == ("atual", "refinamento")


class TestValorHumanoNuncaSobrescrito:
    def test_a_tier_win_for_the_proposal_yields_to_a_confirmed_value(self):
        """Tier would pick the CNH over the matrícula — but the on-file value
        was confirmed by a person, so a human decides."""
        d = dr.resolver_divergencia(
            "nome_oficial",
            valor_atual="FULANO DE TAL", origem_atual="matricula",
            valor_proposto="FULANO DE TAL SILVA", origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples, atual_humano=True,
        )
        assert (d.requer_humano, d.regra) == (True, "valor_humano")

    def test_a_proven_invalid_value_is_still_replaced(self):
        """`REGRAS_PROVA_OBJETIVA`: a typed CPF whose check digit fails is
        not a CPF at all (pinned since 2026-09-29)."""
        d = dr.resolver_divergencia(
            "cpf",
            valor_atual="111.111.111-11", origem_atual="manual",
            valor_proposto="412.954.238-98", origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples, atual_humano=True,
        )
        assert (d.vencedor, d.regra) == ("proposto", "validador")
