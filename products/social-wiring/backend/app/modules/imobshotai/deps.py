"""DI seams of ImobShotAI. Free of `edicao_fotos` imports so the photo routes can depend on it without a cycle."""
from __future__ import annotations

import threading
from typing import Optional

from app.modules.imobshotai.repository import ImobshotRepository, SupabaseImobshotRepository

_lock = threading.Lock()
_repo: Optional[ImobshotRepository] = None


def build_imobshot_repository() -> ImobshotRepository:
    from app.dependencies import get_scoped_admin_client

    return SupabaseImobshotRepository(get_scoped_admin_client("social_wiring"))


def get_imobshot_repository() -> ImobshotRepository:
    """Seam: the card store (process-wide, built on first use)."""
    global _repo
    with _lock:
        if _repo is None:
            _repo = build_imobshot_repository()
        return _repo


__all__ = ["build_imobshot_repository", "get_imobshot_repository"]
