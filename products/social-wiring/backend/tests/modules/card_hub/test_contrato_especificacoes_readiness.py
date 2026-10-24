"""The selected contract specifications SCOPE the readiness (owner direction
2026-10-24): data specific to one specification is never demanded by a
selection that does not use it; a selected specification whose data is
missing is a falta, never a silently dropped clause.

WHAT THESE PIN
--------------
- THE SCOPE-LEAK MATRIX: for every valid catalogue combination, a synthetic
  deal that fills ONLY that combination's data is `pronto` (no falta outside
  `requisitos`) — the one exception being the open owner decision G1 (à vista
  without sinal), which is exactly its named falta; and for each combination,
  removing one required datum yields exactly that falta. The combinations no
  data can satisfy (no payment basis: none of à vista / financiamento /
  parcelas diretas) are named and never `pronto`.
- the gate is `Avaliacao.pede`; legacy mode (no stored selection) has no
  scope at all — and why `sugerir(switches)` cannot stand in for it.
- data present but its specification unselected → ESPEC_CONTRADIZ_DADOS
  (its governed faltas are not asked); MODELO_DIVERGENTE is legacy-only.
- G5: the ``fgts`` specification requires the companies' CRF/FGTS.
- `obter_geracao` / `iniciar` carry the selection, the suggestion, the
  conflicts and the selection's `modelo`.
"""
from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.card_hub.contrato_gerador import especificacoes as esp
from app.modules.card_hub.contrato_gerador.dados import Financiamento
from tests.modules.card_hub import contrato_gerador_fixtures as fx

PENDENTE = "negociacao.multa_rescisoria_base"
#: A selection with none of these has no payment basis no data can satisfy:
#: every parcela shape without financiamento/direta IS the à vista shape.
BASES_DE_PAGAMENTO = frozenset({"a_vista", "financiamento_bancario", "parcelas_diretas"})
EM_DINHEIRO = ("sinal", "intermediaria", "financiamento", "direta")


def _combinacoes() -> list[tuple[str, ...]]:
    saida = []
    resto = esp.CHAVES[1:]
    for n in range(len(resto) + 1):
        for extra in itertools.combinations(resto, n):
            try:
                saida.append(esp.validar((esp.BASE, *extra)))
            except ValueError:
                continue
    return saida


COMBINACOES = _combinacoes()
SATISFAZIVEIS = [c for c in COMBINACOES if BASES_DE_PAGAMENTO & set(c)]
INSATISFAZIVEIS = [c for c in COMBINACOES if not BASES_DE_PAGAMENTO & set(c)]


def _negocio(combo: tuple[str, ...]):
    """A synthetic deal carrying ONLY the data `combo` asks for (plus the
    ungoverned data every contract needs — parties, certidões, imóvel)."""
    sel = set(combo)
    d = fx.base_v1()
    intermediacao = "intermediacao" in sel
    parcelas = []

    def add(pid: str, tipo: str, valor: str, **extra) -> None:
        if intermediacao and tipo in EM_DINHEIRO:
            extra["dispara_corretagem"] = True
        parcelas.append(fx.parcela(pid, tipo, valor, len(parcelas) + 1, **extra))

    sem_dinheiro = not (sel & {"intermediarias", "financiamento_bancario", "parcelas_diretas"})
    # Without `sinal_saldo` a sinal is still the only NEUTRAL money parcela
    # (it witnesses no specification) — used when nothing else pays.
    if "sinal_saldo" in sel or sem_dinheiro:
        add("p-sinal", "sinal", "50000.00", evento="no ato da assinatura do presente instrumento",
            forma_pagamento="PIX", favorecido_id="fav-v")
    if "intermediarias" in sel:
        add("p-int", "intermediaria", "50000.00", evento="em 30 dias da assinatura",
            forma_pagamento="Transferência", favorecido_id="fav-v")
    if "financiamento_bancario" in sel:
        add("p-fin", "financiamento", "300000.00", evento="na liberação do financiamento")
    if "parcelas_diretas" in sel:
        add("p-dir", "direta", "50000.00", vencimento=date(2027, 1, 10), forma_pagamento="PIX",
            favorecido_id="fav-v", confissao_divida="confissao_divida" in sel)
    if "permuta" in sel:
        add("p-permuta", "permuta", "100000.00", permuta_ativo_ids=(fx.PERMUTA_ATIVO_ID,))
    termos = replace(
        d.termos,
        posse_marco="assinatura",
        posse_marco_parcela_id=None,
        corretagem_contratantes="vendedores" if intermediacao else None,
        confissao_juros_am=Decimal("1") if "confissao_divida" in sel else None,
        permuta_posse_prazo_dias=60 if "permuta" in sel else None,
        permuta_posse_marco="assinatura" if "permuta" in sel else None,
    )
    return replace(
        d,
        modelo=esp.modelo_de(combo),
        especificacoes=tuple(combo),
        especificacoes_versao=esp.CATALOGO_VERSAO,
        parcelas=parcelas,
        valor_negociado=sum((p.valor for p in parcelas), Decimal("0")),
        pct_comissao=Decimal("6") if intermediacao else None,
        intermediarios=d.intermediarios if intermediacao else [],
        financiamento=(
            Financiamento(existe=True, situacao="aprovado", fgts="fgts" in sel)
            if "financiamento_bancario" in sel else Financiamento()
        ),
        permuta_imoveis=[fx.permuta_imovel()] if "permuta" in sel else [],
        termos=termos,
    )


