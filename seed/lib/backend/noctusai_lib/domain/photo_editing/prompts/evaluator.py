"""Evaluator — scores an edited photo against its original.

Input images, in order: ``[original, edited]``. Output is strict JSON.
The verdict is shown to agency/platform admins ONLY (contract §1); the
engine stores it in its own record type so a consumer can withhold the
whole row.
"""

from __future__ import annotations

from collections.abc import Iterable

from noctusai_lib.domain.photo_editing.prompts._base import PromptTemplate, RenderedPrompt
from noctusai_lib.domain.photo_editing.prompts.edit import EDIT_INSTRUCTIONS
from noctusai_lib.domain.photo_editing.types import EditType

EVALUATOR_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recomendacao", "score", "motivo", "fidelidade_estrutural"],
    "properties": {
        "recomendacao": {"type": "string", "enum": ["aprovar", "rejeitar"]},
        "score": {"type": "number", "minimum": 0, "maximum": 10},
        "motivo": {"type": "string"},
        "fidelidade_estrutural": {"type": "boolean"},
    },
}

EVALUATOR_PROMPT = PromptTemplate(
    prompt_id="fotos.avaliar",
    version=1,
    response_schema=EVALUATOR_SCHEMA,
    template=(
        "Você avalia edições de fotos de imóveis. A primeira imagem é a ORIGINAL; "
        "a segunda é a EDITADA.\n"
        "\n"
        "Edições que foram pedidas:\n"
        "{edicoes}\n"
        "\n"
        "Guia de estilo aplicado:\n"
        "{guia}\n"
        "\n"
        "Responda em JSON:\n"
        "- fidelidade_estrutural: false se a arquitetura do imóvel foi alterada "
        "(paredes, portas, janelas, pisos, proporções).\n"
        "- score: nota de 0 a 10 para a qualidade da edição segundo o guia.\n"
        "- recomendacao: \"rejeitar\" se fidelidade_estrutural for false ou se a edição "
        "não atende ao guia; caso contrário \"aprovar\".\n"
        "- motivo: uma frase curta em português explicando a nota.\n"
    ),
)


def render_evaluator_prompt(tipos: Iterable[EditType], *, guia_texto: str) -> RenderedPrompt:
    wanted = {EditType(t) for t in tipos}
    edicoes = "\n".join(f"- {EDIT_INSTRUCTIONS[t]}" for t in EditType if t in wanted)
    text = EVALUATOR_PROMPT.render(edicoes=edicoes or "- (nenhuma)", guia=guia_texto)
    return RenderedPrompt(text=text, ref=EVALUATOR_PROMPT.ref, response_schema=EVALUATOR_SCHEMA)


__all__ = ["EVALUATOR_PROMPT", "EVALUATOR_SCHEMA", "render_evaluator_prompt"]
