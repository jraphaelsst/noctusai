"""GENERATED from deploy/fleet/waha-instances.yml by noctus.dev.waha_instance action='render' -- DO NOT EDIT.

Every host:port (every container/service alias, ports 3000 and 3001) of a `send: disabled` line, with its declared
policy. The seed resolves these STRICTEST-WINS and never lets `"*"` apply to them. check_waha_instances_render_sync
fails when this file differs from the render. KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a.
"""
READ_ONLY_LINES: dict[str, dict] = {
    'noctus-waha-assistant-core:3000': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'noctus-waha-assistant-core:3001': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'noctus-waha-assistant:3000': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'noctus-waha-assistant:3001': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'waha-assistant-core:3000': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'waha-assistant-core:3001': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'waha-assistant:3000': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
    'waha-assistant:3001': {'send': 'disabled', 'mark_online': False, 'full_sync': False, 'auto_repair': False, 'webhook_relay': 'http://waha-assistant:3001'},
}
RESOLVABLE_FROM_PRODUCT_NETWORK: tuple[str, ...] = ('noctus-waha-assistant', 'waha-assistant')