def _avaliar(d):
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return sw, derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _campos(av) -> set[str]:
    return {f["campo"] for f in av.faltando}


def _codigos(itens) -> set[str]:
    return {i["codigo"] for i in itens}


def _esperadas(combo) -> set[str]:
    """G1 (open owner question): à vista without sinal can never be ready."""
    return {PENDENTE} if "a_vista" in combo and "sinal_saldo" not in combo else set()


# ─── the matrix ───────────────────────────────────────────────────────────


def test_the_matrix_covers_every_valid_combination():
    assert len(COMBINACOES) == 160
    assert len(SATISFAZIVEIS) == 144 and len(INSATISFAZIVEIS) == 16
    assert sum(len(_remocoes(c, _negocio(c))) for c in SATISFAZIVEIS) == 2320


@pytest.mark.parametrize("combo", SATISFAZIVEIS, ids="+".join)
def test_a_deal_filling_only_its_combination_asks_for_nothing_outside_it(combo):
    d = _negocio(combo)
    sw, av = _avaliar(d)
    assert esp.conflitos(combo, sw) == []
    assert _campos(av) == _esperadas(combo)
    assert av.bloqueios == [] and av.pendentes_confirmacao == []
    assert av.pronto is (not _esperadas(combo))
    # The pending decision is asked under its named label, never resolved.
    for f in av.faltando:
        assert f["rotulo"].startswith("Aguardando decisão do escritório: base da multa rescisória")


@pytest.mark.parametrize("combo", INSATISFAZIVEIS, ids="+".join)
def test_a_combination_without_payment_basis_is_never_ready(combo):
    _sw, av = _avaliar(_negocio(combo))
    assert not av.pronto
    assert "ESPEC_CONTRADIZ_DADOS" in _codigos(av.bloqueios)


def _sem(d, pid: str):
    return replace(d, parcelas=[p for p in d.parcelas if p.id != pid])


def _parcela(d, pid: str, **campos):
    return replace(d, parcelas=[replace(p, **campos) if p.id == pid else p for p in d.parcelas])


def _termos(d, **campos):
    return replace(d, termos=replace(d.termos, **campos))


def _so_essa_paga(d, pid: str) -> bool:
    """Removing `pid` would leave no money parcela (a different deal shape:
    `negociacao.parcelas` / an à vista contradiction) — not one datum."""
    return not any(p.tipo in EM_DINHEIRO for p in d.parcelas if p.id != pid)


