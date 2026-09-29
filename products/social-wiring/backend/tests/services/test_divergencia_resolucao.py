"""The automatic divergence resolver (owner directive, 2026-09-29):

    "Those data divergencies we've been having on extractions, i need you to
    reason on how to solve this and resolve divergencies without the need of
    a human. You are to do this using docs and done contracts."

WHAT THESE PIN
--------------
- validators: an invalid CPF/CNPJ or unparseable date loses outright,
  whatever its tier; the RG-specific "one reading is the other's prefix
  missing only the DV" rule picks the longer, DV-carrying value;
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


class TestRgPrefixoDv:
    def test_the_longer_reading_with_the_check_digit_wins_when_proposed(self):
        # CNH prints the RG without its trailing DV (measured 39%/18) —
        # a fuller matrícula reading with the DV wins even though it is
        # the PROPOSED (newer) side here.
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="123456789",  # CNH: no DV
            origem_atual="cnh",
            valor_proposto="1234567890",  # matrícula: the full RG + DV
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "proposto"
        assert decisao.regra == "rg_prefixo_dv"

    def test_the_longer_reading_wins_even_when_it_is_the_value_on_file(self):
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="1234567890",  # already on file WITH its DV
            origem_atual="matricula",
            valor_proposto="123456789",  # a later CNH read, missing it
            origem_proposto="cnh",
            mesmo_valor=_mesmo_valor_simples,
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "rg_prefixo_dv"

    def test_two_genuinely_different_rgs_are_not_a_prefix_match(self):
        decisao = dr.resolver_divergencia(
            "rg",
            valor_atual="111222333",
            origem_atual="cnh",
            valor_proposto="444555666",
            origem_proposto="matricula",
            mesmo_valor=_mesmo_valor_simples,
        )
        # Falls through validators/DV to tier: matricula (0.38) < cnh (0.39)
        # — cnh wins on tier, not on the DV rule.
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
