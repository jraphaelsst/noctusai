"""Contact management service."""
from __future__ import annotations

import logging
import re

from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)

# Matches strings that are either just digits (phone-as-name fallback) or
# look like a JID (digits@domain), so we know the name field is not a real
# display name and we should overwrite it with a better one.
_PHONE_LIKE_RE = re.compile(r"^[\d+\s\-()@a-z.]+$", re.IGNORECASE)


def _is_phone_like_name(name: str | None) -> bool:
    """True when ``name`` is empty, None, or looks like a phone / JID."""
    if not name:
        return True
    return bool(_PHONE_LIKE_RE.match(name.strip()))


class ContactService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_contacts(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str = None,
        search: str = None,
        tags: list = None,
    ):
        """List contacts for the org.

        Returns (rows, total_count).  Includes all columns including the new
        WhatsApp identity fields (whatsapp_phone, whatsapp_lids, whatsapp_jid,
        source, nome, telefone, email) so the FE Contatos page can render
        both manual and WhatsApp-sourced contacts.
        """
        query = (
            self.db.table("contacts")
            .select("*", count="exact")
            .eq("org_id", self.org_id)
        )
        if status:
            query = query.eq("status", status)
        if search:
            query = query.or_(
                f"nome.ilike.%{search}%,"
                f"email.ilike.%{search}%,"
                f"empresa.ilike.%{search}%,"
                f"telefone.ilike.%{search}%,"
                f"whatsapp_phone.ilike.%{search}%"
            )
        if tags:
            query = query.contains("tags", tags)
        query = query.order("created_at", desc=True)
        offset = (page - 1) * page_size
        result = query.range(offset, offset + page_size - 1).execute()
        return result.data or [], result.count or 0

    def get_contact(self, contact_id: str):
        result = (
            self.db.table("contacts")
            .select("*")
            .eq("id", contact_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def create_contact(self, data: dict):
        data["org_id"] = self.org_id
        result = self.db.table("contacts").insert(data).execute()
        return result.data[0] if result.data else None

    def update_contact(self, contact_id: str, data: dict):
        data["updated_at"] = "now()"
        result = (
            self.db.table("contacts")
            .update(data)
            .eq("id", contact_id)
            .eq("org_id", self.org_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def delete_contact(self, contact_id: str):
        delete_or_404(
            self.db,
            "contacts",
            ("id", contact_id),
            ("org_id", self.org_id),
            message="Contato nao encontrado",
        )
        return True

    def import_contacts(self, contacts: list[dict]):
        """Batch import contacts. Skips duplicates (org_id + email unique constraint)."""
        for c in contacts:
            c["org_id"] = self.org_id
            c["source"] = "import"
        rows = []
        for c in contacts:
            try:
                result = self.db.table("contacts").upsert(
                    c, on_conflict="org_id,email"
                ).execute()
                if result.data:
                    rows.extend(result.data)
            except Exception as e:
                logger.warning("Import skip: %s — %s", c.get("email"), e)
        return {"imported": len(rows), "total": len(contacts)}

    def upsert_whatsapp_contact(
        self,
        *,
        phone: str,
        lids: list[str],
        name: str | None,
        jid: str | None,
    ) -> dict:
        """Find-or-create a contact by WhatsApp phone (canonical dedup key).

        ``phone`` must be digits-only (no ``@``, no ``+``).

        If a contact with (org_id, whatsapp_phone=phone) already exists:
        - Unions ``whatsapp_lids`` (adds newly seen LIDs without clobbering).
        - Sets ``whatsapp_jid`` if currently NULL.
        - Updates ``nome`` only when current nome is None, empty, or phone-like.
        - Sets ``telefone`` if currently NULL.

        If no contact exists: inserts a new row with source='whatsapp'.

        Returns the final contact row dict.
        """
        # ── Look for existing by whatsapp_phone ──────────────────────────────
        existing_result = (
            self.db.table("contacts")
            .select("*")
            .eq("org_id", self.org_id)
            .eq("whatsapp_phone", phone)
            .limit(1)
            .execute()
        )
        existing = existing_result.data[0] if existing_result.data else None

        if existing:
            # Union lids arrays (order-preserving dedup)
            existing_lids: list[str] = existing.get("whatsapp_lids") or []
            merged_lids = list(dict.fromkeys(existing_lids + lids))

            updates: dict = {"whatsapp_lids": merged_lids}
            if not existing.get("whatsapp_jid") and jid:
                updates["whatsapp_jid"] = jid
            if not existing.get("telefone") and phone:
                updates["telefone"] = phone
            if name and _is_phone_like_name(existing.get("nome")):
                updates["nome"] = name
            updates["updated_at"] = "now()"

            result = (
                self.db.table("contacts")
                .update(updates)
                .eq("id", existing["id"])
                .eq("org_id", self.org_id)
                .execute()
            )
            return result.data[0] if result.data else existing

        # ── Insert new WhatsApp contact ───────────────────────────────────────
        new_row: dict = {
            "org_id": self.org_id,
            "source": "whatsapp",
            "status": "active",
            "email": None,  # WhatsApp contacts have no email
            "nome": name or phone,
            "telefone": phone,
            "whatsapp_phone": phone,
            "whatsapp_lids": lids,
            "whatsapp_jid": jid,
        }
        result = self.db.table("contacts").insert(new_row).execute()
        if result.data:
            return result.data[0]
        logger.warning(
            "upsert_whatsapp_contact: insert returned no data for phone=%s org=%s",
            phone,
            self.org_id,
        )
        return new_row
