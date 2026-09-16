"""Image-edit instruction — ONE combined prompt for every enabled edit type.

Sent (with the photo) to ``integrations.image_edit``. The model reads
pt-BR fine and the guide text is pt-BR, so the instruction is pt-BR too.
Structural fidelity is the hard constraint: the evaluator checks it.
"""

from __future__ import annotations

from collections.abc import Iterable

from noctusai_lib.domain.photo_editing.prompts._base import PromptTemplate, RenderedPrompt
from noctusai_lib.domain.photo_editing.types import EditType

EDIT_PROMPT = PromptTemplate(
    prompt_id="fotos.edit",
    version=1,
    template=(
        "Você é um editor de fotos profissional do mercado imobiliário brasileiro.\n"
        "Edite a foto do imóvel aplicando SOMENTE as edições abaixo, seguindo o guia de estilo.\n"
        "\n"
        "Edições solicitadas:\n"
        "{edicoes}\n"
        "\n"
        "Regras invioláveis:\n"
        "- Não altere a arquitetura: paredes, portas, janelas, pisos, tetos e proporções "
        "devem permanecer idênticos.\n"
        "- Não adicione nem remova elementos estruturais do imóvel.\n"
        "- Mantenha o enquadramento e a perspectiva da foto original.\n"
        "- O resultado deve parecer uma fotografia real, sem aspecto artificial.\n"
        "\n"
        "Guia de estilo (versão {guia_sha}):\n"
        "{guia}\n"
    ),
)

#: Human-facing instruction per edit type (pt-BR), in canonical order.
EDIT_INSTRUCTIONS: dict[EditType, str] = {
    EditType.COR_LUZ: "Corrigir cor e luz: exposição equilibrada, balanço de branco neutro, "
    "sombras suaves e cores fiéis.",
    EditType.CEU: "Substituir o céu por um céu azul limpo e natural, coerente com a "
    "iluminação da cena.",
    EditType.DECLUTTER: "Remover objetos soltos e bagunça (itens pessoais, fios, lixo), "
    "sem remover móveis fixos nem elementos do imóvel.",
    EditType.STAGING_VIRTUAL: "Mobiliar virtualmente o ambiente com móveis e decoração "
    "compatíveis com o cômodo, em escala realista.",
}


def render_edit_prompt(
    tipos: Iterable[EditType], *, guia_texto: str, guia_sha256: str
) -> RenderedPrompt:
    """Render the combined instruction. ``tipos`` must be non-empty; the
    order in the prompt is canonical (enum order), not caller order, so the
    same set always renders the same text."""
    wanted = {EditType(t) for t in tipos}
    if not wanted:
        raise ValueError("render_edit_prompt: at least one edit type is required")
    ordered = [t for t in EditType if t in wanted]
    edicoes = "\n".join(f"- {EDIT_INSTRUCTIONS[t]}" for t in ordered)
    text = EDIT_PROMPT.render(edicoes=edicoes, guia=guia_texto, guia_sha=guia_sha256[:12])
    return RenderedPrompt(text=text, ref=EDIT_PROMPT.ref)


__all__ = ["EDIT_INSTRUCTIONS", "EDIT_PROMPT", "render_edit_prompt"]
