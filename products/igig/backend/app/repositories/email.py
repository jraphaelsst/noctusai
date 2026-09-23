"""Repositories for the orçamento e-mail flow (wave-2 slice B — R7/R8).

Two tables from migration 018:

* ``orcamento_email`` — the thread log: every orçamento we SENT (``out``) and
  every reply we matched (``in``). ``UNIQUE (org_id, message_id)`` makes a
  redelivered push idempotent.
* ``gmail_watch`` — per connected mailbox: the ``list_history`` cursor
  (``history_id``) + the watch ``expiration`` the daily renewal keys on.

Kept in their own module (not added to :class:`app.repositories.Repositorios`)
so the e-mail slice composes over ``repos.store`` without editing the shared
repository set — callers build them with :func:`repositorios_email`.

Two reads here are CROSS-ORG and therefore take the raw service-role PostgREST
client instead of a store: the Pub/Sub push carries only an e-mail address (the
org is unknown until the watch row is found), and the daily renewal walks every
org's watches. Both are service-role-only call sites (public webhook / job).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from noctusai_lib.integrations.persistence import Op, Order, QuerySpec, Record, RecordStore
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from .base import BaseRepository

__all__ = [
    "OrcamentoEmailRepository",
    "GmailWatchRepository",
    "RepositoriosEmail",
    "repositorios_email",
    "watches_por_email",
    "iter_todos_watches",
]


class OrcamentoEmailRepository(BaseRepository):
    table = "orcamento_email"
    default_order = (Order("occurred_at"),)

    def do_orcamento(self, org_id: str, orcamento_id: str) -> list[Record]:
        """The thread, oldest first."""
        return self._por("orcamento_id", orcamento_id, org_id)

    def por_message_id(self, org_id: str, message_id: str) -> Record | None:
        achados = self._por("message_id", message_id, org_id)
        return achados[0] if achados else None

    def enviados_com_ids(self, org_id: str, message_ids: list[str]) -> list[Record]:
        """``out`` rows whose stored Message-ID is one of ``message_ids``."""
        if not message_ids:
            return []
        spec = (
            QuerySpec()
            .with_filter("direction", Op.EQ, "out")
            .with_filter("message_id", Op.IN, list(dict.fromkeys(message_ids)))
        )
        return self.listar(org_id, spec=spec)

    def enviados_na_thread(self, org_id: str, thread_id: str) -> list[Record]:
        """``out`` rows already known to sit in a Gmail thread."""
        spec = (
            QuerySpec()
            .with_filter("direction", Op.EQ, "out")
            .with_filter("thread_id", Op.EQ, thread_id)
        )
        return self.listar(org_id, spec=spec)


class GmailWatchRepository(BaseRepository):
    table = "gmail_watch"
    default_order = (Order("created_at"),)

    def da_org(self, org_id: str) -> list[Record]:
        return self.listar(org_id)

    def por_email(self, org_id: str, email: str) -> Record | None:
        achados = self._por("email", email.lower(), org_id)
        return achados[0] if achados else None

    def registrar(
        self,
        org_id: str,
        *,
        email: str,
        history_id: str,
        expiration: datetime,
        topic: str,
    ) -> Record:
        """Upsert the watch for one mailbox (one row per org × e-mail)."""
        valores = {
            "email": email.lower(),
            "history_id": history_id,
            "expiration": _iso(expiration),
            "topic": topic,
        }
        atual = self.por_email(org_id, email)
        if atual is not None:
            return self.atualizar(org_id, str(atual["id"]), valores)
        return self.criar(org_id, valores)

    def avancar_cursor(self, org_id: str, watch_id: str, history_id: str) -> Record:
        return self.atualizar(org_id, watch_id, {"history_id": history_id})

    def remover_da_org(self, org_id: str) -> int:
        removidos = 0
        for linha in self.da_org(org_id):
            if self.remover(org_id, str(linha["id"])):
                removidos += 1
        return removidos


@dataclass(frozen=True)
class RepositoriosEmail:
    emails: OrcamentoEmailRepository
    watches: GmailWatchRepository


def repositorios_email(store: RecordStore) -> RepositoriosEmail:
    return RepositoriosEmail(
        emails=OrcamentoEmailRepository(store),
        watches=GmailWatchRepository(store),
    )


# ── cross-org reads (service-role client only) ──────────────────────
def watches_por_email(admin_db: Any, email: str) -> list[Record]:
    """Every watch row for a mailbox, across orgs — the push's only key."""
    resposta = (
        admin_db.table("gmail_watch")
        .select("*")
        .eq("email", email.lower())
        .order("id")
        .limit(50)
        .execute()
    )
    return list(resposta.data or [])


def iter_todos_watches(admin_db: Any) -> Iterator[Record]:
    """Every watch row on the platform, paged — the daily renewal's input."""
    return iter_paged_rows(
        lambda inicio, fim: (
            admin_db.table("gmail_watch").select("*").order("id").range(inicio, fim).execute().data
        ),
        label="igig.gmail_watch",
    )


def _iso(valor: datetime) -> str:
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat()
