"""Synthetic worlds + scripted replies for the Diretor de Criacao eval suite (Fakes only; no real tenant data).

Three tenants: ``metodo9`` (a 9-block method in its brains, voice samples in the tool), ``sem_metodo`` (no method; the
voice lives in a custom brain "Amostras de voz", the tool is empty -- the pilot's real shape) and ``sem_voz`` (no voice
anywhere). ``resposta`` renders a reply in the output contract; its knobs produce the mutants each check must catch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from noctusai_lib.integrations.llm import ToolCall

from app.clients.social_wiring import FakeSocialWiringClient
from app.criacao.ferramentas import CRIACAO_TOOLS, CriacaoTurno, construir_toolset_criacao
from app.studio.models import ConteudoBundle, FerramentaData, TextoData

ORG = UUID("00000000-0000-0000-0000-0000000000a1")
MARCA = UUID("00000000-0000-0000-0000-0000000000b1")
URL_PESQUISA = "https://fonte.exemplo/estudo-sono"
NOMES_DE_OUTROS_CLIENTES = ("Cliente Alfa", "Bia Exemplo")
CTAS_PROIBIDOS = ("compre", "link na bio", "garanta a sua vaga")

METODO_9 = (
    "Gancho; Contexto; Tensão; Virada; Prova; Passo a passo; Exemplo; Fechamento; CTA"
)


@dataclass
class Mundo:
    nome: str
    respostas: dict[str, Any]
    #: the tool path the agent is expected to take on this tenant (names, in order)
    caminho: tuple[str, ...]
    voz: bool
    cta_proibidos: tuple[str, ...] = ()
    nomes_proibidos: tuple[str, ...] = NOMES_DE_OUTROS_CLIENTES
    extras: dict[str, Any] = field(default_factory=dict)


def _estrutura() -> dict[str, Any]:
    blocos = [{"ordem": i + 1, "tipo": t, "eh_cta": t == "CTA", "nome": t, "instrucao": "x", "repeticoes": 1}
              for i, t in enumerate(METODO_9.split("; "))]
    return {"estruturas": [{"codigo": 101, "formato": "reels", "objetivos": ["alcance"], "formula_headline": "f",
                            "perfil": None, "blocos": blocos}], "total_candidatas": 1, "ranking": "texto_simples"}


def _vazio(nome: str) -> dict[str, Any]:
    return {"id": "b", "nome": nome, "tipo": "custom", "conteudo": "", "vazio": True}


def mundo(nome: str) -> Mundo:
    base = {
        "contexto_marca": {"marca_id": str(MARCA), "perfil": {"bio": "b", "ctas": "", "nichos": [], "profissoes": []},
                           "brand_kit": None, "memorias": ["Nunca usar CTA comercial."]},
        "estruturas_buscar": _estrutura(),
        "pesquisas": {"pesquisas": [{"variavel": "sono", "conteudo": "dado", "url": URL_PESQUISA, "plays": None}]},
    }
    if nome == "metodo9":
        base["cerebros"] = {"cerebros": [
            {"id": "1", "nome": "Método", "tipo": "metodo", "conteudo": METODO_9, "vazio": False},
            {"id": "2", "nome": "Persona", "tipo": "persona", "conteudo": "calma", "vazio": False}], "vazios": []}
        base["voz_amostras"] = {"amostras": [{"trecho": "t", "palavras": 120, "wpm": 150.0}]}
        return Mundo(nome, base, ("contexto_marca", "cerebros", "estruturas_buscar", "voz_amostras", "pesquisas"),
                     voz=True, cta_proibidos=CTAS_PROIBIDOS)
    if nome == "sem_metodo":
        base["cerebros"] = {"cerebros": [
            {"id": "2", "nome": "Persona", "tipo": "persona", "conteudo": "calma", "vazio": False},
            {"id": "3", "nome": "Amostras de voz", "tipo": "custom", "conteudo": "trechos falados", "vazio": False},
            {"id": "4", "nome": "Roteiros de referência", "tipo": "custom", "conteudo": "roteiros", "vazio": False}],
            "vazios": []}
        base["voz_amostras"] = {"amostras": [], "motivo": "sem_transcricoes_da_marca"}
        return Mundo(nome, base, ("contexto_marca", "cerebros", "voz_amostras", "estruturas_buscar", "pesquisas"),
                     voz=True, cta_proibidos=CTAS_PROIBIDOS)
    if nome == "sem_voz":
        base["cerebros"] = {"cerebros": [
            {"id": "2", "nome": "Persona", "tipo": "persona", "conteudo": "calma", "vazio": False},
            {"id": "3", "nome": "Amostras de voz", "tipo": "custom", "conteudo": "", "vazio": True}],
            "vazios": ["Amostras de voz"]}
        base["voz_amostras"] = {"amostras": [], "motivo": "sem_transcricoes_da_marca"}
        return Mundo(nome, base, ("contexto_marca", "cerebros", "voz_amostras", "estruturas_buscar", "pesquisas"),
                     voz=False, cta_proibidos=CTAS_PROIBIDOS)
    raise KeyError(nome)


def conteudo() -> ConteudoBundle:
    return ConteudoBundle(
        textos=(TextoData("runtime.ferramenta_falhou", "Falhou, siga sem a ferramenta."),),
        ferramentas=tuple(FerramentaData(n, f"descricao de {n}", True, {}) for n in CRIACAO_TOOLS),
    )


def turno(m: Mundo, *, token: bool = True) -> tuple[CriacaoTurno, FakeSocialWiringClient]:
    sw = FakeSocialWiringClient()
    if token:
        sw.criacao_token_orgs.add(ORG)
    sw.criacao_responses.update(m.respostas)
    return CriacaoTurno(org_id=ORG, marca_id=MARCA, sw=sw, conteudo=conteudo()), sw


async def percorrer(t: CriacaoTurno, caminho: tuple[str, ...]) -> None:
    """Drive the REAL toolset handler through the expected path (what a model does with tools)."""
    ts = construir_toolset_criacao(t)
    for i, nome in enumerate(caminho):
        args: dict[str, Any] = {}
        if nome == "estruturas_buscar":
            args = {"formato": "reels", "objetivo": "alcance"}
        r = ts.handler(ToolCall(f"c{i}", nome, args))
        if hasattr(r, "__await__"):
            await r


# ── scripted replies ──────────────────────────────────────────────────────────────────────────────────────

CORPO_BOM = (
    "Você já acordou cansada sem saber por quê?\n"
    "Eu também.\n"
    "Foi assim por anos, e eu achava que era normal dormir mal.\n\n"
    "Mas então eu medi o meu sono. Pela primeira vez.\n"
    "O resultado me assustou.\n\n"
    "Aí mudei uma coisa só: a luz do quarto.\n"
    "Simples. Sem remédio, sem truque.\n\n"
    "Em uma semana eu já sentia a diferença.\n"
    "Quer testar também? Salva este vídeo para lembrar."
)
CORPO_ROBOTICO = (
    "Dormir bem é fundamental para a saúde física e mental de todas as pessoas que desejam melhorar a qualidade de vida.\n"
    "Dormir bem ajuda a regular os hormônios responsáveis pelo apetite, pelo humor e pela disposição ao longo do dia inteiro.\n\n"
    "Dormir bem também fortalece o sistema imunológico e reduz significativamente o risco de diversas doenças crônicas.\n"
    "Dormir bem exige uma rotina consistente de horários, de alimentação equilibrada e de ambiente adequado para o descanso."
)


def resposta(
    *, corpo: str = CORPO_BOM, hashtags: str = "#sono #rotina #saude #descanso #bemestar", objetivo: str = "salvamentos",
    cta: str = "Salva este vídeo para lembrar", justificativa: str = "Um único pedido de salvar, no fim, porque o objetivo é salvamento",
    legenda: str = "Medi o meu sono e mudei uma coisa só.", fontes: str = f"{URL_PESQUISA} (verificada)",
    voz: str = "amostras", link: str = "", extra: str = "",
) -> str:
    return (
        "## Opções\n\n"
        f"### Roteiro 1: Sono sem remédio (estrutura #101)\n{corpo}\n\n"
        "### Publicação 1\n"
        f"- Objetivo do post: {objetivo}\n- CTA: {cta}\n- Justificativa do CTA: {justificativa}\n"
        f"- Legenda: {legenda}\n- Hashtags: {hashtags}\n- Primeiro comentário: Qual hábito você mudaria primeiro?\n"
        f"- Link: {link}\n- Fontes: {fontes}\n- Voz: {voz}\n{extra}\n"
        "### Estruturas usadas\n- #101: Gancho; Virada\n"
    )


MUTANTES: dict[str, Callable[[], tuple[str, str]]] = {
    # name -> (reply, the failure code prefix that MUST appear)
    "seis_hashtags": lambda: (resposta(hashtags="#a #b #c #d #e #f"), "pub1:hashtags:6"),
    "quatro_hashtags": lambda: (resposta(hashtags="#a #b #c #d"), "pub1:hashtags:4"),
    "objetivo_ausente": lambda: (resposta(objetivo="vender"), "pub1:objetivo_nao_declarado"),
    "cta_sem_justificativa": lambda: (resposta(justificativa="ok"), "pub1:cta_sem_justificativa"),
    "cta_comercial": lambda: (resposta(cta="Compre agora pelo link na bio", justificativa="Para gerar vendas rápidas hoje"),
                              "pub1:cta_proibido:compre"),
    "vaza_cliente": lambda: (resposta(legenda="Como a Bia Exemplo fez com o sono dela"), "nome:2"),
    "fonte_inventada": lambda: (resposta(fontes="https://inventado.exemplo/pesquisa (verificada)"), "pub1:fonte_inventada"),
    "robotico": lambda: (resposta(corpo=CORPO_ROBOTICO), "roteiro1:frases_curtas"),
    "ancora_repetida": lambda: (resposta(corpo="Você sabia disso.\nOutra frase.\n\nVocê sabia aquilo.\nMais uma."),
                                "roteiro1:abertura_repetida"),
    "link_preenchido": lambda: (resposta(link="https://exemplo.com/post"), "pub1:link_preenchido"),
}
