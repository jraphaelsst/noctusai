"""TEST DATA: the body a platform admin / the content token sends to create the SDR-style platform definition.

Not a code registry -- every attribute is data on the definition row (049), exactly what the UI would send."""
JULIA_BODY = {
    "key": "julia", "nome": "Julia", "runtime": "llm", "owner_product": "social-wiring",
    "escopo_qualificacao": "sdr", "padrao_qualificacao": "imob-lead", "instanciavel": False,
    "rascunho_padrao": {
        "provider": "openai", "model": "gpt-5.6-terra", "effort": "medium", "max_turns": 8,
        "tool_policy": {"web_search": False, "knowledge": False},
    },
}
