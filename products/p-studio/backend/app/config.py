"""P Studio — configuração (pydantic-settings, padrão NoctusAI seed).

Estende ``ProductSettings`` do framework: os campos estruturais (Supabase,
CORS, JWT, rate limiting) já vêm prontos por herança — aqui só entram os
campos específicos do domínio (org_id do estúdio + provedor de cobrança).
Absorvido pela plataforma; ``env_file`` passa a ser o ``.env`` da raiz do
monorepo (herdado de ``ProductSettings``), não mais um `.env` local a este
diretório.
"""
from pydantic import Field

from noctusai_seed import ProductSettings


class PStudioSettings(ProductSettings):
    """P Studio specific settings."""

    cors_origins: str = "@registry:own:p-studio"

    # Organização do estúdio. Deploy single-tenant: o backend carimba este
    # org_id em todo INSERT e a RLS confere contra public.current_org_id().
    # Se divergirem, o banco recusa a escrita — o env var é conveniência,
    # não é o controle de acesso.
    #
    # 🔴 Lido de `P_STUDIO_ORG_ID`, não de `ORG_ID`. No workspace standalone
    # o `.env` era só deste produto e `ORG_ID` era inequívoco; depois da
    # absorção o `.env` é da RAIZ e serve a frota inteira. Um `ORG_ID` nu
    # ali dentro é um nome genérico de dono único: o próximo produto que
    # ler `ORG_ID` herda silenciosamente a organização do P Studio, e o
    # sintoma seria escrita recusada pela RLS num produto que nem sabe que
    # este existe. Nenhum outro produto da frota usa nome nu — todos
    # namespaceiam (`meta_ads_org_id`, `local_dev_org_id`).
    #
    # O ATRIBUTO segue `settings.org_id`, então nada no código muda; só a
    # variável de ambiente ganha prefixo.
    org_id: str = Field(validation_alias="P_STUDIO_ORG_ID")

    # ── Provedor de cobrança ─────────────────────────────────────────────
    # Todos com default: o app precisa subir sem credencial de banco, e a
    # suíte de testes só define as variáveis do Supabase. Quem exige a
    # credencial é o caminho que a usa, não a importação — mesmo padrão de
    # `database.get_admin_client()`.
    #
    # Produção será Banco do Brasil; o Asaas é a casca que destrava o ERP
    # agora. Trocar de provedor é trocar esta variável e o adapter.
    provedor_cobranca: str = "asaas"

    asaas_api_key: str = ""
    asaas_base_url: str = "https://api-sandbox.asaas.com/v3"
    # Segredo compartilhado que o Asaas devolve no header `asaas-access-token`
    # de cada notificação. Não há assinatura HMAC.
    asaas_webhook_token: str = ""


settings = PStudioSettings()
