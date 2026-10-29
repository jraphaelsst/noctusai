"""`ClientsConfig` -- vocabulary and money knobs of the clients organ. Everything here is DATA, never an enum.

Client statuses, session statuses and payment methods are `(slug, label, ...)` rows the product supplies; the
columns are plain TEXT validated by the service against this config (same rule as the leads stages), so a relabel
or a new status is one edit here and no migration. The nouns ("Paciente"/"Pacientes", "Aluno"/"Alunos") are
product copy the FE reads from `GET /api/clients/config` -- the organ's code never names a vertical.

A session status is `billable` when a session in it is charged (it books a receivable through `FinanceBooking`):
"realizada" and "falta" usually are, "agendada" and "cancelada" are not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from noctusai_lib.domain.pipeline.stages import STAGE_COLORS

_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


def _check_slug_label(kind: str, slug: str, label: str) -> None:
    if not _SLUG.match(slug or ""):
        raise ValueError(f"{kind}.slug must be a lowercase identifier, got {slug!r}")
    if not (label or "").strip():
        raise ValueError(f"{kind} {slug!r}: label must not be empty")


def _check_color(kind: str, slug: str, color: Optional[str]) -> None:
    if color is not None and color not in STAGE_COLORS:
        raise ValueError(f"{kind} {slug!r}: color must be one of {STAGE_COLORS}, got {color!r}")


@dataclass(frozen=True)
class ClientStatus:
    slug: str
    label: str
    color: Optional[str] = None

    def __post_init__(self) -> None:
        _check_slug_label("ClientStatus", self.slug, self.label)
        _check_color("ClientStatus", self.slug, self.color)

    def as_dict(self) -> dict:
        return {"slug": self.slug, "label": self.label, "color": self.color}


@dataclass(frozen=True)
class SessionStatus:
    slug: str
    label: str
    color: Optional[str] = None
    #: a session in this status is charged (books a receivable unless waived / priced 0)
    billable: bool = False

    def __post_init__(self) -> None:
        _check_slug_label("SessionStatus", self.slug, self.label)
        _check_color("SessionStatus", self.slug, self.color)

    def as_dict(self) -> dict:
        return {"slug": self.slug, "label": self.label, "color": self.color, "billable": self.billable}


@dataclass(frozen=True)
class PaymentMethod:
    slug: str
    label: str

    def __post_init__(self) -> None:
        _check_slug_label("PaymentMethod", self.slug, self.label)

    def as_dict(self) -> dict:
        return {"slug": self.slug, "label": self.label}


DEFAULT_STATUSES = (
    ClientStatus("ativo", "Ativo", "success"),
    ClientStatus("pausado", "Pausado", "warning"),
    ClientStatus("encerrado", "Encerrado", "muted"),
)
DEFAULT_SESSION_STATUSES = (
    SessionStatus("agendada", "Agendada", "primary", billable=False),
    SessionStatus("realizada", "Realizada", "success", billable=True),
    SessionStatus("falta", "Falta", "destructive", billable=True),
    SessionStatus("cancelada", "Cancelada", "muted", billable=False),
)
DEFAULT_PAYMENT_METHODS = (
    PaymentMethod("pix", "Pix"),
    PaymentMethod("dinheiro", "Dinheiro"),
    PaymentMethod("cartao", "Cartão"),
    PaymentMethod("transferencia", "Transferência"),
    PaymentMethod("outro", "Outro"),
)


def _status(x: Union[ClientStatus, str]) -> ClientStatus:
    return x if isinstance(x, ClientStatus) else ClientStatus(x, x.replace("_", " ").capitalize())


def _session_status(x: Union[SessionStatus, str]) -> SessionStatus:
    return x if isinstance(x, SessionStatus) else SessionStatus(x, x.replace("_", " ").capitalize())


def _method(x: Union[PaymentMethod, str]) -> PaymentMethod:
    return x if isinstance(x, PaymentMethod) else PaymentMethod(x, x.replace("_", " ").capitalize())


@dataclass(frozen=True)
class ClientsConfig:
    """
    Attributes:
        noun_singular / noun_plural: the product's word for a client (FE copy only).
        statuses: client lifecycle; the FIRST one is the default (and the status a lead conversion lands on).
        session_statuses: session states; `default_session_status` must be one of them.
        default_duration_min / default_price_cents: used when neither the session nor the client names one.
        payment_methods: what a manual payment may be recorded as (stored on the finance settlement's `method`).
        timezone: IANA zone the org's wall-clock times live in (weekly slots, session dates on receivables).
        finance_enabled: the host books session money into the finance organ (the FE shows the money tabs).
        horizon_weeks: how far ahead recurring schedules materialize sessions.
        finance_source / finance_ref_prefix: `(source, source_ref)` the receivables are booked under -- the
            finance idempotency key. `source` must be a finance `EntrySource`; the prefix namespaces our refs.
        finance_category_hint: income category name the receivables are filed under (None = uncategorized).
        finance_description_prefix: first word of a receivable's description (`"<prefix> — <name> — dd/mm/aaaa HH:MM"`).
        done_session_status: the status the client summary counts as `sessions_done` (None => every billable status).
        *_table: physical table names inside the product schema.
    """

    noun_singular: str = "Cliente"
    noun_plural: str = "Clientes"
    statuses: Sequence[Union[ClientStatus, str]] = DEFAULT_STATUSES
    session_statuses: Sequence[Union[SessionStatus, str]] = DEFAULT_SESSION_STATUSES
    default_session_status: str = "agendada"
    default_duration_min: int = 50
    default_price_cents: Optional[int] = None
    payment_methods: Sequence[Union[PaymentMethod, str]] = DEFAULT_PAYMENT_METHODS
    timezone: str = "America/Sao_Paulo"
    finance_enabled: bool = True
    horizon_weeks: int = 8
    finance_source: str = "external"
    finance_ref_prefix: str = "clients"
    finance_category_hint: Optional[str] = "Serviços"
    finance_description_prefix: str = "Sessão"
    done_session_status: Optional[str] = "realizada"
    clients_table: str = "clients"
    sessions_table: str = "client_sessions"
    schedules_table: str = "client_schedules"
    payments_table: str = "client_payments"

    def __post_init__(self) -> None:
        statuses = tuple(_status(s) for s in self.statuses)
        session_statuses = tuple(_session_status(s) for s in self.session_statuses)
        methods = tuple(_method(m) for m in self.payment_methods)
        for what, items in (("status", statuses), ("session status", session_statuses), ("payment method", methods)):
            if not items:
                raise ValueError(f"ClientsConfig needs at least one {what}")
            slugs = [i.slug for i in items]
            if len(set(slugs)) != len(slugs):
                raise ValueError(f"ClientsConfig: duplicate {what} slug in {slugs}")
        if self.default_session_status not in {s.slug for s in session_statuses}:
            raise ValueError(f"ClientsConfig.default_session_status {self.default_session_status!r} is not a session status")
        if self.done_session_status is not None and self.done_session_status not in {s.slug for s in session_statuses}:
            raise ValueError(f"ClientsConfig.done_session_status {self.done_session_status!r} is not a session status")
        if self.default_duration_min < 1:
            raise ValueError("ClientsConfig.default_duration_min must be >= 1")
        if self.default_price_cents is not None and self.default_price_cents < 0:
            raise ValueError("ClientsConfig.default_price_cents must be >= 0")
        if not 1 <= self.horizon_weeks <= 52:
            raise ValueError("ClientsConfig.horizon_weeks must be between 1 and 52")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"ClientsConfig.timezone {self.timezone!r} is not an IANA zone") from exc
        for name in ("clients_table", "sessions_table", "schedules_table", "payments_table"):
            if not _SLUG.match(getattr(self, name) or ""):
                raise ValueError(f"ClientsConfig.{name} must be a bare lowercase identifier")
        if not _SLUG.match(self.finance_ref_prefix or ""):
            raise ValueError("ClientsConfig.finance_ref_prefix must be a lowercase identifier")
        object.__setattr__(self, "statuses", statuses)
        object.__setattr__(self, "session_statuses", session_statuses)
        object.__setattr__(self, "payment_methods", methods)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def status_slugs(self) -> tuple[str, ...]:
        return tuple(s.slug for s in self.statuses)  # type: ignore[union-attr]

    @property
    def default_status(self) -> str:
        return self.status_slugs[0]

    @property
    def session_status_slugs(self) -> tuple[str, ...]:
        return tuple(s.slug for s in self.session_statuses)  # type: ignore[union-attr]

    @property
    def method_slugs(self) -> tuple[str, ...]:
        return tuple(m.slug for m in self.payment_methods)  # type: ignore[union-attr]

    def is_billable(self, session_status: str) -> bool:
        st = next((s for s in self.session_statuses if s.slug == session_status), None)  # type: ignore[union-attr]
        return bool(st and st.billable)

    def as_dict(self) -> dict:
        return {
            "noun_singular": self.noun_singular,
            "noun_plural": self.noun_plural,
            "statuses": [s.as_dict() for s in self.statuses],  # type: ignore[union-attr]
            "session_statuses": [s.as_dict() for s in self.session_statuses],  # type: ignore[union-attr]
            "default_session_status": self.default_session_status,
            "default_duration_min": self.default_duration_min,
            "default_price_cents": self.default_price_cents,
            "payment_methods": [m.as_dict() for m in self.payment_methods],  # type: ignore[union-attr]
            "timezone": self.timezone,
            "finance_enabled": self.finance_enabled,
        }


__all__ = [
    "ClientStatus",
    "ClientsConfig",
    "DEFAULT_PAYMENT_METHODS",
    "DEFAULT_SESSION_STATUSES",
    "DEFAULT_STATUSES",
    "PaymentMethod",
    "SessionStatus",
]
