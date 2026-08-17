"""Testes contra a API viva do Asaas. Fora da execução padrão.

    ASAAS_API_KEY='$aact_...' ./venv/bin/pytest -m ao_vivo

Existem por um motivo específico: **suíte de replay apodrece em silêncio.** O
provedor muda a resposta, as fixtures continuam iguais, os testes seguem
verdes e passam a mentir. Estes testes são o detector disso.

Por isso eles checam **deriva de schema, não regra de negócio** — o conjunto
de chaves e os tipos dos campos que o adapter lê. Um teste ao vivo que
reafirma comportamento de negócio quebra quando alguém mexe nos dados de teste
da conta de sandbox, e aí é desligado por todo mundo em duas semanas.

Não há bomba-relógio por idade de fixture: ela dispara numa terça-feira por
motivo alheio à mudança em curso e ensina a ignorar o alarme. Regravar as
fixtures fica no ritual de release, no README.

── Leitura e escrita são separadas ───────────────────────────────────────

Este arquivo nasceu supondo sandbox, onde `criar_cobranca` não custa nada.
Contra chave de produção, o mesmo teste emite um boleto real, com tarifa, no
nome de um pagador real, e dispara notificação. Um teste não pode fazer isso
por acidente — então os que escrevem **pulam sozinhos em produção**, e só
rodam com uma variável explícita:

    ASAAS_PERMITIR_ESCRITA=1 ./venv/bin/pytest -m ao_vivo

Os que só leem rodam em qualquer ambiente, e são a maior parte do valor: é
leitura que detecta deriva de schema nos campos que o adapter traduz.
"""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.providers.asaas import ProvedorAsaas, ambiente_da_chave
from app.providers.erros import ErroProvedor
from app.providers.tipos import ClienteCobranca, PedidoCobranca

CHAVE = os.environ.get("ASAAS_API_KEY", "")
AMBIENTE = ambiente_da_chave(CHAVE) if CHAVE else "desconhecido"

URLS = {
    "sandbox": "https://api-sandbox.asaas.com/v3",
    "producao": "https://api.asaas.com/v3",
}

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(
        not CHAVE,
        reason="ASAAS_API_KEY não definida — gere a chave em sandbox.asaas.com",
    ),
]

# A trava de escrita. Em sandbox, liberada; em produção, exige consentimento.
escreve = pytest.mark.skipif(
    AMBIENTE == "producao" and os.environ.get("ASAAS_PERMITIR_ESCRITA") != "1",
    reason=(
        "chave de produção: criar cobrança emitiria fatura real. "
        "Rode com ASAAS_PERMITIR_ESCRITA=1 se for mesmo a intenção."
    ),
)

REF_CLIENTE = "ao-vivo-cliente-p-studio"


@pytest.fixture(scope="module")
def provedor() -> ProvedorAsaas:
    return ProvedorAsaas(
        api_key=CHAVE,
        base_url=os.environ.get("ASAAS_BASE_URL")
        or URLS.get(AMBIENTE, URLS["sandbox"]),
    )


@pytest.fixture(scope="module")
def cliente_no_provedor(provedor: ProvedorAsaas) -> str:
    return provedor.garantir_cliente(ClienteCobranca(
        referencia_externa=REF_CLIENTE,
        nome="Imobiliária Ao Vivo Ltda",
        cpf_cnpj="34028316000103",
        email="aovivo@exemplo.com.br",
    ))


# ── leitura: seguros em qualquer ambiente ────────────────────────────────

def test_credencial_valida(provedor: ProvedorAsaas):
    """Falha cedo e com mensagem clara se a chave não servir para esta URL."""
    try:
        provedor.buscar_por_referencia("sonda-inexistente")
    except ErroProvedor as e:
        if e.status == 401:
            pytest.fail(
                f"ASAAS_API_KEY rejeitada ({e.codigo}). A chave é exclusiva do "
                f"ambiente: esta é de {AMBIENTE} e a base é {provedor.base_url}."
            )
        raise


def test_busca_sem_resultado_devolve_none(provedor: ProvedorAsaas):
    """O caminho vazio de `buscar_por_referencia`, que é o pré-check de
    idempotência da emissão. Se ele passar a levantar em vez de devolver None,
    nenhuma cobrança é emitida — e só se descobre em produção."""
    assert provedor.buscar_por_referencia("nao-existe-mesmo-p-studio") is None


def test_listagem_traz_o_envelope_que_o_adapter_espera(provedor: ProvedorAsaas):
    """`garantir_cliente` e `buscar_por_referencia` leem `data` desta forma."""
    resposta = provedor.http.requisitar("GET", "/payments", params={"limit": 1})
    assert resposta.get("object") == "list"
    assert isinstance(resposta.get("data"), list)
    assert "hasMore" in resposta


