"""Cadastros sem regra própria: clientes, imóveis, serviços, equipamentos.

Só imóveis tem uma regra — a geração do código interno (PS-001, PS-002…) —
e ela vive aqui em vez de no router.
"""
import re

from app.database import execute
from app.services.base import CrudService


class ClientesService(CrudService):
    table = "clientes"
    order_by = "nome"
    order_desc = False
    soft_delete = True

    def _nao_encontrado(self) -> str:
        return "Cliente não encontrado"


class ServicosService(CrudService):
    table = "servicos"
    order_by = "nome"
    order_desc = False
    soft_delete = True

    def _nao_encontrado(self) -> str:
        return "Serviço não encontrado"


class EquipamentosService(CrudService):
    table = "equipamentos"
    order_by = "nome"
    order_desc = False
    soft_delete = True

    def _nao_encontrado(self) -> str:
        return "Equipamento não encontrado"


class ImoveisService(CrudService):
    table = "imoveis"
    order_by = "codigo"
    order_desc = False

    def _nao_encontrado(self) -> str:
        return "Imóvel não encontrado"

    def criar(self, payload: dict) -> dict:
        if not payload.get("codigo"):
            payload = {**payload, "codigo": self.proximo_codigo()}
        return super().criar(payload)

    def proximo_codigo(self) -> str:
        """Próximo código interno no formato PS-NNN.

        Lê o maior sufixo numérico existente em vez de contar linhas: contar
        reaproveitaria um código depois de qualquer exclusão, e o código
        interno é a referência que o estúdio usa com o cliente — não pode
        apontar para dois imóveis diferentes ao longo do tempo.

        A unicidade real é garantida pelo `UNIQUE (org_id, codigo)`; se duas
        criações simultâneas escolherem o mesmo número, a segunda recebe 409.
        """
        rows = execute(self.db.table(self.table).select("codigo")).data or []
        maior = 0
        for row in rows:
            match = re.fullmatch(r"PS-(\d+)", (row.get("codigo") or "").strip())
            if match:
                maior = max(maior, int(match.group(1)))
        return f"PS-{maior + 1:03d}"
