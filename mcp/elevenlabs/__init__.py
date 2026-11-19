"""`mcp/elevenlabs` — ElevenLabs audio connector MCP.

A connector-MCP server (composes `mcp/_kit`, same shape as `mcp/waha` /
`mcp/n8n`) that lets agents create audio with ElevenLabs: text-to-speech
(with word timings), voice lookup (own + shared), model list, account
usage, instant voice cloning and voice deletion — as LLM-callable
`elevenlabs.<service>.<action>` tools.

Credit-spending and consent-bearing calls (TTS, clone, delete) are
confirm-gated (412, no side-effect). The API key (`ELEVENLABS_API_KEY`)
lives in the co-located gitignored `mcp/elevenlabs/.env`. See README.md.
"""
__version__ = "0.1.0"
