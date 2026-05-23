"""Summarize a class transcript.

The prompt is tuned for the project's goal: eternalize a social-media course's
content and surface its *methodology* (step 2). Output is Portuguese markdown.
"""
from __future__ import annotations

from app.integrations.llm import chat_completion
from app.services.text_utils import strip_code_fence

_SYSTEM = (
    "Você documenta a METODOLOGIA de um curso de social media de forma PURA, "
    "reutilizável e atemporal. Português do Brasil. Seja fiel, detalhado e "
    "acionável — preserve mecanismos, frameworks, táticas e estruturas — mas "
    "siga regras OBRIGATÓRIAS:\n"
    "1. NÃO cite nomes de pessoas, perfis, @s, marcas, clientes ou alunos. "
    "Anonimize ou omita. (Privacidade — não podemos expor ninguém.)\n"
    "2. NÃO inclua números de resultado/desempenho (visualizações, seguidores, "
    "faturamento, 'X de Y vídeos', taxas de crescimento). São resultados passados "
    "e podem enganar — o mundo muda.\n"
    "3. Converta exemplos específicos em PADRÕES/FÓRMULAS generalizáveis (uma "
    "headline real vira um template; um caso vira um princípio).\n"
    "4. Números INTRÍNSECOS ao método (ex.: 'os 3 primeiros segundos', 'os 7 "
    "gatilhos') são parte da metodologia e PODEM ser mantidos.\n"
    "NÃO invente. Apenas a metodologia, crua."
)

_USER_TEMPLATE = """\
Documente a METODOLOGIA da aula "{title}" em markdown — pura e reutilizável, como
a página de um manual que ensina a APLICAR o método (sem pessoas, sem números de
resultado). Use as seções abaixo (adapte/omita; não force seções vazias):

## Resumo
2 a 4 frases com a tese central.

## Conceitos e princípios
Cada conceito com o MECANISMO (o porquê), não só o nome.

## Framework / passo a passo
O processo ensinado, detalhado e na ordem correta.

## Padrões e fórmulas
Estruturas de headline e de conteúdo, GENERALIZADAS como templates preenchíveis
(ex.: "Me dê [tempo curto] e eu [resolvo sua dor]"; "É o fim de [dor comum]: com
[método] você nunca mais vai [erro]"). Nada de exemplos atrelados a pessoas/marcas.

## Táticas e regras de execução
Regras de "faça assim / não faça", critérios de decisão, detalhes de execução.

## Termos do método
Jargões/conceitos do método e referências NÃO-pessoais (ex.: livros). Sem nomes
de pessoas/perfis.

## Itens acionáveis
O que fazer na prática, específico.

Lembre: zero nomes de pessoas/perfis/marcas; zero métricas de desempenho;
transforme todo exemplo em padrão. Transcrição:
\"\"\"
{transcript}
\"\"\"
"""


async def summarize_transcript(title: str, transcript: str) -> str:
    """Return a structured pt-BR markdown summary of the transcript."""
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER_TEMPLATE.format(title=title, transcript=transcript)},
    ]
    return strip_code_fence(await chat_completion(messages))


__all__ = ["summarize_transcript"]
