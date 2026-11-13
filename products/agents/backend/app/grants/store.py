"""``agents.agent_product_grants`` (migration 060) -- the platform grant ledger.

Seed IO shape: ``GrantStore`` Protocol + ``FakeGrantStore`` + ``SupabaseGrantStore`` + ``get_grant_store(settings)``.
Holds token IDS only, never a secret. One live (``pendente`` / ``ativo``) grant per (org, agent, product): a second
``begin`` raises :class:`GrantExists` (the Real maps the partial UNIQUE index violation, the Fake mirrors it).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import db_ts, utcnow, utcnow_iso
from app.stores.errors import Conflict, NotFound

__all__ = [
    "LIVE_STATUSES",
    "STALE_PENDING",
    "FakeGrantStore",
    "Grant",
    "GrantExists",
    "GrantStore",
    "SupabaseGrantStore",
    "get_grant_store",
]

_SCHEMA = "agents"
_TABLE = "agent_product_grants"
LIVE_STATUSES = ("pendente", "ativo")
#: A ``pendente`` row older than this is an attempt that died mid-flight (process crash): ``begin`` retires it as
#: ``falhou`` instead of letting it block the triple forever.
STALE_PENDING = timedelta(minutes=15)
_COLUMNS = (
    "id, org_id, agent_id, agent_key, product, status, channel_token_id, product_token_id, expires_at, "
    "created_by, created_at, revoked_by, revoked_at, last_delivered_at, last_error, especificacoes_editor"
)


class GrantExists(Conflict):
    """A live grant already exists for this (org, agent, product)."""


@dataclass(frozen=True)
class Grant:
    id: UUID
    org_id: UUID
    agent_id: UUID
    agent_key: str
    product: str
    status: str
    channel_token_id: UUID | None = None
    product_token_id: UUID | None = None
    expires_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    revoked_by: UUID | None = None
    revoked_at: datetime | None = None
    last_delivered_at: datetime | None = None
    last_error: str | None = None
    #: Who fills the org's agent specs under this grant (migration 064): ``plataforma`` (staff, Studio) | ``org`` (reserved).
    especificacoes_editor: str = "plataforma"

    def is_live(self, now: datetime | None = None) -> bool:
        """The grant authorizes anything only while ``ativo`` and not expired (NULL expiry = never)."""
        if self.status != "ativo":
            return False
        return self.expires_at is None or self.expires_at > (now or utcnow())


class GrantStore(Protocol):
    def list(self, *, org_id: UUID | None = None) -> list[Grant]:
        """Newest first. Capped by the store (a grant ledger is small; never unbounded)."""
        ...

    def get(self, grant_id: UUID) -> Grant:
        """Raises :class:`NotFound`."""
        ...

    def find_by_channel_token(self, channel_token_id: UUID) -> Grant | None:
        """The grant whose CHANNEL token this is (the request-time liveness check), or ``None``."""
        ...

    def begin(
        self, *, org_id: UUID, agent_id: UUID, agent_key: str, product: str, expires_at: datetime | None,
        created_by: UUID | None,
    ) -> Grant:
        """Insert a ``pendente`` grant. Raises :class:`GrantExists` when a live one exists for the triple."""
        ...

    def activate(
        self, grant_id: UUID, *, channel_token_id: UUID, product_token_id: UUID | None,
    ) -> Grant:
        """-> ``ativo`` with the token ids (``product_token_id`` is ``None`` for a product without a tools token), ``last_delivered_at`` now, ``last_error`` cleared."""
        ...

    def mark_failed(self, grant_id: UUID, error: str) -> Grant:
        """-> ``falhou`` with ``last_error`` (no secrets)."""
        ...

    def note_error(self, grant_id: UUID, error: str | None) -> Grant:
        """Set / clear ``last_error`` without changing the status (a rotation that failed leaves the old pair live)."""
        ...

    def mark_revoked(self, grant_id: UUID, *, revoked_by: UUID | None) -> Grant:
        ...


def _row_grant(row: dict[str, Any]) -> Grant:
    def _uuid(v: Any) -> UUID | None:
        return UUID(str(v)) if v else None

    return Grant(
        id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
        agent_key=row["agent_key"], product=row["product"], status=row["status"],
        channel_token_id=_uuid(row.get("channel_token_id")), product_token_id=_uuid(row.get("product_token_id")),
        expires_at=db_ts(row.get("expires_at")), created_by=_uuid(row.get("created_by")),
        created_at=db_ts(row.get("created_at")), revoked_by=_uuid(row.get("revoked_by")),
        revoked_at=db_ts(row.get("revoked_at")), last_delivered_at=db_ts(row.get("last_delivered_at")),
        last_error=row.get("last_error"), especificacoes_editor=row.get("especificacoes_editor") or "plataforma",
    )


class FakeGrantStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, Grant] = {}

    def _put(self, grant: Grant) -> Grant:
        self._rows[grant.id] = grant
        return grant

    def list(self, *, org_id: UUID | None = None) -> list[Grant]:
        rows = [g for g in self._rows.values() if org_id is None or g.org_id == org_id]
        return sorted(rows, key=lambda g: g.created_at or utcnow(), reverse=True)

    def get(self, grant_id: UUID) -> Grant:
        try:
            return self._rows[grant_id]
        except KeyError as exc:
            raise NotFound(f"grant {grant_id}") from exc

    def find_by_channel_token(self, channel_token_id: UUID) -> Grant | None:
        return next((g for g in self._rows.values() if g.channel_token_id == channel_token_id), None)

    def begin(self, *, org_id, agent_id, agent_key, product, expires_at, created_by) -> Grant:
        now = utcnow()
        for g in list(self._rows.values()):
            if (g.org_id, g.agent_id, g.product) == (org_id, agent_id, product) and g.status in LIVE_STATUSES:
                if g.status == "pendente" and g.created_at and now - g.created_at > STALE_PENDING:
                    self._put(replace(g, status="falhou", last_error="tentativa abandonada"))
                    continue
                raise GrantExists(f"live grant for {agent_key}/{product}")
        return self._put(Grant(
            id=uuid4(), org_id=org_id, agent_id=agent_id, agent_key=agent_key, product=product,
            status="pendente", expires_at=expires_at, created_by=created_by, created_at=now,
        ))

    def activate(self, grant_id, *, channel_token_id, product_token_id) -> Grant:
        g = self.get(grant_id)
        return self._put(replace(
            g, status="ativo", channel_token_id=channel_token_id, product_token_id=product_token_id,
            last_delivered_at=utcnow(), last_error=None,
        ))

    def mark_failed(self, grant_id, error) -> Grant:
        return self._put(replace(self.get(grant_id), status="falhou", last_error=error[:500]))

    def note_error(self, grant_id, error) -> Grant:
        return self._put(replace(self.get(grant_id), last_error=error[:500] if error else None))

    def mark_revoked(self, grant_id, *, revoked_by) -> Grant:
        return self._put(replace(self.get(grant_id), status="revogado", revoked_by=revoked_by, revoked_at=utcnow()))


class SupabaseGrantStore:
    """Real store -- the service-role admin client (the table is service-role only)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _one(self, query, *, unique_code: str | None = None) -> Grant:
        from app.stores._db_errors import exec_query

        rows = exec_query(query, unique_code=unique_code).data or []
        if not rows:
            raise NotFound("grant")
        return _row_grant(rows[0])

    def list(self, *, org_id: UUID | None = None) -> list[Grant]:
        q = self._t().select(_COLUMNS)
        if org_id is not None:
            q = q.eq("org_id", str(org_id))
        # A grant ledger is one row per (org, agent, product); 500 newest is far above any real fleet.
        return [_row_grant(r) for r in (q.order("created_at", desc=True).limit(500).execute().data or [])]

    def get(self, grant_id: UUID) -> Grant:
        return self._one(self._t().select(_COLUMNS).eq("id", str(grant_id)).limit(1))

    def find_by_channel_token(self, channel_token_id: UUID) -> Grant | None:
        rows = self._t().select(_COLUMNS).eq("channel_token_id", str(channel_token_id)).limit(1).execute().data or []
        return _row_grant(rows[0]) if rows else None

    def begin(self, *, org_id, agent_id, agent_key, product, expires_at, created_by) -> Grant:
        from app.stores._db_errors import StudioConflict, exec_query

        stale = (utcnow() - STALE_PENDING).isoformat()
        exec_query(
            self._t().update({"status": "falhou", "last_error": "tentativa abandonada"})
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("product", product)
            .eq("status", "pendente").lt("created_at", stale)
        )
        row = {
            "org_id": str(org_id), "agent_id": str(agent_id), "agent_key": agent_key, "product": product,
            "status": "pendente", "expires_at": expires_at.isoformat() if expires_at else None,
            "created_by": str(created_by) if created_by else None,
        }
        try:
            return self._one(self._t().insert(row), unique_code="grant_exists")
        except StudioConflict as exc:
            raise GrantExists(str(exc)) from exc

    def _update(self, grant_id: UUID, values: dict[str, Any]) -> Grant:
        return self._one(self._t().update(values).eq("id", str(grant_id)))

    def activate(self, grant_id, *, channel_token_id, product_token_id) -> Grant:
        return self._update(grant_id, {
            "status": "ativo", "channel_token_id": str(channel_token_id),
            "product_token_id": str(product_token_id) if product_token_id else None,
            "last_delivered_at": utcnow_iso(), "last_error": None,
        })

    def mark_failed(self, grant_id, error) -> Grant:
        return self._update(grant_id, {"status": "falhou", "last_error": error[:500]})

    def note_error(self, grant_id, error) -> Grant:
        return self._update(grant_id, {"last_error": error[:500] if error else None})

    def mark_revoked(self, grant_id, *, revoked_by) -> Grant:
        return self._update(grant_id, {
            "status": "revogado", "revoked_by": str(revoked_by) if revoked_by else None, "revoked_at": utcnow_iso(),
        })


def get_grant_store(settings: Any, *, deploy_context: bool | None = None) -> GrantStore:
    """The Supabase store when a service-role key is configured; otherwise the Fake -- outside a deploy context only.

    In a deploy context (``noctusai_lib.config.deploy_config.is_deploy_context`` when ``deploy_context`` is None) a
    missing key RAISES: an in-memory ledger there would let a platform admin mint and deliver real tokens whose grant
    is recorded nowhere (same rule as the seed's ``make_grant_delivery``)."""
    if not getattr(settings, "supabase_service_role_key", None):
        if deploy_context is None:
            from noctusai_lib.config.deploy_config import is_deploy_context

            deploy_context = is_deploy_context()
        if deploy_context:
            raise RuntimeError(
                "get_grant_store: refusing the in-memory grant store in a deploy context -- "
                "configure SUPABASE_SERVICE_ROLE_KEY."
            )
        return FakeGrantStore()
    from app.database import get_admin_client

    return SupabaseGrantStore(get_admin_client())
