"""Render-time normalisers found by comparing a generated contract with its
signed counterpart (2026-10-13):

- a foreign party's RNE prints "RNE nº <n>" — never the issuing body;
- an RG órgão without its UF prints as stored AND readiness warns;
- a profissão outside the vocabulary ("aposentanda") is a readiness `falta`,
  never silently rewritten;
- logradouro/bairro/cidade print in title case (particles lower-case);
- the SP "Certidão Única de Débitos" (Resolução Conjunta SFP/PGE nº 1/2026)
  prints ONE clause-3 line in place of the two legacy SP lines, judged by
  its printed validity or emission + 90 days.

Every name, CPF and number here is synthetic.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, frases, profissoes
from app.modules.card_hub.contrato_gerador.dados import Certidao, Endereco
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(n: int, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _texto(n: int, d) -> str:
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)
    return "\n".join(r.paragrafos)


def _comprador(d, **campos):
    return replace(d, compradores=[replace(d.compradores[0], **campos), *d.compradores[1:]])


# ─── 1. identidade: RNE / RG órgão ────────────────────────────────────────


class TestIdentidade:
    def _pessoa(self, **campos):
        return replace(fx.variante(1).compradores[0], **campos)

    def test_rne_prints_numero_without_orgao(self):
        p = self._pessoa(nacionalidade="italiana", identidade_tipo="rne", rg="W-573.678-Z", rg_orgao="DIREX")
        assert frases.identidade_texto(p).endswith("da cédula de identidade RNE nº W-573.678-Z")
        assert "DIREX" not in frases.identidade_texto(p)

    def test_rnm_same_shape(self):
        p = self._pessoa(nacionalidade="italiana", identidade_tipo="rnm", rg="V123456-7", rg_orgao="CGPI/DIREX/DPF")
        assert frases.identidade_texto(p).endswith("da cédula de identidade RNM nº V123456-7")

    def test_rg_keeps_orgao_and_uf(self):
        p = self._pessoa(rg="18.568.536", rg_orgao="SSP/SP")
        assert frases.identidade_texto(p).endswith("da cédula de identidade RG 18.568.536-SSP-SP")
        assert frases.rg_orgao_sem_uf(p) is False

    def test_rg_orgao_sem_uf_prints_orgao_alone_never_invents_uf(self):
        p = self._pessoa(rg="19.131.047-5", rg_orgao="SSP")
        assert frases.rg_texto(p) == "19.131.047-5-SSP"
        assert frases.rg_orgao_sem_uf(p) is True

    @pytest.mark.parametrize("orgao", ["DPF", "", None])
    def test_orgao_federal_or_absent_is_not_sem_uf(self, orgao):
        assert frases.rg_orgao_sem_uf(self._pessoa(rg_orgao=orgao)) is False

    def test_rne_orgao_is_never_judged_for_uf(self):
        p = self._pessoa(nacionalidade="italiana", identidade_tipo="rne", rg_orgao="SSP")
        assert frases.rg_orgao_sem_uf(p) is False

    def test_readiness_avisa_uf_ausente(self):
        d = _comprador(fx.variante(1), rg_orgao="SSP")
        av = _avaliar(1, d)
        nome = d.compradores[0].nome
        mensagens = [a["mensagem"] for a in av.avisos if a["codigo"] == "RG_ORGAO_SEM_UF"]
        assert len(mensagens) == 1
        assert mensagens[0].startswith(f"UF do órgão expedidor do RG de {nome} ausente")
        assert av.pronto  # a warning, not a block


# ─── 2. profissão ─────────────────────────────────────────────────────────


class TestProfissao:
    @pytest.mark.parametrize("valor", [
        "aposentada", "Aposentado", "advogada", "engenheiro civil", "analista de sistemas",
        "Médica", "corretora de imóveis", "empresário", "do lar",
    ])
    def test_reconhecidas(self, valor):
        assert profissoes.reconhecida(valor)

    @pytest.mark.parametrize("valor", ["aposentanda", "xpto", "profissao"])
    def test_nao_reconhecidas(self, valor):
        assert not profissoes.reconhecida(valor)

    def test_readiness_falta_and_text_never_rewritten(self):
        d = _comprador(fx.variante(1), profissao="aposentanda")
        av = _avaliar(1, d)
        nome = d.compradores[0].nome
        faltas = [f for f in av.faltando if f["campo"] == "qualificacao.profissao"]
        assert [f["rotulo"] for f in faltas] == [f"Profissão de {nome} não reconhecida: 'aposentanda'"]
        assert not av.pronto
        # The renderer itself prints the stored value as-is (no silent fix).
        assert "aposentanda" in frases.texto_pessoa(d.compradores[0], em_nucleo=False)


# ─── 3. endereço em title case ────────────────────────────────────────────


class TestEnderecoCaixa:
    def test_signed_style(self):
        e = Endereco(logradouro="AL. LIVERPOOL", numero="81", bairro="RESERVA DO VIANNA",
                     cidade="COTIA", uf="sp", cep="06709300")
        assert frases.endereco_texto(e) == "Al. Liverpool, nº 81 - Reserva do Vianna - Cotia/SP – CEP: 06709-300"

    def test_never_expands_abbreviation(self):
        e = Endereco(logradouro="ALAMEDA LIVERPOOL", numero="81", bairro="", cidade="COTIA", uf="SP", cep="06709300")
        assert frases.endereco_texto(e).startswith("Alameda Liverpool, nº 81 - Cotia/SP")

    @pytest.mark.parametrize("bruto, impresso", [
        ("RUA XV DE NOVEMBRO", "Rua XV de Novembro"),
        ("AVENIDA DOM PEDRO II", "Avenida Dom Pedro II"),
        ("SANTANA DE PARNAÍBA", "Santana de Parnaíba"),
        ("SANTA BÁRBARA D'OESTE", "Santa Bárbara D'Oeste"),
        ("JARDIM DAS FLORES E DOS LAGOS", "Jardim das Flores e dos Lagos"),
        ("DO LAGO", "Do Lago"),
        ("rua das palmeiras", "Rua das Palmeiras"),
        ("RUA  CIVIL", "Rua Civil"),
        # A mixed-case value is a deliberate spelling — printed as stored.
        ("Alphaville Residencial dois", "Alphaville Residencial dois"),
    ])
    def test_titulo_lugar(self, bruto, impresso):
        assert frases.titulo_lugar(bruto) == impresso

    def test_uf_and_cep_upper(self):
        e = Endereco(logradouro="rua a", numero="1", bairro="centro", cidade="são paulo", uf="sp", cep="01001-000")
        assert frases.endereco_texto(e).endswith("São Paulo/SP – CEP: 01001-000")


# ─── 4. Certidão Única de Débitos (SP) ────────────────────────────────────


def _unica(**campos) -> Certidao:
    base = dict(
        tipo=frases.CERTIDAO_UNICA_SP, resultado="negativa", numero="ABCD.1234.EF56.7890",
        emitida_em=date(2026, 9, 1), validade_ate=date(2026, 11, 30), consulta_tipo_documento="cpf",
    )
    return Certidao(**{**base, **campos})


def _sem_legadas(certidoes: list[Certidao]) -> list[Certidao]:
    return [c for c in certidoes if c.tipo not in frases.CERTIDOES_SUBSTITUIDAS_PELA_UNICA_SP]


class TestCertidaoUnica:
    def test_item_line(self):
        assert frases.item_certidao(frases.CERTIDAO_UNICA_SP, _unica()) == (
            "Certidão Única de Débitos do Estado de São Paulo – nº ABCD.1234.EF56.7890 - emitida em 01/09/2026"
        )

    def test_tipos_exigidos_replaces_the_two_legacy_lines_in_place(self):
        idx = derivacao.indice_certidoes([_unica()], "cpf")
        legado = derivacao.tipos_exigidos("cpf")
        com_unica = derivacao.tipos_exigidos("cpf", idx)
        posicao = legado.index("cnd_fazenda_sp")
        assert com_unica[posicao] == frases.CERTIDAO_UNICA_SP
        assert not set(frases.CERTIDOES_SUBSTITUIDAS_PELA_UNICA_SP) & set(com_unica)
        assert len(com_unica) == len(legado) - 1

    @pytest.mark.parametrize("c", [
        None,
        _unica(resultado=None, numero=None, emitida_em=None, validade_ate=None),  # empty placeholder
        _unica(resultado="nao_emitida"),
    ])
    def test_placeholder_or_nao_emitida_keeps_legacy(self, c):
        assert not derivacao.certidao_unica_sp_vale(c)

    def _com_unica(self, **campos):
        # The SELLER: their certidões are the ones the contract presents.
        d = fx.variante(1)
        v0 = d.vendedores[0]
        return replace(d, vendedores=[replace(v0, certidoes=_sem_legadas(v0.certidoes) + [_unica(**campos)]),
                                      *d.vendedores[1:]])

    def test_clause_3_renders_one_line(self):
        base = _texto(1, fx.variante(1))
        texto = _texto(1, self._com_unica())
        assert "Certidão Única de Débitos do Estado de São Paulo – nº ABCD.1234.EF56.7890 - emitida em 01/09/2026" in texto
        assert texto.count("Certidão Única de Débitos") == 1
        # That party's two legacy lines are gone; every other party keeps theirs.
        for legado in ("Não Inscritos na Dívida Ativa do Estado de São Paulo",
                       "Débitos Tributários da Dívida Ativa do Estado de São Paulo"):
            assert texto.count(legado) == base.count(legado) - 1

    def test_legacy_pair_not_required_when_unica_present(self):
        av = _avaliar(1, self._com_unica())
        assert not any(f["campo"] in ("certidao.cnd_fazenda_sp", "certidao.divida_ativa_sp") for f in av.faltando)
        assert av.pronto, (av.faltando, av.bloqueios)

    def _codigos(self, **campos) -> set[str]:
        return {b["codigo"] for b in _avaliar(1, self._com_unica(**campos)).bloqueios}

    def test_the_30_day_emission_rule_applies_like_every_other_certidao(self):
        """Owner decision 2026-10-13: NO exemption — a printed validity that
        still covers the signing date does not excuse a 60-day-old emission."""
        codigos = self._codigos(emitida_em=fx.ASSINATURA - timedelta(days=60),
                                validade_ate=fx.ASSINATURA + timedelta(days=30))
        assert "CERTIDAO_EMISSAO_ANTIGA" in codigos
        assert "CERTIDAO_VENCIDA" not in codigos  # the validity check is separate

    def test_a_fresh_emission_with_a_valid_validity_passes_both(self):
        codigos = self._codigos(emitida_em=fx.ASSINATURA - timedelta(days=10),
                                validade_ate=fx.ASSINATURA + timedelta(days=30))
        assert not codigos & {"CERTIDAO_EMISSAO_ANTIGA", "CERTIDAO_VENCIDA"}

    def test_printed_validity_expired_blocks_even_when_the_emission_is_fresh(self):
        codigos = self._codigos(emitida_em=fx.ASSINATURA - timedelta(days=10),
                                validade_ate=fx.ASSINATURA - timedelta(days=1))
        assert "CERTIDAO_VENCIDA" in codigos
        assert "CERTIDAO_EMISSAO_ANTIGA" not in codigos

    def test_without_printed_validity_the_30_day_rule_is_the_binding_one(self):
        ok = self._codigos(emitida_em=fx.ASSINATURA - timedelta(days=29), validade_ate=None)
        assert not ok & {"CERTIDAO_EMISSAO_ANTIGA", "CERTIDAO_VENCIDA"}
        antiga = self._codigos(emitida_em=fx.ASSINATURA - timedelta(days=31), validade_ate=None)
        assert "CERTIDAO_EMISSAO_ANTIGA" in antiga
        assert "CERTIDAO_VENCIDA" not in antiga  # 31 days < the 90-day validity

    def test_the_90_day_validity_is_a_separate_check(self):
        """Its own validity (emission + 90 days) is still enforced — with a
        looser office policy than 30 days the 90-day cap is what binds."""
        from dataclasses import replace as _replace

        d = self._com_unica(emitida_em=fx.ASSINATURA - timedelta(days=91), validade_ate=None)
        pol = _replace(fx.politica_variante(1), certidao_max_dias=365)
        sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
        av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
        assert any(
            b["codigo"] == "CERTIDAO_VENCIDA" and "90 dias da emissão" in b["mensagem"]
            for b in av.bloqueios
        )

    def test_half_filled_unica_names_its_own_gap(self):
        av = _avaliar(1, self._com_unica(numero=None))
        assert "certidao.certidao_unica_sp.numero" in {f["campo"] for f in av.faltando}
