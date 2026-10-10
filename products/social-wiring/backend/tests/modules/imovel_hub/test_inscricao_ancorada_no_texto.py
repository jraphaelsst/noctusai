"""Owner rule (2026-10-10): the inscrição is stored exactly as printed.

Live e2e: a Cotia/SP guia de IPTU photo printed `23252-53-55-0304-00-000`;
the LLM re-typed it `3225-53-55-0304-00-000`. The value must be grounded in
the page text.
"""
from app.modules.imovel_hub.documentos_service import _ancorar_inscricao

PAGINA = (
    "PREFEITURA DE COTIA\nGUIA DE IPTU 2026\n"
    "INSCRIÇÃO CADASTRAL 23252-53-55-0304-00-000\nVENCIMENTO 10/10/2026\n"
)


def test_valor_redigitado_pela_ia_e_substituido_pelo_impresso():
    out = _ancorar_inscricao({"inscricao_imobiliaria": "3225-53-55-0304-00-000"}, PAGINA)
    assert out == {"inscricao_imobiliaria": "23252-53-55-0304-00-000"}


def test_valor_fiel_mantem_a_pontuacao_impressa():
    out = _ancorar_inscricao({"inscricao_imobiliaria": "23252.53.55.0304.00.000"}, PAGINA)
    assert out == {"inscricao_imobiliaria": "23252-53-55-0304-00-000"}


def test_sem_rotulo_e_sem_o_valor_no_texto_descarta():
    out = _ancorar_inscricao({"inscricao_imobiliaria": "3225-53-55-0304-00-000"}, "sem nada")
    assert out is None


def test_outros_campos_sobrevivem_ao_descarte():
    out = _ancorar_inscricao(
        {"inscricao_imobiliaria": "1111-22", "numero": "9"}, "sem nada"
    )
    assert out == {"numero": "9"}
