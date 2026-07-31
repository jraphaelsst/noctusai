"""FoldersService — CRUD over ``social_wiring.n8n_folders`` /
``social_wiring.n8n_workflow_placement``.

``migrations/038_n8n_folders.sql`` ships these two tables on a sibling
unmerged branch (``feat/n8n-folders-migration``) — this slice codes
against the DOCUMENTED shape without re-authoring a competing copy of
that migration:

    n8n_folders             — id, org_id, account_id, parent_id, name,
                               position, timestamps.
                               UNIQUE(account_id, parent_id, name) +
                               partial unique (account_id, name)
                               WHERE parent_id IS NULL.
    n8n_workflow_placement  — org_id, account_id, workflow_id TEXT,
                               folder_id; PK (account_id, workflow_id).

All tree operations (cycle detection, sibling-name-conflict detection)
are done in PYTHON over one ``list_for_account`` read rather than via
``.eq(column, None)`` filters — a generic Supabase-style query builder
(and this product's ``SQLiteClient`` dev/test double) translates
``.eq(col, None)`` to ``col = NULL`` in SQL, which never matches (NULL
= NULL is NULL, not true) — a real footgun for "root" (parent_id IS
NULL) queries. Per-account folder counts are small, so one full read +
in-memory filtering is both correct and cheap.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import UUID, uuid4

from app.dependencies import get_admin_client

_SCHEMA = "social_wiring"
_FOLDERS_TABLE = "n8n_folders"
_PLACEMENT_TABLE = "n8n_workflow_placement"

# Sentinel distinguishing "parent_id not supplied" (leave unchanged) from
# "parent_id explicitly None" (reparent to root) in FoldersService.update —
# mirrors IntegrationAccountService's `_UNSET` pattern for the same shape.
# Public (imported by routers/folders.py) — unlike IntegrationAccountService's
# `_UNSET`, callers outside this module need it to express "not supplied".
UNSET = object()

__all__ = [
    "FolderRow",
    "FolderNotFound",
    "FolderCycleError",
    "FolderNameConflict",
    "FoldersService",
    "get_folders_service",
    "UNSET",
]


@dataclass(frozen=True)
class FolderRow:
    id: UUID
    org_id: UUID
    account_id: UUID
    parent_id: Optional[UUID]
    name: str
    position: int


class FolderNotFound(Exception):
    """Folder / parent-folder / reassign_to target does not exist."""


class FolderCycleError(Exception):
    """Reparenting a folder into itself or one of its own descendants."""


class FolderNameConflict(Exception):
    """UNIQUE(account_id, parent_id, name) would be violated."""


class FoldersService:
    def __init__(self, client: Any):
        self._client = client

    # ─── table handles ──────────────────────────────────────────────
    def _folders(self):
        return self._client.schema(_SCHEMA).table(_FOLDERS_TABLE)

    def _placements(self):
        return self._client.schema(_SCHEMA).table(_PLACEMENT_TABLE)

    @staticmethod
    def _row_to_folder(row: dict) -> FolderRow:
        raw_parent = row.get("parent_id")
        return FolderRow(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            account_id=UUID(str(row["account_id"])),
            parent_id=UUID(str(raw_parent)) if raw_parent else None,
            name=row["name"],
            position=int(row.get("position") or 0),
        )

    # ─── reads ──────────────────────────────────────────────────────
    def list_for_account(self, account_id: UUID, org_id: UUID) -> list[FolderRow]:
        resp = (
            self._folders()
            .select("*")
            .eq("account_id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        return [self._row_to_folder(r) for r in (resp.data or [])]

    def get(self, folder_id: UUID) -> Optional[FolderRow]:
        """Fetch a folder by id alone (no org filter) — callers derive
        ownership from the returned row's ``org_id`` themselves (the
        PATCH/DELETE routes take no ``account_id`` in the body; see
        ``routers/folders.py``)."""
        resp = self._folders().select("*").eq("id", str(folder_id)).execute()
        rows = resp.data or []
        return self._row_to_folder(rows[0]) if rows else None

    @staticmethod
    def _is_ancestor(
        all_folders: list[FolderRow], ancestor_id: UUID, node_id: UUID
    ) -> bool:
        """True when ``ancestor_id`` is ``node_id`` itself, or is on
        ``node_id``'s path to the root."""
        by_id = {f.id: f for f in all_folders}
        node: Optional[FolderRow] = by_id.get(node_id)
        seen: set[UUID] = set()
        while node is not None:
            if node.id == ancestor_id:
                return True
            if node.id in seen:  # defensive: pre-existing cycle — never loop forever
                break
            seen.add(node.id)
            node = by_id.get(node.parent_id) if node.parent_id else None
        return False

    # ─── writes ─────────────────────────────────────────────────────
    def create(
        self,
        *,
        org_id: UUID,
        account_id: UUID,
        name: str,
        parent_id: Optional[UUID],
    ) -> FolderRow:
        name = name.strip()
        siblings_source = self.list_for_account(account_id, org_id)
        if parent_id is not None and not any(f.id == parent_id for f in siblings_source):
            raise FolderNotFound(f"parent folder {parent_id} not found")
        if any(f.parent_id == parent_id and f.name == name for f in siblings_source):
            raise FolderNameConflict(
                f"a folder named {name!r} already exists at this level"
            )
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "account_id": str(account_id),
            "parent_id": str(parent_id) if parent_id else None,
            "name": name,
            "position": 0,
            "created_at": now,
            "updated_at": now,
        }
        resp = self._folders().insert(data).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError("n8n_folders insert returned no data")
        return self._row_to_folder(rows[0])

    def update(
        self,
        folder_id: UUID,
        *,
        name: Optional[str] = None,
        parent_id: Union[UUID, None, object] = UNSET,
        position: Optional[int] = None,
    ) -> FolderRow:
        current = self.get(folder_id)
        if current is None:
            raise FolderNotFound(f"folder {folder_id} not found")
        all_folders = self.list_for_account(current.account_id, current.org_id)

        new_name = name.strip() if name is not None else current.name
        new_parent = current.parent_id if parent_id is UNSET else parent_id

        if new_parent is not None:
            if new_parent == folder_id:
                raise FolderCycleError("a folder cannot be its own parent")
            if not any(f.id == new_parent for f in all_folders):
                raise FolderNotFound(f"parent folder {new_parent} not found")
            # Reparenting folder_id under new_parent is a cycle iff
            # folder_id is an ancestor of new_parent (i.e. new_parent is
            # folder_id's own descendant).
            if self._is_ancestor(all_folders, folder_id, new_parent):
                raise FolderCycleError(
                    f"cannot move folder {folder_id} into its own descendant {new_parent}"
                )

        siblings = [
            f for f in all_folders if f.parent_id == new_parent and f.id != folder_id
        ]
        if any(f.name == new_name for f in siblings):
            raise FolderNameConflict(
                f"a folder named {new_name!r} already exists at this level"
            )

        updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if name is not None:
            updates["name"] = new_name
        if parent_id is not UNSET:
            updates["parent_id"] = str(new_parent) if new_parent else None
        if position is not None:
            updates["position"] = position
        if len(updates) == 1:  # nothing besides updated_at changed — no-op
            return current

        resp = self._folders().update(updates).eq("id", str(folder_id)).execute()
        rows = resp.data or []
        if not rows:
            raise FolderNotFound(f"folder {folder_id} not found")
        return self._row_to_folder(rows[0])

    def delete(self, folder_id: UUID, *, reassign_to: Optional[UUID]) -> None:
        """Delete a folder, moving its children folders + placed
        workflows to ``reassign_to`` (``None`` ⇒ root — the FE omits
        the query param entirely for "reassign to root", per the S4
        FE's binding contract clarification)."""
        current = self.get(folder_id)
        if current is None:
            raise FolderNotFound(f"folder {folder_id} not found")
        all_folders = self.list_for_account(current.account_id, current.org_id)

        if reassign_to is not None:
            if not any(f.id == reassign_to for f in all_folders):
                raise FolderNotFound(f"reassign_to folder {reassign_to} not found")
            if reassign_to == folder_id or self._is_ancestor(
                all_folders, folder_id, reassign_to
            ):
                raise FolderCycleError(
                    "reassign_to cannot be the folder being deleted or one "
                    "of its own descendants"
                )

        now = datetime.now(timezone.utc).isoformat()
        has_children = any(f.parent_id == folder_id for f in all_folders)
        if has_children:
            self._folders().update(
                {
                    "parent_id": str(reassign_to) if reassign_to else None,
                    "updated_at": now,
                }
            ).eq("account_id", str(current.account_id)).eq(
                "parent_id", str(folder_id)
            ).execute()

        placements = (
            self._placements()
            .select("*")
            .eq("account_id", str(current.account_id))
            .execute()
        ).data or []
        has_placements = any(
            str(p.get("folder_id") or "") == str(folder_id) for p in placements
        )
        if has_placements:
            self._placements().update(
                {"folder_id": str(reassign_to) if reassign_to else None}
            ).eq("account_id", str(current.account_id)).eq(
                "folder_id", str(folder_id)
            ).execute()

        self._folders().delete().eq("id", str(folder_id)).execute()

    # ─── placement (workflow → folder) ─────────────────────────────
    def get_placements(self, account_id: UUID) -> dict[str, UUID]:
        """``{workflow_id: folder_id}`` for every PLACED workflow on
        this account. A workflow with no row, or a row with
        ``folder_id IS NULL``, is simply absent from the returned
        dict — the caller treats a missing key as "at root"."""
        rows = (
            self._placements().select("*").eq("account_id", str(account_id)).execute()
        ).data or []
        out: dict[str, UUID] = {}
        for row in rows:
            fid = row.get("folder_id")
            if fid:
                out[str(row["workflow_id"])] = UUID(str(fid))
        return out

    def set_placement(
        self,
        *,
        org_id: UUID,
        account_id: UUID,
        workflow_id: str,
        folder_id: Optional[UUID],
    ) -> None:
        existing = (
            self._placements()
            .select("workflow_id")
            .eq("account_id", str(account_id))
            .eq("workflow_id", workflow_id)
            .execute()
        ).data or []
        if existing:
            self._placements().update(
                {"folder_id": str(folder_id) if folder_id else None}
            ).eq("account_id", str(account_id)).eq("workflow_id", workflow_id).execute()
        else:
            self._placements().insert(
                {
                    "org_id": str(org_id),
                    "account_id": str(account_id),
                    "workflow_id": workflow_id,
                    "folder_id": str(folder_id) if folder_id else None,
                }
            ).execute()

    def clear_placement(self, *, account_id: UUID, workflow_id: str) -> None:
        """Drop the placement row entirely — the "unassign clears the
        placement row" rule (assign/unassign live in
        ``routers/workflows.py``) and the "delete-workflow" cleanup."""
        self._placements().delete().eq("account_id", str(account_id)).eq(
            "workflow_id", workflow_id
        ).execute()


def get_folders_service() -> FoldersService:
    """DI seam — mirrors ``get_account_service``'s shape. n8n folders
    carry no secrets, so there's no ENCRYPTION_KEY gap to guard here.
    Tests override via
    ``app.dependency_overrides[get_folders_service]``.
    """
    return FoldersService(get_admin_client())
