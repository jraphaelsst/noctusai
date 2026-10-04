"""S4 post-filter: every check fires on a crafted bad answer, none on realistic good ones."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from app.public_ask.postfilter import (
    MOTIVO_CAMINHO_INVALIDO,
    MOTIVO_CAMINHOS_EXCESSO,
    MOTIVO_FONTE,
    MOTIVO_PALAVRAS,
    MOTIVO_TRIAGEM,
    ResultadoPosfiltro,
    aplicar_posfiltro,
    carregar_pacote_posfiltro,
)
from app.public_ask.safety_pack.engine import LOCK_PATH, PACK_DIR, PackError, verify_lock

_WORDS = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)

BONS = [
    "Quando a gente se sente sobrecarregada, costuma achar que precisa resolver tudo de uma vez. Muitas mulheres "
    "descrevem exatamente isso: a cabeça cheia, o corpo cansado e a sensação de que o dia nunca termina. Talvez "
    "valha olhar para uma coisa só, a menor delas, e deixar o resto esperar um pouco. Perceber o que pesa mais já "
    "é um passo. Você pode conversar com alguém de confiança sobre isso, ou apenas anotar o que sente, sem "
    "pressa e sem cobrança. Cada pessoa tem o seu ritmo, e o seu merece respeito.",
    "É comum sentir culpa quando se tira um tempo para si, principalmente quando muita gente depende da gente. "
    "Esse incômodo aparece em várias histórias de mulheres que cuidam de filhos, de pais ou do trabalho ao mesmo "
    "tempo. Descansar não tira nada de ninguém. Talvez ajude pensar em um intervalo curto, de dez minutos, só "
    "seu, sem tarefas. Observe como o corpo responde depois. Se fizer sentido, volte a esse pequeno hábito "
    "outras vezes durante a semana, aos poucos, do jeito que couber na sua rotina.",
    "Relações próximas podem ter fases de distância, e isso costuma doer mesmo quando ninguém fez nada de errado. "
    "O que você descreve parece um desencontro de conversas: cada pessoa esperando que a outra dê o primeiro "
    "passo. Pode ajudar nomear com calma o que você sente e o que gostaria de ouvir, em um momento tranquilo. "
    "Nem toda conversa precisa terminar em acordo; às vezes ser escutada já alivia. Escolha o momento e as "
    "palavras que parecerem mais seguros para você, e permita que o assunto leve o tempo que levar.",
    "Mudanças grandes, como uma casa nova ou um novo trabalho, trazem entusiasmo e perda ao mesmo tempo. Sentir "
    "saudade do que ficou para trás não significa que a escolha foi errada. Muitas mulheres contam que o "
    "primeiro mês é o mais estranho, com rotinas bagunçadas e pouca energia. Vale criar pequenos pontos de "
    "apoio: um caminho conhecido, uma refeição favorita, uma ligação para quem você gosta. Aos poucos o novo "
    "lugar ganha familiaridade. Tudo bem não estar animada todos os dias, e tudo bem contar isso para alguém.",
    "Dormir mal costuma bagunçar o humor, a paciência e até a vontade de fazer coisas simples. Pode ser útil "
    "reparar no que acontece nas horas antes de deitar: telas acesas, preocupações repassadas na cabeça, "
    "cafeína tarde demais. Algumas pessoas gostam de escrever o que ficou pendente para tirar do pensamento. "
    "Outras preferem uma rotina curta e previsível, com luz baixa e silêncio. Observe o que funciona no seu "
    "caso, sem se cobrar resultados rápidos. O sono responde melhor à constância do que a esforços repentinos.",
    "Comparar a própria vida com a de outras pessoas nas redes sociais é uma armadilha conhecida: vemos os "
    "melhores momentos dos outros e todos os bastidores dos nossos. Esse incômodo é compartilhado por muita "
    "gente e diz pouco sobre o seu valor. Experimente notar quando a comparação aparece e o que você sente "
    "naquele instante. Talvez seja útil reduzir o tempo de rolagem ou seguir perfis que tragam calma. Você "
    "também pode conversar com uma amiga sobre isso. Dar atenção ao que é seu costuma devolver foco e leveza.",
    "Dizer não é difícil para quem aprendeu a agradar. Quando você sente um aperto no peito antes de aceitar um "
    "pedido, esse sinal merece atenção, porque conta algo sobre os seus limites. Pode ajudar ensaiar uma "
    "resposta simples e gentil, como pedir um tempo para pensar antes de decidir. Nem todo mundo vai gostar da "
    "mudança no começo, e isso faz parte do processo. Com a prática, o desconforto tende a diminuir. Respeitar "
    "o que cabe na sua semana é uma forma de cuidado, com você e com as outras pessoas.",
    "A saudade de alguém que se foi pode chegar em ondas, em dias comuns e em datas especiais. Não existe prazo "
    "certo para ela diminuir, e cada pessoa vive esse caminho de um jeito. Algumas mulheres encontram alívio em "
    "rituais pequenos, como acender uma vela, cozinhar uma receita da família ou olhar fotografias. Outras "
    "precisam de silêncio. Se você sente vontade de falar sobre essa pessoa, procure quem a conheceu e possa "
    "lembrar junto. Permita-se sentir o que vier, sem julgar se é muito ou pouco, cedo ou tarde.",
    "Começar algo novo depois dos quarenta anos pode soar assustador, mas muitas mulheres relatam que é "
    "justamente nessa fase que sentem mais clareza sobre o que querem. O medo de recomeçar costuma vir "
    "acompanhado de dúvidas sobre tempo e capacidade. Experimente dividir o desejo em passos pequenos e "
    "concretos, como conversar com alguém da área ou testar uma aula curta. Não é preciso decidir tudo agora. "
    "Acompanhe como você se sente a cada etapa e ajuste o rumo quando precisar. Seu interesse já é um bom começo.",
    "Uma garantia de qualidade do pão da padaria, o preço justo e o cuidado no atendimento podem parecer detalhes, "
    "mas pequenos prazeres do cotidiano sustentam o ânimo mais do que imaginamos. Se hoje o dia foi pesado, talvez "
    "valha procurar um desses momentos simples: um café quente, uma caminhada curta, uma música que você "
    "gosta. Eles não resolvem tudo, e nem precisam. Servem como pausa para respirar e recuperar um pouco de "
    "disposição. Perceba o que traz conforto a você e dê espaço para isso na sua semana, sem pressa e sem culpa.",
]


@pytest.fixture(scope="module")
def pacote():
    return carregar_pacote_posfiltro()


def _run(pacote, texto, caminhos=("quero_pensar_mais",), fonte=("a",), recup=("a", "b")):
    return aplicar_posfiltro(texto, caminhos, fonte_ids=fonte, fonte_ids_recuperadas=recup, pacote=pacote)


def _pad(frase: str, base: int = 0) -> str:
    """A good answer with ``frase`` spliced in (keeps the word count in range)."""
    return BONS[base] + " " + frase


def test_good_answers_are_in_range_and_pass(pacote):
    assert len(BONS) >= 8
    for i, b in enumerate(BONS):
        n = len(_WORDS.findall(b))
        assert 80 <= n <= 130, (i, n)
        r = _run(pacote, b)
        assert r.ok, (i, r.motivos)
        assert r.texto == b and r.motivos == () and r.caminhos == ("quero_pensar_mais",)


def test_garantia_does_not_trip_garanto(pacote):
    # BONS[-1] contains "garantia" - whole-word matching: only the verb form "garanto" is a promise.
    assert "garantia" in BONS[-1]
    assert _run(pacote, BONS[-1]).ok
    assert "promessa" in _run(pacote, _pad("Eu garanto que passa.", 0)).motivos


@pytest.mark.parametrize(
    "check,frase",
    [
        ("diagnostico", "Isso parece depressão."),
        ("diagnostico", "Talvez seja um transtorno de ansiedade."),
        ("diagnostico", "Você pode ter TDAH."),
        ("diagnostico", "Esse é um diagnóstico comum."),
        ("medicacao", "Um antidepressivo ajudaria."),
        ("medicacao", "Pergunte sobre a dose do remédio."),
        ("medicacao", "Tome 50 mg à noite."),
        ("promessa", "Vai ficar tudo bem."),
        ("promessa", "Eu garanto que passa."),
        ("promessa", "Te prometo que melhora."),
        ("promessa", "Tudo vai passar logo."),
        ("vinculo", "Estou aqui com você."),
        ("vinculo", "Pode contar comigo."),
        ("vinculo", "Sempre estarei por perto."),
        ("vinculo", "Volte sempre que quiser."),
        ("substituicao", "Você não precisa de terapia."),
        ("substituicao", "Conversar comigo substitui a terapia."),
        ("substituicao", "Não precisa de psicólogo."),
        ("aconselhamento_individual", "Você deveria se divorciar."),
        ("aconselhamento_individual", "Pare de tomar isso."),
        ("aconselhamento_individual", "Contrate um advogado."),
        ("nao_e_x_e_y", "Não é preguiça, é cansaço."),
        ("nao_e_x_e_y", "Não é fraqueza e sim cuidado."),
    ],
)
def test_each_check_fires_on_bad_answer(pacote, check, frase):
    # Replace the tail of a good answer so the word count stays in range and only ``check`` is at issue.
    palavras = BONS[0].split()
    base = " ".join(palavras[: len(palavras) - 6]) + "."
    r = _run(pacote, base + " " + frase)
    assert not r.ok
    assert check in r.motivos, r.motivos


def test_spelling_variants_are_caught(pacote):
    palavras = BONS[0].split()
    base = " ".join(palavras[:-5]) + "."
    for frase in ("ESTOU AQUI COM VOCE!", "vai ficar tuuudo bem", "Depressão."):
        assert not _run(pacote, base + " " + frase).ok


def test_word_count_bounds(pacote):
    assert MOTIVO_PALAVRAS in _run(pacote, "Texto curto demais.").motivos
    longo = BONS[0] + " " + BONS[1]
    assert MOTIVO_PALAVRAS in _run(pacote, longo).motivos
    justo79 = " ".join(["calma"] * 79)
    assert MOTIVO_PALAVRAS in _run(pacote, justo79).motivos
    assert MOTIVO_PALAVRAS not in _run(pacote, " ".join(["calma"] * 80)).motivos
    assert MOTIVO_PALAVRAS not in _run(pacote, " ".join(["calma"] * 130)).motivos
    assert MOTIVO_PALAVRAS in _run(pacote, " ".join(["calma"] * 131)).motivos


def test_paths_checks(pacote):
    assert MOTIVO_CAMINHOS_EXCESSO in _run(
        pacote, BONS[0], caminhos=("quero_pensar_mais", "prefiro_fazer_algo_agora", "quero_pensar_mais")
    ).motivos
    assert MOTIVO_CAMINHO_INVALIDO in _run(pacote, BONS[0], caminhos=("inventado",)).motivos
    ok = _run(pacote, BONS[0], caminhos=("quero_pensar_mais", "prefiro_fazer_algo_agora"))
    assert ok.ok and len(ok.caminhos) == 2


def test_fonte_ids_must_be_retrieved(pacote):
    assert MOTIVO_FONTE in _run(pacote, BONS[0], fonte=("a", "zzz")).motivos
    assert _run(pacote, BONS[0], fonte=(), recup=()).ok


def test_output_triage_above_verde_fails(pacote):
    palavras = BONS[0].split()
    base = " ".join(palavras[:-6]) + "."
    r = _run(pacote, base + " Às vezes dá vontade de me matar.")
    assert not r.ok and MOTIVO_TRIAGEM in r.motivos


def test_fallback_shape_and_no_text_in_motivos(pacote):
    segredo = "SENTINELA-ZZ depressão garanto"
    r = _run(pacote, segredo, fonte=("x",), recup=())
    assert isinstance(r, ResultadoPosfiltro) and not r.ok
    assert r.texto == pacote.fallback_texto and "SENTINELA" not in r.texto
    assert r.caminhos == ("quero_pensar_mais", "prefiro_fazer_algo_agora")
    assert len(r.caminhos) <= 2 and set(r.caminhos) <= pacote.caminhos_permitidos
    blob = json.dumps(r.motivos).lower()
    assert "sentinela" not in blob and "depress" not in blob and "garanto" not in blob
    for m in r.motivos:
        assert re.fullmatch(r"[a-z_]+", m)


def test_pack_is_a_draft_and_fallback_is_natural_length(pacote):
    assert pacote.rascunho is True
    assert 80 > len(_WORDS.findall(pacote.fallback_texto)) >= 20


def test_lock_covers_posfiltro_and_tamper_is_refused(tmp_path):
    assert "posfiltro.json" in verify_lock()["files"]
    pack = tmp_path / "limiar"
    shutil.copytree(PACK_DIR, pack)
    (pack / "posfiltro.json").write_text(
        (pack / "posfiltro.json").read_text(encoding="utf-8").replace("rascunho", "aprovado"), encoding="utf-8"
    )
    with pytest.raises(PackError):
        carregar_pacote_posfiltro(pack_dir=pack, lock_path=LOCK_PATH)


def test_unknown_app_refused():
    with pytest.raises(PackError):
        carregar_pacote_posfiltro("outro")
