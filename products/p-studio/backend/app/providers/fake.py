"""Provedor em memória — o equivalente do `FakeDB` para cobrança.

Vive em `app/` e não em `tests/` de propósito: é a implementação de referência
da interface. Se ele deixa de satisfazer o `Protocol`, o mypy/pyright acusa
antes de qualquer adapter real quebrar, e quem for escrever o adapter do Banco
do Brasil tem aqui o exemplo mínimo do contrato.

Não fala HTTP. Os testes de rota e de webhook usam este; os testes de contrato
do Asaas usam o adapter real com tráfego gravado.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from app.providers.tipos import (
    Cobranca,
    ClienteCobranca,
    EventoCobranca,
    PedidoCobranca,
)


class ProvedorFake:
    """Guarda tudo em dicionários e devolve dados plausíveis."""

    nome = "fake"

    def __init__(self) -> None:
        self.clientes: dict[str, ClienteCobranca] = {}
        self.cobrancas: dict[str, Cobranca] = {}
        # Registro das chamadas, para os testes afirmarem sobre a intenção
        # e não só sobre o resultado.
        self.chamadas: list[tuple[str, object]] = []
        self._seq = 0

    # ── helpers de teste ─────────────────────────────────────────────────
    def _proximo_id(self, prefixo: str) -> str:
        self._seq += 1
        return f"{prefixo}_{self._seq:06d}"

    def marcar_liquidada(self, id_no_provedor: str, pago_em: date) -> Cobranca:
        """Simula o pagamento, para o teste não precisar montar o objeto."""
        cobranca = self.cobrancas[id_no_provedor].model_copy(
            update={"status": "liquidada", "pago_em": pago_em}
        )
        self.cobrancas[id_no_provedor] = cobranca
        return cobranca

    # ── ProvedorCobranca ─────────────────────────────────────────────────
    def garantir_cliente(self, cliente: ClienteCobranca) -> Optional[str]:
        self.chamadas.append(("garantir_cliente", cliente))
        for id_provedor, existente in self.clientes.items():
            if existente.referencia_externa == cliente.referencia_externa:
                return id_provedor
        id_provedor = self._proximo_id("cus")
        self.clientes[id_provedor] = cliente
        return id_provedor

    def criar_cobranca(self, pedido: PedidoCobranca) -> Cobranca:
        self.chamadas.append(("criar_cobranca", pedido))
        id_pagador = pedido.pagador_no_provedor or self.garantir_cliente(pedido.pagador)
        id_provedor = self._proximo_id("pay")
        cobranca = Cobranca(
            id_no_provedor=id_provedor,
            pagador_no_provedor=id_pagador,
            referencia_externa=pedido.referencia_externa,
            status="pendente",
            valor=pedido.valor,
            vencimento=pedido.vencimento,
            forma=pedido.forma,
            url_fatura=f"https://fake.local/i/{id_provedor}",
            linha_digitavel=("34191" + id_provedor[-6:].rjust(6, "0")) * 2,
            pix_copia_e_cola=f"00020126fake{id_provedor}",
            bruto={"id": id_provedor, "provedor": "fake"},
        )
        self.cobrancas[id_provedor] = cobranca
        return cobranca

    def obter_cobranca(self, id_no_provedor: str) -> Cobranca:
        self.chamadas.append(("obter_cobranca", id_no_provedor))
        return self.cobrancas[id_no_provedor]

    def buscar_por_referencia(self, referencia: str) -> Optional[Cobranca]:
        self.chamadas.append(("buscar_por_referencia", referencia))
        for cobranca in self.cobrancas.values():
            if cobranca.referencia_externa == referencia:
                return cobranca
        return None

    def cancelar_cobranca(self, id_no_provedor: str) -> Cobranca:
        self.chamadas.append(("cancelar_cobranca", id_no_provedor))
        cobranca = self.cobrancas[id_no_provedor].model_copy(
            update={"status": "cancelada"}
        )
        self.cobrancas[id_no_provedor] = cobranca
        return cobranca

    def interpretar_evento(self, corpo: dict) -> Optional[EventoCobranca]:
        """Formato de evento próprio do fake — não imita o do Asaas.

        Imitar o corpo de um provedor real aqui seria vazamento: este arquivo
        estaria codificando o formato do Asaas fora do adapter dele, e o teste
        de vazamento (`grep` por `externalReference` etc.) passaria a acusar.
        Quem quiser exercitar o corpo real do Asaas usa o adapter do Asaas com
        fixture gravada.
        """
        self.chamadas.append(("interpretar_evento", corpo))
        mapa = {
            "criada": "criada",
            "confirmada": "confirmada",
            "liquidada": "liquidada",
            "vencida": "vencida",
        }
        tipo_bruto = str(corpo.get("tipo") or "")
        tipo = mapa.get(tipo_bruto)
        if tipo is None:
            return None

        dados = corpo.get("cobranca") or {}
        pago_em = dados.get("pago_em")
        return EventoCobranca(
            id_no_provedor=corpo.get("id") or "evt_fake",
            tipo=tipo,  # type: ignore[arg-type]
            tipo_bruto=tipo_bruto,
            cobranca=Cobranca(
                id_no_provedor=dados.get("id") or "pay_fake",
                referencia_externa=dados.get("referencia_externa"),
                status="liquidada" if tipo == "liquidada" else "pendente",
                valor=Decimal(str(dados.get("valor") or 0)),
                pago_em=date.fromisoformat(pago_em) if pago_em else None,
                bruto=corpo,
            ),
        )
