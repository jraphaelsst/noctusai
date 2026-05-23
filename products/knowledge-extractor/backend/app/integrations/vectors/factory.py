"""VectorStore factory.

Mirrors ``make_drive_downloader`` — routes to Fake or a Real adapter.

Usage:
    store = make_vector_store(use_fake=True)         # tests / demo
    store = make_vector_store()                       # production (Supabase)
    store = make_vector_store(url=..., key=...)       # explicit credentials
"""
from __future__ import annotations

from app.integrations.vectors.protocol import VectorStore


def make_vector_store(
    *,
    use_fake: bool = False,
    use_local: bool = False,
    local_path: str | None = None,
    url: str | None = None,
    service_role_key: str | None = None,
) -> VectorStore:
    """Build a VectorStore per the given parameters.

    Parameters
    ----------
    use_fake:
        Return an in-memory ``FakeVectorStore`` (no network, no Supabase).
    url:
        Supabase project URL.  Falls back to ``settings.supabase_url`` when
        not supplied.  Ignored when ``use_fake=True``.
    service_role_key:
        Supabase service-role key.  Falls back to
        ``settings.supabase_service_role_key``.  Ignored when ``use_fake=True``.

    Raises
    ------
    VectorStoreNotConfigured
        ``use_fake=False`` but Supabase credentials are missing.
    """
    if use_fake:
        from app.integrations.vectors.fake import FakeVectorStore

        return FakeVectorStore()

    from app.config import get_settings

    settings = get_settings()

    if use_local:
        from app.integrations.vectors.local import LocalVectorStore

        path = local_path or getattr(settings, "kb_local_path", "data/kb_local.json")
        return LocalVectorStore(path)

    from app.integrations.vectors.supabase_adapter import SupabaseVectorStore

    # `None` = "not supplied" → fall back to settings. An explicit "" means
    # the caller is asserting "no credentials" → no fallback (so the no-creds
    # path is testable in a credentialed env like noc, where settings carries
    # the dev .env supabase_url). Distinguishing None from "" is what keeps the
    # raise path deterministic regardless of ambient .env.
    effective_url = (
        getattr(settings, "supabase_url", None) if url is None else url
    ) or ""
    effective_key = (
        getattr(settings, "supabase_service_role_key", None)
        if service_role_key is None
        else service_role_key
    ) or ""

    if not effective_url or not effective_key:
        raise VectorStoreNotConfigured(
            "Supabase credentials are not configured.  Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in .env, or pass url= / service_role_key= "
            "directly, or use make_vector_store(use_fake=True) for local dev."
        )

    return SupabaseVectorStore(url=effective_url, service_role_key=effective_key)


class VectorStoreNotConfigured(RuntimeError):
    """Supabase credentials missing — surfaced loudly, never silently degraded."""


__all__ = ["make_vector_store", "VectorStoreNotConfigured"]
