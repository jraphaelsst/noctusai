"""``create_api_keys_router(...)`` — the org-scoped managed-API-keys router.

Lifted 2026-09-17 (`community uses social-wiring's mechanisms`, Slice A)
from `social-wiring`'s ``app/routers/settings_router.py`` API-keys
section (``get_api_key_store_dep`` / ``get_api_key_store_optional_dep`` /
``list_api_keys`` / ``update_api_key`` / ``remove_api_key`` /
``test_api_key``). `social-wiring` is NOT modified in this slice — its
own router keeps running unchanged; it migrates to consume this factory
in a later slice (see the
``NOC-REMEDIATE[sw-consume-seed-api-keys]`` marker left in
``app/services/api_keys_store.py``).

Exact contract preserved (paths, request/response shapes, status codes)::

    GET    /api/settings/api-keys              -> ApiKeysStatusOut
    PUT    /api/settings/api-keys/{key}         -> ApiKeyStatusOut
    DELETE /api/settings/api-keys/{key}         -> ApiKeyStatusOut
    POST   /api/settings/api-keys/{key}/test    -> ApiKeyTestResultOut

**Decoupling.** This module imports NOTHING from ``app.*``. Everything
product-specific is a parameter:

- ``specs``: the ``ApiKeySpec`` tuple (which keys are managed).
- ``store_factory``: zero-arg callable building the encrypted store
  (``noctusai_lib.security.api_keys.build_api_key_store`` bound to the
  product's client/schema/table via ``functools.partial`` — or an
  equivalent). Raising ``EncryptionNotConfigured`` is mapped to a 503
  on the WRITE paths (mirrors `social-wiring`'s ``get_api_key_store_dep``)
  and degrades to platform-chain-only resolution on the READ paths
  (mirrors ``get_api_key_store_optional_dep``).
- ``get_current_user_org``: a FastAPI dependency resolving
  ``(user, token, org_id)`` — e.g. built via
  ``noctusai_lib.api.auth.make_get_current_user_org``.
- ``testers``: optional ``{spec_name: async fn(value) -> ApiKeyTestResultOut}``
  mapping for ``POST .../test``. A key with no tester registered 400s
  with the same "Teste não disponível" message `social-wiring` uses.
  Testers are product-specific (pt-BR operator-facing probe logic) and
  stay product-owned — this router only dispatches to them.
- ``require_admin``: optional ``(user, context: str) -> None`` gate for
  the two WRITE routes (403 when it raises). Defaults to a no-op (open
  write) — a product wanting `social-wiring`'s owner/admin gate passes
  its own check (deliberately NOT lifted here; that check reads
  ``user.user_metadata`` directly rather than the trusted
  ``public.noctus_users.org_role`` — see `social-wiring`'s own
  ``_require_admin`` docstring for why it stayed product-local N=2).

Per ``KB § PATTERNS/backend/di-test-seam.md`` (Class-B): every product
concern is a constructor kwarg, never a module-level monkeypatch target.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.security.api_keys import (
    ApiKeySpec,
    EncryptionNotConfigured,
    resolve_api_key_detail,
    put_api_key,
    delete_api_key,
    mask_value,
)

logger = logging.getLogger(__name__)

#: Signature every entry in the ``testers`` mapping must satisfy.
ApiKeyTester = Callable[[str], Awaitable["ApiKeyTestResultOut"]]

#: No-op admin gate — the default when a product doesn't pass its own.
def _open_admin_gate(user: Any, context: str) -> None:  # noqa: ARG001
    return None


class ApiKeyOptionOut(StrictHttpModel):
    value: str
    label: str
    description: str = ""


class ApiKeyStatusOut(StrictHttpModel):
    key: str
    label: str
    description: str
    is_secret: bool
    testable: bool
    input_type: str
    placeholder: str
    configured: bool
    options: list[ApiKeyOptionOut] = []
    default: Optional[str] = None
    hint: Optional[str] = None
    source: Optional[str] = None
    updated_at: Optional[datetime] = None


class ApiKeysStatusOut(StrictHttpModel):
    items: list[ApiKeyStatusOut]
    total: int


class ApiKeyUpdateIn(StrictHttpModel):
    value: str


class ApiKeyTestResultOut(StrictHttpModel):
    key: str
    success: bool
    message: str


def _spec_or_404(key: str, specs_by_name: dict[str, ApiKeySpec]) -> ApiKeySpec:
    spec = specs_by_name.get(key)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{key}' não é uma chave gerenciável. "
                f"Disponíveis: {', '.join(specs_by_name)}."
            ),
        )
    return spec


def create_api_keys_router(
    deps: Any,
    settings: Any,
    *,
    specs: Iterable[ApiKeySpec],
    store_factory: Callable[[], Any],
    get_current_user_org: Callable[..., Any],
    testers: Optional[dict[str, ApiKeyTester]] = None,
    require_admin: Callable[[Any, str], None] = _open_admin_gate,
    resolver: Callable[[str, Optional[str]], Optional[str]] = resolve_credential,
    prefix: str = "/api/settings",
) -> APIRouter:
    """Build the ``/api/settings/api-keys*`` router.

    ``deps`` / ``settings`` are accepted (unused directly) for
    call-site symmetry with the other ``noctusai_seed`` router
    factories (``create_auth_router(deps, settings)`` etc.) — every
    piece THIS router actually needs is threaded through explicitly
    below instead of read off either object, so a product with a
    non-standard ``deps``/``settings`` shape is never blocked.

    ``resolver`` is the tier-2 DI seam ``resolve_api_key_detail`` itself
    exposes, forwarded rather than left at its hardcoded default so a
    test can exercise the platform-chain fallback deterministically
    instead of reaching the ambient shared ``noctusai_lib.config.
    credentials`` singleton (which a DIFFERENT test in the same process
    may have already configured via ``create_product_app`` — per
    ``KB § PATTERNS/backend/di-test-seam.md``, Class-B).
    """
    specs_by_name = {spec.name: spec for spec in specs}
    testers = dict(testers or {})
    router = APIRouter(prefix=prefix, tags=["settings"])

    def _store_dep():
        """WRITE-path DI seam — a config gap 503s rather than persisting
        plaintext. Mirrors `social-wiring`'s ``get_api_key_store_dep``."""
        try:
            return store_factory()
        except EncryptionNotConfigured as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc

    def _store_optional_dep():
        """READ-path DI seam — a config gap degrades to platform-chain-only
        resolution (``None``) instead of raising. Mirrors `social-wiring`'s
        ``get_api_key_store_optional_dep``."""
        try:
            return store_factory()
        except EncryptionNotConfigured:
            return None

    def _status(spec: ApiKeySpec, org_id: Any, store: Any) -> ApiKeyStatusOut:
        resolution = resolve_api_key_detail(spec.name, str(org_id), store=store, resolver=resolver)
        return ApiKeyStatusOut(
            key=spec.name,
            label=spec.label,
            description=spec.description,
            is_secret=spec.is_secret,
            testable=spec.testable,
            input_type=spec.input_type,
            placeholder=spec.placeholder,
            configured=resolution.configured,
            options=[
                ApiKeyOptionOut(value=o.value, label=o.label, description=o.description)
                for o in spec.options
            ],
            default=spec.default,
            hint=mask_value(resolution.value, spec),
            source=resolution.source,
            updated_at=resolution.updated_at,
        )

    @router.get("/api-keys", response_model=ApiKeysStatusOut)
    def list_api_keys(
        auth: tuple = Depends(get_current_user_org),
        store: Any = Depends(_store_optional_dep),
    ) -> ApiKeysStatusOut:
        _user, _token, raw_org = auth
        items = [_status(spec, raw_org, store) for spec in specs_by_name.values()]
        return ApiKeysStatusOut(items=items, total=len(items))

    @router.put("/api-keys/{key}", response_model=ApiKeyStatusOut)
    def update_api_key(
        key: str,
        payload: ApiKeyUpdateIn,
        auth: tuple = Depends(get_current_user_org),
        store: Any = Depends(_store_dep),
    ) -> ApiKeyStatusOut:
        user, _token, raw_org = auth
        require_admin(user, "Chaves de API")
        spec = _spec_or_404(key, specs_by_name)

        value = payload.value.strip()
        if not value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Informe um valor. Para limpar a chave, use remover.",
            )
        if spec.options and value not in spec.allowed_values:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"'{value}' não é uma opção válida para {spec.label}. "
                    f"Use uma de: {', '.join(spec.allowed_values)}."
                ),
            )
        put_api_key(store, str(raw_org), spec.name, value)
        logger.info(
            "api_keys: %s updated for org %s by %s",
            spec.name, raw_org, getattr(user, "id", "unknown"),
        )
        return _status(spec, raw_org, store)

    @router.delete("/api-keys/{key}", response_model=ApiKeyStatusOut)
    def remove_api_key(
        key: str,
        auth: tuple = Depends(get_current_user_org),
        store: Any = Depends(_store_dep),
    ) -> ApiKeyStatusOut:
        user, _token, raw_org = auth
        require_admin(user, "Chaves de API")
        spec = _spec_or_404(key, specs_by_name)

        removed = delete_api_key(store, str(raw_org), spec.name)
        logger.info(
            "api_keys: %s local override %s for org %s",
            spec.name, "removed" if removed else "was already absent", raw_org,
        )
        return _status(spec, raw_org, store)

    @router.post("/api-keys/{key}/test", response_model=ApiKeyTestResultOut)
    async def test_api_key(
        key: str,
        auth: tuple = Depends(get_current_user_org),
        store: Any = Depends(_store_optional_dep),
    ) -> ApiKeyTestResultOut:
        _user, _token, raw_org = auth
        spec = _spec_or_404(key, specs_by_name)
        tester = testers.get(spec.name)
        if tester is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Teste não disponível para '{spec.name}'.",
            )
        value = resolve_api_key_detail(spec.name, str(raw_org), store=store, resolver=resolver).value
        if not value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{spec.label} não está configurada. "
                    "Configure em Configurações → Chaves de API."
                ),
            )
        return await tester(value)

    return router
