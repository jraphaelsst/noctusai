"""``media_creation`` dependency seams (storage)."""
from __future__ import annotations

from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import get_admin_client
from app.modules.certidoes.deps import storage_for

#: PRIVATE bucket (migration 204) — brand assets are never public; the UI gets
#: short-TTL signed URLs minted per request, never stored.
BRANDING_BUCKET = "social-wiring-branding"

#: Signed-URL lifetime for the branding gallery / font preview.
SIGNED_URL_TTL_SECONDS = 900


def get_branding_storage() -> StorageBackend:
    """FastAPI dependency — blob storage for branding assets.

    Same backend resolution as the certidões module (``storage_for`` on the
    RAW admin client). Tests MUST override this seam with a
    ``FakeStorageBackend``: the mock client's ``.storage`` is a bare
    ``MagicMock`` that answers anything and would "succeed" against garbage.
    """
    return storage_for(get_admin_client())


#: PRIVATE bucket (Migration 224) — brain file uploads only. Backend-only: no
#: authenticated storage policy; the UI gets short-TTL signed URLs.
CEREBRO_BUCKET = "social-wiring-cerebro"


def get_cerebro_storage() -> StorageBackend:
    """FastAPI dependency — blob storage for Segundo Cérebro file uploads.

    Same resolution as :func:`get_branding_storage`. Tests MUST override this
    seam with a ``FakeStorageBackend`` (the mock client's ``.storage`` is a bare
    ``MagicMock`` that answers anything).
    """
    return storage_for(get_admin_client())
