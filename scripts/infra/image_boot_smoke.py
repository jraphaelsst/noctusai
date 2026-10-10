"""Boot smoke for a freshly built product image — run INSIDE the image, before push.

Piped on stdin by `scripts/infra/build-and-push.sh` (`docker run -i --network none
... python - < image_boot_smoke.py`), with the product backend dir as the working
directory. Exit 0 ⇒ the image can import its app and answer `/api/health`.

WHY (2026-10-10 prod rollback). The core image crash-looped on boot:
`routers/transcriptions.py` uses `Form`/`File`, and core's requirements.txt lacked
`python-multipart`. FastAPI raises while REGISTERING such a route, i.e. at import.
Every gate (pytest, predeploy, CI) passed because they all run in the shared
venv, which carries the package transitively — only the image's OWN dependency
set is missing it. So the check has to run in the image itself.

Scope, deliberately: import + `GET /api/health` WITHOUT the lifespan (no
`with TestClient(...)`). Startup hooks reach for Redis/Supabase/schedulers that a
build runner does not have (`--network none`); those are covered by the deploy's
health probe + auto-rollback. This catches the class the shared venv hides:
a missing or broken runtime dependency, and an app that cannot be constructed.
"""
from __future__ import annotations

import sys
import traceback


def main() -> int:
    sys.path.insert(0, ".")
    try:
        import app.main as app_main
        from fastapi.testclient import TestClient

        response = TestClient(app_main.app).get("/api/health")
    except BaseException:  # noqa: BLE001 — any failure to boot IS the finding
        traceback.print_exc()
        print("IMAGE BOOT SMOKE: FAILED — the app does not import/construct in this image.",
              file=sys.stderr)
        return 1
    if response.status_code != 200:
        print(f"IMAGE BOOT SMOKE: FAILED — GET /api/health returned {response.status_code}: "
              f"{response.text[:300]}", file=sys.stderr)
        return 1
    print(f"IMAGE BOOT SMOKE: ok — app imported, /api/health 200 ({response.text[:120]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
