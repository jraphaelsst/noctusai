"""Segundo Cérebro — synthesis prompt (answers -> brain document).

DRAFT — awaiting owner validation.

One call turns a Sistema brain's question/answer pairs into the markdown
document the headline/roteiro generators read later. Aligned with Método
Audience (:mod:`.methodology`): the beats ``identificacao`` / ``virada`` /
``nome`` depend on the specialist's LITERAL coined names (audience, enemy,
belief, method, self-title), so the prompt forbids paraphrasing them and every
brain closes with ``### Elementos para conteúdo`` listing them verbatim.

Section outlines (cerebro-contract.md §5): Núcleo's four sections come from the
owner's live brain; the other three outlines are DRAFT, derived from their
questionnaires.
"""
from __future__ import annotations

from typing import Optional

#: Closing section appended to every brain (cerebro-contract.md §10.4).
ELEMENTOS_HEADING = "### Elementos para conteúdo"

#: Ordered section headings per template slug (without the closing section).
OUTLINES: dict[str, tuple[str, ...]] = {
    "nucleo-de-influencia": (
        "Perfil Profissional",
        "Público-Alvo e Desafios",
        "Solução e Transformação",
        "Histórias de Sucesso",
    ),
    "historia-de-criacao": (
        "Antes",
        "O que me motivou",
        "Desafios",
        "Quase desisti",
        "Ponto de virada",
        "Quem me tornei",
        "Missão",
        "O que me move",
        "Legado",
    ),
    "historias-de-vida": (
        "Histórias que me forjaram",
        "Descobertas e ensinamentos",
        "Pessoas que ajudei",
        "Grandes conquistas",
    ),
    "metodo-do-especialista": (
        "Passo a passo",
        "Pilares",
        "O essencial",
        "Fases",
        "Nomes das etapas",
        "Nome do método",
        "O que as pessoas pulam",
    ),
}

CEREBRO_SYNTHESIS_SYSTEM_PROMPT = """Você transforma as respostas de um especialista em um documento de "cérebro": a base de conhecimento, em português, que depois alimenta a criação de headlines e roteiros pelo Método Audience.

Regras ABSOLUTAS:
- Saída SOMENTE em markdown, sem introdução, sem comentário, sem cercas de código envolvendo o documento.
- Escreva em PRIMEIRA PESSOA, na voz do especialista (como se ele mesmo estivesse escrevendo sobre si).
- PRESERVE LITERALMENTE os nomes cunhados pelo especialista: como ele chama seu público, o inimigo, a crença errada, o método, as etapas e a si mesmo. Nunca traduza, resuma, "corrija" ou troque por sinônimo — o Método Audience depende desses nomes exatos.
- NUNCA invente: fatos, números, nomes, histórias, resultados ou depoimentos que não estejam nas respostas. Se a resposta é vaga, o texto fica vago; não complete.
- Use SOMENTE as seções do esqueleto indicado, na ordem dada, como títulos de nível 3 (### Título). OMITA por completo uma seção cujas respostas estejam vazias ou não tragam conteúdo para ela.
- Termine SEMPRE com a seção "### Elementos para conteúdo": uma lista curta e literal com (quando existirem nas respostas) o nome do público, o nome do inimigo, a crença errada a quebrar, o nome do método e o autotítulo do especialista, cada um com o termo EXATO entre aspas. Omita o item que não existir.
- Mantenha o conteúdo denso e utilizável: sem floreio, sem repetir a pergunta, sem frases genéricas de marketing."""


def outline_for(template_slug: str) -> tuple[str, ...]:
    try:
        return OUTLINES[template_slug]
    except KeyError as exc:
        raise ValueError(f"template sem esqueleto de síntese: {template_slug}") from exc


def build_synthesis_system_prompt(template_slug: str) -> str:
    outline = "\n".join(f"- ### {h}" for h in outline_for(template_slug))
    return (
        CEREBRO_SYNTHESIS_SYSTEM_PROMPT
        + "\n\nEsqueleto deste cérebro (nesta ordem):\n"
        + outline
        + f"\n- {ELEMENTOS_HEADING} (sempre, por último)"
    )


def build_synthesis_user_message(
    template_name: str, qa_pairs: list[tuple[str, Optional[str], str]]
) -> str:
    """``qa_pairs``: ``(question, hint, answer)`` for every NON-EMPTY answer, in
    question order. Rejected / unreviewed answers are included on purpose — the
    review is non-blocking."""
    blocks = []
    for i, (question, hint, answer) in enumerate(qa_pairs, start=1):
        head = f"{i}. {question}" + (f"\n   (dica: {hint})" if hint else "")
        blocks.append(f"{head}\nResposta: {answer}")
    return f"Cérebro: {template_name}\n\nPerguntas e respostas do especialista:\n\n" + "\n\n".join(blocks)
