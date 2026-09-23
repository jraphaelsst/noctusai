"""F5 contract generator — the pure core, over synthetic fixtures (no DB).

WHAT THESE PIN
--------------
- the switch derivation for each of spec §1.3's 6 variants, and its modelo;
- the gate REFUSES with the exact missing fields, never renders blanks;
- Σ parcelas ≠ preço and RG = CPF block;
- clause numbers and "Cláusula X" references stay consecutive and correct as
  conditional clauses switch on/off, and "Parágrafo Único" is decided by what
  actually rendered;
- every "R$ X (Y)" in the rendered text round-trips through the extenso;
- the matrícula's selected text lands byte-identical in word/document.xml;
- the post-render lint catches the sample contracts' hand-assembly errors;
- each of the office's 15 policy answers (spec §6.2, answered 2026-09-15) is
  generator behaviour, pinned at its boundary (1977-12-25/26, 29/30 days,
  89/90 days, the 5-year baixada / last-transfer edge);
- `documento.gerar_pdf` turns that `.docx` into an ABNT PDF: the TITLE
  paragraph is centered + bold, a HEADING is bold, and a matrícula range
  carried through `Matricula.formatacao` renders bold/underlined —
  contract `projects/abnt-formatting-CONTRACT.md` §5.

Rendering uses the REAL seed docxtpl adapter — the Fake never evaluates Jinja.
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

import fitz
import pytest
from reportlab.lib.units import cm

from noctusai_lib.domain.texto_ptbr import dias_por_extenso, parse_brl, reais_por_extenso
from noctusai_lib.integrations.documents import Instrumento, frase_titulo_aquisitivo
from noctusai_lib.integrations.documents.abnt import UnsupportedGlyphError
from noctusai_lib.integrations.documents.formatting import FormatRange
from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import carregador, derivacao, documento, frases, lint
from app.modules.card_hub.contrato_gerador.concordancia import lado
from app.modules.card_hub.contrato_gerador.dados import DadosContrato
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(n: int, d=None):
    d = d if d is not None else fx.variante(n)
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol)
    return d, pol, sw, derivacao.avaliar(d, sw, pol, fx.ASSINATURA)


def _render(n: int, d=None):
    d, pol, sw, av = _avaliar(n, d)
    assert av.pronto, (av.faltando, av.bloqueios)
    return documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)


def _clausulas(paragrafos):
    return [p for p in paragrafos if p.startswith("CLÁUSULA ")]


class TestSwitchesPorVariante:
    ESPERADO = {
        1: ("compra_venda", dict(tem_financiamento=True, tem_intermediaria=True, tem_intermediacao=True,
                                 tem_itens_integrantes=True, tem_fgts=False, tem_saldo_devedor=False,
                                 tem_permuta=False, ad_corpus=False, a_vista=False)),
        2: ("compra_venda", dict(tem_financiamento=True, tem_fgts=True, tem_saldo_devedor=True,
                                 tem_intermediacao=True, tem_permuta=False)),
        3: ("compra_venda", dict(tem_itens_integrantes=False, ad_corpus=True, tem_intermediacao=True)),
        4: ("compra_venda_a_vista", dict(a_vista=True, tem_saldo_devedor=True, tem_intermediacao=True,
                                         tem_financiamento=False)),
        5: ("compra_venda_permuta", dict(tem_permuta=True, tem_financiamento=True, tem_parcelas_diretas=True,
                                         tem_confissao=True, tem_saldo_devedor=True, tem_intermediacao=False)),
        6: ("compra_venda_permuta", dict(tem_permuta=True, tem_intermediaria=True, tem_declaracao_partes=True,
                                         ad_corpus=True, tem_intermediacao=False, tem_confissao=False)),
    }

    @pytest.mark.parametrize("n", range(1, 7))
    def test_variant(self, n):
        d, _pol, sw, av = _avaliar(n)
        modelo, switches = self.ESPERADO[n]
        assert derivacao.modelo_derivado(sw) == modelo
        assert {k: sw[k] for k in switches} == switches
        assert av.pronto, (av.faltando, av.bloqueios)

    @pytest.mark.parametrize("n", range(1, 7))
    def test_every_variant_renders_14_consecutive_clauses_with_a_clean_lint(self, n):
        r = _render(n)
        ordinais = [c.split(" – ")[0].split(" - ")[0] for c in _clausulas(r.paragrafos)]
        assert len(ordinais) == 14  # 13 fixed + exactly one conditional in each sample variant
        assert ordinais[0] == "CLÁUSULA PRIMEIRA" and ordinais[-1] == "CLÁUSULA DÉCIMA QUARTA"
        assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []


class TestNumeracaoAoLigarEDesligarClausulas:
    def _resolutiva(self, paragrafos):
        return next(p for p in paragrafos if p.startswith("A presente transação é realizada"))

    def test_confissao_on_shifts_every_later_number_and_reference(self):
        v1, v5 = _render(1), _render(5)
        assert "na Cláusula Sétima deste" in self._resolutiva(v1.paragrafos)
        assert "na Cláusula Oitava deste" in self._resolutiva(v5.paragrafos)
        assert v5.clausulas["confissao"] == 3 and v5.clausulas["certidoes"] == 4
        assert "confissao" not in v1.clausulas

    def test_declaracao_on_and_intermediacao_off(self):
        v6 = _render(6)
        assert v6.clausulas["declaracao_partes"] == 9
        assert "intermediacao" not in v6.clausulas
        assert v6.clausulas["foro"] == 14

    def test_a_lone_paragraph_is_unico_and_disappears_with_its_switch(self):
        v1, v3 = _render(1), _render(3)
        objeto = lambda ps: ps[ps.index("CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO") + 1 : ps.index("CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO")]
        assert [p for p in objeto(v1.paragrafos) if p.startswith("Parágrafo")][0].startswith("Parágrafo Único:")
        assert not [p for p in objeto(v3.paragrafos) if p.startswith("Parágrafo")]

    def test_paragraphs_restart_per_clause(self):
        r = _render(5)
        preco = r.paragrafos.index("CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO")
        seguinte = next(i for i, p in enumerate(r.paragrafos) if i > preco and p.startswith("CLÁUSULA "))
        rotulos = [p.split(":")[0] for p in r.paragrafos[preco:seguinte] if p.startswith("Parágrafo")]
        assert rotulos == ["Parágrafo Primeiro", "Parágrafo Segundo"]

    def test_pendencia_letters_are_gap_free(self):
        r = _render(2)
        letras = [p.split("-)")[0] for p in r.paragrafos if re.match(r"^[a-z]{1,2}-\) ", p)]
        assert letras == [chr(ord("a") + i) for i in range(len(letras))]


class TestTextoRenderizado:
    def test_every_amount_round_trips_through_its_extenso(self):
        texto = "\n".join(_render(5).paragrafos)
        valores = re.findall(r"R\$ ([\d.]+,\d{2}) \(([^)]*)\)", texto)
        assert len(valores) >= 8
        for digitos, extenso in valores:
            assert reais_por_extenso(parse_brl(digitos)) == extenso

    def test_matricula_literal_text_is_byte_identical_in_document_xml(self):
        r = _render(1)
        xml = documento.document_xml(r.docx)
        for linha in fx.MATRICULA_TEXTO.split("\n"):
            assert linha in xml
        assert any(fx.MATRICULA_TEXTO in p for p in r.paragrafos)

    def test_descricao_imovel_block_narrows_the_imovel_clause_when_present(self):
        """Migration 136: when the extraction carries a `descricao_imovel`
        typed block, the IMÓVEL: clause quotes JUST that block — never the
        whole selection (`fx.MATRICULA_TEXTO`, which in a real de-furnitured
        abertura would still end in `PROPRIETÁRIOS: …`, naming the wrong
        parties on a resold property). `d.matricula.texto` is used NOWHERE
        else in `contexto.py`, so its own second line (a citation of act
        R.1, never part of the property description) is a clean marker for
        "the whole selection leaked in" that the narrowed clause must not
        contain."""
        narrow = (
            "O apartamento nº 11 do Edifício Exemplo, situado na Rua Fictícia, "
            "nº 100, Bairro Modelo, com área privativa de 80,00m2."
        )
        r1_citation = "R.1/12.345 - Prot. 1.000 - Por escritura pública, o imóvel foi transmitido a FULANO DE TAL."
        assert fx.MATRICULA_TEXTO == f"MATRÍCULA Nº 12.345 - IMÓVEL: {narrow}\n{r1_citation}"
        d = fx.variante(1)
        d = replace(d, matricula=replace(d.matricula, descricao_imovel_texto=narrow))

        r = _render(1, d)
        xml = documento.document_xml(r.docx)

        assert narrow in xml
        assert r1_citation not in xml

    def test_missing_descricao_imovel_block_falls_back_and_logs(self, caplog):
        """The pre-136 fixture shape (`descricao_imovel_texto=None`, every
        existing variant) must render EXACTLY as before (same shape as
        `test_matricula_literal_text_is_byte_identical_in_document_xml`) —
        and the fallback must be visible, not silent
        (`KB § 01-PHILOSOPHY.md`)."""
        d = fx.variante(1)
        assert d.matricula.descricao_imovel_texto is None

        with caplog.at_level("WARNING"):
            r = _render(1, d)

        xml = documento.document_xml(r.docx)
        for linha in fx.MATRICULA_TEXTO.split("\n"):
            assert linha in xml
        assert any(fx.MATRICULA_TEXTO in p for p in r.paragrafos)
        assert any(
            "descricao_imovel" in rec.message and "seleção inteira" in rec.message
            for rec in caplog.records
        )

    def test_multa_rescisoria_is_the_sinal(self):
        texto = "\n".join(_render(1).paragrafos)
        assert "multa rescisória no valor de R$ 50.000,00 (cinquenta mil reais)" in texto

    def test_mixed_gender_sellers_take_the_masculine_plural(self):
        d = fx.base_v1()
        segunda = replace(fx.pessoa("v2", "vendedor", "proprietario", "Cicrana Amostra", "Feminino",
                                    "111222333", "55.555.555-5"))
        d = replace(d, vendedores=[d.vendedores[0], segunda])
        texto = "\n".join(_render(1, d).paragrafos)
        assert '"VENDEDORES"' in texto and "Os VENDEDORES" in texto
        assert lado(["f"], "vendedor").NOME == "VENDEDORA"
        assert "VENDEDORA" not in texto


class TestTituloAquisitivoFraseComposta:
    """[titulo-aquisitivo-adquirido-quebra-frase] The confirmed título
    aquisitivo phrase is injected into the frame `A VENDEDORA, {frase},
    tornou-se legítima proprietária` — the composed SENTENCE must read as
    correct Portuguese, not just the standalone helper. Found live on the
    RODRIGO MORASCHI ENRIQUEZ contract, 2026-09-22."""

    def test_a_sugestao_nao_confirmada_pelo_operador_compoe_frase_correta(self):
        """The UI's "Usar esta frase" suggestion, taken verbatim (never
        hand-edited), must not break the frame it gets injected into."""
        sugestao = frase_titulo_aquisitivo(
            Instrumento(
                tipo="Escritura",
                data=date(2023, 2, 28),
                tabelionato="1º Tabelião de Notas de Guarujá",
            ),
            kind="R",
            numero=4,
        )
        assert sugestao == (
            "por Escritura lavrada em 28/02/2023 no 1º Tabelião de Notas de "
            "Guarujá, registrada sob o R-4"
        )

        vendedora = fx.pessoa(
            "v1", "vendedor", "proprietario", "Fulana de Tal", "Feminino",
            "123456789", "11.111.111-1",
        )
        d = fx.variante(1)
        d = replace(
            d,
            vendedores=[vendedora],
            imovel=replace(d.imovel, titulo_aquisitivo_texto=sugestao),
        )
        texto = "\n".join(_render(1, d).paragrafos)

        assert (
            "A VENDEDORA, por Escritura lavrada em 28/02/2023 no 1º Tabelião "
            "de Notas de Guarujá, registrada sob o R-4, tornou-se legítima "
            "proprietária do imóvel descrito a seguir:"
        ) in texto
        assert "adquirido" not in texto.lower()
        assert "adquirida" not in texto.lower()

    def test_um_texto_confirmado_antigo_com_o_defeito_e_higienizado_na_renderizacao(self):
        """A `titulo_aquisitivo_texto` CONFIRMED before this fix shipped
        keeps the old broken shape in the database (migration data is never
        rewritten) — the render frame strips the leading "adquirido"/
        "adquirida" defensively rather than trusting every row was
        re-confirmed."""
        vendedora = fx.pessoa(
            "v1", "vendedor", "proprietario", "Fulana de Tal", "Feminino",
            "123456789", "11.111.111-1",
        )
        d = fx.variante(1)
        d = replace(
            d,
            vendedores=[vendedora],
            imovel=replace(
                d.imovel,
                titulo_aquisitivo_texto="adquirido por escritura lavrada em 28/02/2023, registrada sob o R-4",
            ),
        )
        texto = "\n".join(_render(1, d).paragrafos)
        assert "A VENDEDORA, por escritura lavrada em 28/02/2023" in texto
        assert "A VENDEDORA, adquirido" not in texto


class TestPronomeComprarLheLhes:
    """[pronome-lhe-lhes-lado-errado] "comprar-lhe(s)" agrees with `C`
    (comprador), never `V` — reference contract 08 (RESIDENCIAL EUROVILLE)
    reads "estes a comprar-lhes" with ONE seller and TWO buyers, proving the
    clitic tracks the buyer side."""

    def test_um_vendedor_e_um_comprador_usa_lhe(self):
        texto = "\n".join(_render(1).paragrafos)
        assert "a comprar-lhe o referido imóvel" in texto
        assert "a comprar-lhes o referido imóvel" not in texto

    def test_um_vendedor_e_dois_compradores_usa_lhes(self):
        """The exact reference shape: a SINGLE seller, TWO buyers → "lhes"."""
        d = fx.variante(1)
        segundo_comprador = fx.pessoa(
            "c2", "comprador", "comprador", "Segundo Comprador Exemplo",
            "Masculino", "555666777", "77.777.777-7",
        )
        d = replace(d, compradores=[d.compradores[0], segundo_comprador])
        texto = "\n".join(_render(1, d).paragrafos)
        assert "a comprar-lhes o referido imóvel" in texto
        assert "a comprar-lhe o referido imóvel" not in texto

    def test_dois_vendedores_e_um_comprador_ainda_usa_lhe(self):
        """TWO sellers must NOT flip this to "lhes" — the seller side no
        longer governs this clitic at all."""
        d = fx.variante(1)
        segunda_vendedora = fx.pessoa(
            "v2", "vendedor", "proprietario", "Segunda Vendedora Exemplo",
            "Feminino", "888999000", "88.888.888-8",
        )
        d = replace(d, vendedores=[d.vendedores[0], segunda_vendedora])
        texto = "\n".join(_render(1, d).paragrafos)
        assert "a comprar-lhe o referido imóvel" in texto
        assert "a comprar-lhes o referido imóvel" not in texto


class TestGate:
    def test_a_deal_with_no_termos_filled_refuses_naming_every_clause(self):
        # Migration 114 gave every one of these a home, so what is missing is
        # an un-filled FORM — which is why each names the screen that fixes it.
        _d, _pol, _sw, av = _avaliar(1, fx.sem_termos(fx.variante(1)))
        assert not av.pronto
        assert {f["campo"] for f in av.faltando} == {
            "negociacao.posse_prazo_dias",
            "negociacao.posse_marco",
            "negociacao.corretagem_contratantes",
        }
        assert all(f["onde"] in {"partes", "certidoes", "imovel", "matricula", "negociacao",
                                 "financiamento", "imobiliaria", "contrato"} for f in av.faltando)

    def test_every_missing_field_carries_a_destino_the_ui_can_link_to(self):
        _d, _pol, _sw, av = _avaliar(1, fx.sem_termos(fx.variante(1)))
        for f in av.faltando:
            assert set(f) == {"campo", "rotulo", "onde", "parte_id", "destino", "sugestoes"}
            destino = f["destino"]
            assert set(destino) == {"tela", "rota", "ancora", "ids"}
            assert destino["rota"].startswith("/")
            assert destino["ids"]["contrato_id"] == "contrato-1"
        # The termos clauses are all fixed on the card's Negociação subpage.
        destino = av.faltando[0]["destino"]
        assert destino["tela"] == "card_negociacao"
        assert (destino["rota"], destino["ancora"]) == ("/clientes", "negociacao")
        assert destino["ids"]["cliente_id"] == "c1"

    def test_a_missing_identity_field_suggests_the_documents_that_carry_it(self):
        d = fx.variante(1)
        sem_nome = replace(d.vendedores[0], faltando_qualificacao=["nome_oficial"])
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[sem_nome]))
        item = next(f for f in av.faltando if f["campo"] == "qualificacao.nome_oficial")
        tipos = {s["tipo_documento"] for s in item["sugestoes"]}
        assert tipos == {"rg", "cpf", "cnh", "certidao_casamento", "certidao_nascimento"}
        assert all(s["destino"] == item["destino"] for s in item["sugestoes"])
        assert all(set(s) == {"tipo_documento", "rotulo", "destino"} for s in item["sugestoes"])

    def test_a_manual_only_field_has_no_sugestoes(self):
        _d, _pol, _sw, av = _avaliar(1, fx.sem_termos(fx.variante(1)))
        item = next(f for f in av.faltando if f["campo"] == "negociacao.corretagem_contratantes")
        assert item["sugestoes"] == []

    def test_a_party_destino_points_at_that_partys_own_side_and_id(self):
        d = fx.variante(1)
        sem_genero = replace(d.vendedores[0], genero=None)
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[sem_genero]))
        item = next(f for f in av.faltando if f["campo"] == "qualificacao.genero")
        assert item["destino"]["ancora"] == "vendedor"
        assert item["destino"]["ids"]["parte_id"] == "parte-v1"

    def test_an_imovel_destino_deep_links_to_that_imovel(self):
        d = fx.variante(1)
        _d, _pol, _sw, av = _avaliar(1, replace(d, imovel=replace(d.imovel, situacao_onus=None)))
        item = next(f for f in av.faltando if f["campo"] == "imovel.situacao_onus")
        assert item["destino"]["rota"] == "/imoveis/EX001"
        assert item["destino"]["ids"]["imovel_codigo"] == "EX001"

    def test_soma_das_parcelas_diferente_do_preco_blocks(self):
        d = replace(fx.variante(1), valor_negociado=Decimal("500000.01"))
        _d, _pol, _sw, av = _avaliar(1, d)
        assert [b["codigo"] for b in av.bloqueios] == ["SOMA_PARCELAS_DIFERENTE_DO_PRECO"]
        assert not av.pronto

    def test_matricula_text_with_raw_markup_blocks(self):
        """Migration 135: a pre-retention transcription (or a malformed
        vision reply `parse_markup` had to keep literal) must never reach a
        signed deed with `**`/`<u>` still in it — the highest-value refusal
        this slice adds."""
        d = fx.variante(1)
        d = replace(
            d,
            matricula=replace(
                d.matricula, texto=fx.MATRICULA_TEXTO + " **negrito sem fechar"
            ),
        )
        _d, _pol, _sw, av = _avaliar(1, d)
        assert "MATRICULA_COM_MARCACAO_BRUTA" in _codigos(av.bloqueios)
        assert not av.pronto

    def test_clean_matricula_text_does_not_block(self):
        _d, _pol, _sw, av = _avaliar(1)
        assert "MATRICULA_COM_MARCACAO_BRUTA" not in _codigos(av.bloqueios)

    def test_permuta_matricula_text_with_raw_markup_blocks(self):
        d = fx.variante(5)  # V5: financiamento + permuta
        alvo = d.permuta_imoveis[0]
        d = replace(
            d,
            permuta_imoveis=[
                replace(alvo, descricao_matricula=(alvo.descricao_matricula or "") + " <u>sem fechar")
            ],
        )
        _d, _pol, _sw, av = _avaliar(5, d)
        assert "MATRICULA_COM_MARCACAO_BRUTA" in _codigos(av.bloqueios)

    def test_rg_igual_ao_cpf_warns_but_does_not_block(self):
        """🔴 [2026-09-22] Warning, not block — the Carteira de Identidade
        Nacional (CIN) legitimately uses the CPF number as the identity
        number, so this must never stop the contract from generating."""
        d = fx.variante(1)
        v = replace(d.vendedores[0], rg=d.vendedores[0].cpf)
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert "RG_IGUAL_CPF" in _codigos(av.avisos)
        assert "RG_IGUAL_CPF" not in _codigos(av.bloqueios)
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_missing_profissao_warns_but_does_not_block(self):
        """🔴 [2026-09-22] `profissao` is not a hard gate: contract 08 (the
        office's own reference) qualifies REGINA MARIA PELOSI with no
        profession at all."""
        d = fx.variante(1)
        v = replace(d.vendedores[0], faltando_qualificacao=["profissao"])
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert "PARTE_SEM_PROFISSAO" in _codigos(av.avisos)
        assert not any(f["campo"] == "qualificacao.profissao" for f in av.faltando)
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_a_missing_certidao_is_named_per_parte(self):
        d = fx.variante(1)
        v = replace(d.vendedores[0], certidoes=[c for c in d.vendedores[0].certidoes if c.tipo != "serasa"])
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert [(f["campo"], f["parte_id"], f["onde"]) for f in av.faltando] == [
            ("certidao.serasa", "parte-v1", "certidoes")
        ]

    def test_a_manually_registered_certidao_closes_the_gap_even_while_status_stays_pendente(self):
        """The manual-registration path (`POST /consultas/manual` + a
        human's `PATCH /resultados/{id}` confirm) never advances
        `certidao_resultados.status` past `'pendente'` — no automation ever
        runs for it. This proves the gate does not care: `carregador.
        _certidao` reads only the structured fields (`numero`/`emitida_em`/
        `validade_ate`/`resultado`), never `status` and never `resultado_
        origem`, so a resultado a human filled by hand satisfies the gate
        exactly like an automated `status='sucesso'` one would."""
        d = fx.variante(1)
        registrado_a_mao = {
            "tipo": "serasa",
            "status": "pendente",  # never advanced — no automation ran for it
            "resultado_origem": "manual",
            "resultado": "negativa",
            "numero": "MANUAL-0001",
            "emitida_em": "2026-09-01",
            "validade_ate": "2026-12-01",
        }
        v = replace(
            d.vendedores[0],
            certidoes=[
                c for c in d.vendedores[0].certidoes if c.tipo != "serasa"
            ] + [carregador._certidao(registrado_a_mao)],
        )
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert ("certidao.serasa", "parte-v1", "certidoes") not in [
            (f["campo"], f["parte_id"], f["onde"]) for f in av.faltando
        ]

    def test_a_married_seller_without_the_spouse_on_the_same_side_blocks(self):
        d = fx.variante(1)
        v = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="c1")
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[v]))
        assert "CONJUGE_FORA_DO_LADO" in [b["codigo"] for b in av.bloqueios]

    def test_the_titular_is_certified_like_any_other_party(self):
        # Migration 116 reaches a titular's certidões (`certidoes_por_cliente`),
        # so having no parte row is no longer an unreachable-data refusal: an
        # empty list is "none issued yet" and each tipo is named.
        d = fx.variante(5)
        titular = replace(d.compradores[0], parte_id=None, certidoes=[])
        _d, _pol, _sw, av = _avaliar(5, replace(d, compradores=[titular]))
        campos = {f["campo"] for f in av.faltando}
        assert campos == {f"certidao.{tipo}" for tipo in derivacao.tipos_exigidos("cpf")}
        assert all(f["onde"] == "certidoes" for f in av.faltando)

    @pytest.mark.parametrize("n", range(1, 7))
    def test_no_pending_policy_question_aviso_survives_the_answers(self, n):
        _d, _pol, _sw, av = _avaliar(n)
        codigos = {a["codigo"] for a in av.avisos}
        assert not codigos & {
            "ENCARGO_RESCISAO_NAO_DEFINIDO", "MULTA_DIARIA_POSSE_OMITIDA", "CORRETAGEM_RESCISAO_PELA_COMISSAO",
            "LEI_6515_NAO_CITADA", "TJSP_API_COMO_ESAJ", "CERTIDOES_SEM_VALIDADE",
        }
        assert not any("[Q" in a["mensagem"] for a in av.avisos + av.bloqueios)


def _codigos(itens):
    return [i["codigo"] for i in itens]


def _campos(av):
    return [(f["campo"], f["parte_id"]) for f in av.faltando]


def _texto(n: int, d=None) -> str:
    return "\n".join(_render(n, d).paragrafos)


class TestQ2Lei6515:
    def _casal(self, data_v1, data_v2="igual", estado_civil="casado"):
        d = fx.variante(1)
        data_v2 = data_v1 if data_v2 == "igual" else data_v2
        v1 = replace(d.vendedores[0], estado_civil=estado_civil, regime_bens="comunhao_parcial",
                     conjuge_cliente_id="v2", data_casamento=data_v1)
        v2 = replace(fx.pessoa("v2", "vendedor", "conjuge", "Cicrana Amostra", "Feminino", "111222333", "55.555.555-5"),
                     estado_civil=estado_civil, regime_bens="comunhao_parcial", conjuge_cliente_id="v1",
                     data_casamento=data_v2)
        return replace(d, vendedores=[v1, v2])

    @pytest.mark.parametrize("data, frase", [
        (date(1977, 12, 26), ", na vigência da Lei 6.515/77"),
        (date(1977, 12, 25), ", anterior à vigência da Lei 6.515/77"),
    ])
    def test_the_marriage_date_picks_the_wording(self, data, frase):
        texto = _texto(1, self._casal(data))
        assert f"casados no regime da comunhão parcial de bens{frase}" in texto

    def test_a_casado_without_the_marriage_date_is_missing_it(self):
        _d, _pol, _sw, av = _avaliar(1, self._casal(None))
        assert ("qualificacao.data_casamento", "parte-v1") in _campos(av)

    def test_spouses_with_different_marriage_dates_block(self):
        _d, _pol, _sw, av = _avaliar(1, self._casal(date(1990, 5, 5), date(1990, 5, 6)))
        assert "DATA_CASAMENTO_DIVERGENTE" in _codigos(av.bloqueios)

    def test_uniao_estavel_never_cites_the_law_nor_needs_the_date(self):
        d = self._casal(None, estado_civil="uniao_estavel")
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "6.515" not in _texto(1, d)


class TestQ4Q3Rescisao:
    def test_the_party_at_fault_pays_the_sinal_and_every_proven_cost(self):
        assert (
            "multa rescisória no valor de R$ 50.000,00 (cinquenta mil reais), a ser paga pela parte que der causa "
            "à rescisão, que arcará ainda com todos os custos comprovadamente gerados durante o processo de compra "
            "e venda até a data da rescisão."
        ) in _texto(1)


class TestQ6Fgts:
    def test_fgts_is_worded_inside_the_financiamento_parcela(self):
        r = _render(2)
        financiamento = next(p for p in r.paragrafos if p.startswith("Parcela 03:"))
        assert "através do uso de FGTS e financiamento imobiliário" in financiamento
        assert not any(p.startswith("Parcela 04:") for p in r.paragrafos)

    def test_a_separate_fgts_parcela_blocks(self):
        d = fx.variante(2)
        parcelas = [d.parcelas[0], d.parcelas[1], replace(d.parcelas[2], valor=Decimal("300000.00")),
                    fx.parcela("p4", "fgts", "100000.00", 4, evento="na liberação do FGTS")]
        _d, _pol, _sw, av = _avaliar(2, replace(d, parcelas=parcelas))
        assert _codigos(av.bloqueios) == ["PARCELA_FGTS_SEPARADA"]


class TestQ8Tjsp:
    def test_the_system_emitted_tjsp_stands_in_for_esaj_silently(self):
        d = fx.variante(1)
        v = d.vendedores[0]
        certs = [replace(c, tipo="tjsp") if c.tipo == "tjsp_esaj" else c for c in v.certidoes]
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[replace(v, certidoes=certs)]))
        assert av.pronto, (av.faltando, av.bloqueios)


CNPJ = "11444777000161"


class TestQ9CertidoesDeEmpresa:
    def _com_empresa(self, situacao, data_situacao=None, sem_tipo=None):
        d = fx.variante(1)
        v = d.vendedores[0]
        pj = [c for c in fx.certidoes_pj(CNPJ, "Empresa Amostra Ltda", situacao, data_situacao) if c.tipo != sem_tipo]
        return replace(d, vendedores=[replace(v, certidoes=v.certidoes + pj)])

    @pytest.mark.parametrize("situacao", ["ativa", "inapta"])
    def test_an_active_or_inapta_company_is_required_and_rendered(self, situacao):
        _d, _pol, _sw, av = _avaliar(1, self._com_empresa(situacao, sem_tipo="cnd_federal"))
        assert _campos(av) == [("certidao.cnd_federal", "parte-v1")]
        texto = _texto(1, self._com_empresa(situacao))
        assert "- Em nome de EMPRESA AMOSTRA LTDA\n" in texto + "\n"
        assert "Baixada" not in texto

    @pytest.mark.parametrize("situacao", ["suspensa", "nula"])
    def test_a_suspensa_or_nula_company_is_omitted(self, situacao):
        d = self._com_empresa(situacao, sem_tipo="cnd_federal")
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "EMPRESA AMOSTRA" not in _texto(1, d)

    def test_baixada_exactly_five_years_before_signing_is_omitted(self):
        d = self._com_empresa("baixada", date(2021, 9, 14), sem_tipo="cnd_federal")
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "EMPRESA AMOSTRA" not in _texto(1, d)

    def test_baixada_less_than_five_years_before_signing_is_required_with_the_suffix(self):
        _d, _pol, _sw, av = _avaliar(1, self._com_empresa("baixada", date(2021, 9, 15), sem_tipo="cnd_federal"))
        assert _campos(av) == [("certidao.cnd_federal", "parte-v1")]
        assert "- Em nome de EMPRESA AMOSTRA LTDA - Baixada" in _texto(1, self._com_empresa("baixada", date(2021, 9, 15)))

    def test_unknown_situacao_is_missing(self):
        _d, _pol, _sw, av = _avaliar(1, self._com_empresa(None))
        assert _campos(av) == [(f"certidoes.pj.{CNPJ}.situacao", "parte-v1")]

    def test_baixada_without_its_date_is_missing(self):
        _d, _pol, _sw, av = _avaliar(1, self._com_empresa("baixada"))
        assert _campos(av) == [(f"certidoes.pj.{CNPJ}.data_situacao", "parte-v1")]


class TestQ9AntigoProprietario:
    def _transferido_em(self, quando, *antigos):
        d = fx.variante(1)
        return replace(d, imovel=replace(d.imovel, ultima_transferencia_em=quando),
                       vendedores=d.vendedores + list(antigos))

    def test_unknown_last_transfer_is_missing(self):
        _d, _pol, _sw, av = _avaliar(1, self._transferido_em(None))
        assert _campos(av) == [("matricula.ultima_transferencia", None)]

    def test_unknown_last_transfer_points_at_the_imovel_page(self):
        """[migration 152] `onde` moved from `matricula` to `imovel` — the
        manual override lives on the property page, not the matrículas
        screen, and the rótulo now asks for the wider "transferência de
        propriedade", not only a "compra e venda"."""
        _d, _pol, _sw, av = _avaliar(1, self._transferido_em(None))
        item = av.faltando[0]
        assert item["onde"] == "imovel"
        assert item["destino"]["rota"].startswith("/imoveis/")
        assert "transferência de propriedade" in item["rotulo"]

    def test_a_confirmed_absence_of_any_transfer_is_not_missing(self):
        """[migration 152] "Não consta transferência registrada" is an
        ANSWER — `ultima_transferencia_sem_registro_confirmado=True` clears
        the `faltando` entirely rather than leaving it unknown."""
        d = fx.variante(1)
        d = replace(
            d, imovel=replace(d.imovel, ultima_transferencia_sem_registro_confirmado=True)
        )
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert not any(f["campo"] == "matricula.ultima_transferencia" for f in av.faltando)
        assert not any(f["campo"] == "partes.antigo_proprietario" for f in av.faltando)

    def test_a_transfer_less_than_five_years_ago_requires_a_previous_owner(self):
        _d, _pol, _sw, av = _avaliar(1, self._transferido_em(date(2021, 9, 15)))
        assert _campos(av) == [("partes.antigo_proprietario", None)]

    def test_a_transfer_exactly_five_years_ago_does_not(self):
        antiga = fx.antiga_proprietaria()
        d = self._transferido_em(date(2021, 9, 14), antiga)
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "ANTIGO_PROPRIETARIO_DISPENSADO" in _codigos(av.avisos)
        assert "ANTIGA DONA" not in _texto(1, d)

    def test_the_previous_owner_needs_full_certidoes(self):
        antiga = fx.antiga_proprietaria()
        antiga = replace(antiga, certidoes=[c for c in antiga.certidoes if c.tipo != "serasa"])
        _d, _pol, _sw, av = _avaliar(1, self._transferido_em(date(2021, 9, 15), antiga))
        assert _campos(av) == [("certidao.serasa", "parte-a1")]

    def test_the_previous_owner_presents_certidoes_with_agreement(self):
        texto = _texto(1, self._transferido_em(date(2021, 9, 15), fx.antiga_proprietaria()))
        assert "O VENDEDOR e a antiga proprietária apresentam neste momento as certidões em seus nomes" in texto
        assert "- Em nome de ANTIGA DONA EXEMPLO" in texto
        assert "PARTE_NAO_SIGNATARIA" not in _codigos(_avaliar(1, self._transferido_em(date(2021, 9, 15), fx.antiga_proprietaria()))[3].avisos)

    def test_several_previous_owners_take_the_plural(self):
        dois = replace(fx.pessoa("a2", "vendedor", "antigo_proprietario", "Antigo Dono Amostra", "Masculino",
                                 "333444555", "77.777.777-7"))
        texto = _texto(1, self._transferido_em(date(2021, 9, 15), fx.antiga_proprietaria(), dois))
        assert "O VENDEDOR e os antigos proprietários apresentam" in texto


class TestQ10IdadeDasCertidoes:
    def _emitidas_ha(self, dias):
        d = fx.variante(1)
        v = d.vendedores[0]
        return replace(d, vendedores=[replace(v, certidoes=fx.certidoes_completas(fx.dias_antes(dias)))])

    def test_29_days_old_is_accepted(self):
        _d, _pol, _sw, av = _avaliar(1, self._emitidas_ha(29))
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_30_days_old_blocks(self):
        _d, _pol, _sw, av = _avaliar(1, self._emitidas_ha(30))
        assert set(_codigos(av.bloqueios)) == {"CERTIDAO_EMISSAO_ANTIGA"}

    def test_a_stated_validity_is_still_checked(self):
        d = fx.variante(1)
        v = d.vendedores[0]
        certs = [replace(c, validade_ate=fx.dias_antes(1)) if c.tipo == "cnd_federal" else c for c in v.certidoes]
        _d, _pol, _sw, av = _avaliar(1, replace(d, vendedores=[replace(v, certidoes=certs)]))
        assert _codigos(av.bloqueios) == ["CERTIDAO_VENCIDA"]


class TestQ11PendenciasEEstadoCivil:
    def _estado_civil(self, emitida):
        d = fx.variante(1)
        return replace(d, vendedores=[replace(d.vendedores[0], certidao_estado_civil_emitida_em=emitida)])

    def test_89_days_old_is_accepted(self):
        _d, _pol, _sw, av = _avaliar(1, self._estado_civil(fx.dias_antes(89)))
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_90_days_old_blocks(self):
        _d, _pol, _sw, av = _avaliar(1, self._estado_civil(fx.dias_antes(90)))
        assert _codigos(av.bloqueios) == ["CERTIDAO_ESTADO_CIVIL_ANTIGA"]

    def test_missing_emission_date_is_missing(self):
        _d, _pol, _sw, av = _avaliar(1, self._estado_civil(None))
        assert _campos(av) == [("qualificacao.certidao_estado_civil_emissao", "parte-v1")]

    def test_the_pendencia_text_says_90_days(self):
        assert "Comprovante de estado civil atualizado, emitido há no máximo 90 dias" in _texto(1)

    @pytest.mark.parametrize("contrato, escritorio, esperado", [(None, None, 10), (None, 12, 12), (15, 12, 15)])
    def test_prazo_default_office_default_and_contract_override(self, contrato, escritorio, esperado):
        d = fx.variante(1)
        d = replace(d, prazo_pendencias_dias=contrato,
                    imobiliaria=replace(d.imobiliaria, prazo_pendencias_padrao_dias=escritorio))
        assert f"no prazo de {dias_por_extenso(esperado)}, a contar da assinatura" in _texto(1, d)


class TestProcessoLegado:
    """Migration 151 / owner directive 2026-09-22: `processo_legado=True`
    dispenses the certidão TIME rules — a warning instead of a block —
    for a deal that started before the platform. Never touches
    `CERTIDAO_EMITIDA_APOS_ASSINATURA`, a data error, not an age rule."""

    def _emitidas_ha(self, dias, *, processo_legado=True):
        d = fx.variante(1)
        v = d.vendedores[0]
        return replace(
            d,
            processo_legado=processo_legado,
            vendedores=[replace(v, certidoes=fx.certidoes_completas(fx.dias_antes(dias)))],
        )

    def test_a_30_day_old_certidao_warns_instead_of_blocking(self):
        _d, _pol, _sw, av = _avaliar(1, self._emitidas_ha(30))
        assert _codigos(av.bloqueios) == []
        assert "CERTIDAO_EMISSAO_ANTIGA" in _codigos(av.avisos)
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_the_aviso_names_the_dispensation(self):
        _d, _pol, _sw, av = _avaliar(1, self._emitidas_ha(30))
        aviso = next(a for a in av.avisos if a["codigo"] == "CERTIDAO_EMISSAO_ANTIGA")
        assert aviso["mensagem"].endswith("(processo anterior à plataforma)")

    def test_a_stated_validity_warns_instead_of_blocking(self):
        d = fx.variante(1)
        v = d.vendedores[0]
        certs = [replace(c, validade_ate=fx.dias_antes(1)) if c.tipo == "cnd_federal" else c for c in v.certidoes]
        _d, _pol, _sw, av = _avaliar(
            1, replace(d, processo_legado=True, vendedores=[replace(v, certidoes=certs)])
        )
        assert _codigos(av.bloqueios) == []
        assert "CERTIDAO_VENCIDA" in _codigos(av.avisos)

    def test_a_90_day_old_estado_civil_certidao_warns_instead_of_blocking(self):
        d = fx.variante(1)
        d = replace(
            d,
            processo_legado=True,
            vendedores=[replace(d.vendedores[0], certidao_estado_civil_emitida_em=fx.dias_antes(90))],
        )
        _d, _pol, _sw, av = _avaliar(1, d)
        assert _codigos(av.bloqueios) == []
        assert "CERTIDAO_ESTADO_CIVIL_ANTIGA" in _codigos(av.avisos)
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_certidao_emitida_apos_assinatura_still_blocks(self):
        """A data error, not an age rule — the flag never dispenses it."""
        _d, _pol, _sw, av = _avaliar(1, self._emitidas_ha(-1))  # emitted AFTER assinatura
        assert "CERTIDAO_EMITIDA_APOS_ASSINATURA" in _codigos(av.bloqueios)
        assert not av.pronto

    def test_unflagged_contracts_are_unaffected(self):
        """Regression: the default (`processo_legado=False`) keeps blocking
        — the dispensation is opt-in per contract, never ambient."""
        _d, _pol, _sw, av = _avaliar(1, self._emitidas_ha(30, processo_legado=False))
        assert set(_codigos(av.bloqueios)) == {"CERTIDAO_EMISSAO_ANTIGA"}
        assert not av.pronto

    def test_the_previous_owner_requirement_warns_instead_of_blocking(self):
        """[Owner directive, 2026-09-22] The strict [Q9] rules apply to sales
        that run through the platform; a legacy deal's recent transfer still
        surfaces (`av.avisa`), but never blocks/asks for the previous
        owner's name/gênero/certidões — the human-made reference contract
        for a 2023 legacy acquisition (contract 08) qualifies only the
        seller, with no previous-owner section at all."""
        d = fx.variante(1)
        d = replace(
            d,
            processo_legado=True,
            imovel=replace(d.imovel, ultima_transferencia_em=date(2021, 9, 15)),
        )
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert not any(f["campo"] == "partes.antigo_proprietario" for f in av.faltando)
        assert "ANTIGO_PROPRIETARIO_PROCESSO_LEGADO" in _codigos(av.avisos)

    def test_a_legacy_contract_with_a_recent_transfer_RENDERS(self):
        """🔴 The 500 this class caused, live on prod 2026-09-22.

        Every test above stops at `avaliar()`. The gate said `pronto`, the
        operator pressed "Gerar versão", and POST .../gerar answered 500:
        `IndexError: list index out of range` in
        `frases.antigos_proprietarios_texto`. `montar_contexto` asked for a
        phrase naming the previous owners because the transfer IS recent,
        while the legacy flag had (correctly) skipped ever collecting them —
        gate and template disagreed about who exists. A gate verdict of
        `pronto` is only worth what the RENDER does with it, so this asserts
        the document, not the verdict."""
        d = fx.variante(1)
        d = replace(
            d,
            processo_legado=True,
            imovel=replace(d.imovel, ultima_transferencia_em=date(2021, 9, 15)),
        )
        texto = _texto(1, d)
        assert "antigo proprietário" not in texto
        assert "antiga proprietária" not in texto
        assert "antigos proprietários" not in texto

    def test_the_phrase_refuses_an_empty_group(self):
        """The helper itself must not invent a party for nobody — a silent
        default would put a person in the contract who is not in the deal."""
        with pytest.raises(ValueError):
            frases.antigos_proprietarios_texto([])

    def test_a_non_legacy_contract_still_demands_the_previous_owner(self):
        """Regression: the downgrade never applies to an ordinary contract —
        only `processo_legado=True` triggers it."""
        d = fx.variante(1)
        d = replace(d, imovel=replace(d.imovel, ultima_transferencia_em=date(2021, 9, 15)))
        _d, _pol, _sw, av = _avaliar(1, d)
        assert _campos(av) == [("partes.antigo_proprietario", None)]
        assert "ANTIGO_PROPRIETARIO_PROCESSO_LEGADO" not in _codigos(av.avisos)


class TestQ12Posse:
    def test_missing_office_daily_fine_is_missing(self):
        d = fx.variante(1)
        _d, _pol, _sw, av = _avaliar(1, replace(d, imobiliaria=replace(d.imobiliaria, posse_multa_diaria=None)))
        assert _campos(av) == [("imobiliaria.posse_multa_diaria", None)]

    def test_missing_signing_platform_is_missing(self):
        d = fx.variante(1)
        _d, _pol, _sw, av = _avaliar(1, replace(d, imobiliaria=replace(d.imobiliaria, plataforma_assinatura_url=None)))
        assert _campos(av) == [("imobiliaria.plataforma_assinatura", None)]

    def test_compra_e_venda_carries_one_daily_fine(self):
        assert _texto(1).count("R$ 500,00 (quinhentos reais) por dia de atraso") == 1

    def test_permuta_carries_the_same_daily_fine_for_each_party(self):
        paragrafos = [p for p in _render(6).paragrafos if "R$ 500,00 (quinhentos reais) por dia de atraso" in p]
        assert len(paragrafos) == 2
        assert "o VENDEDOR" in paragrafos[0] and "Rua Fictícia, nº 100" in paragrafos[0]
        assert "a COMPRADORA" in paragrafos[1] and "Avenida Amostra, nº 5" in paragrafos[1]


class TestQ13Permuta:
    def test_each_receiving_party_pays_its_imovel_registry_and_itbi(self):
        texto = _texto(5)
        assert ("As despesas decorrentes da transmissão de cada imóvel, tais como emolumentos de cartório, "
                "registro e ITBI, serão suportadas pela parte que o recebe.") in texto
        assert "serão suportadas pela COMPRADORA" not in texto

    def test_permuta_imovel_narrows_to_descricao_imovel_when_present(self):
        """Migration 136 — the identical defect the OBJETO clause had:
        `fx.MATRICULA_PERMUTA_TEXTO` is a whole selection that, in a real
        de-furnitured abertura, could end in `PROPRIETÁRIOS: …` naming the
        PREVIOUS owners of the swapped property. `descricao_imovel_texto`
        set narrows the permuta parcela line to just the typed block —
        unlike the OBJETO clause this text is plain (no `{{r }}` rich-text
        slot exists for the permuta line), so a plain substring check on
        the rendered text is the whole story."""
        narrow = "A casa térrea situada na Avenida Amostra, nº 5, com dois dormitórios."
        d = fx.variante(5)
        ativo = replace(d.permuta_imoveis[0], descricao_imovel_texto=narrow)
        d = replace(d, permuta_imoveis=[ativo])

        texto = _texto(5, d)

        assert narrow in texto
        assert fx.MATRICULA_PERMUTA_TEXTO not in texto

    def test_permuta_imovel_falls_back_and_logs_when_no_block(self, caplog):
        """The pre-136 fixture shape (`descricao_imovel_texto=None`, the
        default `fx.permuta_imovel()` builds) renders EXACTLY as before —
        and, same as the OBJETO clause, the fallback is logged, not silent."""
        d = fx.variante(5)
        assert d.permuta_imoveis[0].descricao_imovel_texto is None

        with caplog.at_level("WARNING"):
            texto = _texto(5, d)

        assert fx.MATRICULA_PERMUTA_TEXTO in texto
        assert any(
            "descricao_imovel" in rec.message
            and "permuta" in rec.message
            and "seleção inteira" in rec.message
            for rec in caplog.records
        )


class TestQ14Assinaturas:
    def test_witnesses_need_an_rg_not_a_cpf(self):
        """[Q14 revisited] Contract 08's own witnesses carry only RG — RG is
        the hard-required identifying document (f5-template-spec.md §5.1:
        "exactly 2 org_testemunhas with nome + rg"), CPF is optional."""
        d = fx.variante(1)
        t1, t2 = d.testemunhas
        _d, _pol, _sw, av = _avaliar(1, replace(d, testemunhas=[replace(t1, rg=None), replace(t2, cpf=None)]))
        assert _campos(av) == [("imobiliaria.testemunha.1.rg", None)]

    def test_an_invalid_cpf_still_blocks_even_though_cpf_is_optional(self):
        """Optional ≠ unchecked: a CPF that IS supplied must still pass
        mod-11."""
        d = fx.variante(1)
        t1, t2 = d.testemunhas
        _d, _pol, _sw, av = _avaliar(1, replace(d, testemunhas=[replace(t1, cpf="111.111.111-11"), t2]))
        assert any(b["codigo"] == "CPF_INVALIDO" for b in av.bloqueios)

    def test_a_witness_with_no_email_is_an_aviso_not_a_blocker(self):
        """A witness with no e-mail can still generate the document (it is
        needed only to SEND for digital signature) — `av.pronto` must not
        depend on it."""
        d = fx.variante(1)
        t1, t2 = d.testemunhas
        _d, _pol, _sw, av = _avaliar(1, replace(d, testemunhas=[replace(t1, email=None), t2]))
        assert av.pronto, (av.faltando, av.bloqueios)
        assert any(a["codigo"] == "TESTEMUNHA_SEM_EMAIL" for a in av.avisos)

    def test_witnesses_print_rg_and_email_beside_the_name_never_cpf(self):
        """Contract 08's exact witness-block shape: NOME + E-MAIL (when
        present) + RG. Signatories (compradores/vendedores) are unaffected."""
        d = fx.variante(1)
        t1, t2 = d.testemunhas
        d = replace(d, testemunhas=[replace(t1, email="testemunha.um@exemplo.test"), t2])

        r = _render(1, d)
        assert "TESTEMUNHA UM    testemunha.um@exemplo.test" in r.paragrafos
        assert "RG 33.333.333-3" in r.paragrafos
        # t2 has no e-mail set in the fixture — bare name, no dangling blank.
        assert "TESTEMUNHA DOIS" in r.paragrafos
        assert "RG 44.444.444-4" in r.paragrafos
        assert not any(p.startswith("CPF ") for p in r.paragrafos)
        # Signatories keep printing their own e-mail exactly as before.
        assert "FULANO DE TAL    v1@exemplo.test" in r.paragrafos


class TestLint:
    def test_duplicate_heading_and_wrong_reference_are_caught(self):
        paragrafos = [
            "CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO",
            "texto",
            "CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO",
            "descrito na Cláusula Terceira",
            "CLÁUSULA SEGUNDA – DAS CERTIDÕES E DOCUMENTOS",
        ]
        codigos = {h["codigo"] for h in lint.lint(paragrafos, referencias={"objeto": 1}, clausulas={"objeto": 1, "preco": 2})}
        assert {"CLAUSULA_DUPLICADA", "REFERENCIA_CLAUSULA_INEXISTENTE", "REFERENCIA_CLAUSULA_ERRADA"} <= codigos

    def test_letter_gap_paragraph_gap_and_bad_extenso_are_caught(self):
        paragrafos = [
            "CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO",
            "Parágrafo Primeiro: um",
            "Parágrafo Terceiro: dois",
            "a-) item;",
            "b-) item;",
            "d-) item.",
            "R$ 1.000,00 (mil e um reais)",
        ]
        codigos = {h["codigo"] for h in lint.lint(paragrafos, referencias={}, clausulas={"objeto": 1})}
        assert {"PARAGRAFO_FORA_DE_SEQUENCIA", "LETRAS_COM_LACUNA", "EXTENSO_DIVERGENTE"} <= codigos


# ─── ABNT PDF (§5) ──────────────────────────────────────────────────────────


def _abrir(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def _spans(page):
    out = []
    info = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
    for block in info["blocks"]:
        for line in block.get("lines", []):
            out.extend(line["spans"])
    return out


class TestAbntPdf:
    def test_the_stored_version_is_a_real_pdf_never_docx(self):
        r = _render(1)
        pdf = documento.gerar_pdf(r.docx)
        assert pdf[:5] == b"%PDF-"
        # The internal `.docx` intermediate is a DIFFERENT zip-based format —
        # confirm the PDF path did not just hand back the same bytes.
        assert pdf[:2] != b"PK"

    def test_title_paragraph_is_centered_and_bold(self):
        r = _render(1)
        pdf = documento.gerar_pdf(r.docx)
        page = _abrir(pdf)[0]
        titulo = r.paragrafos[0]
        assert titulo.startswith("INSTRUMENTO PARTICULAR")
        # `gerar_pdf` passes this same TITLE text as `doc.title`, which now
        # ALSO drives the running header `render_abnt_pdf` prints top-left
        # on every page (contract §3's "document UI") — excluding the
        # header's band (inside the top margin, y0 < 3cm) keeps this test
        # about the centered BODY-frame title paragraph only, not a
        # same-text-different-place false positive from the header.
        spans = [
            s
            for s in _spans(page)
            if s["text"].strip() and s["text"] in titulo and s["bbox"][1] >= 3 * cm
        ]
        assert spans, "esperava encontrar o texto do título na primeira página"
        assert all("Bold" in s["font"] for s in spans)
        frame_center = page.rect.width / 2
        for s in spans:
            x0, _y0, x1, _y1 = s["bbox"]
            assert abs(((x0 + x1) / 2) - frame_center) < 40

    def test_a_clause_heading_is_bold(self):
        r = _render(1)
        pdf = documento.gerar_pdf(r.docx)
        heading = next(p for p in r.paragrafos if p.startswith("CLÁUSULA "))
        found = False
        for page in _abrir(pdf):
            for s in _spans(page):
                if s["text"].strip() and s["text"] in heading:
                    found = True
                    assert "Bold" in s["font"]
        assert found, "esperava encontrar o texto de uma cláusula em alguma página"

    def test_matricula_range_is_bold_and_underlined_in_the_pdf(self):
        # "FULANO DE TAL" and "R.1/12.345" are both inside fx.MATRICULA_TEXTO
        # (fx.variante(1)'s selected acts) — offsets computed against that
        # literal string, matching contract §5's "carries its bold/underline".
        negrito_inicio = fx.MATRICULA_TEXTO.index("FULANO DE TAL")
        negrito_fim = negrito_inicio + len("FULANO DE TAL")
        sublinhado_inicio = fx.MATRICULA_TEXTO.index("R.1/12.345")
        sublinhado_fim = sublinhado_inicio + len("R.1/12.345")

        d = fx.variante(1)
        d = replace(
            d,
            matricula=replace(
                d.matricula,
                formatacao=(
                    FormatRange(start=negrito_inicio, end=negrito_fim, bold=True),
                    FormatRange(start=sublinhado_inicio, end=sublinhado_fim, underline=True),
                ),
            ),
        )
        r = _render(1, d)
        pdf = documento.gerar_pdf(r.docx)

        negrito_achado = False
        sublinhado_achado = False
        for page in _abrir(pdf):
            for s in _spans(page):
                if s["text"] == "FULANO DE TAL":
                    negrito_achado = True
                    assert "Bold" in s["font"]
            if page.get_drawings():
                sublinhado_achado = True
        assert negrito_achado, "esperava encontrar 'FULANO DE TAL' em negrito"
        assert sublinhado_achado, "esperava um traço de sublinhado (R.1/12.345)"

    def test_a_character_the_core_font_cannot_represent_is_a_loud_refusal(self):
        # `render_abnt_pdf` (seed) raises `UnsupportedGlyphError` naming the
        # character — `gerar_pdf` does not swallow it; `service.gerar` maps
        # it to `ContratoPdfNaoGerado` (422), never a silent 500.
        d = fx.variante(1)
        v = replace(d.vendedores[0], nome="Fulano 🏠 de Tal")
        d = replace(d, vendedores=[v])
        r = _render(1, d)
        with pytest.raises(UnsupportedGlyphError):
            documento.gerar_pdf(r.docx)


class TestNacionalidadeFlex:
    """`frases.nacionalidade_flex` (migration 146) — agreement follows the
    PARTY's own gender, never the spelling a source document happened to
    print. Contract 08 (human reference) renders "brasileira" for a woman
    and "brasileiro" for a man regardless of source spelling; the new-model
    CNH prints "BRASILEIRO" even for a woman — this is the function that
    keeps those two facts from leaking into each other.
    """

    def _pessoa(self, *, genero: str, nacionalidade: str):
        return fx.pessoa(
            "cliente-1", "vendedor", "titular", "FULANA DE TAL", genero,
            "111", "11.111.111-1", nacionalidade=nacionalidade,
        )

    def test_a_masculine_source_reading_is_regendered_for_a_woman(self):
        """The exact CNH bug this migration closes: the document printed
        the masculine form for a woman."""
        p = self._pessoa(genero="Feminino", nacionalidade="brasileiro")
        assert frases.nacionalidade_flex(p) == "brasileira"

    def test_a_feminine_source_reading_is_regendered_for_a_man(self):
        p = self._pessoa(genero="Masculino", nacionalidade="brasileira")
        assert frases.nacionalidade_flex(p) == "brasileiro"

    def test_a_non_brazilian_gentilico_also_agrees_with_the_party(self):
        p = self._pessoa(genero="Feminino", nacionalidade="italiano")
        assert frases.nacionalidade_flex(p) == "italiana"

    def test_a_gentilico_with_no_o_a_ending_still_agrees(self):
        """"francês"/"francesa" — the family gender.py's own module
        docstring calls out as carrying no -o/-a agreement signal at all;
        the closed vocabulary's table (not a suffix rule) is what gets it
        right."""
        p = self._pessoa(genero="Feminino", nacionalidade="frances")
        assert frases.nacionalidade_flex(p) == "francesa"

    def test_the_legacy_parenthetical_form_still_renders(self):
        """`"Brasileiro(a)"` predates 145 (`contrato_gerador_fixtures.
        pessoa`'s own default) and must keep working exactly as it always
        did — this migration is additive, not a breaking rewrite."""
        p = self._pessoa(genero="Feminino", nacionalidade="Brasileiro(a)")
        assert frases.nacionalidade_flex(p) == "brasileira"

    def test_free_text_outside_the_vocabulary_passes_through_lowercased(self):
        p = self._pessoa(genero="Feminino", nacionalidade="Sul-coreana")
        assert frases.nacionalidade_flex(p) == "sul-coreana"


class TestTextoPessoaSemProfissao:
    """🔴 [2026-09-22] `frases.texto_pessoa` omits profissão cleanly when
    absent — the office accepts a qualification without it (contract 08's
    REGINA MARIA PELOSI). Before this fix, an empty `partes` entry joined as
    a dangling ", ," right before "portador(a) da cédula..."."""

    def _pessoa(self, **extra):
        return fx.pessoa(
            "cliente-1", "vendedor", "proprietario", "REGINA MARIA PELOSI",
            "Feminino", "111", "11.111.111-1", estado_civil="divorciado", **extra,
        )

    def test_no_profissao_omits_it_with_no_dangling_comma(self):
        p = self._pessoa(profissao=None)
        texto = frases.texto_pessoa(p, em_nucleo=False)
        assert ", ," not in texto
        assert ",  " not in texto
        assert texto.startswith(
            "REGINA MARIA PELOSI, brasileira, divorciada, portadora da cédula "
            "de identidade RG 11.111.111-1-SSP-SP e inscrita no CPF/MF "
        )

    def test_blank_profissao_is_treated_the_same_as_none(self):
        p = self._pessoa(profissao="   ")
        texto = frases.texto_pessoa(p, em_nucleo=False)
        assert ", ," not in texto

    def test_a_present_profissao_still_renders_between_estado_civil_and_rg(self):
        p = self._pessoa(profissao="empresária")
        texto = frases.texto_pessoa(p, em_nucleo=False)
        assert "divorciada, empresária, portadora" in texto


class TestParceiroSemCreci:
    """[sw-comissao-parceiro-sem-creci] Migration 162:
    `natureza='parceiro_split'` — a commission-split beneficiary the
    generated contract never qualifies as a contracted party. Reference
    contract 08's own commission clause has exactly this shape: TWO
    qualified parties in the "DA INTERMEDIAÇÃO" header, but THREE
    beneficiaries in the payment split paragraph — the 3rd (a company with
    no CRECI) appears only as a bank-deposit line. Before 162,
    `derivacao._intermediacao` required a CRECI on EVERY row unconditionally
    — a 3rd party added the way the schema already allowed (nome + tipo/
    valor + favorecido_id, `creci` genuinely absent) made `avaliacao.pronto`
    False and blocked generation outright, which is why the only way to
    generate at all was to leave that party out — the observed bug: a
    commission clause 2 recipients / R$ 82.650 wide instead of the signed
    reference's 3 recipients / R$ 87.000."""

    def _com_parceiro_sem_creci(self) -> DadosContrato:
        d = fx.variante(1)
        corretor = replace(d.intermediarios[0], valor=Decimal("5"))
        parceiro = replace(
            corretor,
            id="int-2",
            corretor_id=None,
            nome="Parceiro Sem Creci Exemplo LTDA",
            creci=None,
            valor=Decimal("1"),
            natureza="parceiro_split",
            pessoa_tipo="pj",
            documento="45646535000172",
            favorecido_id="fav-parceiro",
        )
        favorecidos = list(d.favorecidos) + [
            fx.Favorecido(
                id="fav-parceiro", nome="Parceiro Sem Creci Exemplo LTDA",
                cpf_cnpj="45646535000172", banco="Banco Exemplo", agencia="0001",
                conta="99999-9",
            )
        ]
        # 5% + 1% = 6% == pct_comissao — keeps the unrelated
        # CORRETAGEM_PERCENTUAL_DIVERGE aviso quiet so this test pins only
        # the readiness/qualification behaviour under test.
        return replace(d, intermediarios=[corretor, parceiro], favorecidos=favorecidos)

    def test_gate_does_not_require_creci_for_a_parceiro_split(self):
        d = self._com_parceiro_sem_creci()
        _d, _pol, _sw, av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert not [f for f in av.faltando if f["campo"].endswith(".creci")]

    def test_the_same_missing_creci_still_blocks_a_plain_intermediario(self):
        """Regression guard: the fix is `natureza`-gated, not a blanket
        removal of the CRECI requirement for the table's original meaning."""
        d = self._com_parceiro_sem_creci()
        # Same row, but AS the table's original meaning (no natureza override).
        d = replace(d, intermediarios=[
            replace(d.intermediarios[1], natureza="intermediario"),
        ])
        _d, _pol, _sw, av = _avaliar(1, d)
        assert not av.pronto
        assert any(f["campo"].endswith(".creci") for f in av.faltando)

    def test_parceiro_split_is_summed_into_the_split_payment_but_not_qualified(self):
        d = self._com_parceiro_sem_creci()
        texto = "\n".join(_render(1, d).paragrafos)
        # Summed into the split-payment paragraph (`frases.split_corretagem`).
        assert "por meio de depósito bancário em favor de Parceiro Sem Creci Exemplo LTDA" in texto
        # NEVER added to "as empresas a seguir qualificadas" — no PJ
        # qualification sentence is printed for it anywhere.
        assert "Parceiro Sem Creci Exemplo LTDA, pessoa jurídica inscrita" not in texto
