"""The generated JSON Schema of the channel turn API (Julia v2 CONTRACT §10.3).

``products/agents/backend/contracts/channels.v2.json`` is GENERATED from the pydantic models of
:mod:`app.schemas.channels` -- the single definition. social-wiring validates every request it builds and parses
fixture responses against that file, so the drift class of 2026-10-19 (SW sent keys agents forbids and silently
stopped replying) cannot recur unseen. A drift test (``tests/contract/test_channels_v2_schema.py``) fails when the
file and the models disagree; regenerate with::

    python -m app.schemas.channels_contract --write
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.schemas.channel_threads import LeadConsentOut, OptOutEventoOut, OptOutOut, OptOutRequest
from app.schemas.channels import ChannelTurnRequest, ChannelTurnResponse, ContextoEstado

__all__ = ["CONTRACT_PATH", "VERSAO", "gerar", "render"]

VERSAO = "channels.v2"
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "channels.v2.json"


def gerar() -> dict[str, Any]:
    """``{"versao", "ChannelTurnRequest", "ChannelTurnResponse", "ContextoEstado", "OptOutRequest", "OptOutOut",
    "OptOutEventoOut", "LeadConsentOut"}``, each a self-contained JSON Schema (its ``$defs`` inside). The last
    four are the lead opt-out call (``POST /api/channels/leads/{ref}/opt-out``), the event record it returns and the
    thread-independent consent read (``GET /api/channels/leads/{ref}/consentimento``)."""
    return {
        "versao": VERSAO,
        "ChannelTurnRequest": ChannelTurnRequest.model_json_schema(),
        "ChannelTurnResponse": ChannelTurnResponse.model_json_schema(mode="serialization"),
        "ContextoEstado": ContextoEstado.model_json_schema(),
        "OptOutRequest": OptOutRequest.model_json_schema(),
        "OptOutOut": OptOutOut.model_json_schema(mode="serialization"),
        "OptOutEventoOut": OptOutEventoOut.model_json_schema(mode="serialization"),
        "LeadConsentOut": LeadConsentOut.model_json_schema(mode="serialization"),
    }


def render() -> str:
    return json.dumps(gerar(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":  # pragma: no cover -- the regenerate command
    if "--write" in sys.argv:
        CONTRACT_PATH.write_text(render(), encoding="utf-8")
        print(f"wrote {CONTRACT_PATH}")
    else:
        sys.stdout.write(render())
