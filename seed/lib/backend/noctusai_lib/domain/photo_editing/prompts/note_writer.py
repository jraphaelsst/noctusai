"""Model-note writer — the daily pt-BR recommendation per image model.

Wired by the consumer's daily scheduler (``fotos.daily_model_notes``,
00:05 America/Sao_Paulo); the engine ships the prompt, the consumer
ships the schedule. Input is OUR OWN metrics, never vendor marketing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from noctusai_lib.domain.photo_editing.prompts._base import PromptTemplate, RenderedPrompt

NOTE_WRITER_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["nota"],
    "properties": {"nota": {"type": "string"}},
}

NOTE_WRITER_PROMPT = PromptTemplate(
    prompt_id="fotos.nota_modelo",
    version=1,
    response_schema=NOTE_WRITER_SCHEMA,
    template=(
        "Escreva uma recomendação curta (no máximo 3 frases, em português) sobre o "
        "modelo de edição de imagens \"{modelo}\", baseada SOMENTE nestes resultados "
        "da nossa plataforma:\n"
        "- fotos avaliadas: {total_fotos}\n"
        "- taxa de aprovação humana: {taxa_aprovacao}\n"
        "- nota média da IA avaliadora: {score_medio}\n"
        "- custo por foto aprovada (USD): {custo_por_aprovada}\n"
        "Se houver poucos dados, diga isso claramente em vez de concluir.\n"
    ),
)


@dataclass(frozen=True)
class ModelMetrics:
    """Mirror of the consumer's ``fotos_modelo_metricas`` RPC row."""

    modelo_id: str
    total_fotos: int
    taxa_aprovacao: Decimal
    score_medio: Decimal
    custo_por_foto_aprovada_usd: Decimal


def render_note_writer_prompt(m: ModelMetrics) -> RenderedPrompt:
    text = NOTE_WRITER_PROMPT.render(
        modelo=m.modelo_id,
        total_fotos=str(m.total_fotos),
        taxa_aprovacao=f"{(m.taxa_aprovacao * 100):.1f}%",
        score_medio=f"{m.score_medio:.2f}",
        custo_por_aprovada=f"{m.custo_por_foto_aprovada_usd:.4f}",
    )
    return RenderedPrompt(
        text=text, ref=NOTE_WRITER_PROMPT.ref, response_schema=NOTE_WRITER_SCHEMA
    )


__all__ = [
    "ModelMetrics",
    "NOTE_WRITER_PROMPT",
    "NOTE_WRITER_SCHEMA",
    "render_note_writer_prompt",
]
