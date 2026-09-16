"""Style-guide builder — writes the company guide from the reference pool.

Input images, in order: ``[antes_1, depois_1, antes_2, depois_2, ...]``.
The guide is TEXT: edit calls send photo + guide, never reference images.
"""

from __future__ import annotations

from collections.abc import Sequence

from noctusai_lib.domain.photo_editing.prompts._base import PromptTemplate, RenderedPrompt
from noctusai_lib.domain.photo_editing.types import ReferencePair

STYLE_GUIDE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["guia"],
    "properties": {"guia": {"type": "string"}},
}

STYLE_GUIDE_PROMPT = PromptTemplate(
    prompt_id="fotos.guia_estilo",
    version=1,
    response_schema=STYLE_GUIDE_SCHEMA,
    template=(
        "Você define o padrão visual de uma empresa de edição de fotos imobiliárias.\n"
        "As imagens chegam em pares: ANTES e DEPOIS, na ordem listada abaixo.\n"
        "\n"
        "{pares}\n"
        "\n"
        "Escreva, em português, um guia de estilo objetivo que um editor possa seguir "
        "para reproduzir o padrão dos DEPOIS: cor e luz, céu, organização, mobiliário "
        "virtual e o que nunca deve ser feito. Use tópicos curtos. Não descreva fotos "
        "específicas — descreva o padrão.\n"
    ),
)


def render_style_guide_prompt(pares: Sequence[ReferencePair]) -> RenderedPrompt:
    if not pares:
        raise ValueError("render_style_guide_prompt: the reference pool is empty")
    linhas = []
    for i, par in enumerate(pares, start=1):
        tipos = ", ".join(t.value for t in par.tipos_edicao) or "sem tipo"
        nota = f" — nota: {par.nota}" if par.nota else ""
        linhas.append(f"Par {i}: cômodo {par.comodo.value}; edições: {tipos}{nota}")
    text = STYLE_GUIDE_PROMPT.render(pares="\n".join(linhas))
    return RenderedPrompt(
        text=text, ref=STYLE_GUIDE_PROMPT.ref, response_schema=STYLE_GUIDE_SCHEMA
    )


__all__ = ["STYLE_GUIDE_PROMPT", "STYLE_GUIDE_SCHEMA", "render_style_guide_prompt"]
