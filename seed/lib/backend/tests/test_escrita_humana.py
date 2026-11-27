"""escrita_humana: every check has a pt-BR positive and a negative; a natural human paragraph passes."""
from __future__ import annotations

import pytest

from noctusai_lib.primitives.escrita_humana import PERFIS, checar_escrita, config, texto_falado

HUMANO = (
    "Fui ontem na feira. Comprei manga. Estava doce demais, quase não acreditei, e ainda voltei com troco. "
    "Minha mãe riu quando contei que a vendedora me chamou de moço. Eu tinha acabado de cortar o cabelo, "
    "então fez sentido. No fim, levei duas caixas pra casa e dividi com os vizinhos."
)


def codigos(texto, perfil="legenda", **kw):
    return [c.split(":")[0] for c in checar_escrita(texto, perfil=perfil, **kw)]


def test_paragrafo_humano_passa_em_todos_os_perfis_textuais():
    for perfil in ("chat", "legenda"):
        assert checar_escrita(HUMANO, perfil=perfil) == []


def test_json_tem_nota_de_calibracao_e_perfis_de_emoji():
    assert "_nota" in config()
    assert set(config()["emoji_max"]) == set(PERFIS)


@pytest.mark.parametrize("perfil", PERFIS)
def test_travessao_em_dash_e_proibido(perfil):
    assert "travessao:1" in checar_escrita("O preço caiu — e muito.", perfil=perfil)


def test_travessao_en_dash_como_pausa_sim_faixa_numerica_nao():
    assert "travessao:1" in checar_escrita("Foi rápido – quase imediato.", perfil="legenda")
    assert checar_escrita("Treine de 10–12 repetições por série.", perfil="legenda") == []
    assert checar_escrita("Ligue-me amanhã, guarda-chuva e bem-vindo.", perfil="legenda") == []


@pytest.mark.parametrize("texto", [
    "Não é sorte, é método.", "Não é caro. É justo.", "Não se trata de preço, mas de valor.",
    "Não se trata de preço e sim de valor.", "Não só vende, mas também ensina.",
])
def test_contraste_nao_e(texto):
    # headline: zero allowed; elsewhere one is fine and two are not
    assert any(c.startswith("contraste_nao_e") for c in checar_escrita(texto, perfil="headline"))
    assert not any(c.startswith("contraste_nao_e") for c in checar_escrita(texto, perfil="legenda"))
    assert any(c.startswith("contraste_nao_e") for c in checar_escrita(f"{texto} {texto}", perfil="legenda"))


def test_contraste_negativo_frase_normal():
    assert "contraste_nao_e" not in codigos("Não é possível agendar hoje. Fica para segunda.", "legenda")


def test_triade_headline_e_limite_em_outros():
    t = "Mais alcance, mais vendas e mais tempo."
    assert "triade" in codigos(t, "headline")
    assert "triade" not in codigos(t, "legenda")
    assert "triade" in codigos(f"{t} Menos custo, menos risco e menos dúvida.", "legenda")


def test_triade_negativos():
    assert "triade" not in codigos("Comprei pão e leite.", "headline")
    assert "triade" not in codigos("Oi, tudo bem e você?", "chat")
    assert "triade" not in codigos("Primeiro eu fui ao mercado comprar pão, leite e ovos para a semana inteira.", "headline")


def test_lexico_ia_lista_as_palavras():
    r = checar_escrita("É crucial iniciar essa jornada.", perfil="headline")
    assert "lexico_ia:crucial,jornada" in r


def test_lexico_ia_densidade_por_150_palavras():
    corpo = " ".join(["Hoje cedo eu saí para caminhar na praia."] * 20)  # 180 palavras
    assert checar_escrita(f"{corpo} Vale ressaltar o sol.", perfil="legenda") == []
    assert any(c.startswith("lexico_ia") for c in checar_escrita(f"{corpo} Vale ressaltar o sol. A jornada seguiu.", perfil="legenda"))
    assert any(c.startswith("lexico_ia") for c in checar_escrita("Vale ressaltar o sol.", perfil="legenda"))


