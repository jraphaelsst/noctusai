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
