"""Two generator gaps the scoring of a real signed deal (857) found, closed
at the root (migration 299). 🔴 SYNTHETIC ONLY — every name, CNPJ and
obligation below is invented.

1. A seller's company read off the Serasa Crednet reaches the contract once a
   human CONFIRMS the participação; until then the gate names it as a
   non-blocking aviso (never a silent drop); a DISMISSED one ("Não é do
   vendedor") is neither in the contract nor in the aviso.
2. `obrigacoes_vendedor` may print inside DAS CERTIDÕES E DOCUMENTOS (after
   the certidão groups, before the pendências paragraph, lettered "a) …;
   b) …."), chosen per deal by `obrigacoes_vendedor_local`; the default
   ('onus') keeps today's ÔNUS paragraph, and the legal-review item lists
   the text either way.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from uuid import uuid4

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import carregador, derivacao, documento, frases, lint
from app.modules.card_hub.contrato_gerador.dados import ParticipacaoNaoConfirmada
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.conftest import ORG_ID

CNPJ_SINTETICO = "11444777000161"
OBRIGACOES = (
    "Apresentar aos COMPRADORES a certidão de cancelamento do protesto apontado;\n"
    "Apresentar aos COMPRADORES o comprovante de baixa da pendência financeira.\n"
    "Apresentar aos COMPRADORES o comprovante de quitação das despesas condominiais"
)


def _avaliar(n: int, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _paragrafos(n: int, d) -> list[str]:
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)
    assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []
    return [p.replace("**", "") for p in r.paragrafos]


def _codigos(itens) -> set[str]:
    return {i["codigo"] for i in itens}


def _clausula(paragrafos: list[str], titulo: str) -> list[str]:
    """The paragraphs of the clause whose heading contains `titulo`."""
    inicio = next(i for i, p in enumerate(paragrafos) if p.startswith("CLÁUSULA") and titulo in p)
    fim = next(
        (i for i in range(inicio + 1, len(paragrafos)) if paragrafos[i].startswith("CLÁUSULA")),
        len(paragrafos),
    )
    return paragrafos[inicio:fim]


# ─── 1. unconfirmed Crednet participações ─────────────────────────────────


def _nao_confirmada(cliente_id: str = "v1", **extra) -> ParticipacaoNaoConfirmada:
    base = dict(
        empresa_id="emp-1", cnpj=CNPJ_SINTETICO, cliente_id=cliente_id,
        razao_social="Comercio Ficticio LTDA", situacao_cadastral="ativa",
    )
    base.update(extra)
    return ParticipacaoNaoConfirmada(**base)


class TestAvisoCrednetNaoConfirmada:
    def test_a_sellers_unconfirmed_company_is_a_non_blocking_aviso_naming_both(self):
        d = replace(fx.variante(1), participacoes_nao_confirmadas=[_nao_confirmada()])
        av = _avaliar(1, d)
        msgs = [a["mensagem"] for a in av.avisos if a["codigo"] == "EMPRESA_CREDNET_NAO_CONFIRMADA"]
        assert msgs == [
            "Empresa Comercio Ficticio LTDA lida do Serasa Crednet de Fulano de Tal não confirmada — "
            "confirme na seção Empresas para incluir as certidões dela no contrato."
        ]
        assert "EMPRESA_CREDNET_NAO_CONFIRMADA" not in _codigos(av.bloqueios)
        assert av.pronto

    def test_no_razao_social_names_the_cnpj(self):
        d = replace(fx.variante(1), participacoes_nao_confirmadas=[_nao_confirmada(razao_social=None)])
        msgs = [a["mensagem"] for a in _avaliar(1, d).avisos if a["codigo"] == "EMPRESA_CREDNET_NAO_CONFIRMADA"]
        assert msgs and msgs[0].startswith(f"Empresa {CNPJ_SINTETICO} lida do Serasa Crednet")

    def test_a_long_closed_company_needs_no_certidoes_so_no_aviso(self):
        antiga = _nao_confirmada(situacao_cadastral="baixada", data_situacao_cadastral=date(2010, 1, 1))
        d = replace(fx.variante(1), participacoes_nao_confirmadas=[antiga])
        assert "EMPRESA_CREDNET_NAO_CONFIRMADA" not in _codigos(_avaliar(1, d).avisos)

    def test_a_comprador_without_permuta_is_not_a_certificando_so_no_aviso(self):
        d = replace(fx.variante(1), participacoes_nao_confirmadas=[_nao_confirmada(cliente_id="c1")])
        assert "EMPRESA_CREDNET_NAO_CONFIRMADA" not in _codigos(_avaliar(1, d).avisos)

    def test_the_aviso_does_not_change_the_rendered_contract(self):
        base = fx.variante(1)
        com = replace(base, participacoes_nao_confirmadas=[_nao_confirmada()])
        assert _paragrafos(1, com) == _paragrafos(1, base)


class TestParticipacaoVale:
    def test_confirmed_or_manual_counts(self):
        assert carregador._participacao_vale({"origem": "serasa_crednet", "confirmado_em": "2026-10-21"})
        assert carregador._participacao_vale({"origem": "manual"})

    def test_unconfirmed_crednet_does_not(self):
        assert not carregador._participacao_vale({"origem": "serasa_crednet"})

    def test_a_dismissed_one_never_counts(self):
        assert not carregador._participacao_vale(
            {"origem": "serasa_crednet", "confirmado_em": None, "descartado_em": "2026-10-21"}
        )


def _seed(scoped) -> None:
    for t in (
        "empresas", "cliente_empresa_participacoes", "certidao_consultas", "certidao_resultados",
    ):
        scoped.set_table_data(t, [])


def _participacao(cliente_id: str, empresa_id: str, **over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cliente_id,
        "empresa_id": empresa_id, "participacao_pct": None, "desde": None,
        "fonte_documento_id": None, "origem": "serasa_crednet",
        "confirmado_por": None, "confirmado_em": None,
        "descartado_por": None, "descartado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(over)
    return row


def _empresa_row(cnpj: str, razao: str) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cnpj": cnpj, "razao_social": razao,
        "nome_fantasia": None, "natureza_juridica": None, "data_abertura": None,
        "situacao_cadastral": "ativa", "data_situacao_cadastral": None, "motivo_situacao": None,
        "dados_origem": "serasa_crednet", "dados_documento_id": None, "dados_em": None,
        "dados_confirmado_por": None, "dados_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    }


class TestCarregadorEmpresas:
    """`carregador._empresas` against the mock DB: confirmed in, undecided
    named, dismissed silent."""

    def test_confirmed_in_undecided_named_dismissed_dropped(self, scoped):
        _seed(scoped)
        vendedor_id = str(uuid4())
        confirmada = _empresa_row("11222333000181", "Confirmada Ficticia LTDA")
        pendente = _empresa_row(CNPJ_SINTETICO, "Pendente Ficticia LTDA")
        descartada = _empresa_row("45997418000153", "Descartada Ficticia LTDA")
        scoped.set_table_data("empresas", [confirmada, pendente, descartada])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_id, confirmada["id"], confirmado_em="2026-10-21T10:00:00+00:00"),
            _participacao(vendedor_id, pendente["id"]),
            _participacao(vendedor_id, descartada["id"], descartado_em="2026-10-21T10:00:00+00:00"),
        ])
        pessoa = replace(fx.vendedor(), cliente_id=vendedor_id)

        empresas, nao_confirmadas = carregador._empresas(
            scoped, ORG_ID, [vendedor_id], {vendedor_id: pessoa}
        )

        assert [e.razao_social for e in empresas] == ["Confirmada Ficticia LTDA"]
        assert [(p.cliente_id, p.cnpj, p.razao_social) for p in nao_confirmadas] == [
            (vendedor_id, CNPJ_SINTETICO, "Pendente Ficticia LTDA")
        ]

    def test_a_company_already_in_through_a_confirmed_spouse_is_not_named(self, scoped):
        _seed(scoped)
        vendedor_id, conjuge_id = str(uuid4()), str(uuid4())
        empresa = _empresa_row(CNPJ_SINTETICO, "Do Casal Ficticia LTDA")
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_id, empresa["id"], confirmado_em="2026-10-21T10:00:00+00:00"),
            _participacao(conjuge_id, empresa["id"]),
        ])
        pessoas = {
            vendedor_id: replace(fx.vendedor(), cliente_id=vendedor_id),
            conjuge_id: replace(fx.vendedor(), cliente_id=conjuge_id, nome="Conjuge Ficticia"),
        }

        empresas, nao_confirmadas = carregador._empresas(
            scoped, ORG_ID, [vendedor_id, conjuge_id], pessoas
        )

        assert len(empresas) == 1
        assert nao_confirmadas == []


# ─── 2. where the seller's typed obligations print ────────────────────────


def _com_obrigacoes(local: str | None = None):
    d = fx.variante(1)
    extra = {"obrigacoes_vendedor": OBRIGACOES}
    if local is not None:
        extra["obrigacoes_vendedor_local"] = local
    return replace(d, termos=replace(d.termos, **extra))


ESPERADO_LETRADO = (
    "a) Apresentar aos COMPRADORES a certidão de cancelamento do protesto apontado; "
    "b) Apresentar aos COMPRADORES o comprovante de baixa da pendência financeira; "
    "c) Apresentar aos COMPRADORES o comprovante de quitação das despesas condominiais."
)


class TestObrigacoesLetradas:
    def test_one_lettered_paragraph_with_the_typed_closers_normalised(self):
        assert frases.obrigacoes_letradas(["Um item;", "Dois itens.", "Três"]) == (
            "a) Um item; b) Dois itens; c) Três."
        )

    def test_nothing_typed_is_empty(self):
        assert frases.obrigacoes_letradas([]) == ""
        assert frases.obrigacoes_letradas(["  ;  "]) == ""


class TestObrigacoesLocal:
    def test_default_stays_in_the_onus_clause(self):
        paragrafos = _paragrafos(1, _com_obrigacoes())
        onus = _clausula(paragrafos, "DO ÔNUS")
        assert onus[-3] == (
            "Parágrafo Único: Apresentar aos COMPRADORES a certidão de cancelamento do protesto apontado;"
        )
        assert not any(p.startswith("a) ") for p in _clausula(paragrafos, "DAS CERTIDÕES"))

    def test_certidoes_places_them_right_after_the_sellers_person_group(self):
        """Signed deal 857's shape: the lettered paragraph follows the
        seller's own group ("1 - Em nome de <vendedor>") and precedes the
        next group (here the imóvel's), never after it."""
        paragrafos = _paragrafos(1, _com_obrigacoes("certidoes"))
        certidoes = _clausula(paragrafos, "DAS CERTIDÕES")
        i = certidoes.index(ESPERADO_LETRADO)
        assert certidoes[i - 1].startswith("1.") and certidoes[i - 1].endswith(".")
        assert certidoes[i + 1].startswith("2 – Em Relação ao Imóvel")
        # gone from the ÔNUS clause — which then has no paragraph at all
        onus = _clausula(paragrafos, "DO ÔNUS")
        assert not any("Apresentar aos COMPRADORES" in p for p in onus)
        assert not any(p.startswith("Parágrafo") for p in onus)

    def test_a_company_group_comes_after_the_obligations_numbering_unchanged(self):
        """Seller person group 1, then the seller's company group 2: the
        obligations sit between them; numbering stays 1, 2, 3 (imóvel)."""
        def com_empresa(d):
            v = d.vendedores[0]
            e = fx.empresa("emp-x", CNPJ_SINTETICO, "Empresa Ficticia LTDA", "ativa", owners=[v])
            return replace(d, empresas=[e])

        sem = _clausula(_paragrafos(1, com_empresa(fx.variante(1))), "DAS CERTIDÕES")
        com = _clausula(_paragrafos(1, com_empresa(_com_obrigacoes("certidoes"))), "DAS CERTIDÕES")
        i = com.index(ESPERADO_LETRADO)
        assert com[i - 1].startswith("1.")
        assert com[i + 1] == "2 - Em nome de EMPRESA FICTICIA LTDA"
        assert [p for p in com if p != ESPERADO_LETRADO] == sem

    def test_no_seller_person_group_falls_back_to_after_all_groups(self):
        """A company seller (no seller PERSON group): after every group,
        before the imóvel's."""
        from tests.modules.card_hub.test_contrato_gerador_partes_clausulas import _pj_vendedora

        d = _pj_vendedora()
        d = replace(d, termos=replace(
            d.termos, obrigacoes_vendedor=OBRIGACOES, obrigacoes_vendedor_local="certidoes",
        ))
        certidoes = _clausula(_paragrafos(1, d), "DAS CERTIDÕES")
        i = certidoes.index(ESPERADO_LETRADO)
        assert certidoes[i - 1].startswith("1.")
        assert certidoes[i + 1].startswith("2 – Em Relação ao Imóvel")

    def test_the_certidoes_paragraph_numbering_is_unchanged(self):
        """The lettered paragraph carries no `par()` label: the certidões
        clause numbers exactly as without it."""
        sem = [p for p in _clausula(_paragrafos(1, fx.variante(1)), "DAS CERTIDÕES") if p.startswith("Parágrafo")]
        com = [
            p for p in _clausula(_paragrafos(1, _com_obrigacoes("certidoes")), "DAS CERTIDÕES")
            if p.startswith("Parágrafo")
        ]
        assert [p.split(":")[0] for p in com] == [p.split(":")[0] for p in sem]

    def test_the_legal_review_item_lists_the_text_in_both_places(self):
        for local in ("onus", "certidoes"):
            av = _avaliar(1, _com_obrigacoes(local))
            item = next(i for i in av.itens_revisao if i["codigo"] == "OBRIGACOES_VENDEDOR_TEXTO_LIVRE")
            assert "comprovante de baixa da pendência financeira" in item["texto"]

    def test_an_unknown_local_blocks(self):
        av = _avaliar(1, _com_obrigacoes("rodape"))
        assert "OBRIGACOES_VENDEDOR_LOCAL_INVALIDO" in _codigos(av.bloqueios)
