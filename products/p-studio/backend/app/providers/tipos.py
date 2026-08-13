"""Vocabulário de cobrança do P Studio — independente de provedor.

Este arquivo é a fronteira. Nada daqui para dentro do app pode saber que o
provedor de hoje é o Asaas; nada daqui para fora pode falar `billingType`,
`externalReference` ou `PAYMENT_RECEIVED`. O teste é literal:

    grep -rE "billingType|externalReference|PAYMENT_|access_token" app/

só pode acusar `app/providers/asaas.py`. Se aparecer em service ou router, o
vazamento já aconteceu.

Isso importa porque a produção vai ser **Banco do Brasil**, não Asaas. O Asaas
é a casca que destrava o ERP agora. Se a abstração vazar formato Asaas, a
migração vira reescrita em vez de um adapter novo.

Por que `Protocol` e não ABC: o fake de teste não precisa herdar de nada, o
que mantém o override de `Depends` numa linha. E o que as implementações
realmente compartilham é encanamento HTTP, não semântica de domínio — então
compartilha-se por composição (`ClienteHTTP`), não por herança.
"""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional, Protocol

from pydantic import BaseModel

# ── Vocabulário ──────────────────────────────────────────────────────────

# `confirmada` e `liquidada` são distintas de propósito. O Asaas separa
# PAYMENT_CONFIRMED (pago, saldo ainda indisponível) de PAYMENT_RECEIVED
# (saldo disponível); boleto D+1 no BB tem exatamente a mesma forma. Colapsar
# as duas é a maneira mais provável de contabilizar receita que ainda não
# entrou — só `liquidada` vira status='recebido' no lançamento.
StatusCobranca = Literal[
    "pendente",    # registrada, aguardando pagamento
    "confirmada",  # paga, saldo ainda não disponível
    "liquidada",   # paga e disponível — só esta dá baixa
    "vencida",
    "estornada",
    "cancelada",
]

FormaCobranca = Literal["pix", "boleto", "cartao", "indefinido"]

TipoEvento = Literal[
    "criada", "confirmada", "liquidada",
    "vencida", "estornada", "removida", "outro",
]


# ── Modelos ──────────────────────────────────────────────────────────────

class ClienteCobranca(BaseModel):
    """O pagador, como o provedor precisa conhecê-lo.

    Os campos de endereço nascem opcionais porque o Asaas os ignora, mas o
    bloco `pagador` do Banco do Brasil exige endereço completo. Deixá-los
    prontos agora evita mexer na interface no dia do BB — e o adapter do BB
    falha com erro de domínio dizendo qual campo falta, em vez de repassar um
    400 críptico do banco.
    """

    referencia_externa: str          # clientes.id
    nome: str
    cpf_cnpj: str                    # só dígitos
    email: Optional[str] = None
    telefone: Optional[str] = None
    cep: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None


class PedidoCobranca(BaseModel):
    """O que o P Studio quer cobrar. Sem vocabulário de provedor."""

    referencia_externa: str          # lancamentos.id — a chave de conciliação
    pagador: ClienteCobranca
    # Redundância deliberada: o Asaas usa o id em cache, o BB não tem objeto
    # cliente e monta o pagador inline a partir do registro completo. Levar os
    # dois evita um round-trip e evita inventar uma porta de cache.
    pagador_no_provedor: Optional[str] = None
    valor: Decimal
    vencimento: date
    forma: FormaCobranca = "indefinido"
    descricao: Optional[str] = None


class Cobranca(BaseModel):
    """A cobrança como o provedor a devolveu, traduzida para o nosso léxico."""

    id_no_provedor: str
    pagador_no_provedor: Optional[str] = None
    referencia_externa: Optional[str] = None
    status: StatusCobranca
    valor: Decimal
    vencimento: Optional[date] = None
    pago_em: Optional[date] = None
    forma: Optional[str] = None
    url_fatura: Optional[str] = None
    linha_digitavel: Optional[str] = None
    pix_copia_e_cola: Optional[str] = None
    # Payload cru. Vai para `provedor_eventos.payload` e para diagnóstico —
    # o log é forense, e guardar só o normalizado destrói a capacidade de
    # responder "o que eles mandaram, afinal?".
    bruto: dict = {}


class EventoCobranca(BaseModel):
    """Notificação do provedor, já normalizada."""

    id_no_provedor: str              # evt_… ou sha256:<hex>
    tipo: TipoEvento
    tipo_bruto: str                  # PAYMENT_RECEIVED etc — guardado cru
    cobranca: Cobranca


# ── A interface ──────────────────────────────────────────────────────────

class ProvedorCobranca(Protocol):
    """Recebíveis. Uma família, não uma classe-deus.

    `ProvedorExtrato` (leitura para conciliação) e `ProvedorPagamento`
    (pagamentos, com `preparar()` e `autorizar()` separados) são interfaces
    irmãs, ainda não construídas. Estão separadas porque misturam classes de
    risco diferentes: ler extrato não é mover dinheiro, e a autorização de
    pagamento nunca deve virar ferramenta de agente.
    """

    nome: str

    def garantir_cliente(self, cliente: ClienteCobranca) -> Optional[str]:
        """Cria ou recupera o pagador; devolve o id no provedor.

        `None` é resposta legítima: o BB não tem objeto cliente — o pagador vai
        inline em cada boleto.
        """
        ...

    def criar_cobranca(self, pedido: PedidoCobranca) -> Cobranca:
        ...

    def obter_cobranca(self, id_no_provedor: str) -> Cobranca:
        ...

    def buscar_por_referencia(self, referencia: str) -> Optional[Cobranca]:
        """Idempotência de saída, não conveniência.

        O Asaas não tem `Idempotency-Key` — a própria documentação manda usar
        `externalReference` e consultar antes de reprocessar. Para o BB o
        equivalente é consultar pelo nosso número antes de registrar de novo.
        """
        ...

    def cancelar_cobranca(self, id_no_provedor: str) -> Cobranca:
        ...

    def interpretar_evento(self, corpo: dict) -> Optional[EventoCobranca]:
        """Traduz o webhook cru. `None` = evento que não nos interessa.

        Fica no provedor para o router não crescer um `if PAYMENT_RECEIVED`.
        Sem isto a abstração seria decorativa.
        """
        ...
