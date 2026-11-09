"""The thread history Julia reads is fitted to a token budget by the server; a short one is byte-identical."""
from __future__ import annotations

from app.channels.turno import ajustar_janela_historico


def test_short_conversation_prompt_is_byte_identical():
    linhas = [("user", "oi, tudo bem?"), ("assistant", "Oi! Posso ajudar?"), ("system", '{"x":1}'), ("user", "quero visitar")]
    out = ajustar_janela_historico(linhas)
    assert out == tuple(linhas)
    assert "\n".join(f"{r}:{t}" for r, t in out) == "\n".join(f"{r}:{t}" for r, t in linhas)


def test_forty_realistic_whatsapp_messages_are_not_touched():
    linhas = [("user" if i % 2 == 0 else "assistant", "mensagem de whatsapp de tamanho normal " * 6) for i in range(40)]
    assert ajustar_janela_historico(linhas) == tuple(linhas)


def test_pathological_history_is_trimmed_keeping_the_latest():
    linhas = [("user" if i % 2 == 0 else "assistant", "z" * 4000) for i in range(41)]
    out = ajustar_janela_historico(linhas, max_tokens=5000)
    assert out[-1] == linhas[-1] and len(out) < len(linhas) and out[0][0] == "user"
