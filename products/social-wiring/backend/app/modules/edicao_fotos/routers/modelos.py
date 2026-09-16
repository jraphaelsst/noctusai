"""`GET /api/edicao-fotos/modelos` — contract §8, the image-model catalog.

R1 serves the catalog itself (`integrations.llm.models`, kind `image_edit`):
id, name, version, batch capability. Live metrics and the daily AI-written
notes are the model-notes slice (W8) and are `null` until it lands — the FE
type (`ModeloCatalogoItem`) already allows that. Read-only; open to members
because the settings page renders it."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from noctusai_lib.domain.photo_editing import Actor
from noctusai_lib.integrations.llm.models import models_for

from app.modules.edicao_fotos.deps import require_member
from app.modules.edicao_fotos.presenters import modelo_out

router = APIRouter(prefix="/api/edicao-fotos/modelos", tags=["edicao-fotos"])

IMAGE_EDIT_PROVIDER = "openai"


@router.get("")
async def list_modelos_route(_actor: Actor = Depends(require_member)) -> list[dict]:
    return [modelo_out(e) for e in models_for(IMAGE_EDIT_PROVIDER, "image_edit")]
