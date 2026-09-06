"""The adapter — where the two vocabularies meet.

Every assertion here covers a failure that does NOT raise. A mis-mapped field
scores zero forever; a wrongly-read `aceita_permutas` empties the result set;
an unreported unresolvable code reads as "this property has no matches". None
of those surface as an error, which is exactly why they need pinning.
"""
from __future__ import annotations

from app.modules.permutas import adapter


def _linha_imovel_catalogo(**over) -> dict:
    """A row shaped like `social_wiring.imoveis` — Vista's column names."""
    base = {
        "codigo": "ONE9265",
        "titulo": "Casa em condomínio na Granja",
        "categoria": "Casa em Condomínio",
        "cidade": "Carapicuíba",
        "bairro": "Aldeia da Fazendinha",
        "uf": "SP",
        "zona": None,
        "regiao": "Oeste",
        "empreendimento": "Aldeia da Fazendinha - Km 23",
        "valor_venda": "1780000.00",
        "area_total": "649.00",
        "area_privativa": "268.00",
        "dormitorios": 3,
        "suites": 2,
        "vagas": 4,
        "descricao_web": "Casa ampla com quintal",
        "fotos": ["a.jpg", "b.jpg", "c.jpg"],
        "tour_360": "https://tour",
        "corretores": [{"nome": "Ana Maria", "email": "anamaria@x.com.br"}],
    }
    base.update(over)
    return base


def _intencao(**over) -> dict:
    base = {
        "id": "at-1",
        "natureza": "imovel",
        "imovel_codigo": "ONE9265",
        "status": "ativo",
        "observacoes": "Aceita permuta com apartamento no Morumbi",
        "regiao_preferida": ["Morumbi"],
        "faixa_preco_min": None,
        "faixa_preco_max": 1_000_000,
        "aceita_completar_diferenca": True,
    }
    base.update(over)
    return base


class TestNomesQueDiscordam:
    """The four columns whose names differ between Vista and the scorer.

    Each of these silently scores zero if mapped wrong — `valor` missing means
    the price category returns 0 and the pair fails the two-of-three gate for
    a reason that has nothing to do with the property.
    """

    def test_valor_vem_de_valor_venda(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["valor"] == 1_780_000.0

    def test_estado_vem_de_uf(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["estado"] == "SP"

    def test_quartos_vem_de_dormitorios(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["quartos"] == 3

    def test_tipo_imovel_vem_de_categoria(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["tipo_imovel"] == "Casa em Condomínio"

    def test_condominio_vem_de_empreendimento(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["condominio_nome"] == "Aldeia da Fazendinha - Km 23"

    def test_zona_cai_para_regiao_quando_ausente(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["zona"] == "Oeste"

    def test_numericos_string_do_driver_viram_float(self):
        """Numeric columns arrive as strings/Decimal; the scorer does maths."""
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert isinstance(d["area_total"], float)
        assert d["area_privativa"] == 268.0


class TestAceitaPermutasEDerivado:
    """🔴 `imoveis.aceita_permuta` is NULL on all 2065 rows.

    Reading the stored column would make `gerar_matches_para_permuta` skip
    every listing — it hard-requires the flag — and return zero matches while
    reporting success. The intent row IS the acceptance.
    """

    def test_intencao_registrada_implica_aceita_permutas(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        assert d["aceita_permutas"] is True

    def test_nao_le_a_coluna_nula_do_catalogo(self):
        d = adapter.ativo_para_scorer(
            _intencao(), imovel=_linha_imovel_catalogo(aceita_permuta=None)
        )
        assert d["aceita_permutas"] is True


class TestImovelSemCatalogoEhNone:
    """An `imovel` intent with no resolvable listing must be dropped, loudly.

    Emitting a stub would put a property with no price, area or location into
    the candidate pool, where it scores against everything on empty fields.
    """

    def test_sem_imovel_retorna_none(self):
        assert adapter.ativo_para_scorer(_intencao(), imovel=None) is None

    def test_permuta_nao_precisa_de_catalogo(self):
        """The other side carries its own snapshot — 52 legacy refs are not
        and never will be in the catalog."""
        d = adapter.ativo_para_scorer(
            {
                "id": "pm-1",
                "natureza": "permuta_imovel",
                "status": "ativo",
                "tipo_imovel": "Casa",
                "cidade": "Cotia",
                "uf": "SP",
                "valor": 900_000,
                "regiao_preferida": [],
            },
            imovel=None,
        )
        assert d is not None
        assert d["valor"] == 900_000.0
        assert d["estado"] == "SP"


class TestInteressesViramAListaDoScorer:
    def test_valor_minimo_maximo_viram_valor_min_max(self):
        """The table's column names and the scorer's key names differ."""
        d = adapter.interesse_para_scorer(
            {"tipo": "imovel", "valor_minimo": "500000.00", "valor_maximo": "900000.00"}
        )
        assert d["valor_min"] == 500_000.0
        assert d["valor_max"] == 900_000.0

    def test_tipo_ausente_assume_imovel(self):
        assert adapter.interesse_para_scorer({})["tipo"] == "imovel"

    def test_interesses_chegam_no_ativo_projetado(self):
        d = adapter.ativo_para_scorer(
            _intencao(),
            imovel=_linha_imovel_catalogo(),
            interesses=[{"tipo": "imovel", "tipo_imovel": "Apartamento"}],
        )
        assert d["interesses"] == [
            {
                "tipo": "imovel",
                "tipo_imovel": "Apartamento",
                "cidade": None,
                "bairro": None,
                "zona": None,
                "valor_min": None,
                "valor_max": None,
                "marca": None,
                "modelo": None,
                "observacoes": None,
            }
        ]


class TestTextosDeEmbedding:
    def test_o_texto_de_interesses_lidera_pela_prosa(self):
        """🔴 The prose comes FIRST.

        The structured criteria are near-empty in this corpus (`cidade` set on
        0 of 135 legacy rows) while the sentence carries the real constraint.
        Burying it behind a list of mostly-null fields is how the only signal
        that exists gets diluted.
        """
        texto = adapter.texto_interesses_para_embedding(
            {"observacoes": "casa sem escada, rua sem ladeira"},
            [{"tipo_imovel": "Casa", "valor_maximo": 800000}],
        )
        assert texto.startswith("casa sem escada, rua sem ladeira")
        assert "Procura: tipo Casa" in texto

    def test_percentual_entra_no_texto(self):
        """"Estuda permuta de 30% a 50%" is the most common note in the data
        and the legacy schema had nowhere to put it."""
        texto = adapter.texto_interesses_para_embedding(
            {"observacoes": ""},
            [{"percentual_min": 30, "percentual_max": 50}],
        )
        assert "30% a 50%" in texto

    def test_sem_nada_declarado_retorna_vazio(self):
        """An ativo that stated nothing gets NO interest vector.

        Embedding a generic stand-in would sit at similar distance from every
        listing and manufacture bilateral matches out of nothing.
        """
        assert adapter.texto_interesses_para_embedding({"observacoes": ""}, []) == ""

    def test_perfil_usa_os_dados_do_catalogo(self):
        d = adapter.ativo_para_scorer(_intencao(), imovel=_linha_imovel_catalogo())
        texto = adapter.texto_para_embedding(d)
        assert "Casa em Condomínio" in texto
        assert "Aldeia da Fazendinha" in texto
        assert "268.0m²" in texto or "268m²" in texto
