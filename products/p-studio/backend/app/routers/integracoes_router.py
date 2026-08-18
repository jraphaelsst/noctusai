"""Webhook do provedor de cobrança, fila de reprocessamento e credenciais.

A rota do webhook é a **única pública que escreve** no sistema. Ela não usa
`get_current_user` porque quem chama é o provedor, não o navegador — a
autenticação é um segredo compartilhado no header.

Sobre responder 200 em quase tudo: o Asaas interrompe a fila de entrega após
15 respostas não-2xx consecutivas, e só volta com reativação manual no painel.
Devolver 500 num evento que não sabemos tratar custa a conciliação de todos os
outros pagamentos. Então a única rejeição normal é 401 — o resto é gravado e
respondido 200, e a rota autenticada de reprocessamento drena o que falhou.

As rotas `/credenciais*` são o lado servidor da tela de Integrações: cadastrar
a chave do Asaas, alternar sandbox ↔ produção e ler o token do webhook para
colar no painel. Nenhuma resposta carrega a chave de API em claro.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_admin_client
from app.dependencies import (
    CurrentUser,
    get_credenciais_service,
    get_current_user,
    get_provedor_cobranca,
    resolver_provedor,
)
from app.providers.tipos import ProvedorCobranca
from app.services.credenciais import AMBIENTES, EncryptionNotConfigured
from app.services.credenciais_service import CredenciaisService, gerar_webhook_token
from app.services.integracao_service import IntegracaoService

router = APIRouter(prefix="/api/integracoes", tags=["integracoes"])


# ── schemas ──────────────────────────────────────────────────────────────

class CredencialIn(BaseModel):
    api_key: str = Field(min_length=8)
    # Ausente PRESERVA o token atual — trocar a chave de API não deve derrubar
    # um webhook já registrado no painel do Asaas.
    webhook_token: Optional[str] = None


class AmbienteIn(BaseModel):
    ambiente: str


# ── autenticação do webhook ──────────────────────────────────────────────

def autenticar_webhook(
    token: Optional[str] = Header(default=None, alias="asaas-access-token"),
) -> str:
    """Autentica o webhook pelo segredo compartilhado e devolve o AMBIENTE.

    O Asaas **não assina o corpo com HMAC** — o que existe é um token que você
    define no painel ao cadastrar o webhook e que volta neste header em toda
    notificação. Como não é preciso ler o corpo cru para validar, nenhuma rota
    precisa virar `async def` só por causa disto.

    Confere contra o token de CADA ambiente cadastrado, não só o ativo, e
    devolve o que casou. Duas razões:

    * O sandbox e a produção são webhooks distintos no painel do Asaas e podem
      estar ambos registrados. Validar só contra o ambiente ativo faria o outro
      tomar 401 — e 15 desses seguidos **param a fila de entrega** daquele
      ambiente até alguém reativar na mão. O ambiente ativo governa qual chave
      EMITE cobrança; não é o mesmo eixo que decide quem pode nos notificar.
    * O ambiente que casou é o contexto correto para interpretar o evento, e é
      ele que vai montar o adapter — um evento do sandbox lido com a chave de
      produção consultaria a cobrança errada.

    `compare_digest` porque é comparação de segredo, e a varredura não faz
    curto-circuito no primeiro acerto pelo mesmo motivo.
    """
    apresentado = token or ""

    # Caminho legado: `ASAAS_WEBHOOK_TOKEN` no `.env`. Mantido para um deploy
    # que ainda não migrou para o banco.
    esperado_env = settings.asaas_webhook_token

    candidatos: list[tuple[str, str]] = []
    if settings.encryption_key:
        servico = get_credenciais_service()
        for ambiente in servico.ambientes_configurados():
            guardado = servico.webhook_token(ambiente)
            if guardado:
                candidatos.append((ambiente, guardado))
    if esperado_env:
        candidatos.append((servico_ambiente_legado(), esperado_env))

    if not candidatos:
        # 503 e não 401: o problema é nosso, não de quem chamou. E fica
        # explícito no log em vez de parecer credencial errada do provedor.
        raise HTTPException(
            status_code=503,
            detail="Webhook não configurado — cadastre a credencial em Integrações.",
        )

    casou: Optional[str] = None
    for ambiente, esperado in candidatos:
        if secrets.compare_digest(apresentado, esperado):
            casou = ambiente
    if casou is None:
        raise HTTPException(status_code=401, detail="Token de webhook inválido")
    return casou


def servico_ambiente_legado() -> str:
    """Ambiente atribuído ao token do `.env`.

    Deriva de `ASAAS_BASE_URL` em vez de assumir sandbox: um deploy legado
    apontado para a API de produção tem um token de produção, e rotulá-lo
    `sandbox` faria o evento ser interpretado com a chave errada.
    """
    return "sandbox" if "sandbox" in (settings.asaas_base_url or "") else "producao"


# ── webhook + fila ───────────────────────────────────────────────────────

@router.post("/asaas/webhook")
def webhook_asaas(
    corpo: dict,
    ambiente: str = Depends(autenticar_webhook),
):
    """Recebe notificação de cobrança.

    Usa o client service-role: a chamada não traz JWT, então não há client
    RLS-scoped a construir. É o primeiro chamador real de `get_admin_client()`,
    que existia justamente para operações administrativas como esta.

    O provedor é montado com a credencial do ambiente QUE AUTENTICOU (ver
    `autenticar_webhook`), não com o ambiente ativo.
    """
    servico = IntegracaoService(get_admin_client(), resolver_provedor(ambiente))
    return servico.receber(corpo)


@router.get("/eventos")
def listar_eventos(
    user: CurrentUser = Depends(get_current_user),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Log dos eventos recebidos. Lê com o client do usuário — aqui a RLS vale."""
    return IntegracaoService(user.db, provedor).pendentes()