def _remocoes(combo, d):
    """(what, mutated deal, the faltas it must add) for each required datum."""
    sel = set(combo)
    paga = next((p for p in d.parcelas if p.tipo in derivacao.TIPOS_PAGOS_A_FAVORECIDO), None)
    out = [
        ("valor_negociado", replace(d, valor_negociado=None), {"negociacao.valor_negociado"}),
        ("posse_prazo", _termos(d, posse_prazo_dias=None), {"negociacao.posse_prazo_dias"}),
        ("posse_marco", _termos(d, posse_marco=None), {"negociacao.posse_marco"}),
        ("compradores", replace(d, compradores=[]), {"partes.compradores"}),
        ("parcela.valor", _parcela(d, d.parcelas[0].id, valor=None),
         {f"negociacao.parcela.{d.parcelas[0].id}.valor"}),
    ]
    if paga is not None:
        out.append(("parcela.forma", _parcela(d, paga.id, forma_pagamento=None),
                    {f"negociacao.parcela.{paga.id}.forma_pagamento"}))
    if "sinal_saldo" in sel:
        out.append(("sinal.favorecido", _parcela(d, "p-sinal", favorecido_id=None),
                    {"negociacao.parcela.p-sinal.favorecido"}))
        if not _so_essa_paga(d, "p-sinal"):
            out.append(("sinal", _sem(d, "p-sinal"), {"negociacao.parcela_sinal"}))
    if "financiamento_bancario" in sel:
        fin = d.financiamento
        out.append(("financiamento", replace(d, financiamento=replace(fin, existe=False)), {"financiamento"}))
        out.append(("financiamento.situacao", replace(d, financiamento=replace(fin, situacao=None)),
                    {"financiamento.situacao"}))
        if not _so_essa_paga(d, "p-fin"):
            out.append(("parcela.financiamento", _sem(d, "p-fin"),
                        {"especificacao.financiamento_bancario"}
                        | ({"especificacao.fgts"} if "fgts" in sel else set())))
    if "fgts" in sel:
        out.append(("fgts", replace(d, financiamento=replace(d.financiamento, fgts=False)),
                    {"especificacao.fgts"}))
    if "parcelas_diretas" in sel:
        out.append(("direta.vencimento", _parcela(d, "p-dir", vencimento=None),
                    {"negociacao.parcela.p-dir.momento"}
                    | ({"negociacao.parcela.p-dir.vencimento"} if "confissao_divida" in sel else set())))
        if not _so_essa_paga(d, "p-dir"):
            out.append(("parcela.direta", _sem(d, "p-dir"),
                        {"especificacao.parcelas_diretas"}
                        | ({"especificacao.confissao_divida"} if "confissao_divida" in sel else set())))
    if "confissao_divida" in sel:
        out.append(("confissao.juros", _termos(d, confissao_juros_am=None), {"negociacao.confissao_juros_am"}))
        out.append(("confissao.marcada", _parcela(d, "p-dir", confissao_divida=False),
                    {"especificacao.confissao_divida"}))
    if "intermediarias" in sel:
        out.append(("intermediaria.evento", _parcela(d, "p-int", evento=None),
                    {"negociacao.parcela.p-int.momento"}))
        if not _so_essa_paga(d, "p-int"):
            out.append(("parcela.intermediaria", _sem(d, "p-int"), {"especificacao.intermediarias"}))
    if "permuta" in sel:
        im = d.permuta_imoveis[0]
        out += [
            ("permuta.inscricao", replace(d, permuta_imoveis=[replace(im, inscricao_municipal=None)]),
             {f"negociacao.permuta.{fx.PERMUTA_ATIVO_ID}.inscricao_municipal"}),
            ("permuta.posse_marco", _termos(d, permuta_posse_marco=None), {"negociacao.permuta_posse_marco"}),
            ("permuta.imoveis", replace(_parcela(d, "p-permuta", permuta_ativo_ids=()), permuta_imoveis=[]),
             {"negociacao.permuta_imoveis"}),
            ("parcela.permuta", replace(_sem(d, "p-permuta"), permuta_imoveis=[]), {"especificacao.permuta"}),
        ]
    if "intermediacao" in sel:
        it = d.intermediarios[0]
        out += [
            ("intermediario.creci", replace(d, intermediarios=[replace(it, creci=None)]),
             {f"negociacao.intermediario.{it.id}.creci"}),
            ("corretagem.contratantes", _termos(d, corretagem_contratantes=None),
             {"negociacao.corretagem_contratantes"}),
            ("pct_comissao", replace(d, pct_comissao=None), {"negociacao.pct_comissao"}),
            ("intermediarios", replace(d, intermediarios=[]), {"especificacao.intermediacao"}),
        ]
    return out


@pytest.mark.parametrize("combo", SATISFAZIVEIS, ids="+".join)
def test_removing_one_required_datum_yields_exactly_that_falta(combo):
    d = _negocio(combo)
    for oque, mutado, novas in _remocoes(combo, d):
        _sw, av = _avaliar(mutado)
        assert _campos(av) == _esperadas(combo) | novas, (combo, oque)


# ─── the gate ─────────────────────────────────────────────────────────────


V1_SEL = ("compra_venda", "sinal_saldo", "financiamento_bancario", "intermediarias", "intermediacao")


