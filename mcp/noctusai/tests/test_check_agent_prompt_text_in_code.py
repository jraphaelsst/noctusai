"""`check_agent_prompt_text_in_code` — Julia v2 D3: prompt text lives in agents DB rows, never in
`products/agents/backend/app/{channels,studio,runtime}`. A per-file RATCHET baseline lets the
pre-existing literals through; only NEW ones block, and a lowered count must lower the baseline.

→ KB § PATTERNS/backend/backend.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    REPO_ROOT,
    _prompt_text_hits,
    check_agent_prompt_text_in_code,
)

APP = "products/agents/backend/app"
BASELINE = "products/agents/backend/prompt-text-baseline.json"


def _tree(root: Path, files: dict[str, str], baseline: dict[str, int] | None = None) -> Path:
    for rel, text in files.items():
        p = root / APP / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    b = root / BASELINE
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"arquivos": baseline or {}}), encoding="utf-8")
    return root


class TestCheckAgentPromptTextInCode:
    def test_tool_description_literal_is_flagged(self, tmp_path):
        _tree(tmp_path, {"channels/tools.py": 'T = ToolSpec(name="x", description="Passa a conversa para uma pessoa.")\n'})
        issues = check_agent_prompt_text_in_code(tmp_path)
        assert len(issues) == 1 and issues[0]["severity"] == "high" and "ToolSpec(description=...)" in issues[0]["issue"]

    def test_section_content_system_constant_and_long_constant_are_flagged(self, tmp_path):
        src = (
            'S = SectionInput(chave="p", titulo="P", ordem=1, conteudo="Você é a Julia.")\n'
            '_RESUMO_SYSTEM = "Resuma."\n'
            'FALLBACK_REPLY = "Não consegui concluir esse pedido agora. Pode reformular a mensagem, por favor?"\n'
        )
        _tree(tmp_path, {"runtime/x.py": src})
        assert len(_prompt_text_hits(src)) == 3
        assert len(check_agent_prompt_text_in_code(tmp_path)) == 1  # one issue per file, naming all three

    def test_structure_is_clean(self, tmp_path):
        src = (
            'ToolSpec(name="x", description=row.descricao)\n'
            'SectionInput(chave="p", titulo="P", ordem=1, conteudo=row.conteudo)\n'
            'KEY = "handoff"\n'
            'MAX_TURNS = 8\n'
            'SECRET_LABEL = "curto"\n'
            'x = ToolSpec(name="y", description="")\n'
        )
        _tree(tmp_path, {"studio/ok.py": src})
        assert check_agent_prompt_text_in_code(tmp_path) == []

    def test_baseline_lets_existing_literals_through_but_not_new_ones(self, tmp_path):
        src = '_A_SYSTEM = "um"\n_B_SYSTEM = "dois"\n'
        _tree(tmp_path, {"channels/c.py": src}, baseline={f"{APP}/channels/c.py": 1})
        issues = check_agent_prompt_text_in_code(tmp_path)
        assert len(issues) == 1 and "baseline allows 1" in issues[0]["issue"]
        _tree(tmp_path, {"channels/c.py": src}, baseline={f"{APP}/channels/c.py": 2})
        assert check_agent_prompt_text_in_code(tmp_path) == []

    def test_the_ratchet_only_shrinks_a_lowered_count_must_lower_the_baseline(self, tmp_path):
        _tree(tmp_path, {"channels/c.py": '_A_SYSTEM = "um"\n'}, baseline={f"{APP}/channels/c.py": 3})
        issues = check_agent_prompt_text_in_code(tmp_path)
        assert len(issues) == 1 and "lower" in issues[0]["issue"]

    def test_a_deleted_file_must_leave_the_baseline(self, tmp_path):
        _tree(tmp_path, {"channels/other.py": "x = 1\n"}, baseline={f"{APP}/channels/gone.py": 2})
        assert "gone" in check_agent_prompt_text_in_code(tmp_path)[0]["issue"]

    def test_noc_allow_escape_on_the_line(self, tmp_path):
        _tree(tmp_path, {"studio/e.py": '_X_SYSTEM = "x"  # noc-allow: prompt-text-in-code — not model-visible\n'})
        assert check_agent_prompt_text_in_code(tmp_path) == []

    def test_scope_is_channels_studio_runtime_and_the_channels_router_only(self, tmp_path):
        _tree(tmp_path, {
            "services/s.py": '_A_SYSTEM = "fora do escopo"\n',
            "routers/channels_router.py": '_RESUMO_SYSTEM = "no escopo"\n',
        }, baseline={f"{APP}/routers/channels_router.py": 1})
        assert check_agent_prompt_text_in_code(tmp_path) == []

    def test_the_live_repo_is_at_its_baseline(self):
        assert check_agent_prompt_text_in_code(REPO_ROOT) == []