def test_lexico_so_palavra_inteira_e_sem_acento():
    assert "lexico_ia" not in codigos("Ela caminha devagar pela vaga ao lado.", "headline")
    assert "lexico_ia" not in codigos("Mergulhadores profissionais chegaram.", "headline")
    assert "lexico_ia:cenario em constante evolução" not in checar_escrita("x", perfil="headline")
    assert any(c.startswith("lexico_ia") for c in checar_escrita("No cenario atual, tudo muda.", perfil="headline"))
    assert any(c.startswith("lexico_ia") for c in checar_escrita("Mergulhe nesse tema.", perfil="headline"))


def test_devagar_nao_casa_vaga():
    # a list term "vaga" must never hit inside "devagar" (whole-word matching)
    from noctusai_lib.primitives.escrita_humana import _alternancia

    assert _alternancia(["vaga"]).search("fala devagar") is None
    assert _alternancia(["vaga"]).search("uma vaga aberta") is not None


@pytest.mark.parametrize("texto", ["Ótima pergunta! Vamos ver.", "Claro! Segue o plano.", "Certamente, aqui vai.", "Com certeza! Já resolvo."])
def test_abertura_bajuladora(texto):
    assert "abertura_bajuladora" in checar_escrita(texto, perfil="chat")


def test_abertura_natural_passa():
    assert "abertura_bajuladora" not in checar_escrita("Claro que não, eu preciso do número antes.", perfil="chat")


@pytest.mark.parametrize("fim", ["Espero ter ajudado.", "Fico à disposição.", "Qualquer dúvida, estou à disposição.", "Se precisar de algo, é só falar.", "Não hesite em chamar."])
def test_fechamento_cliche(fim):
    assert "fechamento_cliche" in checar_escrita(f"O prazo é sexta. {fim}", perfil="chat")


def test_fechamento_so_na_ultima_frase():
    assert "fechamento_cliche" not in checar_escrita("Fico à disposição na sexta. O prazo é segunda.", perfil="chat")


def test_aspas_curvas():
    assert "aspas_curvas" in checar_escrita("Ele disse “sim” e saiu.", perfil="legenda")
    assert "aspas_curvas" not in checar_escrita('Ele disse "sim" e saiu.', perfil="legenda")


def test_title_case():
    assert "title_case" in checar_escrita("Como Fazer Um Bom Roteiro Para Reels", perfil="headline")
    assert "title_case" not in checar_escrita("Como fazer um bom roteiro para reels", perfil="headline")
    # proper nouns of a natural sentence are not Title Case
    assert "title_case" not in checar_escrita("Fui com Maria a São Paulo ver o Pedro tocar violão no bar", perfil="headline")
    assert "title_case" not in checar_escrita("Como Fazer Um Bom Roteiro Para Reels", perfil="chat")
    assert "title_case" not in checar_escrita("Roteiro Bom Reels Rápido", perfil="headline", nomes_proprios=["Roteiro", "Bom", "Reels", "Rápido"])


def test_markdown_so_no_chat():
    md = "**Atenção**\n- item um\n- item dois"
    assert "markdown_no_chat" in checar_escrita(md, perfil="chat")
    assert "markdown_no_chat" in checar_escrita("1. primeiro\n2. segundo", perfil="chat")
    assert "markdown_no_chat" in checar_escrita("# Título\ntexto", perfil="chat")
    assert "markdown_no_chat" not in checar_escrita(md, perfil="legenda")
    assert "markdown_no_chat" not in checar_escrita("Preço de 5-6 reais.", perfil="chat")


@pytest.mark.parametrize("perfil,n_ok", [("chat", 1), ("legenda", 3), ("roteiro", 0), ("headline", 1)])
def test_emoji_limites(perfil, n_ok):
    ok = "Bora 😀" * 0 + "texto" + "🙂" * n_ok
    ruim = "texto" + "🙂" * (n_ok + 1)
    assert not any(c.startswith("emoji_excesso") for c in checar_escrita(ok, perfil=perfil))
    assert f"emoji_excesso:{n_ok + 1}" in checar_escrita(ruim, perfil=perfil)


