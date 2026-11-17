"""GENERATED from deploy/fleet/waha-instances.yml by noctus.dev.waha_instance action='render' -- DO NOT EDIT.

The closed list of declared WhatsApp lines: name -> product, base_url, session, the ENV NAMES of the api key and the
webhook HMAC secret (never values), `shared` (the legacy shared host) and the declared line policy.
check_waha_instances_render_sync fails when this file differs from the render. KB § CONTEXT/INTEGRATIONS/whatsapp.md.
"""
DECLARED_LINES: dict[str, dict] = {
    'assistant': {'product': 'assistant', 'base_url': 'http://waha-assistant:3000', 'session': 'default', 'api_key_env': 'WAHA_ASSISTANT_API_KEY', 'hmac_secret_env': 'WAHA_ASSISTANT_HMAC_SECRET', 'shared': False, 'line_policy': {'send': 'enabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False}},
    'nosnolimiar': {'product': 'nosnolimiar', 'base_url': 'http://waha-nosnolimiar:3000', 'session': 'default', 'api_key_env': 'WAHA_NOSNOLIMIAR_API_KEY', 'hmac_secret_env': 'WAHA_NOSNOLIMIAR_HMAC_SECRET', 'shared': False, 'line_policy': {'send': 'enabled', 'mark_online': True, 'full_sync': True, 'auto_repair': True}},
    'shared': {'product': 'social-wiring', 'base_url': 'http://waha:3000', 'session': 'default', 'api_key_env': 'WAHA_API_KEY', 'hmac_secret_env': 'WAHA_WEBHOOK_HMAC_SECRET', 'shared': True, 'line_policy': {'send': 'enabled', 'mark_online': True, 'full_sync': True, 'auto_repair': True}},
    'sw-vendas': {'product': 'social-wiring', 'base_url': 'http://waha-sw-vendas:3000', 'session': 'default', 'api_key_env': 'WAHA_SW_VENDAS_API_KEY', 'hmac_secret_env': 'WAHA_SW_VENDAS_HMAC_SECRET', 'shared': False, 'line_policy': {'send': 'enabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False}},
}
