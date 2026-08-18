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
    # Default "" DE PROPÓSITO, pelo mesmo motivo escrito no bloco de cobrança
    # logo abaixo: quem exige a credencial é o CAMINHO QUE A USA, não a
    # importação. Sem default, `settings = PStudioSettings()` (fim deste
    # arquivo, padrão da casa em toda a frota) explodia com ValidationError
    # em qualquer processo que apenas IMPORTASSE este módulo sem a env var —
    # e o teste de seed-lib `test_per_product_cors_sentinel` faz exatamente
    # isso: importa o config de cada produto do registry para ler
    # `model_fields['cors_origins'].default`, uma leitura de CLASSE que nunca
    # precisou de uma instância válida. Resultado: `dev` ficou vermelho no
    # instante em que a absorção pôs `p-studio` no registry.
    #
    # 🔴 "" NÃO é um valor utilizável e nunca deve virar um: `org_id` carimba
    # todo INSERT e escopa toda leitura, então um "" que vazasse para uma
    # query seria um erro silencioso — a classe de bug que este repositório
    # trata como inaceitável. O guard está em `dependencies.get_current_user`,
    # o único ponto onde este campo entra num request, e recusa alto.
    org_id: str = Field("", validation_alias="P_STUDIO_ORG_ID")

    # ── Provedor de cobrança ─────────────────────────────────────────────
    # Todos com default: o app precisa subir sem credencial de banco, e a
    # suíte de testes só define as variáveis do Supabase. Quem exige a
    # credencial é o caminho que a usa, não a importação — mesmo padrão de
    # `database.get_admin_client()`.
    #
    # Produção será Banco do Brasil; o Asaas é a casca que destrava o ERP
    # agora. Trocar de provedor é trocar esta variável e o adapter.
    provedor_cobranca: str = "asaas"

    # 🔴 As três variáveis abaixo são o caminho de DESENVOLVIMENTO. Em produção
    # a credencial vive cifrada em `p_studio.provedor_credenciais` (migration
    # 008) e é gerenciada pela tela de Integrações — ver
    # `app/services/credenciais.py`. Elas continuam existindo porque a suíte e
    # o dev local rodam sem banco de credenciais, e porque um deploy que ainda
    # não cadastrou nada precisa continuar de pé. A resolução é banco-primeiro,
    # env-depois, e está em `dependencies.get_provedor_cobranca`.
    asaas_api_key: str = ""
    asaas_base_url: str = "https://api-sandbox.asaas.com/v3"
    # Segredo compartilhado que o Asaas devolve no header `asaas-access-token`
    # de cada notificação. Não há assinatura HMAC.
    asaas_webhook_token: str = ""

    # Chave Fernet que cifra as credenciais em repouso. Sem ela o produto
    # RECUSA gravar credencial (`EncryptionNotConfigured` → 503) em vez de
    # gravar em claro — o degradar-em-silêncio é justamente o que o
    # `token_store` do seed faria sozinho, e o que não queremos aqui.
    #
    # Declarada no produto e não em `ProductSettings` porque hoje N=2 (só o
    # social-wiring tem o campo). Regra de recorrência: N=2 é triagem, N≥3 é
    # formalização obrigatória — o terceiro consumidor promove isto ao seed.
    # → `KB § PATTERNS/architect/project-execution.md`
    encryption_key: str = ""


settings = PStudioSettings()
