"""SW migration 318 (Julia's line: `origem` / `categoria`) GuardProbes executed against the REAL social-wiring chain on PGlite:
each CHECK must read `refused` once applied (prod reads `no_fixture` until the migration is applied), and the chain must apply
318 twice. Also pins that the retired 258 `agente_exige_autorizados` guard is really gone from the schema."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_SEED = (
    "INSERT INTO social_wiring.whatsapp_connections (org_id, user_id, label, base_url, encrypted_api_key, webhook_token) "
    "VALUES (gen_random_uuid(), gen_random_uuid(), 'noc-seed', 'https://noc-seed.invalid', 'x', 'noc-seed-token');"
)
_IDS = {"conversation_messages.origem.valores", "whatsapp_chats.categoria.valores"}


def _outcomes() -> dict[str, str]:
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", {})
    probes = [p for p in vdg.DEFAULT_REGISTRY if p.id in _IDS]
    assert len(probes) == 2
    steps.append({"product": "social-wiring", "file": "seed", "sql": _SEED, "mode": "file", "twice": False})
    for p in probes:
        steps.append({"product": "social-wiring", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out = {}
    for st in res["steps"]:
        if st["file"] in _IDS:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    return out


def test_every_318_guard_refuses_on_the_real_chain(pglite):
    out = _outcomes()
    assert set(out.values()) == {"refused"}, out
    assert set(out) == _IDS


def test_the_retired_258_probe_is_not_registered():
    assert all(p.guard_name != "whatsapp_connections_agente_exige_autorizados" for p in vdg.DEFAULT_REGISTRY)
