"""Captações — a agenda operacional e o checklist de equipamentos.

Esta é a tela que o protótipo aceitava preencher e descartava no reload
(`useState` sem persistência). Aqui ela grava de verdade, e o checklist de
equipamentos vira linha de tabela em vez de array de strings — assim o
estúdio consegue perguntar "onde está o drone na quinta-feira".
"""
from datetime import date

from app.database import execute
from app.services.base import CrudService


class CaptacoesService(CrudService):
    table = "captacoes"
    order_by = "data"
    order_desc = False

    def _nao_encontrado(self) -> str:
        return "Captação não encontrada"

    # ── leitura ──────────────────────────────────────────────────────────
    def listar_periodo(
        self, inicio: date | None = None, fim: date | None = None
    ) -> list[dict]:
        query = self.db.table(self.table).select("*")
        if inicio:
            query = query.gte("data", inicio.isoformat())
        if fim:
            query = query.lte("data", fim.isoformat())
        captacoes = execute(query.order("data").order("hora")).data or []
        if not captacoes:
            return []

        clientes = self._mapa("clientes")
        equipamentos = self._mapa("equipamentos", "id,nome,categoria")
        ids = [c["id"] for c in captacoes]
        vinculos = execute(
            self.db.table("captacao_equipamentos")
            .select("id,captacao_id,equipamento_id,conferido")
            .in_("captacao_id", ids)
        ).data or []

        checklist: dict[str, list[dict]] = {}
        for v in vinculos:
            equip = equipamentos.get(v["equipamento_id"]) or {}
            checklist.setdefault(v["captacao_id"], []).append(
                {
                    "id": v["id"],
                    "equipamento_id": v["equipamento_id"],
                    "nome": equip.get("nome"),
                    "categoria": equip.get("categoria"),
                    "conferido": bool(v.get("conferido")),
                }
            )

        return [
            {
                **c,
                "cliente_nome": (clientes.get(c.get("cliente_id")) or {}).get("nome"),
                "equipamentos": checklist.get(c["id"], []),
            }
            for c in captacoes
        ]

    def obter_completo(self, captacao_id: str) -> dict:
        self.obter(captacao_id)  # 404 cedo
        encontradas = [c for c in self.listar_periodo() if c["id"] == captacao_id]
        return encontradas[0]

    # ── escrita ──────────────────────────────────────────────────────────
    def criar_com_checklist(self, payload: dict, equipamento_ids: list[str]) -> dict:
        # Endereço em branco cai para o do imóvel: o usuário escolhe o imóvel
        # na agenda e não deveria ter que redigitar o endereço.
        if not payload.get("endereco") and payload.get("imovel_id"):
            payload["endereco"] = self._endereco_do_imovel(payload["imovel_id"])

        captacao = self.criar(payload)
        self._gravar_checklist(captacao["id"], equipamento_ids)
        return self.obter_completo(captacao["id"])

    def atualizar_com_checklist(
        self, captacao_id: str, changes: dict, equipamento_ids: list[str] | None
    ) -> dict:
        self.obter(captacao_id)

        if equipamento_ids is not None:
            # Substitui a lista inteira. Perde o estado `conferido` dos itens
            # que permanecem — aceitável: mexer no checklist significa que a
            # conferência anterior não vale mais.
            execute(
                self.db.table("captacao_equipamentos")
                .delete()
                .eq("captacao_id", captacao_id)
            )
            self._gravar_checklist(captacao_id, equipamento_ids)

        if changes:
            self.atualizar(captacao_id, changes)
        return self.obter_completo(captacao_id)

    def marcar_item(self, item_id: str, conferido: bool) -> dict:
        rows = execute(
            self.db.table("captacao_equipamentos")
            .update({"conferido": conferido})
            .eq("id", item_id)
        ).data
        if not rows:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Item do checklist não encontrado")
        return rows[0]

    def _gravar_checklist(self, captacao_id: str, equipamento_ids: list[str]) -> None:
        if not equipamento_ids:
            return
        execute(
            self.db.table("captacao_equipamentos").insert(
                [
                    {
                        "org_id": self.org_id,
                        "captacao_id": captacao_id,
                        "equipamento_id": eid,
                        "conferido": False,
                    }
                    for eid in dict.fromkeys(equipamento_ids)
                ]
            )
        )

    def _endereco_do_imovel(self, imovel_id: str) -> str:
        rows = execute(
            self.db.table("imoveis").select("endereco").eq("id", imovel_id)
        ).data
        return rows[0]["endereco"] if rows else ""
