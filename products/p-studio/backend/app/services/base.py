"""CRUD base — a forma comum a todo cadastro do estúdio.

Os routers ficam finos; os services concentram IO e regra. Os cadastros
simples (clientes, imóveis, serviços, equipamentos) não têm regra própria,
então herdam tudo daqui e só declaram tabela e ordenação. Os domínios com
regra de verdade (negócios, captações, produções, financeiro) têm service
próprio e usam este como base.

O client vem sempre RLS-scoped pelo JWT do usuário, então nenhuma query
precisa filtrar org_id na leitura — a policy já filtrou. Na escrita o org_id
é carimbado para satisfazer o WITH CHECK.
"""
from typing import Any, Optional

from fastapi import HTTPException
from supabase import Client

from app.database import execute


class CrudService:
    table: str = ""
    order_by: str = "created_at"
    order_desc: bool = True
    soft_delete: bool = False  # cadastros desativam; transacionais apagam

    def __init__(self, db: Client, org_id: str) -> None:
        self.db = db
        self.org_id = org_id

    # ── leitura ──────────────────────────────────────────────────────────
    def listar(self, *, incluir_inativos: bool = False) -> list[dict]:
        query = self.db.table(self.table).select("*")
        if self.soft_delete and not incluir_inativos:
            query = query.eq("ativo", True)
        return execute(query.order(self.order_by, desc=self.order_desc)).data or []

    def obter(self, item_id: str) -> dict:
        rows = execute(self.db.table(self.table).select("*").eq("id", item_id)).data
        if not rows:
            raise HTTPException(status_code=404, detail=self._nao_encontrado())
        return rows[0]

    # ── escrita ──────────────────────────────────────────────────────────
    def criar(self, payload: dict) -> dict:
        row = {**payload, "org_id": self.org_id}
        return execute(self.db.table(self.table).insert(row)).data[0]

    def atualizar(self, item_id: str, changes: dict) -> dict:
        if not changes:
            raise HTTPException(status_code=400, detail="Nada para atualizar")
        rows = execute(
            self.db.table(self.table).update(changes).eq("id", item_id)
        ).data
        if not rows:
            raise HTTPException(status_code=404, detail=self._nao_encontrado())
        return rows[0]

    def excluir(self, item_id: str) -> None:
        if self.soft_delete:
            self.atualizar(item_id, {"ativo": False})
            return
        execute(self.db.table(self.table).delete().eq("id", item_id))

    # ── helpers ──────────────────────────────────────────────────────────
    def _nao_encontrado(self) -> str:
        return f"Registro não encontrado em {self.table}"

    def _mapa(self, tabela: str, campos: str = "id,nome") -> dict[str, dict]:
        """Carrega uma tabela inteira indexada por id.

        Usado para enriquecer listagens (nome do cliente ao lado do negócio)
        sem disparar uma query por linha. Os catálogos do estúdio têm dezenas
        de linhas, não milhares — carregar tudo é mais barato que um join
        por item, e mantém o service legível.
        """
        rows = execute(self.db.table(tabela).select(campos)).data or []
        return {r["id"]: r for r in rows}


def somente_preenchidos(payload: Any) -> dict:
    """`model_dump` só com o que o cliente realmente mandou.

    `exclude_unset` distingue "não mencionou o campo" de "mandou null" —
    sem isso, um PATCH parcial apagaria todo campo omitido.
    """
    return payload.model_dump(mode="json", exclude_unset=True)


def obrigatorio(valor: Optional[str], mensagem: str) -> str:
    if not valor:
        raise HTTPException(status_code=400, detail=mensagem)
    return valor
