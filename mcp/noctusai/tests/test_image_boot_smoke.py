"""scripts/infra/image_boot_smoke.py — the in-image boot smoke build-and-push.sh
runs before pushing (2026-10-10 core crash-loop on a missing python-multipart).

Exercised on the host against synthetic backends (the payload is plain Python;
the image only supplies cwd + interpreter), plus the wiring in the build script."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PAYLOAD = REPO / "scripts/infra/image_boot_smoke.py"
BUILD = REPO / "scripts/infra/build-and-push.sh"


def _backend(tmp_path: Path, main_py: str) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app/__init__.py").write_text("")
    (tmp_path / "app/main.py").write_text(main_py)
    return tmp_path


def _run(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-", ], cwd=cwd, input=PAYLOAD.read_text(),
                          capture_output=True, text=True, timeout=120)


def test_healthy_app_passes(tmp_path):
    r = _run(_backend(tmp_path, (
        "from fastapi import FastAPI\napp = FastAPI()\n"
        "@app.get('/api/health')\ndef h():\n    return {'status': 'ok'}\n")))
    assert r.returncode == 0, r.stderr
    assert "IMAGE BOOT SMOKE: ok" in r.stdout


def test_import_time_failure_fails(tmp_path):
    # The prod shape: FastAPI raises while registering a Form route when
    # python-multipart is absent — i.e. at import.
    r = _run(_backend(tmp_path, "raise RuntimeError('Form data requires \"python-multipart\"')\n"))
    assert r.returncode == 1
    assert "python-multipart" in r.stderr and "FAILED" in r.stderr


def test_missing_module_fails(tmp_path):
    r = _run(_backend(tmp_path, "import not_a_declared_dependency_xyz\n"))
    assert r.returncode == 1
    assert "ModuleNotFoundError" in r.stderr


def test_unhealthy_health_fails(tmp_path):
    r = _run(_backend(tmp_path, (
        "from fastapi import FastAPI\nfrom fastapi.responses import JSONResponse\napp = FastAPI()\n"
        "@app.get('/api/health')\ndef h():\n    return JSONResponse({'status': 'down'}, status_code=503)\n")))
    assert r.returncode == 1
    assert "503" in r.stderr


def test_lifespan_is_not_run(tmp_path):
    # Startup hooks need services a build runner (--network none) lacks; the
    # smoke must judge the image's deps, not the runner's network.
    r = _run(_backend(tmp_path, (
        "from contextlib import asynccontextmanager\nfrom fastapi import FastAPI\n"
        "@asynccontextmanager\nasync def life(app):\n    raise ConnectionError('redis')\n    yield\n"
        "app = FastAPI(lifespan=life)\n"
        "@app.get('/api/health')\ndef h():\n    return {'status': 'ok'}\n")))
    assert r.returncode == 0, r.stderr


def test_build_script_smokes_every_image_before_the_push_section():
    src = BUILD.read_text()
    build_fn = src[src.index("build_product() {"):src.index("boot_smoke() {")]
    assert 'boot_smoke "$slug" "$image"' in build_fn
    assert src.index("boot_smoke() {") < src.index("# ── 3. login + push")
    assert "--network none" in src and "image_boot_smoke.py" in src
    assert "-e REDIS_URL=" in src  # no service reachable ⇒ declare no Redis