@router.post("/reprocessar")
def reprocessar(
    user: CurrentUser = Depends(get_current_user),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Drena os eventos que falharam ao processar.

    Autenticada de propósito: é ação administrativa, e reprocessar em massa
    deve ser um ato deliberado de alguém da equipe.
    """
    return IntegracaoService(user.db, provedor).reprocessar()


# ── credenciais ──────────────────────────────────────────────────────────
#
# Todas autenticadas. A chave de API nunca volta em claro; o token do webhook
# volta só na rota dedicada, porque ele precisa ser colado no painel do Asaas
# e é o backend quem o gerou.

def _validar_ambiente(ambiente: str) -> str:
    if ambiente not in AMBIENTES:
        raise HTTPException(
            status_code=422,
            detail=f"Ambiente inválido: {ambiente!r}. Aceitos: {', '.join(AMBIENTES)}.",
        )
    return ambiente


def _servico(user: CurrentUser) -> CredenciaisService:
    """Constrói o service traduzindo a lacuna de cifra para 503.

    `EncryptionNotConfigured` é falha de CONFIGURAÇÃO DO DEPLOY, não do
    pedido — 503 com a mensagem que diz o que gerar, e não um 500 opaco.
    """
    try:
        return get_credenciais_service()
    except EncryptionNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/credenciais")
def status_credenciais(user: CurrentUser = Depends(get_current_user)):
    """Estado das credenciais — mascarado. É o que a tela desenha."""
    servico = _servico(user)
    dados = servico.status()
    dados["webhook_url"] = _webhook_url()
    return dados


def _webhook_url() -> Optional[str]:
    """A URL a cadastrar no painel do Asaas, ou `None` se o deploy não sabe.

    Resolve pelo esquema canônico da casa (`PRODUCT_URL_P_STUDIO` →
    `PRODUCT_URL_PATTERN` → `public.products.url_base`), nunca por uma
    constante local: `url_base` da linha do catálogo é `http://localhost:8014`
    para TODOS os produtos da frota — inclusive os quatro que servem produção
    hoje — então ele não é o campo de roteamento público, e montar a URL a
    partir dele publicaria um localhost na tela.

    `None` em vez de um palpite: a tela mostra "não foi possível determinar" e
    manda configurar, o que é verdade. Um palpite errado seria pior que o
    silêncio — o dono cadastraria no Asaas uma URL que não existe e as
    notificações iriam para o vazio.
    """
    from noctusai_lib.config.product_urls import resolve_product_url

    try:
        base = resolve_product_url("p-studio")
    except ValueError:
        return None
    if "localhost" in base or "127.0.0.1" in base:
        return None
    return f"{base}/api/integracoes/asaas/webhook"


@router.put("/credenciais/{ambiente}")
def salvar_credencial(
    ambiente: str,
    corpo: CredencialIn,
    user: CurrentUser = Depends(get_current_user),
):
    """Cadastra ou substitui a chave de um ambiente.

    Invalida a memoização de provedores: sem isso o adapter antigo, construído
    com a chave anterior, continuaria sendo servido até o processo reiniciar —
    e o sintoma seria "salvei a chave nova e continua dando 401".
    """
    _validar_ambiente(ambiente)
    servico = _servico(user)
    try:
        resultado = servico.salvar(ambiente, corpo.api_key, corpo.webhook_token)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    from app.providers import limpar_cache

    limpar_cache()
    return resultado


@router.delete("/credenciais/{ambiente}", status_code=204)
def remover_credencial(
    ambiente: str,
    user: CurrentUser = Depends(get_current_user),
):
    _validar_ambiente(ambiente)
    _servico(user).remover(ambiente)

    from app.providers import limpar_cache

    limpar_cache()
    return None


@router.get("/credenciais/{ambiente}/webhook-token")
def ler_webhook_token(
    ambiente: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Devolve o segredo do webhook em claro, para colar no painel do Asaas.

    Rota separada e explícita em vez de campo no `GET /credenciais`: o segredo
    só viaja quando alguém pede por ele, e fica visível no log de acesso como
    um ato distinto de "abrir a tela".
    """
    _validar_ambiente(ambiente)
    token = _servico(user).webhook_token(ambiente)
    if not token:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma credencial cadastrada para o ambiente {ambiente}.",
        )
    return {"ambiente": ambiente, "webhook_token": token}


