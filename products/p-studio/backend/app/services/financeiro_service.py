"""Financeiro — lançamentos e o resumo da tela.

`atrasado` é derivado, não armazenado: um lançamento faturado cujo vencimento
passou está atrasado *agora*, sem depender de um job noturno ter rodado. O
banco guarda quatro status; a API expõe cinco.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException

from app.database import execute
from app.providers.tipos import (
    ClienteCobranca,
    FormaCobranca,
    PedidoCobranca,
    ProvedorCobranca,
)
from app.services.base import CrudService


# Status a partir dos quais um lançamento pode ser liquidado. `recebido` já
# está liquidado e `cancelado` não deve ser — nem pelo funil, nem pelo banco.
BAIXAVEIS = ("a_faturar", "faturado")


def _agora() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def registrar_recebimento(
    db,
    lancamento: dict,
    pago_em: date | None = None,
    forma_pagamento: str | None = None,
) -> bool:
    """Transição única para `recebido`. Devolve False se não fez nada.

    Existem três caminhos que liquidam um lançamento — a baixa manual, o funil
    comercial (quando o negócio chega em `recebido`) e o webhook do provedor de
    cobrança. Os três passam por aqui, e a razão é `pago_em`.

    Reexecutar uma baixa reescrevia `pago_em`. Como `resumo()`,
    `_faturamento_mes` e `_receita_por_mes` todos chaveiam nessa data quando o
    status é `recebido`, uma segunda baixa movia receita de mês sem deixar
    rastro. Aqui o primeiro a liquidar vence: quem chegar depois recebe False e
    não toca em nada.

    Também não é `CrudService.atualizar`, que levanta 404 quando não acha a
    linha. O webhook não pode levantar — o Asaas interrompe a fila de entrega
    depois de 15 respostas não-2xx seguidas.
    """
    if lancamento.get("status") not in BAIXAVEIS:
        return False

    changes: dict = {
        "status": "recebido",
        "pago_em": (pago_em or date.today()).isoformat(),
    }
    if forma_pagamento:
        changes["forma_pagamento"] = forma_pagamento

    execute(db.table("lancamentos").update(changes).eq("id", lancamento["id"]))
    return True


def status_exibido(lancamento: dict, hoje: date | None = None) -> str:
    """Status armazenado + o `atrasado` derivado."""
    status = lancamento.get("status") or "a_faturar"
    if status not in ("a_faturar", "faturado"):
        return status
    vencimento = lancamento.get("vencimento")
    if not vencimento:
        return status
    if isinstance(vencimento, str):
        vencimento = date.fromisoformat(vencimento[:10])
    return "atrasado" if vencimento < (hoje or date.today()) else status


class FinanceiroService(CrudService):
    table = "lancamentos"
    order_by = "vencimento"
    order_desc = False

    def __init__(self, db, org_id: str, provedor: Optional[ProvedorCobranca] = None):
        """`provedor` é opcional para os ~8 call sites que só leem lançamentos
        não precisarem mudar — e para que uma integração mal configurada não
        derrube a tela do financeiro inteira, só a emissão de cobrança."""
        super().__init__(db, org_id)
        self._prov = provedor

    def _provedor(self) -> ProvedorCobranca:
        if self._prov is None:
            raise HTTPException(
                status_code=503,
                detail="Nenhum provedor de cobrança configurado nesta rota.",
            )
        return self._prov

    def _nao_encontrado(self) -> str:
        return "Lançamento não encontrado"

    # ── leitura ──────────────────────────────────────────────────────────
    def listar_completo(self, status: str | None = None) -> list[dict]:
        lancamentos = self.listar()
        clientes = self._mapa("clientes")

        enriquecidos = [
            {
                **l,
                "valor": float(l.get("valor") or 0),
                "status_exibido": status_exibido(l),
                "cliente_nome": (clientes.get(l.get("cliente_id")) or {}).get("nome"),
            }
            for l in lancamentos
        ]
        if status:
            # Filtra pelo status EXIBIDO — quem pede "atrasado" quer os
            # derivados, que no banco estão gravados como `faturado`.
            enriquecidos = [l for l in enriquecidos if l["status_exibido"] == status]
        return enriquecidos

    def obter_completo(self, lancamento_id: str) -> dict:
        lancamento = self.obter(lancamento_id)
        clientes = self._mapa("clientes")
        return {
            **lancamento,
            "valor": float(lancamento.get("valor") or 0),
            "status_exibido": status_exibido(lancamento),
            "cliente_nome": (clientes.get(lancamento.get("cliente_id")) or {}).get("nome"),
        }

    # ── escrita ──────────────────────────────────────────────────────────
    def dar_baixa(
        self, lancamento_id: str, pago_em: date | None, forma_pagamento: str | None
    ) -> dict:
        """Baixa manual. 404 se o lançamento não existe; silenciosa se já
        estava liquidado — a resposta devolve o estado atual de qualquer forma."""
        lancamento = self.obter(lancamento_id)
        registrar_recebimento(self.db, lancamento, pago_em, forma_pagamento)
        return self.obter_completo(lancamento_id)

    # ── cobrança no provedor ─────────────────────────────────────────────
    def emitir_cobranca(
        self, lancamento_id: str, forma: FormaCobranca = "indefinido"
    ) -> dict:
        """Emite a cobrança do lançamento no provedor e grava o espelho.

        Idempotente por dois mecanismos independentes, porque o Asaas não tem
        `Idempotency-Key` e emitir boleto duas vezes é visível para o cliente:

        1. Se já existe `provedor_cobranca_id` na linha, devolve como está.
        2. Se não existe localmente mas o provedor já conhece a nossa
           referência (uma emissão anterior cujo commit não completou),
           adota a cobrança existente em vez de criar outra.

        A UNIQUE (provedor, provedor_cobranca_id) da migração 003 é a terceira
        rede, no banco.
        """
        lancamento = self.obter(lancamento_id)

        if lancamento.get("provedor_cobranca_id"):
            return self.obter_completo(lancamento_id)

        if lancamento.get("status") == "recebido":
            raise HTTPException(400, "Lançamento já recebido — nada a cobrar.")
        if lancamento.get("status") == "cancelado":
            raise HTTPException(400, "Lançamento cancelado — nada a cobrar.")

        provedor = self._provedor()
        cliente = self._pagador(lancamento)

        cobranca = provedor.buscar_por_referencia(lancamento_id)
        if cobranca is None:
            if not lancamento.get("vencimento"):
                raise HTTPException(
                    400, "Lançamento sem vencimento — obrigatório para cobrar."
                )
            cobranca = provedor.criar_cobranca(PedidoCobranca(
                referencia_externa=lancamento_id,
                pagador=cliente,
                pagador_no_provedor=self._pagador_no_provedor(lancamento, provedor.nome),
                valor=Decimal(str(lancamento.get("valor") or 0)),
                vencimento=date.fromisoformat(str(lancamento["vencimento"])[:10]),
                forma=forma,
                descricao=lancamento.get("descricao"),
            ))

        self.atualizar(lancamento_id, {
            "provedor": provedor.nome,
            "provedor_cobranca_id": cobranca.id_no_provedor,
            "provedor_status": cobranca.status,
            "url_fatura": cobranca.url_fatura,
            "linha_digitavel": cobranca.linha_digitavel,
            "pix_copia_e_cola": cobranca.pix_copia_e_cola,
            "sincronizado_em": _agora(),
            # Emitir a cobrança é o ato de faturar. Só promove quem ainda
            # estava `a_faturar` — não rebaixa nada.
            **({"status": "faturado"} if lancamento.get("status") == "a_faturar" else {}),
        })

        # O id do pagador no provedor é caro de redescobrir (uma busca por
        # requisição), então fica em cache no cliente.
        if cobranca.pagador_no_provedor and lancamento.get("cliente_id"):
            execute(
                self.db.table("clientes")
                .update({
                    "provedor": provedor.nome,
                    "provedor_cliente_id": cobranca.pagador_no_provedor,
                })
                .eq("id", lancamento["cliente_id"])
            )

        return self.obter_completo(lancamento_id)

    def _pagador(self, lancamento: dict) -> ClienteCobranca:
        """Monta o pagador a partir do cadastro, falhando com mensagem útil.

        O erro precisa dizer QUAL campo falta: sem isso o usuário recebe um
        400 do banco em inglês e abre chamado.
        """
        clientes = self._mapa("clientes", "*")
        cliente = clientes.get(lancamento.get("cliente_id"))
        if cliente is None:
            raise HTTPException(400, "Lançamento sem cliente — não há quem cobrar.")
        if not cliente.get("cpf_cnpj"):
            raise HTTPException(
                400,
                f"Cliente {cliente.get('nome')!r} está sem CPF/CNPJ. "
                "Preencha o documento no cadastro antes de emitir cobrança.",
            )
        return ClienteCobranca(
            referencia_externa=cliente["id"],
            nome=cliente["nome"],
            cpf_cnpj=cliente["cpf_cnpj"],
            email=cliente.get("email"),
            telefone=cliente.get("telefone"),
            cep=cliente.get("cep"),
            endereco=cliente.get("endereco"),
            bairro=cliente.get("bairro"),
            cidade=cliente.get("cidade"),
            uf=cliente.get("estado"),
        )

    def _pagador_no_provedor(self, lancamento: dict, provedor: str) -> Optional[str]:
        cliente = self._mapa("clientes", "*").get(lancamento.get("cliente_id")) or {}
        if cliente.get("provedor") == provedor:
            return cliente.get("provedor_cliente_id")
        return None

    def sincronizar_cobranca(self, lancamento_id: str) -> dict:
        """Reconsulta o provedor. Existe porque o BB concilia por consulta, não
        por webhook — então este é o caminho que a migração vai usar."""
        lancamento = self.obter(lancamento_id)
        id_no_provedor = lancamento.get("provedor_cobranca_id")
        if not id_no_provedor:
            raise HTTPException(400, "Lançamento sem cobrança emitida.")

        cobranca = self._provedor().obter_cobranca(id_no_provedor)
        changes: dict = {
            "provedor_status": cobranca.status,
            "sincronizado_em": _agora(),
        }
        if cobranca.linha_digitavel:
            changes["linha_digitavel"] = cobranca.linha_digitavel
        self.atualizar(lancamento_id, changes)

        if cobranca.status == "liquidada":
            registrar_recebimento(
                self.db, lancamento, cobranca.pago_em, cobranca.forma
            )
        return self.obter_completo(lancamento_id)

    # ── resumo ───────────────────────────────────────────────────────────
    def resumo(self) -> dict:
        hoje = date.today()
        lancamentos = self.listar()

        total = recebido = em_aberto = atrasado = 0.0
        receita_mes = receita_ano = 0.0
        inadimplentes: set[str] = set()
        recebidos_qtd = 0

        for l in lancamentos:
            valor = float(l.get("valor") or 0)
            exibido = status_exibido(l, hoje)

            if exibido == "cancelado":
                continue

            total += valor

            if exibido == "recebido":
                recebido += valor
                recebidos_qtd += 1
                pago = l.get("pago_em")
                if pago:
                    pago_date = date.fromisoformat(pago[:10]) if isinstance(pago, str) else pago
                    if pago_date.year == hoje.year:
                        receita_ano += valor
                        if pago_date.month == hoje.month:
                            receita_mes += valor
            elif exibido == "atrasado":
                atrasado += valor
                em_aberto += valor
                if l.get("cliente_id"):
                    inadimplentes.add(l["cliente_id"])
            else:  # a_faturar | faturado dentro do prazo
                em_aberto += valor

        return {
            "faturamento_total": round(total, 2),
            "recebido": round(recebido, 2),
            "em_aberto": round(em_aberto, 2),
            "atrasado": round(atrasado, 2),
            "receita_mes": round(receita_mes, 2),
            "receita_ano": round(receita_ano, 2),
            "ticket_medio": round(recebido / recebidos_qtd, 2) if recebidos_qtd else 0.0,
            "clientes_inadimplentes": len(inadimplentes),
        }

    def receita_por_cliente(self) -> list[dict]:
        clientes = self._mapa("clientes")
        acumulado: dict[str, float] = {}
        for l in self.listar():
            if status_exibido(l) == "recebido" and l.get("cliente_id"):
                acumulado[l["cliente_id"]] = acumulado.get(l["cliente_id"], 0) + float(
                    l.get("valor") or 0
                )
        return sorted(
            (
                {
                    "cliente_id": cid,
                    "nome": (clientes.get(cid) or {}).get("nome"),
                    "valor": round(v, 2),
                }
                for cid, v in acumulado.items()
            ),
            key=lambda r: r["valor"],
            reverse=True,
        )
