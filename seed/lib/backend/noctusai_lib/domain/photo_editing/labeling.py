"""Real-estate photo labeling — room type + quality / edit attributes.

One vision call per photo returns a strict JSON label. Used first to label
datasets (toolkit tool ``noctus.dev.photo_label_dataset``) and later for the
runtime room classification of the photo-editing engine. The fine
``ROOM_TYPES`` taxonomy maps onto the existing coarse ``types.Room`` enum via
``to_room``; nothing here changes that enum or any DB constraint.

The prompt is NOT here: it is the registry row ``fotos.rotular`` (vendor + model too). IO seams:
``label_photo(..., registry=, analisar=)``; tests pass a Fake registry and a fake analyzer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.photo_editing.types import Room
from noctusai_lib.integrations.prompt_registry import PromptRegistry, chamar_ia_visao

ROOM_TYPES: tuple[str, ...] = (
    "sala", "sala_jantar", "cozinha", "quarto", "suite", "banheiro", "lavabo",
    "varanda", "area_servico", "fachada", "area_lazer", "piscina",
    "churrasqueira", "academia", "garagem", "jardim", "vista", "planta",
    "detalhe", "outro",
)

EXPOSURE = ("under", "ok", "over")
WHITE_BALANCE = ("warm", "neutral", "cool", "mixed")
VERTICALS = ("straight", "tilted")
SKY = ("none", "dull", "blue", "replaced")
WINDOWS = ("blown", "balanced", "n_a")
STAGING = ("empty", "furnished", "cluttered")
FRAMING = ("wide", "normal", "tight")
LENS = ("ultrawide", "normal")

_ENUMS: dict[str, tuple[str, ...]] = {
    "room_type": ROOM_TYPES, "exposure": EXPOSURE, "white_balance": WHITE_BALANCE,
    "verticals": VERTICALS, "sky": SKY, "windows": WINDOWS, "staging": STAGING,
    "framing": FRAMING, "lens": LENS,
}

_ROOM_MAP: dict[str, Room] = {
    "sala": Room.SALA, "sala_jantar": Room.SALA,
    "cozinha": Room.COZINHA, "area_servico": Room.COZINHA,
    "quarto": Room.QUARTO, "suite": Room.QUARTO,
    "banheiro": Room.BANHEIRO, "lavabo": Room.BANHEIRO,
    "varanda": Room.VARANDA, "fachada": Room.FACHADA,
    "area_lazer": Room.AREA_EXTERNA, "piscina": Room.AREA_EXTERNA,
    "churrasqueira": Room.AREA_EXTERNA, "academia": Room.AREA_EXTERNA,
    "garagem": Room.AREA_EXTERNA, "jardim": Room.AREA_EXTERNA,
    "vista": Room.AREA_EXTERNA, "planta": Room.OUTRO, "detalhe": Room.OUTRO,
    "outro": Room.OUTRO,
}

LABEL_FIELDS: tuple[str, ...] = (
    "room_type", "exposure", "white_balance", "verticals", "sky", "windows",
    "staging", "framing", "lens", "quality_score", "edit_needed", "notes",
)

#: Registry key of the labeling prompt (`public.plataforma_agentes`); prompt, vendor and model live in the
#: DB row (core migration seed), never in code. KB § PATTERNS/ai/prompts-from-registry.md.
CHAVE = "fotos.rotular"


class LabelParseError(ValueError):
    """The model reply is not a valid label (missing key / out-of-enum value)."""


@dataclass(frozen=True)
class PhotoLabel:
    room_type: str
    exposure: str
    white_balance: str
    verticals: str
    sky: str
    windows: str
    staging: str
    framing: str
    lens: str
    quality_score: int
    edit_needed: tuple[str, ...]
    notes: str

    @property
    def room(self) -> Room:
        return to_room(self.room_type)

    def as_row(self) -> dict[str, Any]:
        """CSV-friendly dict (``edit_needed`` joined with '; ')."""
        row = {f: getattr(self, f) for f in LABEL_FIELDS}
        row["edit_needed"] = "; ".join(self.edit_needed)
        return row


def to_room(room_type: str) -> Room:
    """Map a fine ``ROOM_TYPES`` value to the coarse ``Room`` enum."""
    try:
        return _ROOM_MAP[room_type]
    except KeyError:
        raise LabelParseError(f"unknown room_type {room_type!r}") from None


def parse_label(text: str) -> PhotoLabel:
    """Parse a model reply into a ``PhotoLabel``; raise ``LabelParseError`` on
    anything missing or out of enum (no silent defaults)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise LabelParseError(f"no JSON object in reply: {(text or '')[:120]!r}")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise LabelParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LabelParseError("reply JSON is not an object")
    # Extra keys are ignored on purpose (field finding: a model added `furnished`);
    # the label is built only from LABEL_FIELDS.
    missing = [k for k in LABEL_FIELDS if k not in data]
    if missing:
        raise LabelParseError(f"missing keys {missing}")
    # Field finding: models answer sky "n_a" for interiors (mirroring `windows`);
    # it is an explicit synonym of "none". Any other out-of-enum value is rejected.
    if data["sky"] == "n_a":
        data["sky"] = "none"
    for key, allowed in _ENUMS.items():
        if data[key] not in allowed:
            raise LabelParseError(f"bad {key} {data[key]!r}")
    score = data["quality_score"]
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
        raise LabelParseError(f"bad quality_score {score!r}")
    edits = data["edit_needed"]
    if isinstance(edits, str):
        edits = [e.strip() for e in edits.split(";") if e.strip()]
    if not isinstance(edits, list) or not all(isinstance(e, str) for e in edits):
        raise LabelParseError("edit_needed must be a list of strings")
    if not isinstance(data["notes"], str):
        raise LabelParseError("notes must be a string")
    return PhotoLabel(
        **{k: data[k] for k in _ENUMS},
        quality_score=score,
        edit_needed=tuple(edits),
        notes=data["notes"],
    )


async def label_photo(
    image: bytes,
    *,
    org_id: Optional[str] = None,
    registry: Optional[PromptRegistry] = None,
    analisar: Optional[Callable[..., Awaitable[Any]]] = None,
) -> PhotoLabel:
    """Label one photo: the registry row ``fotos.rotular`` supplies prompt, vendor and model.

    ``registry`` / ``analisar`` are the DI seams (tests pass a Fake registry and a fake analyzer)."""
    res = await chamar_ia_visao(CHAVE, image, org_id=org_id, registry=registry, analisar=analisar)
    return parse_label(res.texto)
