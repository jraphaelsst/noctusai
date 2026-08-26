"""Integration provider registry — v1 definition of supported providers.

A single source-of-truth for the FE "connect an account" flow: what
providers are available, whether they support OAuth vs manual key entry,
what fields to show, and which OAuth scopes to request.

Extension recipe (adding a new provider):
  1. Add an entry to ``PROVIDERS`` below (registry entry).
  2. If OAuth: add an ``oauth_start`` + ``oauth_callback`` handler pair in
     ``integration_accounts_router.py`` under the new provider name.
  3. If manual key: add the ``manual_key_fields`` list — FE renders them
     as a form. No backend route changes needed.

Consumers read this via GET /api/integrations/providers.
"""
from __future__ import annotations

from typing import Any

__all__ = ["PROVIDERS", "SUPPORTED_PROVIDER_IDS"]

# Registry of v1 supported providers.
#
# Keys per entry:
#   id            str — machine key (matches the CHECK constraint in the SQL)
#   display_name  str — shown in the UI picker
#   icon          str — icon name the FE resolves via its icon registry
#   oauth_supported bool — True if OAuth flow is available
#   manual_entry  bool — True if a plain API key can also be entered
#   manual_key_fields  list[dict] — fields shown when manual_entry=True
#     each: {name, label, type ("text"|"password"), placeholder}
#   scopes        list[str] — OAuth scopes (only for oauth_supported=True)
#   tutorial_url  str | None — external setup guide
PROVIDERS: list[dict[str, Any]] = [
    {
        # Grupo OLX covers ZAP, VivaReal, OLX and — once the advertiser
        # asks ImovelWeb for an activation code — ImovelWeb and Casa
        # Mineira too. One provider row, because they are one integration.
        #
        # `oauth_supported: False` is the vendor's shape, not a shortcut:
        # OLX issues a static per-CRM secret at homologation and has no
        # OAuth flow at all.
        "id": "olx",
        "display_name": "Grupo OLX (ZAP / VivaReal / ImovelWeb)",
        "icon": "olx",
        "oauth_supported": False,
        "manual_entry": True,
        "manual_key_fields": [
            {
                "name": "webhook_secret",
                "label": "Chave do webhook (SECRET_KEY)",
                "type": "password",
                "placeholder": "Fornecida pelo Grupo OLX na homologação",
            },
            {
                "name": "api_key",
                "label": "X-API-KEY (Gestor de Leads)",
                "type": "password",
                "placeholder": "Opcional — apenas para enviar leads AO OLX",
            },
            {
                "name": "agent_name",
                "label": "X-Agent-Name (Gestor de Leads)",
                "type": "text",
                "placeholder": "Opcional — acompanha o X-API-KEY",
            },
        ],
        "scopes": [],
        "tutorial_url": "https://developers.grupozap.com/webhooks/integration_leads.html",
    },
    {
        # ImovelWeb / Wimoveis / Casa Mineira via OpenNavent — Navent
        # (Grupo QuintoAndar), a DIFFERENT vendor from the `olx` row above
        # despite the overlapping portal names. Grupo OLX does bridge
        # ImovelWeb into its own Gestor de Leads, so an advertiser can be
        # live on both; the leads then arrive twice, under two vendor ids,
        # and the direct pipe is the one that names the portal honestly.
        #
        # `oauth_supported: False` is about the ACCOUNT-CONNECT flow, not
        # about the API: OpenNavent uses OAuth2 client credentials, which
        # is machine-to-machine — no user, no redirect, no per-org consent
        # to collect. There is nothing for the picker to send a user to.
        "id": "imovelweb",
        "display_name": "ImovelWeb / Wimoveis (OpenNavent)",
        "icon": "imovelweb",
        "oauth_supported": False,
        "manual_entry": True,
        "manual_key_fields": [
            {
                "name": "webhook_secret",
                "label": "Chave do callback (definida por nós)",
                "type": "password",
                "placeholder": "Escolhida por nós e registrada no portal",
            },
            {
                "name": "client_id",
                "label": "Client ID (OpenNavent)",
                "type": "text",
                "placeholder": "Fornecido por integracao@imovelweb.com.br",
            },
            {
                "name": "client_secret",
                "label": "Client Secret (OpenNavent)",
                "type": "password",
                "placeholder": "Fornecido junto com o Client ID",
            },
        ],
        "scopes": [],
        "tutorial_url": "https://open-classifieds.notion.site/bra",
    },
    {
        "id": "youtube",
        "display_name": "YouTube",
        "icon": "youtube",
        "oauth_supported": True,
        "manual_entry": False,
        "manual_key_fields": [],
        "scopes": [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
        "tutorial_url": (
            "https://support.google.com/youtube/answer/2657946"
        ),
    },
    {
        "id": "google_drive",
        "display_name": "Google Drive",
        "icon": "google_drive",
        "oauth_supported": True,
        "manual_entry": False,
        "manual_key_fields": [],
        "scopes": [
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        "tutorial_url": None,
    },
    {
        "id": "gmail",
        "display_name": "Gmail",
        "icon": "gmail",
        "oauth_supported": True,
        "manual_entry": False,
        "manual_key_fields": [],
        "scopes": [
            "https://www.googleapis.com/auth/gmail.send",
        ],
        "tutorial_url": None,
    },
    {
        "id": "meta",
        "display_name": "Meta (Facebook / Instagram)",
        "icon": "meta",
        "oauth_supported": True,
        "manual_entry": True,
        "manual_key_fields": [
            {
                "name": "system_user_token",
                "label": "System User Token",
                "type": "password",
                "placeholder": "EAABsbCS...",
            },
        ],
        "scopes": [
            "pages_show_list",
            "instagram_basic",
            "instagram_content_publish",
        ],
        "tutorial_url": (
            "https://developers.facebook.com/docs/facebook-login/guides/access-tokens"
        ),
    },
    {
        "id": "instagram",
        "display_name": "Instagram (Business Login)",
        "icon": "instagram",
        "oauth_supported": True,
        "manual_entry": True,
        "manual_key_fields": [
            {
                "name": "access_token",
                "label": "Access Token",
                "type": "password",
                "placeholder": "IGAA...",
            },
        ],
        "scopes": [
            "instagram_business_basic",
            "instagram_business_manage_messages",
        ],
        "tutorial_url": (
            "https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login"
        ),
    },
    {
        # v2 field-set (2026-07-16): base_url + api_key replace the old
        # webhook_url + optional-api_key shape. Listing/managing workflows
        # needs the instance's public API root ({base_url}/api/v1) + the
        # X-N8N-API-KEY header — a per-workflow webhook_url can't list
        # anything, and an optional api_key meant half the accounts could
        # never call the API at all. Per-workflow webhook run URLs are
        # derived ({base_url}/webhook/{path}) from the workflow's own
        # webhook node at read time, never stored on the account.
        "id": "n8n",
        "display_name": "n8n",
        "icon": "n8n",
        "oauth_supported": False,
        "manual_entry": True,
        "manual_key_fields": [
            {
                "name": "base_url",
                "label": "URL da instância",
                "type": "text",
                "placeholder": "https://n8n.example.com",
            },
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "placeholder": "n8n-api-key",
            },
        ],
        "scopes": [],
        "tutorial_url": "https://docs.n8n.io/api/authentication/",
    },
]

# Set of valid provider ids — mirrors the SQL CHECK constraint.
SUPPORTED_PROVIDER_IDS: frozenset[str] = frozenset(p["id"] for p in PROVIDERS)
