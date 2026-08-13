"""P Studio — configuração (pydantic-settings, padrão NoctusAI)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str = ""

    # Organização do estúdio. Deploy single-tenant: o backend carimba este
    # org_id em todo INSERT e a RLS confere contra public.current_org_id().
    # Se divergirem, o banco recusa a escrita — o env var é conveniência,
    # não é o controle de acesso.
    org_id: str

    cors_origins: str = "http://localhost:5176"

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


settings = Settings()
