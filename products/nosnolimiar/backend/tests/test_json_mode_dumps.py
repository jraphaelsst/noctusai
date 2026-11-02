"""
Write payloads must be JSON-mode dumps — router -> REAL service -> MockSupabase.

History (fleet sweep 2026-10-15): ``payload.model_dump(exclude_none=True)``
left ``UUID`` / ``date`` / ``Decimal`` objects in the row, and supabase-py
(httpx ``json=``, stdlib encoder, no ``default=``) raised
``TypeError: Object of type UUID is not JSON serializable`` -> a live 502
(orbity POST /api/crm/leads). Router tests mocked the service and service
tests received pre-stringified dicts, so nothing caught it.

The leads organ writes ``datetime`` / ``Decimal`` / ``UUID`` columns, so the
bug fires the moment any of them reaches a body unconverted. Two guards:

1. a structural guard: every ``.model_dump(...)`` under ``app/`` names a
   ``mode=`` explicitly (``mode="json"`` for anything reaching a DB write);
2. an e2e round-trip: ``POST /api/leads`` -> real leads service ->
   ``MockSupabaseClient`` (which refuses non-JSON-serializable writes).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# `path:line` of dumps that deliberately keep python mode (response/log
# consumers that need the typed values). Every entry needs a reason.
# TODO(new-product): extend only with a justification comment per entry.
PYTHON_MODE_ALLOWED: set[str] = set()


def _dumps_without_mode() -> list[str]:
    hits: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "model_dump"
                and not any(kw.arg == "mode" for kw in node.keywords)
            ):
                hits.append(f"{path.relative_to(APP_DIR.parent)}:{node.lineno}")
    return hits


def test_every_model_dump_names_its_mode():
    missing = [h for h in _dumps_without_mode() if h not in PYTHON_MODE_ALLOWED]
    assert not missing, (
        "model_dump() without mode= — a UUID/date/Decimal field reaching "
        "supabase-py raises 'not JSON serializable' (live 502). Use "
        f"model_dump(mode=\"json\", ...): {missing}"
    )


def test_create_lead_write_is_json_serializable(client):
    resp = client.post("/api/leads", json={"name": "Paciente", "phone": "(11) 99457-3387", "origin": "instagram"})
    assert resp.status_code == 201, resp.text
    inserted = client.mock_supabase.table("leads").inserted_payloads
    assert inserted, "the create never reached the client"
    json.dumps(inserted[-1])  # the wire encoder supabase-py uses
