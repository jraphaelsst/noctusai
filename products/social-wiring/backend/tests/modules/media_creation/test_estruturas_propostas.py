"""EST-4a: the server-side validator of the chat agent's proposals (estruturas-contract.md section 8.5)."""
import uuid

from app.modules.media_creation.services.propostas import (
    EstruturaCitavel,
    PropostaValidada,
    ResultadoPropostas,
    extrair_propostas,
)

A, B, C, D = (uuid.uuid4() for _ in range(4))
PERMITIDOS = {
    "10": EstruturaCitavel(A, "10", "reels"),
    "11": EstruturaCitavel(B, "11", "reels"),
    "12": EstruturaCitavel(C, "12", "reels"),
    "13": EstruturaCitavel(D, "13", "reels"),
    "20": EstruturaCitavel(uuid.uuid4(), "20", "carrossel"),
}


def _ev(r: ResultadoPropostas) -> dict:
    return {e["tipo"]: e["contagem"] for e in r.eventos}


def test_the_pinned_seam_shape():
    r = extrair_propostas("1. Pare de adiar o seu sorriso (estrutura #10)", PERMITIDOS)
    assert isinstance(r, ResultadoPropostas) and r.propostas == (
        PropostaValidada(ordem=1, headline="Pare de adiar o seu sorriso", gatilho=None, estrutura_ids=(A,)),
    )
    assert r.eventos == ()


def test_numbered_headlines_with_single_and_mixed_citations_and_the_gatilho_tag():
    texto = (
        "### Análise da Estrutura Escolhida\nTexto.\n\n"
        "1. **Pare de sofrer com dor de dente** (Recompensa) (estrutura #10)\n"
        "2. Ninguém te conta isso sobre implantes (estrutura #11 + #12)\n"
        "3. Seu sorriso merece mais (estrutura #10 + #11 + #12)\n"
        "\n### Estruturas usadas\n- #10 (@fulano): Gancho, Prova\n- #11 (@sicrano): CTA\n"
    )
    r = extrair_propostas(texto, PERMITIDOS)
    assert [p.ordem for p in r.propostas] == [1, 2, 3]
    assert r.propostas[0].headline == "Pare de sofrer com dor de dente" and r.propostas[0].gatilho == "Recompensa"
    assert r.propostas[1].estrutura_ids == (B, C) and r.propostas[2].estrutura_ids == (A, B, C)
    assert r.eventos == ()  # the "Estruturas usadas" bullets are never headlines


def test_a_code_outside_the_context_is_dropped_and_counted():
    r = extrair_propostas("1. Headline boa aqui (estrutura #10 + #999)\n2. Outra headline boa (estrutura #888)", PERMITIDOS)
    assert [p.estrutura_ids for p in r.propostas] == [(A,)]  # #2 has no valid code left -> not a proposta
    assert _ev(r) == {"citacao_rejeitada": 2}


def test_a_different_formato_code_is_dropped_the_principal_is_the_first_valid_code():
    r = extrair_propostas("1. Headline para o carrossel (estrutura #20 + #10)\n2. Outra para reels aqui (estrutura #10 + #20 + #11)", PERMITIDOS)
    assert r.propostas[0].estrutura_ids == (PERMITIDOS["20"].id,)  # #20 is the principal; the reels #10 is dropped
    assert r.propostas[1].estrutura_ids == (A, B)
    assert _ev(r) == {"formato_misturado": 2}


def test_more_than_three_codes_keeps_three_and_counts_the_rest():
    r = extrair_propostas("1. Headline com muitas Estruturas (estrutura #10 + #11 + #12 + #13)", PERMITIDOS)
    assert r.propostas[0].estrutura_ids == (A, B, C) and _ev(r) == {"citacao_rejeitada": 1}


def test_a_headline_with_a_leftover_placeholder_is_dropped_and_counted():
    r = extrair_propostas(
        "1. Como a [autoridade teórica] muda tudo (estrutura #10)\n2. Headline completa de verdade (estrutura #10)", PERMITIDOS
    )
    assert [p.headline for p in r.propostas] == ["Headline completa de verdade"] and r.propostas[0].ordem == 1
    assert _ev(r) == {"placeholder_remanescente": 1}


def test_no_parsable_headline_is_an_empty_result():
    assert extrair_propostas("Preciso saber mais sobre o seu nicho. Qual o público?", PERMITIDOS) == ResultadoPropostas((), ())
    assert extrair_propostas("", PERMITIDOS).propostas == ()


def test_at_most_ten_and_duplicates_collapse():
    linhas = "\n".join(f"{i}. Headline número {i} bem distinta (estrutura #10)" for i in range(1, 15))
    linhas += "\n1. Headline número 1 bem distinta (estrutura #11)"
    r = extrair_propostas(linhas, PERMITIDOS)
    assert len(r.propostas) == 10 and [p.ordem for p in r.propostas] == list(range(1, 11))


def test_an_uncited_numbered_headline_counts_as_a_rejected_citation_but_prose_bullets_do_not():
    r = extrair_propostas("1. Headline sem nenhuma citação\n- uma observação qualquer sobre o tema\n2. Esta tem (estrutura #10) certo", PERMITIDOS)
    assert len(r.propostas) == 1 and _ev(r) == {"citacao_rejeitada": 1}


def test_questions_are_never_counted_and_accents_in_the_tag_are_tolerated():
    r = extrair_propostas("1. Você quer saber mais?\n2. Headline com tag sem acento (Misterio) (estrutura #10)", PERMITIDOS)
    assert r.propostas[0].gatilho == "Mistério" and r.eventos == ()


def test_the_validator_never_touches_a_database():
    import ast
    from pathlib import Path

    from app.modules.media_creation.services import propostas

    fontes = ast.parse(Path(propostas.__file__).read_text())
    imports = {n.module or "" for n in ast.walk(fontes) if isinstance(n, ast.ImportFrom)}
    assert not any("supabase" in m or "client" in m or "dependencies" in m for m in imports)
