"""Equipe — the org's content team, the Esteira card hub's member source (esteira-contract.md 2.2 / 5.2).

Org scoped; a foreign id is a 404. A duplicate name (case-insensitive) is 409 ``membro_duplicado``.
DELETE is soft (``ativo=false``) when the member is on any post, hard otherwise.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import paged_rows

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.services.esteira_service import EsteiraError, coded

EQUIPE = "cs_equipe"
COLS = "id,nome,funcao,cor,user_id,ativo"


def present_membro(row: dict) -> dict:
    return {
        "id": row["id"],
        "nome": row["nome"],
        "funcao": row.get("funcao"),
        "cor": row.get("cor"),
        "user_id": row.get("user_id"),
        "ativo": bool(row.get("ativo", True)),
    }


class EquipeService:
    def __init__(self, db: Any, org_id: str, user_id: Optional[str]):
        self.db = db
        self.org_id = str(org_id)
        self.user_id = str(user_id) if user_id else None

    def _row(self, membro_id: str) -> dict:
        rows = self.db.table(EQUIPE).select("*").eq("id", str(membro_id)).eq("org_id", self.org_id).execute().data
        if not rows:
            raise EsteiraError(404, "Membro não encontrado")
        return rows[0]

    def _assert_nome_livre(self, nome: str, *, exclude: Optional[str] = None) -> None:
        for r in paged_rows(self.db, EQUIPE, self.org_id, select="id,nome"):
            if str(r["id"]) != str(exclude) and (r.get("nome") or "").strip().lower() == nome.strip().lower():
                raise coded(409, "membro_duplicado", "Já existe um membro com este nome.")

    def listar(self, incluir_inativos: bool) -> list[dict]:
        refine = None if incluir_inativos else (lambda q: q.eq("ativo", True))
        rows = paged_rows(self.db, EQUIPE, self.org_id, refine=refine)
        rows.sort(key=lambda r: (r.get("nome") or "").lower())
        return [present_membro(r) for r in rows]

    def criar(self, body: Any) -> dict:
        self._assert_nome_livre(body.nome)
        row = {
            "org_id": self.org_id,
            "nome": body.nome,
            "funcao": body.funcao,
            "cor": body.cor,
            "user_id": str(body.user_id) if body.user_id else None,
            "ativo": True,
            "created_by": self.user_id,
        }
        try:
            created = self.db.table(EQUIPE).insert(row).execute().data
        except Exception as exc:  # noqa: BLE001 - mapped below, anything else re-raised
            if is_unique_violation(exc):
                raise coded(409, "membro_duplicado", "Já existe um membro com este nome.") from exc
            raise
        return present_membro(created[0])

    def atualizar(self, membro_id: str, body: Any) -> dict:
        row = self._row(membro_id)
        values = body.model_dump(exclude_unset=True, mode="json")
        # nome / ativo are NOT NULL: an explicit null is ignored, not written.
        values = {k: v for k, v in values.items() if v is not None or k in ("funcao", "cor", "user_id")}
        if "nome" in values:
            self._assert_nome_livre(values["nome"], exclude=row["id"])
        if not values:
            return present_membro(row)
        try:
            updated = self.db.table(EQUIPE).update(values).eq("id", row["id"]).eq("org_id", self.org_id).execute().data
        except Exception as exc:  # noqa: BLE001
            if is_unique_violation(exc):
                raise coded(409, "membro_duplicado", "Já existe um membro com este nome.") from exc
            raise
        return present_membro(updated[0] if updated else {**row, **values})

    def excluir(self, membro_id: str) -> None:
        row = self._row(membro_id)
        em_uso = (
            self.db.table("cs_post_membros")
            .select("post_id")
            .eq("org_id", self.org_id)
            .eq("equipe_id", row["id"])
            .limit(1)
            .execute()
            .data
        )
        if em_uso:
            self.db.table(EQUIPE).update({"ativo": False}).eq("id", row["id"]).eq("org_id", self.org_id).execute()
        else:
            self.db.table(EQUIPE).delete().eq("id", row["id"]).eq("org_id", self.org_id).execute()
