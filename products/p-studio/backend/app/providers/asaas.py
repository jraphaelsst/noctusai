"""Adapter do Asaas.

**Este é o único arquivo do backend autorizado a conhecer o vocabulário do
Asaas.** `billingType`, `externalReference`, `customer`, `PAYMENT_RECEIVED` e o
header `access_token` não podem aparecer em nenhum service ou router — é assim
que a migração para o Banco do Brasil vira "escrever outro adapter" em vez de
"reescrever o financeiro".

Fatos da API confirmados na documentação oficial e por sondagem do sandbox:

* Autenticação é um header só: `access_token: <chave>`. Sem OAuth, sem mTLS,
  sem certificado. Sondagem sem chave devolve 401 limpo.
* A chave é criada apenas pela interface web, é exibida uma única vez e é
  exclusiva do ambiente. Chave de produção no sandbox devolve 401 com
  `invalid_environment` — verificado contra a API viva em 13/08/2026.
* **Não existe `Idempotency-Key`.** A própria documentação orienta usar
  `externalReference` e consultar antes de reprocessar; é por isso que
  `buscar_por_referencia` existe na interface.
* `PAYMENT_CONFIRMED` (pago, saldo indisponível) e `PAYMENT_RECEIVED` (saldo
  disponível) são eventos distintos. Só o segundo dá baixa aqui.
"""
from datetime import date
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.providers.erros import ErroProvedor
from app.providers.http import ClienteHTTP
from app.providers.tipos import (
    Cobranca,
    ClienteCobranca,
    EventoCobranca,
    PedidoCobranca,
    StatusCobranca,
    TipoEvento,
)

# `status` da cobrança no Asaas → nosso léxico.
_STATUS: dict[str, StatusCobranca] = {
    "PENDING": "pendente",
    "AWAITING_RISK_ANALYSIS": "pendente",
    "APPROVED_BY_RISK_ANALYSIS": "pendente",
    "AUTHORIZED": "pendente",
    "CONFIRMED": "confirmada",
    "RECEIVED": "liquidada",
    "RECEIVED_IN_CASH": "liquidada",
    "OVERDUE": "vencida",
    "REFUNDED": "estornada",
    "PARTIALLY_REFUNDED": "estornada",
    "REFUND_REQUESTED": "estornada",
    "CHARGEBACK_REQUESTED": "estornada",
    "CHARGEBACK_DISPUTE": "estornada",
    "AWAITING_CHARGEBACK_REVERSAL": "estornada",
    "DELETED": "cancelada",
}

# `event` do webhook → nosso léxico. Eventos fora deste mapa devolvem None em
# `interpretar_evento` e o webhook responde 200 sem efeito — nunca erro, que
# derrubaria a fila de entrega.
_EVENTOS: dict[str, TipoEvento] = {
    "PAYMENT_CREATED": "criada",
    "PAYMENT_UPDATED": "criada",
    "PAYMENT_CONFIRMED": "confirmada",
    "PAYMENT_RECEIVED": "liquidada",
    "PAYMENT_RECEIVED_IN_CASH": "liquidada",
    "PAYMENT_OVERDUE": "vencida",
    "PAYMENT_REFUNDED": "estornada",
    "PAYMENT_PARTIALLY_REFUNDED": "estornada",
    "PAYMENT_DELETED": "removida",
}

_FORMAS = {
    "pix": "PIX",
    "boleto": "BOLETO",
    "cartao": "CREDIT_CARD",
    "indefinido": "UNDEFINED",
}

# Volta: `UNDEFINED` vira None de propósito. O CHECK de
# `lancamentos.forma_pagamento` não tem esse valor, e a perda não importa —
# quando o cliente pagar, o Asaas informa a forma real.
_FORMAS_VOLTA = {
    "PIX": "pix",
    "BOLETO": "boleto",
    "CREDIT_CARD": "cartao",
    "DEBIT_CARD": "cartao",
    "UNDEFINED": None,
}


# ── ambiente ─────────────────────────────────────────────────────────────
#
# O ambiente é conceito de primeira classe aqui, e não comentário no
# `.env.example`, por um motivo concreto: uma cobrança criada em produção é um
# boleto real, registrado no nome de um cliente real, com tarifa real. Errar o
# ambiente não é errar um teste — é emitir uma fatura.
#
# São dois sinais independentes, e é justamente por serem independentes que
# comparar os dois vale a pena: o prefixo da chave e o host da URL.

Ambiente = str  # "sandbox" | "producao" | "desconhecido"

_PREFIXOS = {"$aact_prod_": "producao", "$aact_hmlg_": "sandbox"}


def ambiente_da_chave(chave: str) -> Ambiente:
    """Lê o ambiente do prefixo da chave, sem tocar a rede."""
    for prefixo, ambiente in _PREFIXOS.items():
        if chave.startswith(prefixo):
            return ambiente
    return "desconhecido"


