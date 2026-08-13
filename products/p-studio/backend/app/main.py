"""P Studio — backend FastAPI (padrão NoctusAI product).

Gestão operacional e financeira de uma produtora de fotografia e audiovisual
imobiliário. Rodar com: uvicorn app.main:app --reload --port 8020

Produto standalone construído nos moldes da plataforma NoctusAI: schema
`p_studio` no Postgres compartilhado, RLS por organização, routers/services/
schemas por domínio, migrations SQL numeradas. Na absorção pela plataforma,
este app passa a ser criado por `create_product_app()` do noctusai_seed.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.providers.erros import ErroProvedor
from app.routers.cadastros_router import (
    clientes_router,
    equipamentos_router,
    imoveis_router,
    servicos_router,
)
from app.routers.captacoes_router import router as captacoes_router
from app.routers.dashboard_router import router as dashboard_router
from app.routers.financeiro_router import router as financeiro_router
from app.routers.integracoes_router import router as integracoes_router
from app.routers.me_router import router as me_router
from app.routers.negocios_router import router as negocios_router
from app.routers.producoes_router import router as producoes_router

app = FastAPI(title="P Studio", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me_router)
app.include_router(dashboard_router)
app.include_router(clientes_router)
app.include_router(imoveis_router)
app.include_router(servicos_router)
app.include_router(equipamentos_router)
app.include_router(negocios_router)
app.include_router(captacoes_router)
app.include_router(producoes_router)
app.include_router(financeiro_router)
app.include_router(integracoes_router)


# Status do provedor que chegam ao nosso cliente sem tradução. Todo o resto
# vira 502.
#
# A régua é: repassa quando o status descreve algo que o CHAMADOR pode agir a
# respeito. Um 400 do Asaas significa que o payload que *nós* montamos estava
# errado — devolver 400 culparia o usuário por um bug nosso, e é por isso que
# 400/422 não estão aqui. Já um 404 significa que a cobrança não existe mais no
# provedor (apagada no painel, por exemplo), e a tela precisa distinguir isso de
# "o Asaas caiu" para dizer a coisa certa.
REPASSADOS = {
    404: 404,  # cobrança inexistente no provedor
    429: 429,  # rate limit — o cliente deve recuar, não repetir na hora
    503: 503,  # provedor não configurado (nosso, não deles)
    504: 504,  # timeout
}


@app.exception_handler(ErroProvedor)
def tratar_erro_provedor(_: Request, erro: ErroProvedor) -> JSONResponse:
    """Traduz falha de provedor externo em resposta HTTP.

    O primeiro exception handler do projeto, e existe por um motivo preciso:
    `ErroProvedor` não é `HTTPException` de propósito, porque também é
    levantado no webhook e no reprocessamento, onde erro HTTP seria a resposta
    errada. Aqui ele vira HTTP só quando a origem foi mesmo uma rota.

    502/504 e não 500: a falha é de um sistema a jusante, e a distinção importa
    para quem lê o log — 500 manda procurar bug nosso.
    """
    status = REPASSADOS.get(erro.status, 502)
    return JSONResponse(
        status_code=status,
        content={
            "detail": erro.mensagem,
            "provedor": erro.provedor,
            "codigo": erro.codigo,
            # O suporte do banco pede isto. Devolver junto evita a ida e volta
            # de "manda o traceId da chamada".
            "trace_id": erro.trace_id,
            "retentavel": erro.retentavel,
        },
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "p-studio"}
