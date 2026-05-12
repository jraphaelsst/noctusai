"""SQLAlchemy ORM models for personal-finance.

The product's primary data path is the Supabase admin/user client (services
in `app.services.*_service.py` consume Supabase row dicts directly — no ORM
in the read/write hot path). SQLAlchemy is introduced here purely for the
seed `make_audit_writer(db, ToolCallAudit)` contract — the
`noctusai_lib.domain.ai.tool_audit` writer requires a typed table class.

See `app.services.audit_hook` for the wiring + lazy-engine pattern,
mirrored from `products/media-scheduling/backend/app/models/__init__.py`.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# SQLAlchemy bases — used only by audit-side ORM model below.
Base = declarative_base()
SCHEMA = "personal-finance"

from app.models.tool_call_audit import ToolCallAudit  # noqa: E402,F401

__all__ = [
    "Base",
    "SCHEMA",
    "ToolCallAudit",
]