def test_cobranca_inexistente_da_404(provedor: ProvedorAsaas):
    """404 com corpo VAZIO — verificado contra a API viva. A tradução de erro
    precisa aguentar isso sem estourar ao tentar ler JSON."""
    with pytest.raises(ErroProvedor) as exc:
        provedor.obter_cobranca("pay_000000000000")
    assert exc.value.status == 404
    assert exc.value.mensagem  # nunca vazio, mesmo sem corpo


def test_chave_no_ambiente_errado_e_401(provedor: ProvedorAsaas):
    """O erro mais provável de acontecer de verdade — trocar de ambiente é
    trocar duas variáveis, e esquecer uma é fácil."""
    oposto = "sandbox" if AMBIENTE == "producao" else "producao"
    errado = ProvedorAsaas.__new__(ProvedorAsaas)  # pula o guard do construtor
    from app.providers.http import ClienteHTTP

    errado.http = ClienteHTTP(
        provedor="asaas", base_url=URLS[oposto],
        headers={"access_token": CHAVE},
    )
    with pytest.raises(ErroProvedor) as exc:
        errado.http.requisitar("GET", "/customers", params={"limit": 1})
    assert exc.value.status == 401
    assert exc.value.codigo == "invalid_environment"


# ── escrita: pulam em produção ───────────────────────────────────────────

@escreve
def test_criar_cobranca_devolve_os_campos_que_o_adapter_le(
    provedor: ProvedorAsaas, cliente_no_provedor: str
):
    """Deriva de schema: o adapter lê estes campos, eles precisam existir."""
    cobranca = provedor.criar_cobranca(PedidoCobranca(
        referencia_externa=f"ao-vivo-{date.today().isoformat()}",
        pagador=ClienteCobranca(
            referencia_externa=REF_CLIENTE,
            nome="Imobiliária Ao Vivo Ltda",
            cpf_cnpj="34028316000103",
        ),
        pagador_no_provedor=cliente_no_provedor,
        valor=Decimal("1800.00"),
        vencimento=date.today() + timedelta(days=7),
        forma="boleto",
        descricao="Sonda de contrato — pode ser removida",
    ))

    assert cobranca.id_no_provedor
    assert cobranca.status == "pendente"
    assert cobranca.valor == Decimal("1800.00")
    assert cobranca.referencia_externa
    assert cobranca.url_fatura, "invoiceUrl sumiu da resposta"

    # Chaves cruas que a tradução depende — se qualquer uma sumir, o adapter
    # passa a devolver None em silêncio.
    for chave in ("id", "status", "value", "dueDate", "billingType",
                  "externalReference", "customer", "invoiceUrl"):
        assert chave in cobranca.bruto, f"campo {chave!r} sumiu da API"


@escreve
def test_boleto_traz_linha_digitavel(
    provedor: ProvedorAsaas, cliente_no_provedor: str
):
    cobranca = provedor.criar_cobranca(PedidoCobranca(
        referencia_externa=f"ao-vivo-boleto-{date.today().isoformat()}",
        pagador=ClienteCobranca(
            referencia_externa=REF_CLIENTE, nome="Imobiliária Ao Vivo Ltda",
            cpf_cnpj="34028316000103",
        ),
        pagador_no_provedor=cliente_no_provedor,
        valor=Decimal("100.00"),
        vencimento=date.today() + timedelta(days=10),
        forma="boleto",
    ))
    obtida = provedor.obter_cobranca(cobranca.id_no_provedor)
    assert obtida.linha_digitavel, "identificationField sumiu"


@escreve
def test_busca_por_referencia_encontra_o_que_acabamos_de_criar(
    provedor: ProvedorAsaas, cliente_no_provedor: str
):
    """É o mecanismo de idempotência de saída — se o filtro parar de
    funcionar, passamos a emitir cobrança duplicada."""
    referencia = f"ao-vivo-idem-{date.today().isoformat()}"
    criada = provedor.criar_cobranca(PedidoCobranca(
        referencia_externa=referencia,
        pagador=ClienteCobranca(
            referencia_externa=REF_CLIENTE, nome="Imobiliária Ao Vivo Ltda",
            cpf_cnpj="34028316000103",
        ),
        pagador_no_provedor=cliente_no_provedor,
        valor=Decimal("50.00"),
        vencimento=date.today() + timedelta(days=5),
        forma="pix",
    ))

    achada = provedor.buscar_por_referencia(referencia)
    assert achada is not None, "filtro externalReference parou de funcionar"
    assert achada.id_no_provedor == criada.id_no_provedor


@escreve
def test_garantir_cliente_e_idempotente(provedor: ProvedorAsaas, cliente_no_provedor: str):
    segundo = provedor.garantir_cliente(ClienteCobranca(
        referencia_externa=REF_CLIENTE,
        nome="Imobiliária Ao Vivo Ltda",
        cpf_cnpj="34028316000103",
    ))
    assert segundo == cliente_no_provedor, "criaria cliente duplicado"
