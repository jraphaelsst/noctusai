"""DI seam for the website build's `_site/` directory.

Both `website_settings_service` (reads `_site/settings.defaults.json`) and
`website_html` (reads `_site/manifest.json` + prerendered pages) need to
know where the built website lives. Production reads it from
`settings.serve_spa_dir` (itself sourced from `SERVE_SPA_DIR`, the same
env var `noctusai_seed.app._mount_spa` uses). Tests install an explicit
tmp directory here instead of monkeypatching the `settings` singleton —
the seam every other product-local service with a swappable collaborator
uses (mirrors `app.services.webhook_delivery.configure_webhook_sender` /
`reset_webhook_sender`). `KB § PATTERNS/backend/di-test-seam.md`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from app.config import settings

_override: Optional[Path] = None


def configure_site_dir(path: Optional[Union[str, Path]]) -> None:
    """Install (or with `None`, clear) an explicit spa-dir override."""
    global _override
    _override = Path(path) if path is not None else None


def reset_site_dir() -> None:
    """Drop any injected override. Fixture teardown calls this — always
    pair with `configure_site_dir`, exactly like
    `webhook_delivery.reset_webhook_sender`."""
    configure_site_dir(None)


def get_spa_dir() -> Path:
    """The single-container SPA/website build root (contains `_site/`)."""
    if _override is not None:
        return _override
    return Path(settings.serve_spa_dir)


__all__ = ["configure_site_dir", "get_spa_dir", "reset_site_dir"]
