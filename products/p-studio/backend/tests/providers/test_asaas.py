"""Contrato do adapter do Asaas.

A maior parte destes testes afirma sobre a **requisição que sai**, não sobre a
resposta que entra. É deliberado: a resposta vem de fixture, então afirmar
sobre ela prova pouco; o que pode quebrar em silêncio e derrubar a conciliação
é mandarmos o campo errado. `externalReference` é o exemplo canônico — se ele
sumir, tudo continua "funcionando" até o primeiro webhook chegar sem ter a
quem pertencer.

As trocas gravadas ainda dependem de `scripts/gravar_asaas.py` ter rodado com
uma chave de sandbox. Enquanto não rodou, os testes que precisam delas fazem
`skip` — nunca passam por acidente com dado inventado. Os testes de tradução e
de requisição abaixo não dependem de fixture nenhuma e rodam sempre.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.providers.asaas import (
    ProvedorAsaas,
    _digitos,
    _hash_do_corpo,
    _sem_nulos,
    ambiente_da_chave,
    ambiente_da_url,
)
from app.providers.erros import ErroProvedor
from app.providers.tipos import ClienteCobranca, PedidoCobranca
from tests.providers.conftest import (
    FIXTURES,
    carregar,
    corpo_enviado,
    transporte_gravado,
)

CHAVE = "$aact_chave_de_teste"


def _provedor(transport: httpx.MockTransport) -> ProvedorAsaas:
    return ProvedorAsaas(api_key=CHAVE, transport=transport)


def _pedido(**overrides) -> PedidoCobranca:
    base = dict(
        referencia_externa="lanc-abc-123",
        pagador=ClienteCobranca(
            referencia_externa="cli-xyz",
            nome="Imobiliária Alfa",
            cpf_cnpj="34.028.316/0001-03",
        ),
        pagador_no_provedor="cus_000001",
        valor=Decimal("1800.00"),
        vencimento=date(2026, 9, 10),
        forma="boleto",
        descricao="Ensaio fotográfico",
    )
    base.update(overrides)
    return PedidoCobranca(**base)


# ── o que sai na requisição ──────────────────────────────────────────────

def _captura(respostas: list[tuple[int, dict]]):
    """Transporte simples que só registra as requisições e devolve o roteiro."""
    enviadas: list[httpx.Request] = []
    fila = list(respostas)

    def handler(requisicao: httpx.Request) -> httpx.Response:
        enviadas.append(requisicao)
        status, corpo = fila.pop(0)
        return httpx.Response(status, json=corpo)

    return httpx.MockTransport(handler), enviadas


def test_criar_cobranca_manda_external_reference():
    """A chave de conciliação. Sem ela o webhook chega órfão."""
    transporte, enviadas = _captura([(200, {"id": "pay_1", "status": "PENDING"})])
    _provedor(transporte).criar_cobranca(_pedido())

    assert corpo_enviado(enviadas[0])["externalReference"] == "lanc-abc-123"


def test_criar_cobranca_manda_o_header_de_autenticacao():
    transporte, enviadas = _captura([(200, {"id": "pay_1", "status": "PENDING"})])
    _provedor(transporte).criar_cobranca(_pedido())

    assert enviadas[0].headers["access_token"] == CHAVE


def test_criar_cobranca_traduz_a_forma_de_pagamento():
    for forma, esperado in [
        ("boleto", "BOLETO"), ("pix", "PIX"),
        ("cartao", "CREDIT_CARD"), ("indefinido", "UNDEFINED"),
    ]:
        transporte, enviadas = _captura([(200, {"id": "p", "status": "PENDING"})])
        _provedor(transporte).criar_cobranca(_pedido(forma=forma))
        assert corpo_enviado(enviadas[0])["billingType"] == esperado


def test_criar_cobranca_manda_data_iso_e_valor_numerico():
    transporte, enviadas = _captura([(200, {"id": "p", "status": "PENDING"})])
    _provedor(transporte).criar_cobranca(_pedido())

    corpo = corpo_enviado(enviadas[0])
    assert corpo["dueDate"] == "2026-09-10"
    assert corpo["value"] == 1800.00


def test_criar_cobranca_nao_manda_chaves_nulas():
    """Mandar `null` explícito faz o Asaas reclamar de campo opcional."""
    transporte, enviadas = _captura([(200, {"id": "p", "status": "PENDING"})])
    _provedor(transporte).criar_cobranca(_pedido(descricao=None))

    assert "description" not in corpo_enviado(enviadas[0])


def test_criar_cobranca_usa_o_pagador_em_cache_sem_consultar():
    """Com `pagador_no_provedor` preenchido, é uma chamada só."""
    transporte, enviadas = _captura([(200, {"id": "p", "status": "PENDING"})])
    _provedor(transporte).criar_cobranca(_pedido())

    assert len(enviadas) == 1
    assert enviadas[0].url.path.endswith("/payments")


def test_sem_pagador_em_cache_resolve_o_cliente_antes():
    transporte, enviadas = _captura([
        (200, {"data": []}),                       # busca não acha
        (200, {"id": "cus_novo"}),                 # cria
        (200, {"id": "pay_1", "status": "PENDING"}),
    ])
    _provedor(transporte).criar_cobranca(_pedido(pagador_no_provedor=None))

    assert [r.url.path for r in enviadas] == [
        "/v3/customers", "/v3/customers", "/v3/payments"
    ]
    assert corpo_enviado(enviadas[2])["customer"] == "cus_novo"


def test_garantir_cliente_reaproveita_cadastro_existente():
    """Criar duas vezes geraria dois clientes com o mesmo CPF."""
    transporte, enviadas = _captura([(200, {"data": [{"id": "cus_ja_existe"}]})])

    id_cliente = _provedor(transporte).garantir_cliente(ClienteCobranca(
        referencia_externa="cli-xyz", nome="Alfa", cpf_cnpj="34028316000103",
    ))

    assert id_cliente == "cus_ja_existe"
    assert len(enviadas) == 1  # não fez POST


def test_garantir_cliente_manda_documento_sem_pontuacao():
    transporte, enviadas = _captura([(200, {"data": []}), (200, {"id": "cus_1"})])

    _provedor(transporte).garantir_cliente(ClienteCobranca(
        referencia_externa="cli-xyz", nome="Alfa", cpf_cnpj="34.028.316/0001-03",
    ))

    assert corpo_enviado(enviadas[1])["cpfCnpj"] == "34028316000103"


def test_cliente_sem_documento_falha_com_erro_de_dominio():
    """Erro nosso, dizendo o campo — não um 400 críptico do provedor."""
    transporte, _ = _captura([])
    with pytest.raises(ErroProvedor) as exc:
        _provedor(transporte).garantir_cliente(ClienteCobranca(
            referencia_externa="cli-xyz", nome="Sem Doc", cpf_cnpj="",
        ))

    assert exc.value.status == 422
    assert "CPF/CNPJ" in exc.value.mensagem


# ── o que entra: tradução de resposta ────────────────────────────────────

def test_traduz_status_do_asaas_para_o_nosso_lexico():
    transporte, _ = _captura([])
    p = _provedor(transporte)
    for bruto, esperado in [
        ("PENDING", "pendente"), ("CONFIRMED", "confirmada"),
        ("RECEIVED", "liquidada"), ("RECEIVED_IN_CASH", "liquidada"),
        ("OVERDUE", "vencida"), ("REFUNDED", "estornada"),
        ("DELETED", "cancelada"),
    ]:
        assert p._para_cobranca({"id": "p", "status": bruto}).status == esperado


def test_status_desconhecido_cai_em_pendente_sem_explodir():
    """Status novo do provedor não pode derrubar a conciliação."""
    transporte, _ = _captura([])
    cobranca = _provedor(transporte)._para_cobranca(
        {"id": "p", "status": "STATUS_QUE_NAO_EXISTE_AINDA"}
    )
    assert cobranca.status == "pendente"


def test_confirmada_nao_e_liquidada():
    """CONFIRMED = pago, saldo indisponível. Só RECEIVED dá baixa."""
    transporte, _ = _captura([])
    p = _provedor(transporte)
    assert p._para_cobranca({"id": "p", "status": "CONFIRMED"}).status == "confirmada"
    assert p._para_cobranca({"id": "p", "status": "RECEIVED"}).status == "liquidada"


def test_traduz_campos_do_boleto():
    transporte, _ = _captura([])
    cobranca = _provedor(transporte)._para_cobranca({
        "id": "pay_123", "status": "PENDING", "value": 1800.0,
        "dueDate": "2026-09-10", "billingType": "BOLETO",
        "externalReference": "lanc-abc-123", "customer": "cus_1",
        "invoiceUrl": "https://sandbox.asaas.com/i/pay_123",
        "identificationField": "34191790010104351004791020150008291070026000",
        "payload": "00020126580014br.gov.bcb.pix",
    })

    assert cobranca.id_no_provedor == "pay_123"
    assert cobranca.referencia_externa == "lanc-abc-123"
    assert cobranca.valor == Decimal("1800.0")
    assert cobranca.vencimento == date(2026, 9, 10)
    assert cobranca.forma == "boleto"
    assert cobranca.linha_digitavel.startswith("34191")
    assert cobranca.pix_copia_e_cola.startswith("00020126")


def test_undefined_vira_forma_nula():
    """O CHECK de forma_pagamento não tem 'indefinido'; perda irrelevante."""
    transporte, _ = _captura([])
    cobranca = _provedor(transporte)._para_cobranca(
        {"id": "p", "status": "PENDING", "billingType": "UNDEFINED"}
    )
    assert cobranca.forma is None


def test_pago_em_prefere_payment_date():
    transporte, _ = _captura([])
    cobranca = _provedor(transporte)._para_cobranca({
        "id": "p", "status": "RECEIVED",
        "paymentDate": "2026-09-12", "clientPaymentDate": "2026-09-11",
    })
    assert cobranca.pago_em == date(2026, 9, 12)


# ── webhook ──────────────────────────────────────────────────────────────

def test_interpreta_evento_de_liquidacao():
    transporte, _ = _captura([])
    evento = _provedor(transporte).interpretar_evento({
        "id": "evt_abc", "event": "PAYMENT_RECEIVED",
        "payment": {"id": "pay_1", "status": "RECEIVED",
                    "externalReference": "lanc-abc-123", "value": 1800.0,
                    "paymentDate": "2026-09-12"},
    })

    assert evento is not None
    assert evento.tipo == "liquidada"
    assert evento.tipo_bruto == "PAYMENT_RECEIVED"   # guardado cru para forense
    assert evento.cobranca.referencia_externa == "lanc-abc-123"


def test_confirmado_nao_vira_liquidado_no_evento():
    transporte, _ = _captura([])
    evento = _provedor(transporte).interpretar_evento({
        "id": "evt_x", "event": "PAYMENT_CONFIRMED",
        "payment": {"id": "p", "status": "CONFIRMED"},
    })
    assert evento.tipo == "confirmada"


def test_evento_desconhecido_devolve_none():
    """None → webhook responde 200 sem efeito. Erro pausaria a fila."""
    transporte, _ = _captura([])
    p = _provedor(transporte)
    assert p.interpretar_evento({"id": "e", "event": "PAYMENT_CHECKOUT_VIEWED",
                                 "payment": {}}) is None
    assert p.interpretar_evento({"event": "COISA_NOVA", "payment": {}}) is None
    assert p.interpretar_evento({}) is None


def test_evento_sem_bloco_payment_devolve_none():
    transporte, _ = _captura([])
    assert _provedor(transporte).interpretar_evento(
        {"id": "e", "event": "PAYMENT_RECEIVED"}
    ) is None


def test_evento_sem_id_ganha_hash_deterministico():
    transporte, _ = _captura([])
    corpo = {"event": "PAYMENT_RECEIVED", "payment": {"id": "p", "status": "RECEIVED"}}

    a = _provedor(transporte).interpretar_evento(corpo)
    b = _provedor(transporte).interpretar_evento(dict(corpo))

    assert a.id_no_provedor.startswith("sha256:")
    assert a.id_no_provedor == b.id_no_provedor


# ── erro traduzido, contra tráfego real capturado ────────────────────────

def test_erro_401_real_do_sandbox_vira_erro_provedor():
    """Fixture capturada do sandbox de verdade — ver o campo `_procedencia`."""
    troca = carregar("erro_401_chave_invalida")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(troca["resposta"]["status"], json=troca["resposta"]["body"])

    with pytest.raises(ErroProvedor) as exc:
        _provedor(httpx.MockTransport(handler)).buscar_por_referencia("qualquer")

    assert exc.value.status == 401
    assert exc.value.codigo == "invalid_access_token"
    assert "inválida" in exc.value.mensagem
    # 401 não é retentável: insistir com credencial errada só queima cota.
    assert exc.value.retentavel is False


def test_erro_5xx_e_retentavel():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"errors": [{"description": "fora do ar"}]})

    with pytest.raises(ErroProvedor) as exc:
        _provedor(httpx.MockTransport(handler)).obter_cobranca("pay_1")

    assert exc.value.retentavel is True


def test_timeout_vira_erro_retentavel():
    def handler(requisicao: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("demorou", request=requisicao)

    with pytest.raises(ErroProvedor) as exc:
        _provedor(httpx.MockTransport(handler)).obter_cobranca("pay_1")

    assert exc.value.status == 504
    assert exc.value.retentavel is True


# ── utilitários ──────────────────────────────────────────────────────────

def test_digitos_limpa_pontuacao():
    assert _digitos("34.028.316/0001-03") == "34028316000103"
    assert _digitos("(11) 98765-4321") == "11987654321"
    assert _digitos(None) is None
    assert _digitos("sem digito") is None


def test_sem_nulos_preserva_zero_e_false():
    assert _sem_nulos({"a": 0, "b": False, "c": None, "d": ""}) == {
        "a": 0, "b": False, "d": ""
    }


def test_hash_do_corpo_independe_da_ordem_das_chaves():
    assert _hash_do_corpo({"a": 1, "b": 2}) == _hash_do_corpo({"b": 2, "a": 1})


# ── procedência das fixtures ─────────────────────────────────────────────

def test_fixtures_sem_segredo():
    """Falha se alguma fixture carregar chave de API.

    Este repositório já teve senha em texto puro commitada uma vez — a
    verificação é barata e o estrago é permanente.
    """
    suspeitos = []
    for caminho in FIXTURES.glob("*.json"):
        texto = caminho.read_text(encoding="utf-8")
        if "$aact_" in texto or '"access_token"' in texto:
            suspeitos.append(caminho.name)
    assert not suspeitos, f"segredo em fixture: {suspeitos}"


def test_toda_fixture_declara_procedencia():
    """Fixture sem `_procedencia` é suspeita de ter sido escrita à mão."""
    for caminho in FIXTURES.glob("*.json"):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        assert dados.get("_procedencia"), f"{caminho.name} sem _procedencia"
        assert dados.get("gravado_em"), f"{caminho.name} sem gravado_em"


# ── ambiente ─────────────────────────────────────────────────────────────
#
# O ambiente virou conceito imposto no adapter depois que uma chave de
# PRODUÇÃO entrou no projeto. A diferença entre os dois ambientes deixou de ser
# acadêmica: em sandbox, `criar_cobranca` não custa nada; em produção, emite um
# boleto real, com tarifa, e notifica o pagador.

def test_ambiente_sai_do_prefixo_da_chave():
    assert ambiente_da_chave("$aact_prod_abc") == "producao"
    assert ambiente_da_chave("$aact_hmlg_abc") == "sandbox"
    assert ambiente_da_chave("qualquer-outra-coisa") == "desconhecido"


def test_ambiente_sai_do_host_da_url():
    assert ambiente_da_url("https://api-sandbox.asaas.com/v3") == "sandbox"
    assert ambiente_da_url("https://api.asaas.com/v3") == "producao"
    assert ambiente_da_url("http://localhost:9999") == "desconhecido"


def test_chave_de_producao_com_url_de_sandbox_recusa_na_construcao():
    """Falha aqui, não na primeira cobrança.

    A API responderia 401 `invalid_environment` — mas 401 chegando por um job
    noturno ou pelo webhook vira mistério, e no webhook nem chega a aparecer,
    porque ele responde 200 a quase tudo por desenho.
    """
    with pytest.raises(ErroProvedor) as exc:
        ProvedorAsaas(
            api_key="$aact_prod_abc",
            base_url="https://api-sandbox.asaas.com/v3",
        )
    assert "producao" in exc.value.mensagem
    assert "sandbox" in exc.value.mensagem


def test_chave_de_sandbox_com_url_de_producao_recusa_na_construcao():
    with pytest.raises(ErroProvedor):
        ProvedorAsaas(
            api_key="$aact_hmlg_abc", base_url="https://api.asaas.com/v3"
        )


def test_prefixo_desconhecido_nao_bloqueia():
    """Se o Asaas mudar a convenção de prefixo, um deploy válido não pode
    quebrar por causa de uma heurística nossa."""
    provedor = ProvedorAsaas(
        api_key="chave-de-formato-novo", base_url="https://api.asaas.com/v3"
    )
    assert provedor.ambiente == "desconhecido"


def test_combinacao_coerente_passa():
    assert ProvedorAsaas(
        api_key="$aact_prod_abc", base_url="https://api.asaas.com/v3"
    ).ambiente == "producao"


# ── tráfego real de produção, capturado ──────────────────────────────────

def test_ambiente_errado_real_vira_401_nao_retentavel():
    """Fixture capturada apontando a chave de produção para o sandbox."""
    troca = carregar("erro_401_ambiente_errado")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(troca["resposta"]["status"], json=troca["resposta"]["body"])

    with pytest.raises(ErroProvedor) as exc:
        _provedor(httpx.MockTransport(handler)).buscar_por_referencia("x")

    assert exc.value.status == 401
    assert exc.value.codigo == "invalid_environment"
    assert exc.value.retentavel is False


def test_404_com_corpo_vazio_vira_erro_com_mensagem():
    """O 404 do Asaas não tem corpo — verificado contra a API viva.

    Sem mensagem de fallback, o suporte receberia string vazia e a tela não
    teria o que mostrar. Este é o caso que a extração tolerante existe para
    aguentar.
    """
    transporte = transporte_gravado("cobranca_inexistente")

    with pytest.raises(ErroProvedor) as exc:
        _provedor(transporte).obter_cobranca("pay_000000000000")

    assert exc.value.status == 404
    assert exc.value.mensagem
    assert exc.value.retentavel is False


def test_busca_vazia_real_devolve_none():
    """O envelope de lista vazio, como a API viva devolve. É o pré-check de
    idempotência da emissão: se ele estourar, nenhuma cobrança sai."""
    transporte = transporte_gravado("cobranca_por_referencia_vazia")
    assert _provedor(transporte).buscar_por_referencia("nao-existe") is None


def test_a_chave_real_nao_escapou_do_env():
    """O `.env` é o único lugar onde a credencial pode existir.

    Os outros guards de segredo procuram um *padrão* (`$aact_`) dentro das
    fixtures. Este procura a **chave concreta que está configurada agora**, no
    projeto inteiro — que é o que pega o caso real: alguém cola a chave num
    script de depuração, num README de "como rodar", ou num teste, para não ter
    de exportar a variável. Este repositório já teve senha em texto puro
    commitada uma vez.

    Roda de graça e sem rede: se não houver `.env`, não há o que vazar.
    """
    raiz = Path(__file__).resolve().parents[2]
    env = raiz / ".env"
    if not env.exists():
        pytest.skip("sem .env local — nada configurado para vazar")

    segredos = {}
    for linha in env.read_text(encoding="utf-8").splitlines():
        if linha.startswith(("#", " ")) or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        nome, valor = nome.strip(), valor.strip().strip('"').strip("'")
        # Escolhe pelo NOME da variável, não pelo tamanho do valor: a primeira
        # versão disto usava "valor com 24+ caracteres" e acusou o
        # ASAAS_BASE_URL, que é público e aparece em meia dúzia de arquivos de
        # propósito. Guard que grita sem motivo é guard que alguém desliga.
        if valor and any(
            marca in nome.upper()
            for marca in ("KEY", "TOKEN", "SECRET", "SENHA", "PASSWORD")
        ):
            segredos[nome] = valor

    if not segredos:
        pytest.skip(".env sem credencial preenchida")

    ignorados = {"venv", ".venv", "node_modules", "dist", "__pycache__",
                 ".git", ".pytest_cache", "coverage"}
    suspeitos = []
    for caminho in raiz.parent.rglob("*"):
        if not caminho.is_file() or caminho.name == ".env":
            continue
        if ignorados & set(caminho.parts):
            continue
        if caminho.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".json",
                                  ".md", ".sql", ".sh", ".yml", ".yaml", ".txt",
                                  ".example", ".env"}:
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for nome, valor in segredos.items():
            if valor in texto:
                suspeitos.append(f"{nome} em {caminho.relative_to(raiz.parent)}")

    assert not suspeitos, (
        "credencial do .env encontrada fora dele:\n  " + "\n  ".join(suspeitos)
    )


# ── enriquecimento: linha digitável e pix copia-e-cola ───────────────────
#
# Estes campos NÃO existem no objeto da cobrança. Descoberto contra o sandbox
# real: a versão anterior do adapter os lia de `dados.get(...)` e devolvia None
# sempre — cobrança emitida chegava na tela sem linha digitável para copiar, e
# nada no log explicava.

def test_boleto_busca_a_linha_digitavel_em_endpoint_separado():
    transporte, enviadas = _captura([
        (200, {"id": "pay_1", "status": "PENDING", "billingType": "BOLETO"}),
        (200, {"identificationField": "46191110000000000000012931347012115440000180000",
               "nossoNumero": "12931347", "barCode": "4619115440000180000111"}),
    ])
    cobranca = _provedor(transporte).criar_cobranca(_pedido(forma="boleto"))

    assert enviadas[1].url.path == "/v3/payments/pay_1/identificationField"
    assert cobranca.linha_digitavel.startswith("46191110000")


def test_pix_busca_o_copia_e_cola_em_endpoint_separado():
    transporte, enviadas = _captura([
        (200, {"id": "pay_2", "status": "PENDING", "billingType": "PIX"}),
        (200, {"success": True, "payload": "00020101021226820014br.gov.bcb.pix",
               "encodedImage": "iVBORw0KGgo="}),
    ])
    cobranca = _provedor(transporte).criar_cobranca(_pedido(forma="pix"))

    assert enviadas[1].url.path == "/v3/payments/pay_2/pixQrCode"
    assert cobranca.pix_copia_e_cola.startswith("00020101")
    # `encodedImage` é o PNG do QR em base64. Não entra no nosso modelo: o
    # frontend gera o QR a partir do copia-e-cola, e guardar imagem em coluna
    # de texto é como um payload de 4KB vira lentidão sem ninguém notar.
    assert "encodedImage" not in (cobranca.pix_copia_e_cola or "")


def test_falha_no_enriquecimento_nao_derruba_a_emissao():
    """A cobrança existe e é válida. Perder o campo acessório não pode
    transformar uma emissão bem-sucedida em erro para o usuário."""
    transporte, _ = _captura([
        (200, {"id": "pay_3", "status": "PENDING", "billingType": "BOLETO"}),
        (500, {"errors": [{"description": "instabilidade"}]}),
    ])
    cobranca = _provedor(transporte).criar_cobranca(_pedido(forma="boleto"))

    assert cobranca.id_no_provedor == "pay_3"
    assert cobranca.linha_digitavel is None


def test_cobranca_encerrada_nao_gera_chamada_extra():
    """Linha digitável de boleto já liquidado não serve para nada."""
    transporte, enviadas = _captura([
        (200, {"id": "pay_4", "status": "RECEIVED", "billingType": "BOLETO"}),
    ])
    _provedor(transporte).obter_cobranca("pay_4")

    assert len(enviadas) == 1


def test_interpretar_evento_nao_toca_a_rede():
    """O webhook precisa responder rápido e não pode depender de uma segunda
    chamada. Se o enriquecimento vazar para cá, o MockTransport sem roteiro
    estoura — que é exatamente o alarme que queremos."""
    transporte, enviadas = _captura([])
    evento = _provedor(transporte).interpretar_evento({
        "id": "evt_1", "event": "PAYMENT_RECEIVED",
        "payment": {"id": "pay_5", "status": "RECEIVED", "billingType": "BOLETO"},
    })

    assert evento is not None
    assert enviadas == []


def test_enriquecimento_contra_trafego_real_gravado():
    """As duas trocas, como o sandbox de verdade as devolveu."""
    transporte = transporte_gravado("cobranca_criada", "cobranca_linha_digitavel")
    cobranca = _provedor(transporte).criar_cobranca(_pedido(forma="boleto"))

    assert cobranca.linha_digitavel
    assert cobranca.url_fatura
    # O campo NÃO está no objeto da cobrança — é isto que a fixture prova.
    assert "identificationField" not in cobranca.bruto