def test_conectivos_densidade_e_consecutivos():
    assert any(c.startswith("conectivos_densos") for c in checar_escrita("Além disso, vale. Por outro lado, custa.", perfil="legenda"))
    assert "conectivos_consecutivos" in checar_escrita("Eu fui. Além disso, comprei. Dessa forma, voltei.", perfil="legenda")
    assert not any(c.startswith("conectivos") for c in checar_escrita("Fui à loja. Além disso, comprei pão.", perfil="legenda"))


def test_giria_registro():
    assert "giria:pra,ta" in checar_escrita("Tá bom, vou pra casa.", perfil="legenda", registro="formal")
    assert not any(c.startswith("giria") for c in checar_escrita("Tá bom, vou pra casa.", perfil="legenda"))
    assert "giria:pq,vc" in checar_escrita("Pq vc não veio?", perfil="legenda")
    assert "giria:kkk,tbm" in checar_escrita("eu tbm kkkk", perfil="chat")
    assert not any(c.startswith("giria") for c in checar_escrita("Preço de tabela, tubo e tabuleiro.", perfil="chat", registro="formal"))


UNIFORME = "Eu fui à loja comprar pão hoje cedo. Depois eu voltei para casa com pão fresco. Então eu fiz o café da manhã. Por fim eu comi tudo sozinho."
VARIADO = "Parei. Olhei o relógio e vi que faltavam dez minutos para o ônibus passar na esquina da padaria. Corri. Peguei o último lugar na janela, ofegante, rindo sozinho do susto."


def test_ritmo_so_roteiro():
    r = checar_escrita(UNIFORME, perfil="roteiro")
    assert any(c.startswith("ritmo_uniforme") for c in r)
    assert any(c.startswith("frases_muito_curtas") for c in r)
    assert not any(c.startswith(("ritmo_", "frases_")) for c in checar_escrita(UNIFORME, perfil="legenda"))
    assert not any(c.startswith(("ritmo_", "frases_")) for c in checar_escrita(VARIADO, perfil="roteiro"))


def test_ritmo_codigos_antigos_continuam():
    longo = " ".join(["Eu vou explicar com calma cada detalhe importante desse assunto aqui para voce."] * 4)
    assert any(c.startswith("frases_curtas:") for c in checar_escrita(longo, perfil="roteiro"))
    rep = "Olha isso agora mesmo. Foi rápido.\n\nOlha isso de novo. Foi longo."
    assert "abertura_repetida:olha isso" in checar_escrita(rep, perfil="roteiro")


CARROSSEL = """**Slide 1 — Gancho do bloco**
Cansou de postar sem resposta?
**Slide 2 — Virada**
Mude o primeiro quadro do vídeo e teste essa mudança por uma semana inteira, sem pressa nenhuma.
**Quadro 3 — Fecho**
Salve esse post pra depois.
**Tela 4** Comente a sua dúvida.
### Texto na tela
(Gancho) Poste hoje, que o resultado aparece rápido."""


def test_carrossel_valido_passa_com_markup_estrutural():
    assert "—" in CARROSSEL
    assert checar_escrita(CARROSSEL, perfil="roteiro") == []


def test_markup_estrutural_nao_vira_title_case_nem_ritmo_nem_travessao():
    assert "Gancho" not in texto_falado("(Gancho) Poste hoje.")
    assert "Slide" not in texto_falado(CARROSSEL)
    assert "Comente a sua dúvida." in texto_falado(CARROSSEL)
    # but a dash in the spoken text itself still fails
    assert "travessao:1" in checar_escrita("**Slide 1 — Gancho**\nEu fui — e voltei.", perfil="roteiro")


def test_perfil_e_registro_invalidos():
    with pytest.raises(ValueError):
        checar_escrita("x", perfil="blog")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        checar_escrita("x", perfil="chat", registro="neutro")  # type: ignore[arg-type]


def test_texto_vazio_passa():
    assert checar_escrita("", perfil="roteiro") == []
