"""API layer — FastAPI-specific concerns the seed exposes to products.

**Layer contract.** Anything in `api/` MUST:
- Live entirely above the FastAPI request boundary — middleware,
  dependency factories, routers the seed mounts, request/response shapes.
- May import from `primitives/`, `config/`, `integrations/database`.
- MUST NOT import from `domain/` (the dependency goes the other way —
  domain code is consumed BY routers, not the reverse).

**Why a layer.** "FastAPI things" used to be smeared across the seed-lib
top level (`auth.py`, `middleware.py`, `roles.py`, `rate_limit.py`,
`app_factory.py`). Future API additions (mounted routers, exception
handlers, CORS config) belong here too. Centralizing means a fresh agent
opening `noctusai_lib/api/` sees the full surface of "what the seed
contributes to a product's HTTP layer".

**Active occupants:**
- `auth.py` — JWT + SSO factories, `verify_*` helpers
- `middleware.py` — correlation-ID middleware, request logger
- `rate_limit.py` — slowapi configuration helpers
- `app_factory.py` — `create_product_app(...)` companion shim
- `crud_safety.py` — `delete_with_existence_check` + `delete_or_404` (replaces the unreliable `.delete()` + `if not result.data` 404 shape)

(`roles.py` was originally planned here, but it's pure constants +
predicates — no FastAPI, no IO. Moved to `primitives/roles.py` during
Step 3 cleanup so `domain/` code can use it without violating the
dep-direction rule.)

See `KB § PATTERNS/seed-lib-layout.md` for the full layer model.
"""
