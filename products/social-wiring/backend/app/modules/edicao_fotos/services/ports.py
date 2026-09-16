"""Wires the seed photo-editing engine onto social-wiring's real adapters.

`build_ports()` is the ONE place the product decides which concrete adapter
backs each engine port (`KB § PATTERNS/backend/photo-editing-seed.md` §4):

| port        | adapter |
|-------------|---------|
| repo        | `make_photo_editing_repository` over a PUBLIC-default service-role client (`get_core_client`) — the pipeline tables are reached through `.schema("social_wiring")`, and `cost_ledger` (Core 046) through the bare `public` table. The product's admin client defaults to `social_wiring`, which would send `cost_ledger` writes to the wrong schema. |
| jobs        | `make_job_repository` over the `social_wiring`-default admin client — `claim_next_job` & co. live in `social_wiring` (migration 121) and are called as bare RPCs. |
| storage     | `BucketPhotoStorage` over the seed Supabase `StorageBackend`, bucket `edicao-fotos` (migration 127). |
| reference_storage | `BucketPhotoStorage`, bucket `edicao-fotos-referencias` (migration 127) — the global reference pool; pairs store keys here. |
| imaging     | `get_imaging_adapter()` (Pillow). |
| image_edit  | `openai_image_edit_factory(resolve_credential("openai_api_key", org))` — REFUSES without a key; never the Fake. |
| llm         | `LlmStructuredAdapter()`. |
| fx          | `get_fx_rate_adapter(live=True)` (BCB PTAX). |
| notifier    | `InAppBatchReadyNotifier`. |
| edit_quota  | `DefaultingQuotaTracker` (Redis when `REDIS_URL` resolves) capped by `EDICAO_FOTOS_EDICOES_POR_DIA`. |

Built lazily and cached: nothing here runs at import time.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.domain.jobs import make_job_repository
from noctusai_lib.domain.permissions import (
    PermissionGrantRepository,
    make_permission_grant_repository,
)
from noctusai_lib.domain.photo_editing import (
    BucketPhotoStorage,
    LlmStructuredAdapter,
    PhotoEditingPorts,
    make_photo_editing_repository,
    openai_image_edit_factory,
)
from noctusai_lib.integrations.fx import get_fx_rate_adapter
from noctusai_lib.integrations.imaging import get_imaging_adapter
from noctusai_lib.integrations.quota import (
    DefaultingQuotaTracker,
    QuotaConfig,
    QuotaTracker,
    make_quota_tracker,
)
from noctusai_lib.integrations.storage import make_storage_backend

from app.modules.edicao_fotos.services.notifier import InAppBatchReadyNotifier

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
COST_SCHEMA = "public"
BUCKET_FOTOS = "edicao-fotos"
BUCKET_REFERENCIAS = "edicao-fotos-referencias"
QUOTA_WINDOW_SECONDS = 86_400


class EdicaoFotosUnavailable(RuntimeError):
    """The engine cannot be wired in this process (no Supabase service role)."""

    code = "edicao_fotos_indisponivel"


def openai_key_for_org(org_id: Optional[str]) -> Optional[str]:
    """The platform credential chain (product store → org → platform → env)."""
    return resolve_credential("openai_api_key", org_id)


def build_edit_quota(cfg: Any) -> QuotaTracker:
    default = QuotaConfig(cap=int(cfg.edicao_fotos_edicoes_por_dia), window_seconds=QUOTA_WINDOW_SECONDS)
    redis_url = getattr(cfg, "redis_url", "") or ""
    if redis_url:
        from noctusai_lib.integrations.redis import make_redis_client

        inner = make_quota_tracker(
            kind="redis", redis_client=make_redis_client(redis_url), key_prefix="noctus:quota:sw"
        )
    else:
        logger.warning(
            "edicao_fotos: REDIS_URL vazio — cota de edições em memória (reinicia com o processo)."
        )
        inner = make_quota_tracker(kind="memory")
    return DefaultingQuotaTracker(inner, default=default)


def _clients() -> tuple[Any, Any]:
    from app.dependencies import _use_sqlite, get_admin_client, get_core_client

    if _use_sqlite:
        raise EdicaoFotosUnavailable(
            "Edição de Fotos requer o Supabase (DATABASE_BACKEND=sqlite não suporta o pipeline)."
        )
    return get_admin_client(), get_core_client()


def build_ports(cfg: Any) -> PhotoEditingPorts:
    admin, core = _clients()
    repo = make_photo_editing_repository(
        supabase_client=core, schema=SCHEMA, cost_schema=COST_SCHEMA
    )
    backend = make_storage_backend(kind="supabase", client=admin)
    return PhotoEditingPorts(
        repo=repo,
        jobs=make_job_repository(supabase_client=admin, schema_name=SCHEMA),
        storage=BucketPhotoStorage(backend, bucket=BUCKET_FOTOS),
        reference_storage=BucketPhotoStorage(backend, bucket=BUCKET_REFERENCIAS),
        imaging=get_imaging_adapter(),
        image_edit=openai_image_edit_factory(openai_key_for_org),
        llm=LlmStructuredAdapter(),
        fx=get_fx_rate_adapter(live=True),
        notifier=InAppBatchReadyNotifier(core_client=lambda: core, repo=repo),
        edit_quota=build_edit_quota(cfg),
    )


def build_grant_repository() -> PermissionGrantRepository:
    _admin, core = _clients()
    return make_permission_grant_repository(supabase_client=core)


_lock = threading.Lock()
_ports: Optional[PhotoEditingPorts] = None
_grants: Optional[PermissionGrantRepository] = None


def get_ports(cfg: Any) -> PhotoEditingPorts:
    """Process-wide ports, built on first use."""
    global _ports
    with _lock:
        if _ports is None:
            _ports = build_ports(cfg)
        return _ports


def get_grant_repository() -> PermissionGrantRepository:
    global _grants
    with _lock:
        if _grants is None:
            _grants = build_grant_repository()
        return _grants


__all__ = [
    "BUCKET_FOTOS",
    "BUCKET_REFERENCIAS",
    "EdicaoFotosUnavailable",
    "build_edit_quota",
    "build_grant_repository",
    "build_ports",
    "get_grant_repository",
    "get_ports",
    "openai_key_for_org",
]
