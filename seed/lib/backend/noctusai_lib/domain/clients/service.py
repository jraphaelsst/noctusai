"""`ClientsService` -- the clients use-cases over a `ClientsStore` + the finance `FinanceBooking` seam, org-scoped.

* Clients: CRUD validated against `ClientsConfig` (status is DATA, phone canonical E.164 via the leads rule,
  CPF digits with valid check digits). `summary` (next/last session, sessions done, open/overdue/paid money) is
  computed server-side in BATCH for a whole page -- one sessions read + one receivables read, never per client.
* Schedules: a weekly slot materializes `default_session_status` sessions through `horizon_weeks` (from
  max(today, starts_on) to ends_on). Materialization is idempotent twice over: the `(schedule_id, starts_at)`
  unique guard, and the schedule's `materialized_until` cursor (only days past it are generated, so a generated
  session the user deleted never comes back). It runs on schedule create/update AND lazily on every sessions /
  client read (`top_up`), so the horizon rolls forward with no cron. A schedule edit rewrites only FUTURE sessions
  of that schedule still in the default status and not booked; past or handled sessions are never touched.
* Booking: a session that is (or becomes) billable -- billable status, not waived, effective price > 0 -- books a
  receivable through `FinanceBooking.book_receivable`; becoming non-billable cancels it (refused with 409
  `SESSAO_COM_PAGAMENTO` once it has a settlement); a price edit updates the amount (same 409 when settled).
  The receivable's `source_ref` is `<prefix>:session:<id>` (+ `:<booking_rev>` after an un-bill), so a re-bill
  books a fresh receivable instead of finding the cancelled one.
* Payments: a manual payment is allocated across the client's open receivables (oldest due first) through
  finance's settle path on the chosen account; the method rides on each settlement, the notes on the
  `client_payments` record.
* Leads: `ensure_from_lead` turns a lead into a client, idempotent on `(org_id, lead_id)`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from uuid import uuid4

from noctusai_lib.domain._organ_common import mask_doc
from noctusai_lib.domain.finance.booking import FinanceBooking, NoopFinanceBooking
from noctusai_lib.domain.leads.store import as_dt
from noctusai_lib.primitives.identificador import cpf_dv_valido
from noctusai_lib.primitives.phone import normalize_phone

from .config import ClientsConfig
from .errors import (
    AGENDA_INVALIDA,
    CLIENTE_COM_FINANCEIRO,
    DOCUMENTO_INVALIDO,
    FILTRO_INVALIDO,
    LANCAMENTO_INVALIDO,
    METODO_INVALIDO,
    NOME_OBRIGATORIO,
    SESSAO_COM_PAGAMENTO,
    STATUS_INVALIDO,
    TELEFONE_INVALIDO,
    VALOR_EXCEDE_ABERTO,
    VALOR_INVALIDO,
    ClientConflictError,
    conflict,
    invalid,
    not_found,
)
from .store import ClientFilters, ClientsStore

logger = logging.getLogger(__name__)

#: the widest window the cross-client agenda serves in one read
MAX_AGENDA_DAYS = 62
_OPEN = ("open", "partial")
_CANCELLED = "cancelled"

_CLIENT_FIELDS = (
    "name", "phone", "email", "doc", "birth_date", "status", "tags", "notes",
    "default_price_cents", "session_duration_min", "started_at",
)
_NOT_NULL_CLIENT = ("name", "status", "started_at")


def _clean(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip() if isinstance(value, str) or value is None else str(value)
    return value or None


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _to_date(value: Any) -> Optional[date]:
    text = _iso_date(value)
    return date.fromisoformat(text) if text else None


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _hhmm(value: Any) -> str:
    return str(value or "")[:5]


def _tags(values: Optional[Iterable[str]]) -> list[str]:
    out: list[str] = []
    for t in values or []:
        t = (t or "").strip()
        if t and t not in out:
            out.append(t)
    return out


class ClientsService:
    def __init__(
        self,
        store: ClientsStore,
        config: ClientsConfig,
        booking: Optional[FinanceBooking] = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.store = store
        self.config = config
        self.booking: FinanceBooking = booking if booking is not None else NoopFinanceBooking()
        self._clock = clock

    # -- time ---------------------------------------------------------------------------------------

    def now(self) -> datetime:
        return self._clock().astimezone(timezone.utc)

    def today(self) -> date:
        return self.now().astimezone(self.config.tz).date()

    def _local(self, value: Any) -> Optional[datetime]:
        dt = as_dt(value)
        return dt.astimezone(self.config.tz) if dt else None

    def _aware(self, value: datetime) -> datetime:
        """A request instant; a naive one is the org's wall-clock time."""
        return value if value.tzinfo else value.replace(tzinfo=self.config.tz)

    def _day_start(self, d: date) -> datetime:
        return datetime.combine(d, time.min, tzinfo=self.config.tz)

    def _horizon(self) -> date:
        return self.today() + timedelta(weeks=self.config.horizon_weeks)

    # -- validation ---------------------------------------------------------------------------------

    def _check_status(self, status: str) -> str:
        if status not in self.config.status_slugs:
            raise invalid("status", f"Status desconhecido: {status}.", STATUS_INVALIDO)
        return status

    def _check_session_status(self, status: str) -> str:
        if status not in self.config.session_status_slugs:
            raise invalid("status", f"Status de sessão desconhecido: {status}.", STATUS_INVALIDO)
        return status

    @staticmethod
    def _phone(raw: Optional[str]) -> Optional[str]:
        raw = _clean(raw)
        if raw is None:
            return None
        phone = normalize_phone(raw)
        if phone is None:
            raise invalid("phone", "Telefone inválido. Use o DDD + número (ex.: 11 99999-9999).", TELEFONE_INVALIDO)
        return phone

    @staticmethod
    def _doc(raw: Optional[str]) -> Optional[str]:
        raw = _clean(raw)
        if raw is None:
            return None
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) != 11 or not cpf_dv_valido(digits):
            raise invalid("doc", "CPF inválido.", DOCUMENTO_INVALIDO)
        return digits

    def _normalize_client(self, data: Mapping[str, Any]) -> dict:
        out: dict[str, Any] = {}
        for key in _CLIENT_FIELDS:
            if key not in data:
                continue
            value = data[key]
            if value is None and key in _NOT_NULL_CLIENT:
                continue  # a cleared required field keeps its value (name has its own check below)
            if key == "phone":
                out[key] = self._phone(value)
            elif key == "doc":
                out[key] = self._doc(value)
            elif key == "status":
                out[key] = self._check_status(value)
            elif key == "tags":
                out[key] = _tags(value)
            elif key in ("birth_date", "started_at"):
                out[key] = _iso_date(value)
            elif key in ("default_price_cents", "session_duration_min"):
                out[key] = int(value) if value is not None else None
            elif key == "name":
                out[key] = (value or "").strip()
            else:
                out[key] = _clean(value)
        return out

    # -- clients: reads -----------------------------------------------------------------------------

    def _client(self, org_id: str, client_id: str) -> dict:
        row = self.store.get_client(str(org_id), str(client_id))
        if row is None:
            raise not_found(self.config.noun_singular)
        return row

    def get(self, org_id: str, client_id: str, *, is_admin: bool = False) -> dict:
        org_id = str(org_id)
        row = self._client(org_id, client_id)
        self.top_up(org_id, client_id=row["id"])
        return self._present_clients(org_id, [row], is_admin=is_admin)[0]

    def list_clients(
        self, org_id: str, filters: ClientFilters, *, limit: int = 50, offset: int = 0, is_admin: bool = False
    ) -> tuple[list[dict], Optional[int]]:
        """`(clients, next_offset)` ordered by name; summaries computed for the whole page in batch."""
        org_id = str(org_id)
        if filters.status:
            self._check_status(filters.status)
        self.top_up(org_id)
        rows = self.store.query_clients(org_id, filters, limit=limit + 1, offset=offset)
        more = len(rows) > limit
        rows = rows[:limit]
        return self._present_clients(org_id, rows, is_admin=is_admin), (offset + limit if more else None)

    def tags(self, org_id: str) -> list[str]:
        return self.store.all_tags(str(org_id))

    def _present_clients(self, org_id: str, rows: Sequence[dict], *, is_admin: bool) -> list[dict]:
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        sessions = self.store.sessions_of_clients(org_id, ids)
        entries = self._entries(org_id, [s.get("entry_id") for s in sessions])
        by_client: dict[str, list[dict]] = {i: [] for i in ids}
        for s in sessions:
            by_client.setdefault(s["client_id"], []).append(s)
        return [self.present_client(r, self._summary(by_client[r["id"]], entries), is_admin=is_admin) for r in rows]

    def _summary(self, sessions: Sequence[dict], entries: Mapping[str, dict]) -> dict:
        now, today = self.now(), self.today()
        cancelled_like = {
            s.slug for s in self.config.session_statuses
            if not s.billable and s.slug != self.config.default_session_status
        }
        done = (
            {self.config.done_session_status}
            if self.config.done_session_status
            else {s.slug for s in self.config.session_statuses if s.billable}
        )
        upcoming = [as_dt(s["starts_at"]) for s in sessions if s["status"] not in cancelled_like and as_dt(s["starts_at"]) >= now]
        past = [as_dt(s["starts_at"]) for s in sessions if s["status"] not in cancelled_like and as_dt(s["starts_at"]) < now]
        money = self._money([entries[s["entry_id"]] for s in sessions if s.get("entry_id") in entries], today)
        return {
            "next_session_at": self._local(min(upcoming)).isoformat() if upcoming else None,
            "last_session_at": self._local(max(past)).isoformat() if past else None,
            "sessions_done": sum(1 for s in sessions if s["status"] in done),
            "open_cents": money["open_cents"],
            "overdue_cents": money["overdue_cents"],
            "paid_cents": money["paid_cents"],
        }

    @staticmethod
    def _money(entries: Iterable[dict], today: date) -> dict:
        open_c = overdue_c = paid_c = 0
        for e in entries:
            if e["status"] == _CANCELLED:
                continue
            paid_c += int(e["settled_cents"])
            if e["status"] in _OPEN:
                rest = int(e["amount_cents"]) - int(e["settled_cents"])
                open_c += rest
                due = _to_date(e.get("due_date"))
                if due is not None and due < today:
                    overdue_c += rest
        return {"open_cents": open_c, "overdue_cents": overdue_c, "paid_cents": paid_c}

    def present_client(self, row: dict, summary: dict, *, is_admin: bool) -> dict:
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "phone": row.get("phone"),
            "email": row.get("email"),
            "doc": row.get("doc") if is_admin else mask_doc(row.get("doc")),
            "birth_date": _iso_date(row.get("birth_date")),
            "status": row["status"],
            "tags": list(row.get("tags") or []),
            "notes": row.get("notes"),
            "lead_id": str(row["lead_id"]) if row.get("lead_id") else None,
            "whatsapp_chat_id": row.get("whatsapp_chat_id"),
            "default_price_cents": row.get("default_price_cents"),
            "session_duration_min": row.get("session_duration_min"),
            "started_at": _iso_date(row.get("started_at")),
            "created_at": self._instant(row.get("created_at")),
            "updated_at": self._instant(row.get("updated_at")),
            "summary": summary,
        }

    @staticmethod
    def _instant(value: Any) -> Optional[str]:
        dt = as_dt(value)
        return dt.isoformat() if dt else None

    # -- clients: writes ----------------------------------------------------------------------------

    def create(self, org_id: str, data: Mapping[str, Any], *, user_id: Optional[str] = None, is_admin: bool = False) -> dict:
        org_id = str(org_id)
        fields = self._normalize_client(data)
        if not fields.get("name"):
            raise invalid("name", "Informe o nome.", NOME_OBRIGATORIO)
        now = _utc_iso(self.now())
        row = {
            "id": str(uuid4()),
            "status": self.config.default_status,
            "tags": [],
            "started_at": self.today().isoformat(),
            **fields,
            "created_at": now,
            "updated_at": now,
            "created_by": user_id,
        }
        saved = self.store.insert_client(org_id, row)
        return self.present_client(saved, self._summary([], {}), is_admin=is_admin)

    def update(self, org_id: str, client_id: str, data: Mapping[str, Any], *, is_admin: bool = False) -> dict:
        org_id = str(org_id)
        self._client(org_id, client_id)
        patch = self._normalize_client(data)
        if "name" in data and data["name"] is None:
            raise invalid("name", "O nome não pode ficar vazio.", NOME_OBRIGATORIO)
        if "name" in patch and not patch["name"]:
            raise invalid("name", "O nome não pode ficar vazio.", NOME_OBRIGATORIO)
        if patch:
            patch["updated_at"] = _utc_iso(self.now())
            if self.store.update_client(org_id, str(client_id), patch) is None:
                raise not_found(self.config.noun_singular)
        return self.get(org_id, client_id, is_admin=is_admin)

    def delete(self, org_id: str, client_id: str) -> None:
        org_id = str(org_id)
        self._client(org_id, client_id)
        if self.store.booked_sessions_of_client(org_id, str(client_id)):
            raise conflict(
                CLIENTE_COM_FINANCEIRO,
                "Há lançamentos financeiros ligados a este cadastro; altere o status para encerrado em vez de excluir.",
            )
        if not self.store.delete_client(org_id, str(client_id)):
            raise not_found(self.config.noun_singular)

    def ensure_from_lead(self, org_id: str, lead: Mapping[str, Any]) -> tuple[dict, bool]:
        """`(client_row, created)` -- the client of `lead`, created once. Idempotent on `(org_id, lead_id)`
        (a concurrent conversion loses the UNIQUE race and returns the winner)."""
        org_id = str(org_id)
        lead_id = str(lead["id"])
        existing = self.store.client_by_lead(org_id, lead_id)
        if existing is not None:
            return existing, False
        now = _utc_iso(self.now())
        row = {
            "id": str(uuid4()),
            "name": (lead.get("name") or "").strip() or lead.get("phone") or "—",
            "phone": normalize_phone(lead.get("phone")) if lead.get("phone") else None,
            "email": _clean(lead.get("email")),
            "status": self.config.default_status,
            "tags": _tags(lead.get("tags")),
            "lead_id": lead_id,
            "whatsapp_chat_id": lead.get("whatsapp_chat_id"),
            "started_at": self.today().isoformat(),
            "created_at": now,
            "updated_at": now,
        }
        try:
            return self.store.insert_client(org_id, row), True
        except ClientConflictError:
            winner = self.store.client_by_lead(org_id, lead_id)
            if winner is None:
                raise
            return winner, False

    # -- schedules ----------------------------------------------------------------------------------

    def present_schedule(self, row: dict) -> dict:
        return {
            "id": str(row["id"]),
            "client_id": str(row["client_id"]),
            "weekday": int(row["weekday"]),
            "time": _hhmm(row.get("slot_time")),
            "duration_min": int(row["duration_min"]),
            "price_cents": row.get("price_cents"),
            "starts_on": _iso_date(row.get("starts_on")),
            "ends_on": _iso_date(row.get("ends_on")),
            "active": bool(row.get("active")),
            "created_at": self._instant(row.get("created_at")),
            "updated_at": self._instant(row.get("updated_at")),
        }

    def _schedule(self, org_id: str, schedule_id: str) -> dict:
        row = self.store.get_schedule(str(org_id), str(schedule_id))
        if row is None:
            raise not_found("Agenda")
        return row

    def list_schedules(self, org_id: str, client_id: str) -> list[dict]:
        org_id = str(org_id)
        self._client(org_id, client_id)
        return [self.present_schedule(r) for r in self.store.schedules_of_client(org_id, str(client_id))]

    @staticmethod
    def _check_window(starts_on: Optional[str], ends_on: Optional[str]) -> None:
        if starts_on and ends_on and ends_on < starts_on:
            raise invalid("ends_on", "O fim da agenda vem antes do início.", AGENDA_INVALIDA)

    def create_schedule(self, org_id: str, client_id: str, data: Mapping[str, Any]) -> dict:
        org_id = str(org_id)
        client = self._client(org_id, client_id)
        now = _utc_iso(self.now())
        row = {
            "id": str(uuid4()),
            "client_id": str(client["id"]),
            "weekday": int(data["weekday"]),
            "slot_time": f"{_hhmm(data['time'])}:00",
            "duration_min": int(data.get("duration_min") or client.get("session_duration_min") or self.config.default_duration_min),
            "price_cents": data.get("price_cents"),
            "starts_on": _iso_date(data.get("starts_on")) or self.today().isoformat(),
            "ends_on": _iso_date(data.get("ends_on")),
            "active": True,
            "materialized_until": None,
            "created_at": now,
            "updated_at": now,
        }
        self._check_window(row["starts_on"], row["ends_on"])
        saved = self.store.insert_schedule(org_id, row)
        return self.present_schedule(self._materialize(org_id, saved, client))

    def update_schedule(self, org_id: str, schedule_id: str, data: Mapping[str, Any]) -> dict:
        org_id = str(org_id)
        current = self._schedule(org_id, schedule_id)
        patch: dict[str, Any] = {}
        for key in ("weekday", "duration_min", "active"):
            if data.get(key) is not None:
                patch[key] = data[key]
        if data.get("time") is not None:
            patch["slot_time"] = f"{_hhmm(data['time'])}:00"
        if data.get("starts_on") is not None:
            patch["starts_on"] = _iso_date(data["starts_on"])
        for key in ("price_cents", "ends_on"):
            if key in data:
                patch[key] = _iso_date(data[key]) if key == "ends_on" else data[key]
        patch = {k: v for k, v in patch.items() if not self._same(k, current.get(k), v)}
        if not patch:
            return self.present_schedule(current)
        merged = {**current, **patch}
        self._check_window(_iso_date(merged.get("starts_on")), _iso_date(merged.get("ends_on")))
        regenerate = bool({"weekday", "slot_time", "starts_on", "ends_on", "active"} & patch.keys())
        future = self._rewritable_future(org_id, str(schedule_id))
        if regenerate:
            self.store.delete_sessions(org_id, [s["id"] for s in future])
            patch["materialized_until"] = None
        else:
            in_place = {k: patch[k] for k in ("price_cents", "duration_min") if k in patch}
            for s in future:
                self.store.update_session(org_id, s["id"], {**in_place, "updated_at": _utc_iso(self.now())})
        patch["updated_at"] = _utc_iso(self.now())
        saved = self.store.update_schedule(org_id, str(schedule_id), patch)
        if saved is None:
            raise not_found("Agenda")
        if regenerate and saved.get("active"):
            saved = self._materialize(org_id, saved)
        return self.present_schedule(saved)

    @staticmethod
    def _same(key: str, old: Any, new: Any) -> bool:
        if key in ("starts_on", "ends_on"):
            return _iso_date(old) == _iso_date(new)
        if key == "slot_time":
            return _hhmm(old) == _hhmm(new)
        return old == new

    def delete_schedule(self, org_id: str, schedule_id: str) -> None:
        org_id = str(org_id)
        self._schedule(org_id, schedule_id)
        self.store.delete_sessions(org_id, [s["id"] for s in self._rewritable_future(org_id, str(schedule_id))])
        if not self.store.delete_schedule(org_id, str(schedule_id)):
            raise not_found("Agenda")

    def _rewritable_future(self, org_id: str, schedule_id: str) -> list[dict]:
        """Future sessions of the schedule still in the default status and not booked -- the only ones a schedule
        edit may rewrite or delete."""
        rows = self.store.sessions_of_schedule_after(org_id, schedule_id, _utc_iso(self.now()))
        return [s for s in rows if s["status"] == self.config.default_session_status and not s.get("entry_id")]

    def top_up(self, org_id: str, *, client_id: Optional[str] = None) -> int:
        """Roll every due schedule's horizon forward (one read when nothing is due). Returns sessions created."""
        org_id = str(org_id)
        through = self._horizon().isoformat()
        return sum(self._generate(org_id, sched, None)[1] for sched in self.store.schedules_due(org_id, through, client_id=client_id))

    def _materialize(self, org_id: str, schedule: dict, client: Optional[dict] = None) -> dict:
        saved, _n = self._generate(org_id, schedule, client)
        return saved

    def _generate(self, org_id: str, schedule: dict, client: Optional[dict]) -> tuple[dict, int]:
        """Create the schedule's sessions from its cursor to the horizon; advance the cursor. `(schedule, created)`."""
        today, through = self.today(), self._horizon()
        if not schedule.get("active"):
            return schedule, 0
        start = max(today, _to_date(schedule["starts_on"]))
        cursor = _to_date(schedule.get("materialized_until"))
        if cursor is not None:
            start = max(start, cursor + timedelta(days=1))
        end = through
        ends_on = _to_date(schedule.get("ends_on"))
        if ends_on is not None:
            end = min(end, ends_on)
        now = self.now()
        slot = time.fromisoformat(f"{_hhmm(schedule['slot_time'])}:00")
        rows = []
        day = start + timedelta(days=(int(schedule["weekday"]) - start.weekday()) % 7)
        stamp = _utc_iso(now)
        while day <= end:
            at = datetime.combine(day, slot, tzinfo=self.config.tz)
            if at > now:
                rows.append({
                    "id": str(uuid4()),
                    "client_id": str(schedule["client_id"]),
                    "schedule_id": str(schedule["id"]),
                    "starts_at": _utc_iso(at),
                    "duration_min": int(schedule["duration_min"]),
                    "status": self.config.default_session_status,
                    "price_cents": schedule.get("price_cents"),
                    "waive_charge": False,
                    "notes": None,
                    "entry_id": None,
                    "booking_rev": 0,
                    "created_at": stamp,
                    "updated_at": stamp,
                })
            day += timedelta(days=7)
        inserted = self.store.insert_generated_sessions(org_id, rows) if rows else []
        if inserted and self.config.is_billable(self.config.default_session_status):
            client = client or self._client(org_id, schedule["client_id"])
            for s in inserted:
                self._sync_booking(org_id, client, s, s, price_changed=True)
        saved = self.store.update_schedule(org_id, str(schedule["id"]), {"materialized_until": through.isoformat()})
        return (saved or {**schedule, "materialized_until": through.isoformat()}), len(inserted)

    # -- sessions -----------------------------------------------------------------------------------

    def _session(self, org_id: str, session_id: str) -> dict:
        row = self.store.get_session(str(org_id), str(session_id))
        if row is None:
            raise not_found("Sessão")
        return row

    def _entries(self, org_id: str, entry_ids: Iterable[Optional[str]]) -> dict[str, dict]:
        ids = sorted({str(i) for i in entry_ids if i})
        return {e["id"]: e for e in self.booking.receivables(org_id, ids)} if ids else {}

    def _payment_status(self, entry: Optional[dict]) -> str:
        if entry is None or entry["status"] == _CANCELLED:
            return "none"
        if entry["status"] == "paid":
            return "paid"
        due = _to_date(entry.get("due_date"))
        if due is not None and due < self.today():
            return "overdue"
        return "partial" if int(entry["settled_cents"]) > 0 else "open"

    def present_session(self, row: dict, client_name: Optional[str], entry: Optional[dict]) -> dict:
        return {
            "id": str(row["id"]),
            "client_id": str(row["client_id"]),
            "client_name": client_name,
            "schedule_id": str(row["schedule_id"]) if row.get("schedule_id") else None,
            "starts_at": self._local(row["starts_at"]).isoformat(),
            "duration_min": int(row["duration_min"]),
            "status": row["status"],
            "price_cents": row.get("price_cents"),
            "waive_charge": bool(row.get("waive_charge")),
            "notes": row.get("notes"),
            "entry_id": str(row["entry_id"]) if row.get("entry_id") else None,
            "payment_status": self._payment_status(entry),
            "created_at": self._instant(row.get("created_at")),
            "updated_at": self._instant(row.get("updated_at")),
        }

    def _present_sessions(self, org_id: str, rows: Sequence[dict], clients: Optional[Mapping[str, dict]] = None) -> list[dict]:
        if not rows:
            return []
        if clients is None:
            clients = {c["id"]: c for c in self.store.clients_by_ids(org_id, {r["client_id"] for r in rows})}
        entries = self._entries(org_id, [r.get("entry_id") for r in rows])
        return [
            self.present_session(r, (clients.get(r["client_id"]) or {}).get("name"), entries.get(str(r.get("entry_id"))))
            for r in rows
        ]

    def agenda(self, org_id: str, start: date, end: date) -> list[dict]:
        """Every client's sessions on days `start..end` (inclusive), ascending."""
        org_id = str(org_id)
        if end < start:
            raise invalid("from", "A data inicial vem depois da final.", FILTRO_INVALIDO)
        if (end - start).days > MAX_AGENDA_DAYS:
            raise invalid("to", f"O período máximo é de {MAX_AGENDA_DAYS} dias.", FILTRO_INVALIDO)
        self.top_up(org_id)
        rows = self.store.sessions_between(
            org_id, _utc_iso(self._day_start(start)), _utc_iso(self._day_start(end + timedelta(days=1)))
        )
        return self._present_sessions(org_id, rows)

    def client_sessions(
        self, org_id: str, client_id: str, *, start: Optional[date] = None, end: Optional[date] = None, status: Optional[str] = None
    ) -> list[dict]:
        """One client's sessions (optionally a day window / status), newest first."""
        org_id = str(org_id)
        client = self._client(org_id, client_id)
        if start and end and end < start:
            raise invalid("from", "A data inicial vem depois da final.", FILTRO_INVALIDO)
        if status:
            self._check_session_status(status)
        self.top_up(org_id, client_id=client["id"])
        if start or end:
            lo = _utc_iso(self._day_start(start)) if start else "0001-01-01T00:00:00+00:00"
            hi = _utc_iso(self._day_start(end + timedelta(days=1))) if end else "9999-12-31T00:00:00+00:00"
            rows = self.store.sessions_between(org_id, lo, hi, client_id=client["id"], status=status)
        else:
            rows = [r for r in self.store.sessions_of_clients(org_id, [client["id"]]) if status is None or r["status"] == status]
        rows = sorted(rows, key=lambda r: (as_dt(r["starts_at"]), str(r["id"])), reverse=True)
        return self._present_sessions(org_id, rows, {client["id"]: client})

    def create_session(self, org_id: str, client_id: str, data: Mapping[str, Any]) -> dict:
        org_id = str(org_id)
        client = self._client(org_id, client_id)
        status = self._check_session_status(data.get("status") or self.config.default_session_status)
        now = _utc_iso(self.now())
        row = {
            "id": str(uuid4()),
            "client_id": str(client["id"]),
            "schedule_id": None,
            "starts_at": _utc_iso(self._aware(data["starts_at"])),
            "duration_min": int(data.get("duration_min") or client.get("session_duration_min") or self.config.default_duration_min),
            "status": status,
            "price_cents": data.get("price_cents"),
            "waive_charge": bool(data.get("waive_charge") or False),
            "notes": _clean(data.get("notes")),
            "entry_id": None,
            "booking_rev": 0,
            "created_at": now,
            "updated_at": now,
        }
        saved = self.store.insert_session(org_id, row)
        saved = self._sync_booking(org_id, client, saved, saved, price_changed=True)
        return self._present_sessions(org_id, [saved], {client["id"]: client})[0]

    def update_session(self, org_id: str, session_id: str, data: Mapping[str, Any]) -> dict:
        org_id = str(org_id)
        current = self._session(org_id, session_id)
        client = self._client(org_id, current["client_id"])
        patch: dict[str, Any] = {}
        if data.get("starts_at") is not None:
            patch["starts_at"] = _utc_iso(self._aware(data["starts_at"]))
        if data.get("duration_min") is not None:
            patch["duration_min"] = int(data["duration_min"])
        if data.get("status") is not None:
            patch["status"] = self._check_session_status(data["status"])
        if data.get("waive_charge") is not None:
            patch["waive_charge"] = bool(data["waive_charge"])
        if "price_cents" in data:
            patch["price_cents"] = data["price_cents"]
        if "notes" in data:
            patch["notes"] = _clean(data["notes"])
        patch = {k: v for k, v in patch.items() if current.get(k) != v and not (k == "starts_at" and as_dt(current["starts_at"]) == as_dt(v))}
        if not patch:
            return self._present_sessions(org_id, [current], {client["id"]: client})[0]
        after = {**current, **patch}
        planned = self._sync_booking(org_id, client, current, after, price_changed="price_cents" in patch, write=False)
        patch.update({k: planned[k] for k in ("entry_id", "booking_rev") if planned.get(k) != current.get(k)})
        patch["updated_at"] = _utc_iso(self.now())
        saved = self.store.update_session(org_id, str(session_id), patch)
        if saved is None:
            raise not_found("Sessão")
        return self._present_sessions(org_id, [saved], {client["id"]: client})[0]

    def delete_session(self, org_id: str, session_id: str) -> None:
        org_id = str(org_id)
        current = self._session(org_id, session_id)
        if current.get("entry_id"):
            entry = self._entries(org_id, [current["entry_id"]]).get(str(current["entry_id"]))
            if entry is not None and entry["status"] != _CANCELLED:
                if int(entry["settled_cents"]) > 0:
                    raise conflict(SESSAO_COM_PAGAMENTO, "A sessão já tem pagamento registrado; estorne-o no Financeiro antes.")
                self.booking.cancel_receivable(org_id, str(current["entry_id"]))
        if not self.store.delete_sessions(org_id, [str(session_id)]):
            raise not_found("Sessão")

    # -- booking ------------------------------------------------------------------------------------

    def _price(self, session: Mapping[str, Any], client: Mapping[str, Any]) -> Optional[int]:
        if session.get("price_cents") is not None:
            return int(session["price_cents"])
        if client.get("default_price_cents") is not None:
            return int(client["default_price_cents"])
        return self.config.default_price_cents

    def _billable(self, session: Mapping[str, Any], client: Mapping[str, Any]) -> bool:
        price = self._price(session, client)
        return self.config.is_billable(session["status"]) and not session.get("waive_charge") and bool(price and price > 0)

    def _source_ref(self, session: Mapping[str, Any]) -> str:
        rev = int(session.get("booking_rev") or 0)
        base = f"{self.config.finance_ref_prefix}:session:{session['id']}"
        return f"{base}:{rev}" if rev else base

    def _description(self, session: Mapping[str, Any], client: Mapping[str, Any]) -> str:
        at = self._local(session["starts_at"])
        return f"{self.config.finance_description_prefix} — {client['name']} — {at:%d/%m/%Y %H:%M}"

    def _sync_booking(
        self, org_id: str, client: dict, before: dict, after: dict, *, price_changed: bool, write: bool = True
    ) -> dict:
        """Bring the receivable in line with `after`. Every refusal is raised BEFORE any finance write.

        Returns `after` with the resulting `entry_id` / `booking_rev` (persisted when `write`; otherwise the
        caller persists them with its own patch)."""
        result = dict(after)
        entry = None
        if before.get("entry_id"):
            entry = self._entries(org_id, [before["entry_id"]]).get(str(before["entry_id"]))
        live = entry is not None and entry["status"] != _CANCELLED
        settled = int(entry["settled_cents"]) if live else 0
        billable = self._billable(after, client)
        when = self._local(after["starts_at"])
        if billable and not live:
            if before.get("entry_id"):  # the old receivable is gone (cancelled in Financeiro): book a fresh one
                result["booking_rev"] = int(before.get("booking_rev") or 0) + 1
            result["entry_id"] = self.booking.book_receivable(
                org_id,
                source=self.config.finance_source,
                source_ref=self._source_ref(result),
                description=self._description(after, client),
                counterparty_name=client["name"],
                counterparty_doc=client.get("doc"),
                amount_cents=int(self._price(after, client) or 0),
                competence_month=when.date().replace(day=1),
                due_date=when.date(),
                category_hint=self.config.finance_category_hint,
            )
        elif billable and live:
            amount = int(self._price(after, client) or 0)
            new_amount = amount if price_changed and amount != int(entry["amount_cents"]) else None
            if new_amount is not None and settled > 0:
                raise conflict(SESSAO_COM_PAGAMENTO, "A sessão já tem pagamento registrado; o valor não pode mudar.")
            moved = as_dt(before["starts_at"]) != as_dt(after["starts_at"])
            if new_amount is not None or moved:
                self.booking.update_receivable(
                    org_id,
                    str(before["entry_id"]),
                    amount_cents=new_amount,
                    description=self._description(after, client) if moved else None,
                    due_date=when.date() if moved else None,
                    competence_month=when.date().replace(day=1) if moved else None,
                )
        elif not billable and live:
            if settled > 0:
                raise conflict(SESSAO_COM_PAGAMENTO, "A sessão já tem pagamento registrado; estorne-o no Financeiro antes.")
            self.booking.cancel_receivable(org_id, str(before["entry_id"]))
            result["entry_id"] = None
            result["booking_rev"] = int(before.get("booking_rev") or 0) + 1
        elif not billable and before.get("entry_id"):  # a receivable cancelled elsewhere: forget it
            result["entry_id"] = None
            result["booking_rev"] = int(before.get("booking_rev") or 0) + 1
        if write and (result.get("entry_id") != after.get("entry_id") or result.get("booking_rev") != after.get("booking_rev")):
            saved = self.store.update_session(
                org_id, str(after["id"]), {"entry_id": result.get("entry_id"), "booking_rev": result.get("booking_rev", 0)}
            )
            if saved is None:
                raise not_found("Sessão")
            return saved
        return result

    # -- finance ------------------------------------------------------------------------------------

    def _client_entries(self, org_id: str, client_id: str) -> list[dict]:
        booked = self.store.booked_sessions_of_client(org_id, client_id)
        entries = self._entries(org_id, [s["entry_id"] for s in booked])
        today = self.today()
        out = []
        for s in booked:
            e = entries.get(str(s["entry_id"]))
            if e is None or e["status"] == _CANCELLED:
                continue
            due = _to_date(e.get("due_date"))
            out.append({
                "entry_id": e["id"],
                "session_id": str(s["id"]),
                "description": e.get("description") or "",
                "amount_cents": int(e["amount_cents"]),
                "settled_cents": int(e["settled_cents"]),
                "due_date": _iso_date(e.get("due_date")),
                "status": e["status"],
                "overdue": bool(e["status"] in _OPEN and due is not None and due < today),
            })
        out.sort(key=lambda e: (e["due_date"] or "", e["entry_id"]), reverse=True)
        return out

    def client_finance(self, org_id: str, client_id: str) -> dict:
        org_id = str(org_id)
        client = self._client(org_id, client_id)
        entries = self._client_entries(org_id, client["id"])
        money = self._money(
            ({"status": e["status"], "amount_cents": e["amount_cents"], "settled_cents": e["settled_cents"], "due_date": e["due_date"]} for e in entries),
            self.today(),
        )
        return {**money, "entries": entries}

    def record_payment(self, org_id: str, client_id: str, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
        """Allocate a manual payment across the client's open receivables (oldest due first) on `account_id`.

        Returns `{settlement_ids, finance}`. The `client_payments` row is written first and completed with the
        settlement ids; a failure mid-way keeps the settlements already made (they are real money, recorded on the
        row) and re-raises -- nothing is swallowed."""
        org_id = str(org_id)
        client = self._client(org_id, client_id)
        method = data["method"]
        if method not in self.config.method_slugs:
            raise invalid("method", f"Forma de pagamento desconhecida: {method}.", METODO_INVALIDO)
        amount = int(data["amount_cents"])
        if amount <= 0:
            raise invalid("amount_cents", "O valor deve ser maior que zero.", VALOR_INVALIDO)
        entries = [e for e in self._client_entries(org_id, client["id"]) if e["status"] in _OPEN]
        if data.get("entry_ids"):
            wanted = [str(i) for i in data["entry_ids"]]
            known = {e["entry_id"] for e in entries}
            unknown = [i for i in wanted if i not in known]
            if unknown:
                raise invalid("entry_ids", "Lançamento em aberto não encontrado para este cadastro.", LANCAMENTO_INVALIDO)
            entries = [e for e in entries if e["entry_id"] in set(wanted)]
        entries.sort(key=lambda e: (e["due_date"] or "", e["entry_id"]))
        total_open = sum(e["amount_cents"] - e["settled_cents"] for e in entries)
        if amount > total_open:
            raise invalid("amount_cents", "O valor excede o total em aberto.", VALOR_EXCEDE_ABERTO)

        payment = self.store.insert_payment(org_id, {
            "id": str(uuid4()),
            "client_id": str(client["id"]),
            "amount_cents": amount,
            "paid_on": _iso_date(data["paid_on"]),
            "account_id": str(data["account_id"]),
            "method": method,
            "notes": _clean(data.get("notes")),
            "settlement_ids": [],
            "created_by": user_id,
            "created_at": _utc_iso(self.now()),
        })
        settlement_ids: list[str] = []
        left = amount
        try:
            for e in entries:
                if left <= 0:
                    break
                part = min(left, e["amount_cents"] - e["settled_cents"])
                if part <= 0:
                    continue
                settlement_ids.append(self.booking.settle_receivable(
                    org_id,
                    e["entry_id"],
                    account_id=str(data["account_id"]),
                    amount_cents=part,
                    settled_on=_to_date(data["paid_on"]),
                    method=method,
                    external_ref=f"{self.config.finance_ref_prefix}:payment:{payment['id']}:{e['entry_id']}",
                ))
                left -= part
        except Exception:
            logger.exception(
                "clients: payment %s stopped after %d settlement(s) of %d cents", payment["id"], len(settlement_ids), amount
            )
            if settlement_ids:
                self.store.update_payment(org_id, payment["id"], {"settlement_ids": settlement_ids})
            else:
                self.store.delete_payment(org_id, payment["id"])
            raise
        self.store.update_payment(org_id, payment["id"], {"settlement_ids": settlement_ids})
        return {"settlement_ids": settlement_ids, "finance": self.client_finance(org_id, client["id"])}


__all__ = ["MAX_AGENDA_DAYS", "ClientsService"]
