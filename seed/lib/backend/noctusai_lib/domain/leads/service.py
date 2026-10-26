"""`LeadsService` -- the leads use-cases over a `LeadsStore`, scoped by org on every call.

* CRUD with validation against the product's `LeadsConfig` (stage / origin are DATA, phone is canonical
  E.164 via `primitives.phone.normalize_phone`).
* `move()` -- the ONE card-move mechanic: fractional `position` from `domain.pipeline.ordering`
  (a drag is one write, never a column renumber).
* `board()` -- one column per configured stage (empty ones included), leads on a stage the config no
  longer lists appear in an extra "Sem etapa" column instead of vanishing.
* `upsert_from_whatsapp()` / `touch_last_message()` -- the WhatsApp seam. `upsert_from_whatsapp(org_id,
  connection_id, chat)` is call-compatible with the inbox organ's `on_new_chat` hook; `chat` is any object or
  mapping with `chat_id / name / phone / last_message_preview / last_message_at` (`WhatsAppChatLike`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from noctusai_lib.domain.pipeline.ordering import POSITION_FIELD, position_for_index, position_on_top
from noctusai_lib.primitives.phone import normalize_phone

from .config import LeadsConfig
from .errors import (
    ETAPA_INVALIDA,
    ORIGEM_INVALIDA,
    TELEFONE_INVALIDO,
    LeadConflictError,
    invalid,
    not_found,
)
from .store import LeadFilters, LeadsStore, as_dt, board_sort_key, position_of_row

logger = logging.getLogger(__name__)

#: slug of the synthetic board column that holds leads whose stage is no longer in the config
ORPHAN_STAGE = "__sem_etapa"
ORPHAN_LABEL = "Sem etapa"
DEFAULT_PREVIEW_MAX = 200
_NAMELESS = "Contato sem nome"
POSITION_FIELD_COL = "position"

#: fields a caller may set on create / update (everything else is server-owned)
_EDITABLE = ("name", "phone", "email", "origin", "notes", "tags", "first_contact_at")


@runtime_checkable
class WhatsAppChatLike(Protocol):
    """The slice of the inbox organ's `InboxChat` the leads organ reads (a dict with these keys works too)."""

    chat_id: str
    name: Optional[str]
    phone: Optional[str]
    last_message_preview: Optional[str]
    last_message_at: Optional[datetime]