class TestGate:
    def test_legacy_mode_has_no_scope(self):
        _sw, av = _avaliar(fx.variante(1))
        assert av.requisitos is None and av.pede("negociacao.intermediario.x.creci")

    def test_a_selection_scopes_governed_keys_and_never_ungoverned_ones(self):
        _sw, av = _avaliar(_negocio(("compra_venda", "a_vista", "sinal_saldo")))
        assert av.requisitos == esp.requisitos(("compra_venda", "a_vista", "sinal_saldo"))
        assert not av.pede("negociacao.intermediario.x.creci")
        assert not av.pede("financiamento.situacao")
        assert av.pede("negociacao.parcela_sinal")
        assert av.pede("certidao.cnd_federal") and av.pede("especificacao.permuta")

    def test_why_legacy_is_not_scoped_by_the_suggestion(self):
        """`sugerir(switches)` as a legacy scope would DROP the sinal the
        legacy gate asks for on a deal whose only parcela is fgts."""
        d = replace(fx.variante(4), parcelas=[fx.parcela("p1", "fgts", "500000.00", 1)])
        sw, av = _avaliar(d)
        assert "negociacao.parcela_sinal" in _campos(av)
        assert not esp.exige(esp.requisitos(esp.sugerir(sw)), "negociacao.parcela_sinal")

    def test_unselected_data_is_a_contradiction_not_a_falta(self):
        """V1 has intermediação; selected without it, the broker's missing
        CRECI is not asked — the data contradicts the selection instead."""
        sel = tuple(c for c in V1_SEL if c != "intermediacao")
        d = fx.variante(1)
        d = replace(d, especificacoes=sel, intermediarios=[replace(d.intermediarios[0], creci=None)])
        _sw, av = _avaliar(d)
        assert not any(c.startswith("negociacao.intermediario.") for c in _campos(av))
        bloqueio = next(b for b in av.bloqueios if b["codigo"] == "ESPEC_CONTRADIZ_DADOS")
        assert "intermediação (corretagem)" in bloqueio["mensagem"]

    def test_each_contradiction_is_listed(self):
        d = replace(fx.variante(1), especificacoes=("compra_venda", "sinal_saldo", "financiamento_bancario"))
        sw, av = _avaliar(d)
        mensagem = next(b["mensagem"] for b in av.bloqueios if b["codigo"] == "ESPEC_CONTRADIZ_DADOS")
        contra = esp.conflitos(d.especificacoes, sw)
        assert len(contra) == 2 and all(c in mensagem for c in contra)

    def test_modelo_divergente_is_legacy_only(self):
        d = replace(fx.variante(1), modelo="compra_venda_permuta")
        assert "MODELO_DIVERGENTE" in _codigos(_avaliar(d)[1].avisos)
        assert "MODELO_DIVERGENTE" not in _codigos(_avaliar(replace(d, especificacoes=V1_SEL))[1].avisos)

    def test_a_stored_selection_the_catalogue_refuses_blocks(self):
        _sw, av = _avaliar(replace(fx.variante(1), especificacoes=("compra_venda", "inventada")))
        assert "ESPECIFICACOES_INVALIDAS" in _codigos(av.bloqueios)
        assert av.requisitos is None

    def test_g1_a_vista_without_sinal_asks_the_pending_decision_not_the_sinal(self):
        sel = ("compra_venda", "a_vista")
        d = replace(_negocio(sel), parcelas=[fx.parcela(
            "p-int", "intermediaria", "500000.00", 1, evento="na escritura", forma_pagamento="PIX",
            favorecido_id="fav-v")], especificacoes=("compra_venda", "a_vista", "intermediarias"))
        _sw, av = _avaliar(d)
        assert _campos(av) == {PENDENTE}
        assert av.faltando[0]["rotulo"].startswith(
            "Aguardando decisão do escritório: base da multa rescisória para contrato à vista"
        )

    def test_legacy_still_asks_the_sinal_on_every_deal(self):
        d = fx.variante(4)
        d = replace(d, parcelas=[replace(d.parcelas[1], ordem=1)], valor_negociado=Decimal("400000.00"))
        assert "negociacao.parcela_sinal" in _campos(_avaliar(d)[1])


class TestTables:
    def test_every_pending_decision_has_a_label(self):
        assert set(derivacao.ROTULO_PENDENTE_DECISAO) == set(esp.PENDENTES_DECISAO)

    def test_every_data_witnessed_specification_names_its_absence(self):
        com_dados = {e.chave for e in esp.CATALOGO if e.switches_implicados}
        assert set(derivacao.ESPECIFICACAO_SEM_DADOS) == com_dados - {"a_vista", "sinal_saldo"}
        assert not any(esp.governa(f"especificacao.{c}") for c in derivacao.ESPECIFICACAO_SEM_DADOS)


class TestG5CrfFgts:
    def _com_empresa(self, **extra):
        d = fx.variante(2)  # financiamento with FGTS
        e = fx.empresa("e1", "11444777000161", "Empresa Exemplo Ltda", "ativa", owners=[d.vendedores[0]])
        return replace(d, empresas=[e], **extra)

    def test_the_fgts_specification_requires_the_companies_crf(self):
        sel = (*V1_SEL[:3], "fgts", *V1_SEL[3:])
        _sw, av = _avaliar(self._com_empresa(especificacoes=sel))
        assert "certidao.fgts_regularidade" in _campos(av)
        assert "CRF_FGTS_OPCIONAL" not in _codigos(av.avisos)
        assert derivacao.exige_crf_fgts(self._com_empresa(especificacoes=sel))

    def test_legacy_keeps_the_crf_optional(self):
        _sw, av = _avaliar(self._com_empresa())
        assert "certidao.fgts_regularidade" not in _campos(av)
        assert "CRF_FGTS_OPCIONAL" in _codigos(av.avisos)
