"""Daily AI-written model notes (plan §1 "Models": notes rewritten daily at
00:05 America/Sao_Paulo from OUR OWN results).

The consumer owns the schedule (it enqueues ``fotos.notas_modelos``); the
engine owns what a run does:

1. Resolve the note-writer model (``steps.Step.NOTAS``) and refuse an
   unknown/unpriced one BEFORE any call.
2. For each enabled image-edit catalog model: read the live metrics; skip a
   model with no decided photos (a note about nothing costs money and says
   nothing); skip a model already noted since ``since`` (a retried job never
   writes twice).
3. Ask the writer for ``{"nota": str}``; store the note WITH the metrics it
   was written from (``dados_base``) so a human can audit it.

Platform scope: no org, so the call is billed only through the llm organ's
process-wide usage sink, never ``cost_ledger`` (whose ``org_id`` is NOT
NULL) — the same rule as the style-guide builder.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from noctusai_lib.domain.photo_editing.costs import catalog_entry
from noctusai_lib.domain.photo_editing.learning import InvalidModelOutputError
from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts
from noctusai_lib.domain.photo_editing.prompts.note_writer import (
    NOTE_WRITER_PROMPT,
    ModelMetrics,
    render_note_writer_prompt,
)
from noctusai_lib.domain.photo_editing.steps import STEP_KIND, Step, resolve_step_model
from noctusai_lib.integrations.llm.models import models_for

logger = logging.getLogger(__name__)

NOTE_SCHEMA_NAME = "nota_modelo"
NOTE_MAX_CHARS = 1200


class NoteWriterOutputError(InvalidModelOutputError):
    """The writer returned something that is not a usable note (retryable,
    like every malformed model output)."""


@dataclass(frozen=True)
class NotesReport:
    written: tuple[str, ...] = ()
    skipped_recent: tuple[str, ...] = ()
    skipped_no_data: tuple[str, ...] = ()
    writer_model: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def metrics_payload(m: ModelMetrics) -> dict[str, Any]:
    return {
        "total_fotos": m.total_fotos,
        "taxa_aprovacao": str(m.taxa_aprovacao),
        "score_medio": str(m.score_medio),
        "custo_por_foto_aprovada_usd": str(m.custo_por_foto_aprovada_usd),
    }


def image_models(ports: PhotoEditingPorts) -> list[str]:
    return [m.id for m in models_for(ports.config.image_edit_provider, "image_edit")]


async def write_model_notes(
    ports: PhotoEditingPorts,
    *,
    since: datetime | None = None,
    model_ids: list[str] | None = None,
) -> NotesReport:
    writer = await resolve_step_model(ports, Step.NOTAS)
    catalog_entry(ports.config.llm_provider, writer, STEP_KIND[Step.NOTAS])  # fail before spend
    targets = list(model_ids) if model_ids is not None else image_models(ports)
    latest = await ports.repo.latest_model_notes(targets) if since is not None else {}
    written: list[str] = []
    recent: list[str] = []
    no_data: list[str] = []
    for modelo_id in targets:
        note = latest.get(modelo_id)
        if since is not None and note is not None and note.gerado_em and note.gerado_em >= since:
            recent.append(modelo_id)
            continue
        metrics = await ports.repo.model_metrics(modelo_id)
        if metrics.total_fotos <= 0:
            no_data.append(modelo_id)
            continue
        rendered = render_note_writer_prompt(metrics)
        result = await ports.llm.analyze(
            images=[],
            prompt=rendered.text,
            response_schema=rendered.response_schema or {},
            model=writer,
            org_id=None,
            schema_name=NOTE_SCHEMA_NAME,
        )
        texto = result.data.get("nota") if isinstance(result.data, dict) else None
        if not isinstance(texto, str) or not texto.strip():
            raise NoteWriterOutputError(f"note writer returned no note for {modelo_id}")
        await ports.repo.add_model_note(
            modelo_id=modelo_id,
            texto=texto.strip()[:NOTE_MAX_CHARS],
            dados_base={
                **metrics_payload(metrics),
                "modelo_escritor": result.model or writer,
                "modelo_escritor_versao": result.model_version,
                "prompt": NOTE_WRITER_PROMPT.ref,
            },
        )
        written.append(modelo_id)
    logger.info(
        "photo_editing.notes written=%d recent=%d no_data=%d writer=%s",
        len(written),
        len(recent),
        len(no_data),
        writer,
    )
    return NotesReport(
        written=tuple(written),
        skipped_recent=tuple(recent),
        skipped_no_data=tuple(no_data),
        writer_model=writer,
    )


__all__ = [
    "NOTE_SCHEMA_NAME",
    "NoteWriterOutputError",
    "NotesReport",
    "image_models",
    "metrics_payload",
    "write_model_notes",
]
