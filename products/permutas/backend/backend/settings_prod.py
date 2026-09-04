"""Production settings shim — permutas (absorbed legacy Permutas platform).

Promoted from `deploy/legacy/settings_prod.py` when the app was absorbed into
noc as `products/permutas/` (2026-09-04). Two jobs:

1. Keep the upstream base config intact while overriding, from the environment,
   the things the vendored `settings.py` hardcodes insecurely
   (`SECRET_KEY`, `DEBUG = True`, fixed `ALLOWED_HOSTS`).
2. Route the ORM at noc's own database — schema `permutas` in the `noctusai`
   Supabase project — instead of the retired standalone `One Permutas` project.

`DJANGO_SETTINGS_MODULE=backend.settings_prod` is set in the Dockerfile.
"""
import os

from backend.settings import *  # noqa: F401,F403  (inherit the app's base config)

# Required at runtime — fail loud if unset (NEVER fall back to the dev literal,
# which is committed in a public repo). The build-time `collectstatic` step
# passes a throwaway value inline; the container runtime supplies the real key.
SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Served behind the Cloudflare tunnel (TLS terminated at the edge) → trust the
# forwarded proto so Django builds https URLs + sets secure cookies.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ─── Schema routing: noc's database, `permutas` schema ────────────────────────
# The absorption moved all 27 tables out of the standalone `One Permutas`
# project and into schema `permutas` of the shared `noctusai` project (verified
# row-for-row + md5-per-table, 2026-09-04). Table NAMES are unchanged, so the
# ORM needs no model edits — only a search_path telling Postgres where to look.
#
# `public` is kept as a fallback so shared extensions still resolve, but
# `permutas` is FIRST: an unqualified CREATE/INSERT lands in our schema, never
# in the fleet's shared `public`.
#
# NOTE the base settings assign `OPTIONS = {'sslmode': 'require'}` wholesale,
# which would DROP anything set before it — so this merge must run AFTER the
# `from backend.settings import *` above, and must preserve sslmode.
PERMUTAS_DB_SCHEMA = os.environ.get("PERMUTAS_DB_SCHEMA", "permutas")
if DATABASES.get("default", {}).get("ENGINE", "").endswith("postgresql"):  # noqa: F405
    _opts = dict(DATABASES["default"].get("OPTIONS") or {})  # noqa: F405
    _opts.setdefault("sslmode", "require")
    _opts["options"] = f"-c search_path={PERMUTAS_DB_SCHEMA},public"
    DATABASES["default"]["OPTIONS"] = _opts  # noqa: F405

# ─── Authorization: deny by default (defense in depth) ────────────────────────
# DRF's built-in DEFAULT_PERMISSION_CLASSES is AllowAny, so any viewset that
# simply OMITS `permission_classes` is world-readable AND world-writable. On
# 2026-08-26 that shipped `/api/condominio/`, `/api/imovel/` and
# `/api/proprietario/` (full ModelViewSet CRUD, incl. 256 proprietário rows of
# LGPD personal data) to anonymous callers on the public internet.
#
# Re-asserted HERE because this is the layer we control at deploy time: if the
# vendored app source is ever rolled back or repointed, the base settings alone
# would silently reopen the hole.
#
# Scope note: this covers viewsets that inherit the DEFAULT. It canNOT override
# a viewset that sets `permission_classes` explicitly.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405  (inherited from backend.settings)
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}
