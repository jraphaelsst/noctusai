"""Channel conversations (Lais A2): the product turn API's domain layer.

``retention`` — deletion on request + the 180-day purge (LGPD, contract §10.1
M5). ``tools`` — the page-0 ``handoff`` tool. ``budget`` — the channel-specific
per-org daily cap default (M4). The HTTP surface is
``app/routers/channels_router.py`` (turns / status / deletion) and
``app/routers/channel_token_router.py`` (the §4 token mint).
"""
