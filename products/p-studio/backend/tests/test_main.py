"""App: health, CORS e proteção padrão das rotas."""
import pytest

from app.main import app

PROTEGIDAS = [
    "/api/me",
    "/api/dashboard",
    "/api/clientes-metricas",
    "/api/clientes",
    "/api/imoveis",
    "/api/servicos",
    "/api/equipamentos",
    "/api/negocios",
    "/api/captacoes",
    "/api/producoes",
    "/api/financeiro",
    "/api/financeiro/resumo",
    "/api/financeiro/por-cliente",
]

# Catálogos de etapas/status: constantes do domínio, não dados da organização.
# São públicas de propósito — a tela precisa das colunas do kanban antes de
# ter qualquer dado, e nenhuma delas revela informação do estúdio.
PUBLICAS = ["/api/health", "/api/negocios/etapas", "/api/producoes/etapas",
            "/api/financeiro/status"]


@pytest.mark.parametrize("rota", PUBLICAS)
def test_rotas_publicas_dispensam_token(client_anon, rota):
    assert client_anon.get(rota).status_code == 200


def test_health(client_anon):
    res = client_anon.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "product": "p-studio"}


@pytest.mark.parametrize("rota", PROTEGIDAS)
def test_rotas_protegidas_exigem_token(client_anon, rota):
    assert client_anon.get(rota).status_code == 401


def test_cors_libera_o_frontend(client_anon):
    res = client_anon.get("/api/health", headers={"Origin": "http://localhost:5176"})
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5176"


def test_cors_nao_libera_origem_desconhecida(client_anon):
    res = client_anon.get("/api/health", headers={"Origin": "https://mal.example"})
    assert "access-control-allow-origin" not in res.headers


def test_todas_as_rotas_de_dominio_estao_registradas():
    """Guarda contra um router esquecido no `include_router` do main."""
    caminhos = {r.path for r in app_routes()}
    for prefixo in ("/api/clientes", "/api/imoveis", "/api/servicos",
                    "/api/equipamentos", "/api/negocios", "/api/captacoes",
                    "/api/producoes", "/api/financeiro", "/api/integracoes"):
        assert prefixo in caminhos or any(c.startswith(prefixo) for c in caminhos), \
            f"router ausente: {prefixo}"


def app_routes():
    from app.main import app

    return app.routes


# ── guarda estrutural ────────────────────────────────────────────────────
#
# As listas acima documentam a intenção, mas não impedem o acidente: quem
# criar uma rota nova e esquecer o `Depends(get_current_user)` não aparece em
# lista nenhuma. Este teste caminha pela árvore de dependências de TODA rota
# registrada e exige autenticação, salvo isenção explícita e justificada.
#
# O webhook forçou isto a existir: ele é a primeira rota pública que escreve,
# e a divisão binária "protegida ou pública" deixou de descrever a realidade.

ISENTAS = {
    # Catálogos de domínio — constantes, não dados da organização.
    ("GET", "/api/health"),
    ("GET", "/api/negocios/etapas"),
    ("GET", "/api/producoes/etapas"),
    ("GET", "/api/financeiro/status"),
    # Webhook: quem chama é o provedor, não o navegador. Autenticado por
    # segredo compartilhado no header (`verificar_token_asaas`), não por JWT.
    ("POST", "/api/integracoes/asaas/webhook"),
    # Documentação do FastAPI.
    ("GET", "/docs"), ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"), ("GET", "/openapi.json"),
}


def _depende_de_autenticacao(rota) -> bool:
    """Procura `get_current_user` na árvore de dependências da rota."""
    from app.dependencies import get_current_user

    dependente = getattr(rota, "dependant", None)
    if dependente is None:
        return False

    pilha = [dependente]
    while pilha:
        atual = pilha.pop()
        if atual.call is get_current_user:
            return True
        pilha.extend(atual.dependencies)
    return False


def test_toda_rota_exige_autenticacao_ou_esta_isenta():
    faltando = []
    for rota in app_routes():
        metodos = getattr(rota, "methods", None)
        if not metodos:
            continue
        for metodo in metodos - {"HEAD", "OPTIONS"}:
            if (metodo, rota.path) in ISENTAS:
                continue
            if not _depende_de_autenticacao(rota):
                faltando.append(f"{metodo} {rota.path}")

    assert not faltando, (
        "rotas sem autenticação e sem isenção declarada:\n  "
        + "\n  ".join(sorted(faltando))
        + "\n\nAdicione Depends(get_current_user) ou justifique em ISENTAS."
    )


def test_o_webhook_esta_isento_mas_exige_o_segredo():
    """Isenção de JWT não é isenção de autenticação."""
    from app.routers.integracoes_router import verificar_token_asaas

    rota = next(
        r for r in app_routes()
        if getattr(r, "path", "") == "/api/integracoes/asaas/webhook"
    )
    chamadas = [d.call for d in rota.dependant.dependencies]
    assert verificar_token_asaas in chamadas


# ── tradução de erro de provedor ─────────────────────────────────────────
#
# O handler existe desde a camada de provedores, mas nada verificava o mapa de
# status. Ele ganhou testes quando o 404 real do Asaas apareceu: uma cobrança
# apagada no painel do banco chegava à tela como 502, indistinguível de "o
# Asaas caiu".

import pytest as _pytest

from app.main import REPASSADOS, tratar_erro_provedor
from app.providers.erros import ErroProvedor


def _status(status: int) -> int:
    erro = ErroProvedor("asaas", "falhou", status=status)
    return tratar_erro_provedor(None, erro).status_code


@_pytest.mark.parametrize("status", sorted(REPASSADOS))
def test_status_acionavel_pelo_chamador_passa_direto(status):
    assert _status(status) == status


@_pytest.mark.parametrize("status", [400, 401, 403, 422, 500, 502])
def test_o_resto_vira_502(status):
    """400/422 do provedor significam que o payload que NÓS montamos estava
    errado. Repassar 400 culparia o usuário por um bug nosso."""
    assert _status(status) == 502


def test_o_corpo_carrega_o_trace_id():
    """O suporte do banco pede isto; devolver junto evita a ida e volta."""
    import json

    erro = ErroProvedor("asaas", "falhou", status=502, trace_id="abc-123",
                        codigo="x")
    corpo = json.loads(tratar_erro_provedor(None, erro).body)
    assert corpo["trace_id"] == "abc-123"
    assert corpo["provedor"] == "asaas"
