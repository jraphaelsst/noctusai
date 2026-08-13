"""P Studio — configuração (pydantic-settings, padrão NoctusAI seed).

Estende ``ProductSettings`` do framework: os campos estruturais (Supabase,
CORS, JWT, rate limiting) já vêm prontos por herança — aqui só entram os
campos específicos do domínio (org_id do estúdio + provedor de cobrança).
Absorvido pela plataforma; ``env_file`` passa a ser o ``.env`` da raiz do
monorepo (herdado de ``ProductSettings``), não mais um `.env` local a este
diretório.
"""
from noctusai_seed import ProductSettings


class PStudioSettings(ProductSettings):
    """P Studio specific settings."""

    cors_origins: str = "@registry:own:p-studio"

    # Organização do estúdio. Deploy single-tenant: o backend carimba este
    # org_id em todo INSERT e a RLS confere contra public.current_org_id().
    # Se divergirem, o banco recusa a escrita — o env var é conveniência,
    # não é o controle de acesso.
    org_id: str

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
