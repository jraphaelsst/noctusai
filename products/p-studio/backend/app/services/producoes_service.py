"""Produções — o pipeline de pós e seu histórico append-only.

A spec § 4 pede data/hora, responsável, comentários e histórico de alterações
por etapa. Guardar isso em colunas da produção só registraria o estado atual;
`producao_eventos` registra o que aconteceu. Toda transição grava um evento.
"""
from datetime import date

from app.database import execute
from app.schemas.producoes import ETAPAS
from app.services.base import CrudService


class ProducoesService(CrudService):
    table = "producoes"
    order_by = "updated_at"
    order_desc = True

    def _nao_encontrado(self) -> str:
        return "Produção não encontrada"

    # ── leitura ──────────────────────────────────────────────────────────
    def listar_completo(self) -> list[dict]:
        producoes = self.listar()
        if not producoes:
            return []

        clientes = self._mapa("clientes")
        captacoes = self._mapa("captacoes", "id,endereco")
        return [
            {
                **p,
                "cliente_nome": (clientes.get(p.get("cliente_id")) or {}).get("nome"),
                "endereco": (captacoes.get(p.get("captacao_id")) or {}).get("endereco"),
                "eventos": [],  # a listagem do kanban não carrega histórico
            }
            for p in producoes
        ]

    def obter_completo(self, producao_id: str) -> dict:
        producao = self.obter(producao_id)
        clientes = self._mapa("clientes")
        captacoes = self._mapa("captacoes", "id,endereco")
        eventos = execute(
            self.db.table("producao_eventos")
            .select("*")
            .eq("producao_id", producao_id)
            .order("created_at", desc=True)
        ).data or []
        return {
            **producao,
            "cliente_nome": (clientes.get(producao.get("cliente_id")) or {}).get("nome"),
            "endereco": (captacoes.get(producao.get("captacao_id")) or {}).get("endereco"),
            "eventos": eventos,
        }

    # ── transições ───────────────────────────────────────────────────────
    def mudar_etapa(
        self,
        producao_id: str,
        etapa: str,
        responsavel: str | None = None,
        comentario: str | None = None,
    ) -> dict:
        producao = self.obter(producao_id)
        anterior = producao["etapa"]

        changes: dict = {"etapa": etapa}
        if responsavel:
            changes["responsavel"] = responsavel
        # `entregue_em` alimenta o prazo médio do dashboard. Só é carimbado na
        # primeira vez: reentrar na etapa não deve reescrever a data real da
        # entrega.
        if etapa == "entregue" and not producao.get("entregue_em"):
            changes["entregue_em"] = date.today().isoformat()

        self.atualizar(producao_id, changes)
        self._registrar_evento(
            producao_id,
            etapa=etapa,
            tipo="transicao",
            responsavel=responsavel,
            comentario=comentario or f"{self._label(anterior)} → {self._label(etapa)}",
        )
        return self.obter_completo(producao_id)

    def comentar(
        self, producao_id: str, comentario: str, responsavel: str | None = None
    ) -> dict:
        producao = self.obter(producao_id)
        self._registrar_evento(
            producao_id,
            etapa=producao["etapa"],
            tipo="comentario",
            responsavel=responsavel,
            comentario=comentario,
        )
        return self.obter_completo(producao_id)

    def _registrar_evento(
        self,
        producao_id: str,
        *,
        etapa: str,
        tipo: str,
        responsavel: str | None,
        comentario: str | None,
    ) -> None:
        execute(
            self.db.table("producao_eventos").insert(
                {
                    "org_id": self.org_id,
                    "producao_id": producao_id,
                    "etapa": etapa,
                    "tipo": tipo,
                    "responsavel": responsavel,
                    "comentario": comentario,
                }
            )
        )

    @staticmethod
    def _label(etapa: str) -> str:
        from app.schemas.producoes import ETAPA_LABELS

        return ETAPA_LABELS.get(etapa, etapa)

    @staticmethod
    def ordem(etapa: str) -> int:
        return ETAPAS.index(etapa) if etapa in ETAPAS else -1
