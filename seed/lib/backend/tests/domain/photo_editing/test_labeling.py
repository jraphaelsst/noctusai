"""Photo labeling: parser strictness, room mapping, DI seam."""

from __future__ import annotations

import asyncio
import json

import pytest

from noctusai_lib.domain.photo_editing import (
    LABEL_CHAVE,
    ROOM_TYPES,
    LabelParseError,
    PhotoLabel,
    Room,
    label_photo,
    parse_label,
    to_room,
)

GOOD = {
    "room_type": "suite", "exposure": "ok", "white_balance": "warm", "verticals": "tilted",
    "sky": "none", "windows": "blown", "staging": "furnished", "framing": "wide",
    "lens": "ultrawide", "quality_score": 3, "edit_needed": ["straighten verticals", "pull windows"],
    "notes": "ok",
}


def test_parse_ok_with_prose_wrapper():
    lab = parse_label("Here:\n" + json.dumps(GOOD))
    assert isinstance(lab, PhotoLabel)
    assert lab.edit_needed == ("straighten verticals", "pull windows")
    assert lab.room is Room.QUARTO
    assert lab.as_row()["edit_needed"] == "straighten verticals; pull windows"


@pytest.mark.parametrize("key", list(GOOD))
def test_missing_key_rejected(key):
    d = {k: v for k, v in GOOD.items() if k != key}
    with pytest.raises(LabelParseError, match="missing"):
        parse_label(json.dumps(d))


@pytest.mark.parametrize("key,val", [("room_type", "sotao"), ("exposure", "dark"), ("quality_score", 6),
                                      ("quality_score", True), ("quality_score", "3"), ("edit_needed", 5)])
def test_bad_value_rejected(key, val):
    with pytest.raises(LabelParseError):
        parse_label(json.dumps({**GOOD, key: val}))


def test_no_json_rejected():
    with pytest.raises(LabelParseError):
        parse_label("sorry, cannot")


def test_every_room_type_maps():
    assert all(isinstance(to_room(r), Room) for r in ROOM_TYPES)
    with pytest.raises(LabelParseError):
        to_room("nope")


def _registry():
    from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, PromptEntry

    return FakePromptRegistry([PromptEntry(LABEL_CHAVE, "n", "d", "anthropic", "claude-sonnet-5", "ROW PROMPT",
                                           capacidade="vision")])


def test_label_photo_reads_prompt_vendor_model_from_the_registry_row():
    seen = {}

    async def fake(image, prompt, **kw):
        seen.update(image=image, prompt=prompt, **kw)
        return json.dumps(GOOD)

    lab = asyncio.run(label_photo(b"x", org_id="o", registry=_registry(), analisar=fake))
    assert lab.room_type == "suite"
    assert seen == {"image": b"x", "prompt": "ROW PROMPT", "provider": "anthropic",
                    "model": "claude-sonnet-5", "org_id": "o"}


def test_missing_row_raises_not_falls_back():
    import pytest
    from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, RegistroIAIndisponivel

    async def fake(*a, **k):
        raise AssertionError("must not be called")

    with pytest.raises(RegistroIAIndisponivel):
        asyncio.run(label_photo(b"x", registry=FakePromptRegistry(), analisar=fake))


def test_chave_is_a_valid_registry_key():
    from noctusai_lib.integrations.prompt_registry import chave_valida

    assert LABEL_CHAVE == "fotos.rotular" and chave_valida(LABEL_CHAVE)


def test_extra_keys_ignored_and_never_reach_row():
    lab = parse_label(json.dumps({**GOOD, "furnished": True, "confidence": 0.9}))
    assert set(lab.as_row()) == set(GOOD)
    assert not hasattr(lab, "furnished")


def test_sky_n_a_is_synonym_of_none():
    assert parse_label(json.dumps({**GOOD, "sky": "n_a"})).sky == "none"


def test_lens_wide_still_rejected():
    with pytest.raises(LabelParseError, match="lens"):
        parse_label(json.dumps({**GOOD, "lens": "wide"}))
