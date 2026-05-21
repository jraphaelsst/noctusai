"""Production settings shim for the legacy one-permutas app.

The reference `backend/backend/settings.py` HARDCODES an insecure `SECRET_KEY`,
`DEBUG = True`, and a fixed `ALLOWED_HOSTS` — and the reference repo is
READ-ONLY (an external snapshot we don't edit). This shim imports that base and
overrides only those three (plus CSRF + proxy-TLS) from the environment, so a
prod deploy is secure without touching upstream.

Wiring: the deploy step copies this file into the build context's `backend/`
(next to `settings.py`), and the Dockerfile sets
`DJANGO_SETTINGS_MODULE=backend.settings_prod`. Env var NAMES match
`deploy/legacy/.env.example` (SECRET_KEY / DEBUG / ALLOWED_HOSTS /
CSRF_TRUSTED_ORIGINS).
"""
import os

from backend.settings import *  # noqa: F401,F403  (inherit the app's base config)

# Required at runtime — fail loud if unset (NEVER fall back to the dev literal,
# which is committed in a public repo). The build-time `collectstatic` step
# passes a throwaway value inline; the container runtime supplies the real key
# via the compose env_file.
SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Served behind Caddy / the Cloudflare tunnel (TLS terminated at the edge) →
# trust the forwarded proto so Django builds https URLs + sets secure cookies.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
