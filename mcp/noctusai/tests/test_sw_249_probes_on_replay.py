"""SW 249 (certidao_resultados.resultado_origem gains 'texto') on the REAL
social-wiring chain on PGlite.

1. The registered GuardProbe still sees the widened CHECK refuse an unknown
   origin (`refused`).
2. 'texto' itself passes the CHECK: the insert below can only fail on the
   consulta FK (23503) once 249 is applied — before 249 it fails on the CHECK
   (23514), which the second test proves by dropping 249 from the chain.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_M249 = "products/social-wiring/backend/migrations/249_certidao_resultado_origem_texto.sql"
_PROBE = "social_wiring.certidao_resultados_resultado_origem_check"
_TEXTO = "sw-249-texto-accepted"
_SENT = re.compile(r"NOC_PROBE:(\w+):")

_TEXTO_SQL = """
DO $$
BEGIN
  BEGIN
    INSERT INTO social_wiring.certidao_resultados (consulta_id, org_id, tipo, nome_display, resultado_origem)
    VALUES (gen_random_uuid(), gen_random_uuid(), 'trf3', 'noc-probe', 'texto');
    RAISE EXCEPTION 'NOC_PROBE:inserted: no constraint fired';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:%' THEN RAISE;
    ELSIF SQLSTATE = '23514' THEN RAISE EXCEPTION 'NOC_PROBE:check: %', SQLERRM;
    ELSIF SQLSTATE = '23503' THEN RAISE EXCEPTION 'NOC_PROBE:fk: %', SQLERRM;
    ELSE RAISE EXCEPTION 'NOC_PROBE:other: %', SQLERRM;
    END IF;
  END;
END $$;
"""


def _outcomes(overrides: dict[str, str]) -> dict[str, str]:
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", overrides)
    probe = next(p for p in vdg.DEFAULT_REGISTRY if p.id == _PROBE)
    steps.append({"product": "social-wiring", "file": _PROBE, "sql": vdg.wrap_rollback_only(probe.sql),
                  "mode": "file", "twice": False})
    steps.append({"product": "social-wiring", "file": _TEXTO, "sql": _TEXTO_SQL,
                  "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out = {}
    for st in res["steps"]:
        if st["file"] in (_PROBE, _TEXTO):
            err = (st["failures"][0]["error"] if st["failures"] else "")
            m = _SENT.search(err)
            out[st["file"]] = (m.group(1) if m else f"UNCLASSIFIED: {err}")
    return out


def test_249_refuses_unknown_and_accepts_texto(pglite):
    assert _outcomes({}) == {_PROBE: "refused", _TEXTO: "fk"}


def test_texto_is_refused_without_249(pglite):
    out = _outcomes({_M249: "SELECT 1;\n"})
    assert out[_TEXTO] == "check", out
