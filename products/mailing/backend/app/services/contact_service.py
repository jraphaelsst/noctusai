"""Contact management service."""
import logging

from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)


class ContactService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_contacts(self, page: int = 1, page_size: int = 20,
                      status: str = None, search: str = None, tags: list = None):
        query = self.db.table("contacts").select("*", count="exact").eq("org_id", self.org_id)
        if status:
            query = query.eq("status", status)
        if search:
            query = query.or_(f"nome.ilike.%{search}%,email.ilike.%{search}%,empresa.ilike.%{search}%")
        if tags:
            query = query.contains("tags", tags)
        query = query.order("created_at", desc=True)
        offset = (page - 1) * page_size
        result = query.range(offset, offset + page_size - 1).execute()
        return result.data or [], result.count or 0

    def get_contact(self, contact_id: str):
        result = self.db.table("contacts").select("*").eq("id", contact_id).eq("org_id", self.org_id).execute()
        return result.data[0] if result.data else None

    def create_contact(self, data: dict):
        data["org_id"] = self.org_id
        result = self.db.table("contacts").insert(data).execute()
        return result.data[0] if result.data else None

    def update_contact(self, contact_id: str, data: dict):
        data["updated_at"] = "now()"
        result = (self.db.table("contacts").update(data)
                  .eq("id", contact_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def delete_contact(self, contact_id: str):
        delete_or_404(
            self.db, "contacts",
            ("id", contact_id), ("org_id", self.org_id),
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
