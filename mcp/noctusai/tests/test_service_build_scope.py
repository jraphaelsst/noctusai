"""Sanctioned services (deploy/fleet/services.txt) are scoped by their OWN build
workflow's `on.push.paths`, not by the fleet-wide product predicate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import build_scope as BS  # noqa: E402
from tools.noctus.dev import deploy_verify as DV  # noqa: E402
from tools.noctus.dev.deploy_pull import _rebuild_decision  # noqa: E402


def _drift(slug, files):
    def run_local(cmd):
        if cmd[:2] == ["git", "cat-file"]:
            return 0, "", ""
        return 0, "\n".join(files) + "\n", ""
    return DV._diff_drift(run_local, slug, "a" * 40, "b" * 40)


def test_workflow_paths_are_the_scope_source():
    paths = BS.service_build_paths("transcriber")
    assert "deploy/services/transcriber/**" in paths
    assert BS.service_build_paths("no-such-service") == []


def test_seed_dockerfile_compose_only_diff_is_steady_state():
    d = _drift("transcriber", [
        "seed/lib/backend/noctusai_lib/foo.py", "Dockerfile",
        "products/store/backend/Dockerfile", "deploy/fleet/docker-compose.prod.yml",
        "seed/lib/backend/noctusai_lib/integrations/other/x.py",
    ])
    assert d["actionable_drift"] is False and d["fleet_wide_change"] is False


@pytest.mark.parametrize("f", [
    "deploy/services/transcriber/Dockerfile",
    "deploy/services/transcriber/requirements.lock",
    "seed/lib/backend/noctusai_lib/integrations/transcription/worker.py",
    ".github/workflows/build-transcriber.yml",
])
def test_service_own_inputs_are_drift(f):
    d = _drift("transcriber", ["seed/lib/x.py", f])
    assert d["actionable_drift"] is True and f in d["build_relevant_files"]


def test_products_unaffected():
    assert _drift("store", ["deploy/services/transcriber/Dockerfile"])["actionable_drift"] is False
    assert _drift("store", ["seed/lib/x.py"])["actionable_drift"] is True


def test_rebuild_decision_service_files_not_fleet_wide():
    r = _rebuild_decision(["deploy/services/transcriber/Dockerfile"], build_set=["core", "store"])
    assert r["services"] == ["transcriber"] and r["fleet_wide"] is False
    assert r["rebuild_set"] == [] and r["needed"] is True
    seed = _rebuild_decision(["seed/lib/x.py"], build_set=["core", "store"])
    assert seed["services"] == [] and seed["fleet_wide"] is True