@router.post("/credenciais/{ambiente}/webhook-token")
def rotacionar_webhook_token(
    ambiente: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Gera um token de webhook novo, preservando a chave de API.

    Depois disto o painel do Asaas precisa ser atualizado — até lá as
    notificações chegam com o token velho e tomam 401.
    """
    _validar_ambiente(ambiente)
    servico = _servico(user)
    atual = servico.credencial(ambiente)
    if not atual or not atual.get("api_key"):
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma credencial cadastrada para o ambiente {ambiente}.",
        )
    novo = gerar_webhook_token()
    servico.salvar(ambiente, atual["api_key"], novo)
    return {"ambiente": ambiente, "webhook_token": novo}


@router.patch("/credenciais/ativo")
def definir_ambiente_ativo(
    corpo: AmbienteIn,
    user: CurrentUser = Depends(get_current_user),
):
    """Alterna qual ambiente EMITE cobrança.

    Só permite ativar um ambiente que tem credencial: ativar o vazio deixaria
    o produto num estado em que toda emissão falha, e o erro apareceria longe
    daqui, na primeira tentativa de cobrar.
    """
    ambiente = _validar_ambiente(corpo.ambiente)
    servico = _servico(user)
    if ambiente not in servico.ambientes_configurados():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Ambiente '{ambiente}' não tem credencial cadastrada — "
                "cadastre a chave antes de ativá-lo."
            ),
        )
    servico.definir_ambiente(ambiente)

    from app.providers import limpar_cache

    limpar_cache()
    return servico.status()