def ambiente_da_url(base_url: str) -> Ambiente:
    if "sandbox" in base_url:
        return "sandbox"
    if "api.asaas.com" in base_url:
        return "producao"
    return "desconhecido"


def _para_data(valor: Any) -> Optional[date]:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


class ProvedorAsaas:
    """Implementa `ProvedorCobranca` contra a API v3 do Asaas."""

    nome = "asaas"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api-sandbox.asaas.com/v3",
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = base_url
        self.ambiente = ambiente_da_chave(api_key)

        # Divergência entre chave e URL falha aqui, não na primeira cobrança.
        # A API devolveria 401 `invalid_environment`, mas 401 chegando pelo
        # webhook ou por um job noturno vira mistério; aqui vira uma frase.
        # Só acusa quando os DOIS lados são reconhecidos — se a convenção de
        # prefixo do Asaas mudar, um deployment válido não pode quebrar por
        # causa de uma heurística nossa.
        da_url = ambiente_da_url(base_url)
        if self.ambiente != "desconhecido" and da_url != "desconhecido" \
                and self.ambiente != da_url:
            raise ErroProvedor(
                self.nome,
                f"A chave é de {self.ambiente} e ASAAS_BASE_URL aponta para "
                f"{da_url} ({base_url}). A chave do Asaas é exclusiva do "
                "ambiente — ajuste as duas variáveis juntas.",
                status=500,
            )

        self.http = ClienteHTTP(
            provedor=self.nome,
            base_url=base_url,
            headers={
                "access_token": api_key,
                "Content-Type": "application/json",
                # O Asaas pede identificação do integrador; ajuda o suporte
                # deles a achar nossas chamadas.
                "User-Agent": "p-studio/0.1 (NoctusAI)",
            },
            transport=transport,
        )

    # ── clientes ─────────────────────────────────────────────────────────
    def garantir_cliente(self, cliente: ClienteCobranca) -> Optional[str]:
        """Cria o pagador, reaproveitando se já existir.

        A busca por `externalReference` vem antes do POST porque o Asaas não
        rejeita duplicata: criar duas vezes gera dois clientes com o mesmo
        CPF, e a segunda cobrança sai vinculada ao cadastro errado.
        """
        if not cliente.cpf_cnpj:
            raise ErroProvedor(
                self.nome,
                f"Cliente {cliente.nome!r} está sem CPF/CNPJ — "
                "obrigatório para emitir cobrança.",
                status=422,
            )

        achados = self.http.requisitar(
            "GET", "/customers",
            params={"externalReference": cliente.referencia_externa, "limit": 1},
        )
        dados = achados.get("data") or []
        if dados:
            return dados[0].get("id")

        criado = self.http.requisitar("POST", "/customers", json={
            "name": cliente.nome,
            "cpfCnpj": _digitos(cliente.cpf_cnpj),
            "email": cliente.email,
            "mobilePhone": _digitos(cliente.telefone) if cliente.telefone else None,
            "postalCode": _digitos(cliente.cep) if cliente.cep else None,
            "address": cliente.endereco,
            "province": cliente.bairro,
            "externalReference": cliente.referencia_externa,
            "notificationDisabled": False,
        })
        return criado.get("id")

    # ── cobranças ────────────────────────────────────────────────────────
    def criar_cobranca(self, pedido: PedidoCobranca) -> Cobranca:
        id_pagador = pedido.pagador_no_provedor or self.garantir_cliente(pedido.pagador)

        corpo = {
            "customer": id_pagador,
            "billingType": _FORMAS.get(pedido.forma, "UNDEFINED"),
            "value": float(pedido.valor),
            "dueDate": pedido.vencimento.isoformat(),
            "description": pedido.descricao,
            # A chave de conciliação. Sem ela o webhook chega e não há como
            # saber a qual lançamento pertence.
            "externalReference": pedido.referencia_externa,
        }
        return self._enriquecer(self._para_cobranca(
            self.http.requisitar("POST", "/payments", json=_sem_nulos(corpo))
        ))

    def obter_cobranca(self, id_no_provedor: str) -> Cobranca:
        return self._enriquecer(self._para_cobranca(
            self.http.requisitar("GET", f"/payments/{id_no_provedor}")
        ))

    def buscar_por_referencia(self, referencia: str) -> Optional[Cobranca]:
        resposta = self.http.requisitar(
            "GET", "/payments",
            params={"externalReference": referencia, "limit": 1},
        )
        dados = resposta.get("data") or []
        return self._enriquecer(self._para_cobranca(dados[0])) if dados else None

    # ── enriquecimento ───────────────────────────────────────────────────
    def _enriquecer(self, cobranca: Cobranca) -> Cobranca:
        """Busca linha digitável e pix copia-e-cola, que vêm em OUTRO endpoint.

        Descoberto contra o sandbox real em 13/08/2026: `identificationField` e
        o `payload` do Pix **não existem no objeto da cobrança** — nem na
        resposta do POST, nem na do GET. A versão anterior os lia de
        `dados.get(...)` e devolvia `None` sempre, silenciosamente. O sintoma
        para o usuário seria uma tela de cobrança emitida sem linha digitável
        para copiar, e nada no log dizendo por quê.

        São duas chamadas distintas, uma por forma de pagamento:
          GET /payments/{id}/identificationField  → boleto
          GET /payments/{id}/pixQrCode            → pix (campo `payload`)

        Três limites deliberados:

        * **Não roda no webhook.** `interpretar_evento` não passa por aqui: o
          webhook precisa responder rápido e não pode depender de uma segunda
          chamada de rede para gravar o evento.
        * **Não roda para cobrança encerrada.** Linha digitável de boleto já
          liquidado não serve para nada.
        * **Falha em silêncio, de propósito.** A cobrança foi criada e é
          válida; perder o campo acessório não pode transformar uma emissão
          bem-sucedida em erro. O campo fica `None` e a próxima sincronização
          tenta de novo.
        """
        if cobranca.status in ("liquidada", "confirmada", "estornada", "cancelada"):
            return cobranca
        if not cobranca.id_no_provedor:
            return cobranca

        try:
            if cobranca.forma == "boleto" and not cobranca.linha_digitavel:
                dados = self.http.requisitar(
                    "GET", f"/payments/{cobranca.id_no_provedor}/identificationField"
                )
                cobranca.linha_digitavel = dados.get("identificationField")
            elif cobranca.forma == "pix" and not cobranca.pix_copia_e_cola:
                dados = self.http.requisitar(
                    "GET", f"/payments/{cobranca.id_no_provedor}/pixQrCode"
                )
                cobranca.pix_copia_e_cola = dados.get("payload")
        except ErroProvedor:
            pass

        return cobranca

    def cancelar_cobranca(self, id_no_provedor: str) -> Cobranca:
        self.http.requisitar("DELETE", f"/payments/{id_no_provedor}")
        return self.obter_cobranca(id_no_provedor)

    # ── webhook ──────────────────────────────────────────────────────────
    def interpretar_evento(self, corpo: dict) -> Optional[EventoCobranca]:
        tipo_bruto = str(corpo.get("event") or "")
        tipo = _EVENTOS.get(tipo_bruto)
        if tipo is None:
            return None

        dados = corpo.get("payment")
        if not isinstance(dados, dict):
            return None

        return EventoCobranca(
            id_no_provedor=str(corpo.get("id") or _hash_do_corpo(corpo)),
            tipo=tipo,
            tipo_bruto=tipo_bruto,
            cobranca=self._para_cobranca(dados),
        )

    # ── tradução ─────────────────────────────────────────────────────────
    def _para_cobranca(self, dados: dict) -> Cobranca:
        status_bruto = str(dados.get("status") or "")
        return Cobranca(
            id_no_provedor=str(dados.get("id") or ""),
            pagador_no_provedor=dados.get("customer"),
            referencia_externa=dados.get("externalReference"),
            status=_STATUS.get(status_bruto, "pendente"),
            valor=Decimal(str(dados.get("value") or 0)),
            vencimento=_para_data(dados.get("dueDate")),
            # `paymentDate` é quando o cliente pagou; `clientPaymentDate` é a
            # data informada pelo cliente em recebimento manual. A primeira é
            # a que vale para a nossa competência de caixa.
            pago_em=_para_data(dados.get("paymentDate"))
            or _para_data(dados.get("clientPaymentDate")),
            forma=_FORMAS_VOLTA.get(str(dados.get("billingType") or "")),
            url_fatura=dados.get("invoiceUrl"),
            linha_digitavel=dados.get("identificationField"),
            pix_copia_e_cola=dados.get("payload"),
            bruto=dados,
        )


# ── utilitários ──────────────────────────────────────────────────────────

def _digitos(valor: Optional[str]) -> Optional[str]:
    """CPF/CNPJ/CEP/telefone sem pontuação — o Asaas recusa formatado."""
    if valor is None:
        return None
    return "".join(c for c in str(valor) if c.isdigit()) or None


def _sem_nulos(corpo: dict) -> dict:
    """Remove chaves nulas. Mandar `null` explícito faz o Asaas reclamar em
    campos opcionais que ele preferia não receber."""
    return {k: v for k, v in corpo.items() if v is not None}


def _hash_do_corpo(corpo: dict) -> str:
    """Id determinístico para eventos sem `id`.

    Fallback honesto: o prefixo `sha256:` deixa explícito na tabela que aquele
    id foi calculado por nós, não recebido do provedor.
    """
    import hashlib
    import json

    canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonico.encode("utf-8")).hexdigest()