def _chat_get(chat: Any, key: str) -> Any:
    return chat.get(key) if isinstance(chat, Mapping) else getattr(chat, key, None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def present(row: dict) -> dict:
    """The JSON shape of a lead: timestamps as ISO strings, `position` as a number."""
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
    if isinstance(out.get(POSITION_FIELD_COL), str):
        try:
            out[POSITION_FIELD_COL] = float(out[POSITION_FIELD_COL])
        except ValueError:
            logger.warning("leads: unparseable position %r on lead %s", out[POSITION_FIELD_COL], out.get("id"))
    out["tags"] = list(out.get("tags") or [])
    return out


def _as_cards(rows: list[dict]) -> list[dict]:
    """Rows in the shape `pipeline.ordering` reads (its field is `kanban_pos`)."""
    return [{POSITION_FIELD: position_of_row(r)} for r in rows]


class LeadsService:
    def __init__(self, store: LeadsStore, config: LeadsConfig) -> None:
        self.store = store
        self.config = config

    # -- validation ---------------------------------------------------------------------------------

    def _check_stage(self, stage: str) -> str:
        if stage not in self.config.stage_slugs:
            raise invalid("stage", f"Etapa desconhecida: {stage}.", ETAPA_INVALIDA)
        return stage

    def _check_origin(self, origin: str) -> str:
        if origin not in self.config.origin_slugs:
            raise invalid("origin", f"Origem desconhecida: {origin}.", ORIGEM_INVALIDA)
        return origin

    @staticmethod
    def _phone(raw: Optional[str]) -> Optional[str]:
        raw = _clean(raw)
        if raw is None:
            return None
        phone = normalize_phone(raw)
        if phone is None:
            raise invalid("phone", "Telefone inválido. Use o DDD + número (ex.: 11 99999-9999).", TELEFONE_INVALIDO)
        return phone

    def _normalize(self, data: Mapping[str, Any]) -> dict:
        out: dict[str, Any] = {}
        for key in _EDITABLE:
            if key not in data:
                continue
            value = data[key]
            if key == "phone":
                out[key] = self._phone(value)
            elif key == "origin":
                if value is None:
                    continue  # no origin named: create falls back to the default, update keeps the current one
                out[key] = self._check_origin(value)
            elif key == "tags":
                out[key] = [t.strip() for t in (value or []) if t and t.strip()]
            elif key == "first_contact_at":
                if value is None:
                    continue
                out[key] = as_dt(value)
            elif key == "name":
                out[key] = (value or "").strip()
            else:
                out[key] = _clean(value)
        return out

    # -- reads --------------------------------------------------------------------------------------

    def get(self, org_id: str, lead_id: str) -> dict:
        row = self.store.get(str(org_id), str(lead_id))
        if row is None:
            raise not_found("Lead")
        return row

    def list_leads(self, org_id: str, filters: LeadFilters, *, limit: int = 50, offset: int = 0) -> tuple[list[dict], Optional[int]]:
        """`(rows, next_offset)`; `next_offset` is None on the last page."""
        if filters.stage == ORPHAN_STAGE:
            filters = LeadFilters(**{**filters.__dict__, "stage": None, "stage_not_in": self.config.stage_slugs})
        elif filters.stage:
            self._check_stage(filters.stage)
        if filters.origin:
            self._check_origin(filters.origin)
        rows = self.store.query(str(org_id), filters, limit=limit + 1, offset=offset)
        more = len(rows) > limit
        return rows[:limit], (offset + limit if more else None)

    def board(self, org_id: str, filters: Optional[LeadFilters] = None) -> list[dict]:
        """One column per stage: `{etapa, stage, total, exibidos, cards}` (+ "Sem etapa" when needed)."""
        org_id = str(org_id)
        f = (filters or LeadFilters()).without_stage()
        cap = self.config.board_stage_limit
        columns = []
        for stage in self.config.stages:
            cards = self.store.column(org_id, stage.slug, f, limit=cap)  # type: ignore[union-attr]
            total = self.store.count(org_id, LeadFilters(**{**f.__dict__, "stage": stage.slug}))  # type: ignore[union-attr]
            columns.append(self._column(stage.slug, stage.as_dict(), total, cards))  # type: ignore[union-attr]
        orphan_f = LeadFilters(**{**f.__dict__, "stage_not_in": self.config.stage_slugs})
        orphan_total = self.store.count(org_id, orphan_f)
        if orphan_total:
            orphans = sorted(self.store.query(org_id, orphan_f, limit=cap), key=board_sort_key)
            stage = {"slug": ORPHAN_STAGE, "label": ORPHAN_LABEL, "color": "muted"}
            columns.append(self._column(ORPHAN_STAGE, stage, orphan_total, orphans))
            logger.warning("leads: %d lead(s) on a stage missing from the config are shown under %r", orphan_total, ORPHAN_LABEL)
        return columns

    @staticmethod
    def _column(etapa: str, stage: dict, total: int, cards: list[dict]) -> dict:
        return {"etapa": etapa, "stage": stage, "total": total, "exibidos": len(cards), "cards": [present(c) for c in cards]}

    # -- writes -------------------------------------------------------------------------------------

    def create(self, org_id: str, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
        org_id = str(org_id)
        fields = self._normalize(data)
        if not fields.get("name"):
            raise invalid("name", "Informe o nome do lead.", "nome_obrigatorio")
        stage = self._check_stage(data.get("stage") or self.config.first_stage)
        now = _now()
        row = {
            "id": str(uuid4()),
            "created_at": now,
            "updated_at": now,
            "tags": [],
            "origin": self.config.default_origin,
            **fields,
            "stage": stage,
            POSITION_FIELD_COL: self._top(org_id, stage),
            "stage_changed_at": now,
            "first_contact_at": fields.get("first_contact_at") or now,
            "created_by": user_id,
        }
        return self.store.insert(org_id, row)

    def update(self, org_id: str, lead_id: str, data: Mapping[str, Any]) -> dict:
        org_id = str(org_id)
        current = self.get(org_id, lead_id)
        patch = self._normalize(data)
        if "name" in patch and not patch["name"]:
            raise invalid("name", "O nome não pode ficar vazio.", "nome_obrigatorio")
        if data.get("stage") and data["stage"] != current["stage"]:
            self._check_stage(data["stage"])
            patch.update(stage=data["stage"], stage_changed_at=_now(), **{POSITION_FIELD_COL: self._top(org_id, data["stage"])})
        if not patch:
            return current
        patch["updated_at"] = _now()
        saved = self.store.update(org_id, str(lead_id), patch)
        if saved is None:
            raise not_found("Lead")
        return saved

    def delete(self, org_id: str, lead_id: str) -> None:
        if not self.store.delete(str(org_id), str(lead_id)):
            raise not_found("Lead")

    def move(self, org_id: str, lead_id: str, stage: str, index: int = 0) -> dict:
        """Put the lead at `index` (0 = top) of `stage`'s column. One write; neighbours are untouched."""
        org_id = str(org_id)
        self._check_stage(stage)
        current = self.get(org_id, lead_id)
        index = max(0, int(index))
        neighbours = self.store.column(org_id, stage, LeadFilters(), limit=index + 1, exclude_id=str(lead_id))
        patch: dict[str, Any] = {POSITION_FIELD_COL: position_for_index(_as_cards(neighbours), index), "updated_at": _now()}
        if current["stage"] != stage:
            patch["stage_changed_at"] = _now()
        patch["stage"] = stage
        saved = self.store.update(org_id, str(lead_id), patch)
        if saved is None:
            raise not_found("Lead")
        return saved

    def _top(self, org_id: str, stage: str) -> Decimal:
        return position_on_top(_as_cards(self.store.column(org_id, stage, LeadFilters(), limit=1)))

    # -- WhatsApp seam ------------------------------------------------------------------------------

    def upsert_lead_from_chat(self, org_id: str, connection_id: str, chat: Any) -> tuple[dict, bool]:
        """Sync core of `upsert_from_whatsapp`: `(lead, created)`. Idempotent by (connection, chat)."""
        org_id, connection_id = str(org_id), str(connection_id)
        chat_id = _chat_get(chat, "chat_id")
        if not chat_id:
            raise invalid("chat_id", "O chat não tem identificador.", "chat_invalido")
        existing = self.store.find_by_chat(org_id, connection_id, chat_id)
        if existing:
            return existing, False
        phone = normalize_phone(_chat_get(chat, "phone"))  # a chat with an unresolved number still becomes a lead
        now = _now()
        row = {
            "id": str(uuid4()),
            "created_at": now,
            "updated_at": now,
            "name": _clean(_chat_get(chat, "name")) or phone or _NAMELESS,
            "phone": phone,
            "origin": self.config.whatsapp_origin,
            "stage": self.config.first_stage,
            POSITION_FIELD_COL: self._top(org_id, self.config.first_stage),
            "stage_changed_at": now,
            "tags": [],
            "whatsapp_connection_id": connection_id,
            "whatsapp_chat_id": chat_id,
            "first_contact_at": now,
            "last_message_at": as_dt(_chat_get(chat, "last_message_at")),
            "last_message_preview": _preview(_chat_get(chat, "last_message_preview")),
        }
        try:
            return self.store.insert(org_id, row), True
        except LeadConflictError:  # a concurrent webhook won the race: its row is the lead
            winner = self.store.find_by_chat(org_id, connection_id, chat_id)
            if winner is None:
                raise
            return winner, False

    async def upsert_from_whatsapp(self, org_id: Any, connection_id: Any, chat: WhatsAppChatLike | Mapping[str, Any]) -> dict:
        """`on_new_chat(org_id, connection_id, chat)` -- creates the lead of a chat (once); returns it."""
        lead, _created = await asyncio.to_thread(self.upsert_lead_from_chat, str(org_id), str(connection_id), chat)
        return lead

    def touch_last_message_sync(
        self, org_id: str, connection_id: str, chat_id: str, *, preview: Optional[str], at: Optional[datetime]
    ) -> Optional[dict]:
        lead = self.store.find_by_chat(str(org_id), str(connection_id), chat_id)
        if lead is None:
            return None
        when = as_dt(at)
        known = as_dt(lead.get("last_message_at"))
        if when and known and when < known:
            return lead  # an older message arriving late must not rewind the card
        patch = {"last_message_preview": _preview(preview), "last_message_at": when or known, "updated_at": _now()}
        return self.store.update(str(org_id), lead["id"], patch)

    async def touch_last_message(
        self, org_id: Any, connection_id: Any, chat_id: str, *, preview: Optional[str], at: Optional[datetime] = None
    ) -> Optional[dict]:
        """Keep the card's preview fresh. No lead for the chat (never created, or deleted) => `None`, nothing recreated."""
        return await asyncio.to_thread(
            self.touch_last_message_sync, str(org_id), str(connection_id), chat_id, preview=preview, at=at
        )


def _preview(text: Optional[str]) -> Optional[str]:
    text = (text or "").strip()
    return text[:DEFAULT_PREVIEW_MAX] if text else None


__all__ = ["DEFAULT_PREVIEW_MAX", "LeadsService", "ORPHAN_LABEL", "ORPHAN_STAGE", "WhatsAppChatLike", "present"]
