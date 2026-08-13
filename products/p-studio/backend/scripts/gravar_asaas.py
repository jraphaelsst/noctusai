#!/usr/bin/env python
"""Grava tráfego real do Asaas como fixtures de teste.

    ASAAS_API_KEY='$aact_...' ./venv/bin/python scripts/gravar_asaas.py

Fica fora de `testpaths` de propósito — o pytest nunca coleta este arquivo, e
a suíte padrão continua sem rede.

Por que existe: a alternativa é escrever à mão o que a gente *acha* que a API
devolve, e é exatamente assim que uma suíte verde passa a mentir. Aqui as
fixtures são tráfego capturado; qualquer um pode reexecutar e comparar o diff.

**A redação mora aqui, nunca num passo manual.** Chave de API e dados pessoais
são removidos no momento da gravação, porque "lembrar de limpar antes do
commit" falha exatamente uma vez e o estrago é permanente. Há um teste
(`test_fixtures_sem_segredo`) que falha se algo escapar.

**Somente leitura por padrão.** Este script nasceu supondo sandbox, onde criar
cobrança não custa nada. Com chave de produção, a mesma linha de código emite
um boleto real, no nome de um cliente real, com tarifa real. Então:

    (sem flag)              só GET — seguro em qualquer ambiente
    --criar                 cria cliente e cobrança (recusa em produção)
    --criar --confirmo-producao   cria de verdade, em produção, com fatura real

A trava é uma flag e não uma pergunta interativa porque este script também
roda em terminal não interativo.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://gravador.invalido")
os.environ.setdefault("SUPABASE_ANON_KEY", "gravador")
os.environ.setdefault("ORG_ID", "00000000-0000-0000-0000-0000000000ff")

import httpx  # noqa: E402

from app.providers.asaas import ProvedorAsaas, ambiente_da_chave  # noqa: E402
from app.providers.erros import ErroProvedor  # noqa: E402
from app.providers.tipos import ClienteCobranca, PedidoCobranca  # noqa: E402

DESTINO = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "asaas"

URLS = {
    "sandbox": "https://api-sandbox.asaas.com/v3",
    "producao": "https://api.asaas.com/v3",
}

# Campos varridos do corpo antes de gravar. Em sandbox o dado é fictício; em
# produção é gente de verdade, e aí isto deixa de ser higiene e vira o motivo
# de o script poder rodar contra a conta real.
CAMPOS_PESSOAIS = {
    "cpfCnpj", "email", "phone", "mobilePhone", "name", "postalCode",
    "address", "addressNumber", "province", "complement", "city", "state",
    "company", "personType",
}


def _redigir(valor):
    if isinstance(valor, dict):
        return {
            k: ("[REDIGIDO]" if k in CAMPOS_PESSOAIS and v else _redigir(v))
            for k, v in valor.items()
        }
    if isinstance(valor, list):
        return [_redigir(v) for v in valor]
    return valor


def _gravar(nome: str, requisicao: httpx.Request, resposta: httpx.Response,
            procedencia: str) -> None:
    corpo_req = None
    if requisicao.content:
        try:
            corpo_req = _redigir(json.loads(requisicao.content))
        except ValueError:
            corpo_req = "[NÃO-JSON]"

    # Corpo não-JSON é gravado como texto cru, num campo próprio. Enfiá-lo num
    # dict (`{"texto": ...}`) faria o replay devolver JSON onde a API viva não
    # devolve nada — e o 404 do Asaas vem justamente com corpo VAZIO. A fixture
    # perderia exatamente a característica que ela existe para provar.
    resposta_gravada: dict = {"status": resposta.status_code}
    try:
        resposta_gravada["body"] = _redigir(resposta.json())
    except ValueError:
        resposta_gravada["texto"] = resposta.text[:500]

    troca = {
        "_procedencia": procedencia,
        "gravado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requisicao": {
            "method": requisicao.method,
            # `access_token` NUNCA é gravado. Nem redigido: simplesmente não vai.
            "url": str(requisicao.url).split("?")[0],
            "params": dict(requisicao.url.params),
            "body": corpo_req,
        },
        "resposta": resposta_gravada,
    }
    caminho = DESTINO / f"{nome}.json"
    caminho.write_text(
        json.dumps(troca, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"  gravado  {caminho.name}  (HTTP {resposta.status_code})")


def _montar(chave: str, ambiente: str):
    """Adapter com gancho de captura instalado."""
    capturas: list[tuple[httpx.Request, httpx.Response]] = []

    def capturar(resposta: httpx.Response) -> None:
        resposta.read()
        capturas.append((resposta.request, resposta))

    provedor = ProvedorAsaas(
        api_key=chave,
        base_url=os.environ.get("ASAAS_BASE_URL") or URLS[ambiente],
    )
    provedor.http._client.event_hooks["response"] = [capturar]
    return provedor, capturas


# ── leitura ──────────────────────────────────────────────────────────────

def gravar_leitura(chave: str, ambiente: str, procedencia: str) -> None:
    """Trocas sem efeito colateral. Rodam contra qualquer ambiente."""
    provedor, capturas = _montar(chave, ambiente)

    print(f"\ngravando trocas somente-leitura contra {ambiente}…")

    provedor.buscar_por_referencia("sonda-que-nao-existe")
    _gravar("cobranca_por_referencia_vazia", *capturas[-1], procedencia)
    capturas.clear()

    try:
        provedor.obter_cobranca("pay_000000000000")
    except ErroProvedor:
        pass  # 404 é o ponto: queremos o formato do erro.
    if capturas:
        _gravar("cobranca_inexistente", *capturas[-1], procedencia)
        capturas.clear()

    provedor.http.requisitar("GET", "/customers", params={"limit": 1})
    _gravar("clientes_listagem", *capturas[-1], procedencia)
    capturas.clear()


def gravar_ambiente_errado(chave: str, ambiente: str) -> None:
    """O 401 `invalid_environment`, capturado de propósito.

    Vale uma fixture porque é o erro que mais provavelmente vai acontecer de
    verdade — trocar de ambiente é trocar duas variáveis, e esquecer uma é
    fácil. O guard de construção do adapter impede a divergência quando os dois
    lados são reconhecíveis; esta troca é o que a API responde quando ele não
    impede (chave de prefixo desconhecido, por exemplo).
    """
    oposto = "sandbox" if ambiente == "producao" else "producao"
    with httpx.Client(timeout=httpx.Timeout(15.0, connect=8.0)) as c:
        resposta = c.get(
            URLS[oposto] + "/customers",
            params={"limit": 1},
            headers={"access_token": chave, "User-Agent": "p-studio/0.1 (NoctusAI)"},
        )
    _gravar(
        "erro_401_ambiente_errado", resposta.request, resposta,
        f"capturado: chave de {ambiente} apontada para {oposto}",
    )


# ── escrita ──────────────────────────────────────────────────────────────

def gravar_escrita(chave: str, ambiente: str, procedencia: str) -> None:
    """Cria cliente e cobrança. **Em produção isto emite fatura real.**"""
    provedor, capturas = _montar(chave, ambiente)

    ref_cliente = "fixture-cliente-p-studio"
    ref_lancamento = f"fixture-lancamento-{date.today().isoformat()}"

    print(f"\ngravando trocas de ESCRITA contra {ambiente}…")

    id_cliente = provedor.garantir_cliente(ClienteCobranca(
        referencia_externa=ref_cliente,
        nome="Imobiliária Fixture Ltda",
        cpf_cnpj="34028316000103",
        email="fixture@exemplo.com.br",
        cep="01310100",
    ))
    for i, (req, resp) in enumerate(capturas):
        _gravar(f"cliente_{i}_{req.method.lower()}", req, resp, procedencia)
    capturas.clear()

    cobranca = provedor.criar_cobranca(PedidoCobranca(
        referencia_externa=ref_lancamento,
        pagador=ClienteCobranca(
            referencia_externa=ref_cliente,
            nome="Imobiliária Fixture Ltda",
            cpf_cnpj="34028316000103",
        ),
        pagador_no_provedor=id_cliente,
        valor="1800.00",
        vencimento=date.today() + timedelta(days=7),
        forma="boleto",
        descricao="Ensaio fotográfico + drone",
    ))
    # `criar_cobranca` faz duas chamadas: o POST e o enriquecimento (linha
    # digitável ou pix copia-e-cola, que vivem em endpoint separado). As duas
    # viram fixture — a segunda é a que documenta o campo que não existe no
    # objeto da cobrança.
    _gravar("cobranca_criada", *capturas[0], procedencia)
    if len(capturas) > 1:
        _gravar("cobranca_linha_digitavel", *capturas[1], procedencia)
    capturas.clear()

    provedor.obter_cobranca(cobranca.id_no_provedor)
    _gravar("cobranca_obtida", *capturas[0], procedencia)
    capturas.clear()

    provedor.buscar_por_referencia(ref_lancamento)
    _gravar("cobranca_por_referencia", *capturas[0], procedencia)
    capturas.clear()

    # Pix pela mesma cobrança não dá — a forma é definida na criação. Uma
    # cobrança Pix só para capturar o `pixQrCode`.
    pix = provedor.criar_cobranca(PedidoCobranca(
        referencia_externa=f"fixture-pix-{date.today().isoformat()}",
        pagador=ClienteCobranca(
            referencia_externa=ref_cliente,
            nome="Imobiliária Fixture Ltda",
            cpf_cnpj="34028316000103",
        ),
        pagador_no_provedor=id_cliente,
        valor="50.00",
        vencimento=date.today() + timedelta(days=5),
        forma="pix",
        descricao="Sonda de contrato Pix",
    ))
    if len(capturas) > 1:
        _gravar("cobranca_pix_copia_e_cola", *capturas[1], procedencia)
    print(f"  (cobrança Pix {pix.id_no_provedor} criada para a fixture)")
    capturas.clear()

    print(f"\nOK — cobrança {cobranca.id_no_provedor} criada em {ambiente}.")
    print(f"Fatura: {cobranca.url_fatura}")
    if ambiente == "producao":
        print(
            "\n⚠  Esta é uma fatura REAL. Cancele no painel se foi só sonda:\n"
            f"   https://www.asaas.com/  →  Cobranças  →  {cobranca.id_no_provedor}"
        )
    else:
        print(
            "\nPróximo passo: pague essa cobrança no sandbox e copie o corpo do "
            "webhook do painel para tests/fixtures/asaas/webhook_liquidada.json"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--criar", action="store_true",
                        help="cria cliente e cobrança (efeito colateral real)")
    parser.add_argument("--confirmo-producao", action="store_true",
                        help="libera --criar contra a conta de produção")
    args = parser.parse_args()

    chave = os.environ.get("ASAAS_API_KEY", "")
    if not chave:
        print(
            "ASAAS_API_KEY não definida.\n"
            "Sandbox: https://sandbox.asaas.com/ → Integrações (a chave é "
            "exibida uma única vez).",
            file=sys.stderr,
        )
        return 1

    ambiente = ambiente_da_chave(chave)
    if ambiente == "desconhecido":
        print(
            "Não reconheci o ambiente pelo prefixo da chave. Defina "
            "ASAAS_BASE_URL explicitamente e rode de novo.",
            file=sys.stderr,
        )
        return 1

    print(f"chave de {ambiente.upper()}")

    if args.criar and ambiente == "producao" and not args.confirmo_producao:
        print(
            "\nRECUSADO: --criar com chave de produção.\n\n"
            "Isto criaria um cliente e emitiria um boleto REAL na conta, com\n"
            "tarifa e com notificação ao pagador. Se é mesmo o que você quer:\n\n"
            "    --criar --confirmo-producao\n\n"
            "O caminho normal é gerar uma chave em sandbox.asaas.com e usar\n"
            "aquela — o sandbox tem simulação de pagamento, que é o que fecha\n"
            "o ciclo emitir → pagar → webhook.",
            file=sys.stderr,
        )
        return 2

    DESTINO.mkdir(parents=True, exist_ok=True)
    procedencia = f"capturado da API viva do Asaas ({ambiente})"

    gravar_leitura(chave, ambiente, procedencia)
    gravar_ambiente_errado(chave, ambiente)

    if args.criar:
        gravar_escrita(chave, ambiente, procedencia)
    else:
        print(
            "\nSomente leitura — nada foi criado. Para gravar as trocas de "
            "criação de cobrança, use --criar."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
