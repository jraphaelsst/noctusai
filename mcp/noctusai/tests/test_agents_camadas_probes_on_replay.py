"""Agents 073 (agent layers BASE -> SDR -> agent), 074 (hand-off fallback number), 076 (eval-loop gate), 079
(emergency inactivity window), 080 (follow-up cap) 086 (eval-loop config) and 087 (one eval run per user): every GuardProbe of each
migration runs on the REAL core + agents chain on PGlite and reports `refused`. Own groups, like 049's geracao
probes: the 012-017 studio-probe class excludes them."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_GROUPS = {
    "073_agent_camadas.sql": (vdg._AGENTS_CAMADAS_PROBES,
                              {"agents_camada_check", "guard_agent_camada", "guard_version_pai_pin"}),
    "074_numero_fallback_atendimento.sql": (vdg._AGENTS_FALLBACK_PROBES,
                                            {"runtime_settings_key_check", "runtime_settings_numero_fallback_e164"}),
    "076_eval_loops.sql": (vdg._AGENTS_EVAL_LOOP_PROBES,
                           {"eval_loops_parada_consistente", "uq_agents_eval_loops_ativo_por_suite"}),
    "086_eval_loop_config.sql": (vdg._AGENTS_EVAL_LOOP_CONFIG_PROBES,
                                 {"runtime_settings_eval_loop_valores", "guard_eval_loop_config_eventos_append_only"}),
    "087_eval_um_por_usuario.sql": (vdg._AGENTS_EVAL_UM_POR_USUARIO_PROBES,
                                    {"guard_eval_um_por_usuario", "guard_eval_recusas_eventos_append_only"}),
    "079_emergencia_inatividade.sql": (vdg._AGENTS_EMERGENCIA_PROBES,
                                       {"thread_alertas_tipo_check", "ck_thread_participantes_fecha_inativo_min"}),
    "080_retomada_limite.sql": (vdg._AGENTS_RETOMADA_PROBES,
                                {"thread_retomada_eventos_append_only", "thread_retomada_eventos_resultado_check",
                                 "qualificacao_parametros_max_retomadas_check"}),
    "081_catalogo_opcoes.sql": (vdg._AGENTS_CATALOGO_PROBES,
                                {"qualificacao_parametros_catalogo_check", "lead_imovel_eventos_catalogo_check"}),
}


@pytest.mark.parametrize("mig", sorted(_GROUPS))
def test_the_probes_are_registered(mig):
    probes, guards = _GROUPS[mig]
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert {p.guard_name for p in probes} == guards
    for p in probes:
        assert by_id[p.id] is p and p.product == "agents" and p.migrations[-1] == mig


@pytest.mark.parametrize("mig", sorted(_GROUPS))
def test_every_probe_is_refused_on_the_real_chain(mig, pglite):
    probes, _ = _GROUPS[mig]
    migs = {f"products/agents/backend/migrations/{m}" for p in probes for m in p.migrations}
    steps = mr._steps_for(Path(REPO_ROOT), "agents", migs, "worktree", {})
    for p in probes:
        steps.append({"product": "agents", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in probes}
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    bad = {k: v for k, v in out.items() if v != "refused"}
    assert not bad and len(out) == len(probes), bad
