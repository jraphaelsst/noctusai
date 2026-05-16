"""Contact list management service."""
import logging

from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)


class ListService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_all(self):
        result = (self.db.table("contact_lists").select("*")
                  .eq("org_id", self.org_id).order("created_at", desc=True).execute())
        return result.data or []

    def get_list(self, list_id: str):
        result = (self.db.table("contact_lists").select("*")
                  .eq("id", list_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def create_list(self, data: dict):
        data["org_id"] = self.org_id
        result = self.db.table("contact_lists").insert(data).execute()
        return result.data[0] if result.data else None

    def update_list(self, list_id: str, data: dict):
        data["updated_at"] = "now()"
        result = (self.db.table("contact_lists").update(data)
                  .eq("id", list_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def delete_list(self, list_id: str):
        delete_or_404(
            self.db, "contact_lists",
            ("id", list_id), ("org_id", self.org_id),
            message="Lista nao encontrada",
        )
        return True

    def add_members(self, list_id: str, contact_ids: list[str]):
        rows = [{"list_id": list_id, "contact_id": cid} for cid in contact_ids]
        result = self.db.table("contact_list_members").upsert(
            rows, on_conflict="list_id,contact_id"
        ).execute()
        self._update_count(list_id)
        return result.data or []

    def remove_members(self, list_id: str, contact_ids: list[str]):
        # Idempotent bulk membership removal — uses `.in_()` rather than `.eq()`,
        # so `noctusai_lib.api.crud_safety.delete_or_404` (eq-only) is not the
        # right shape. Absent members are a no-op by design (caller passes a
        # whole-set list and wants "ensure these are gone").
        self.db.table("contact_list_members").delete().eq("list_id", list_id).in_("contact_id", contact_ids).execute()
        self._update_count(list_id)
        return True

    def resolve_contacts(self, list_id: str):
        """Resolve all contacts in a list. For static: join table. For dynamic: run filter query."""
        lst = self.get_list(list_id)
        if not lst:
            return []
        if lst["tipo"] == "static":
            result = (self.db.table("contact_list_members")
                      .select("contact_id, contacts(*)")
                      .eq("list_id", list_id).execute())
            return [r.get("contacts") for r in (result.data or []) if r.get("contacts")]
        else:
            return self._resolve_dynamic(lst.get("filtros", {}))

    def _resolve_dynamic(self, filtros: dict):
        """Build a query from dynamic segment filters."""
        query = self.db.table("contacts").select("*").eq("org_id", self.org_id).eq("status", "active")
        if filtros.get("tags_include"):
            query = query.contains("tags", filtros["tags_include"])
        if filtros.get("empresa"):
            query = query.eq("empresa", filtros["empresa"])
        if filtros.get("source"):
            query = query.eq("source", filtros["source"])
        result = query.order("created_at", desc=True).execute()
        return result.data or []

    def _update_count(self, list_id: str):
        result = (self.db.table("contact_list_members").select("id", count="exact")
                  .eq("list_id", list_id).execute())
        count = result.count or 0
        self.db.table("contact_lists").update({"contact_count": count}).eq("id", list_id).execute()
