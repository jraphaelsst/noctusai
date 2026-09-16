"""Rule proposer — turns an agency's rejection comments into "don't" rules.

Text-only call. Proposals are drafts: a human approves before a rule
enters the effective guide.
"""

from __future__ import annotations

from collections.abc import Sequence

from noctusai_lib.domain.photo_editing.prompts._base import PromptTemplate, RenderedPrompt

RULE_PROPOSER_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["regras"],
    "properties": {
        "regras": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["texto", "comentarios"],
                "properties": {
                    "texto": {"type": "string"},
                    # 1-based indexes into the numbered comment list.
                    "comentarios": {"type": "array", "items": {"type": "integer"}},
                },
            },
        }
    },
}

RULE_PROPOSER_PROMPT = PromptTemplate(
    prompt_id="fotos.propor_regras",
    version=1,
    response_schema=RULE_PROPOSER_SCHEMA,
    template=(
        "Uma imobiliária rejeitou fotos editadas com os comentários numerados abaixo.\n"
        "\n"
        "{comentarios}\n"
        "\n"
        "Regras já em vigor para esta imobiliária (não repita):\n"
        "{regras_atuais}\n"
        "\n"
        "Proponha regras curtas no formato \"Não ...\" que evitem essas rejeições no "
        "futuro. Só proponha uma regra quando o comentário indicar algo que a edição "
        "fez de errado. Para cada regra, liste os números dos comentários que a "
        "motivaram. Se nenhum comentário justificar uma regra, devolva uma lista vazia.\n"
    ),
)


def render_rule_proposer_prompt(
    comentarios: Sequence[str], regras_atuais: Sequence[str]
) -> RenderedPrompt:
    if not comentarios:
        raise ValueError("render_rule_proposer_prompt: no rejection comments")
    numerados = "\n".join(f"{i}. {c}" for i, c in enumerate(comentarios, start=1))
    atuais = "\n".join(f"- {r}" for r in regras_atuais) or "- (nenhuma)"
    text = RULE_PROPOSER_PROMPT.render(comentarios=numerados, regras_atuais=atuais)
    return RenderedPrompt(
        text=text, ref=RULE_PROPOSER_PROMPT.ref, response_schema=RULE_PROPOSER_SCHEMA
    )


__all__ = ["RULE_PROPOSER_PROMPT", "RULE_PROPOSER_SCHEMA", "render_rule_proposer_prompt"]
