"""Regression tests for `check_llm_prompt_from_registry` (owner rule 2026-11-08: agent prompts are
consumed 100% from the database via the prompt registry, never from code). Red + green fixtures on a tmp
repo tree; no network, no real tree except the final baseline-currency check."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import llm_prompt_registry_scan as lps  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    REPO_ROOT,
    check_llm_prompt_from_registry,
    refresh_llm_prompt_from_registry_baseline,
)

SEAM = "from noctusai_lib.integrations.llm import chat_completion\n"


def _write(root: Path, rel: str, src: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if src.startswith(SEAM):  # SEAM is unindented; dedent only the indented body after it
        src = SEAM + textwrap.dedent(src[len(SEAM):])
    p.write_text(textwrap.dedent(src), encoding="utf-8")


def _baseline(root: Path, files: dict[str, int]) -> None:
    p = root.joinpath(*lps.BASELINE_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"files": files}), encoding="utf-8")


class TestLlmPromptFromRegistry:
    def test_clean_tree_no_issues(self, tmp_path):
        assert check_llm_prompt_from_registry(repo_root=tmp_path) == []

    def test_seam_call_flagged(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", SEAM + "async def f():\n    return await chat_completion(messages=[])\n")
        out = check_llm_prompt_from_registry(repo_root=tmp_path)
        assert len(out) == 1 and out[0]["severity"] == "warning" and out[0]["product"] == "p"
        assert "prompt_registry" in out[0]["issue"]

    def test_alias_and_di_default_are_sites(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", """
            from noctusai_lib.integrations.llm import chat_completion as text_fn
            def f(chat_fn=text_fn):
                return chat_fn
            def g(chat_fn=text_fn):
                return chat_fn
        """)
        assert lps.scan_tree(tmp_path)["products/p/backend/app/svc.py"][0]["symbol"] == "chat_completion"
        assert len(lps.scan_tree(tmp_path)["products/p/backend/app/svc.py"]) == 2

    def test_module_attribute_call_flagged(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", """
            from noctusai_lib.integrations import llm
            def f():
                return llm.analyze_image(b"x")
        """)
        assert [x["symbol"] for x in lps.scan_tree(tmp_path)["products/p/backend/app/svc.py"]] == ["analyze_image"]

    def test_vendor_sdk_calls_flagged(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", """
            def f(client):
                client.messages.create(model="m")
                client.chat.completions.create(model="m")
                client.responses.create(model="m")
                client.images.edit(model="m")
                return ClaudeSDKClient()
        """)
        syms = sorted(x["symbol"] for x in lps.scan_tree(tmp_path)["products/p/backend/app/svc.py"])
        assert syms == ["ClaudeSDKClient", "chat.completions.create", "images.edit", "messages.create", "responses.create"]

    def test_digest_narrative_and_help_chat_flagged(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", """
            from noctusai_lib.domain.digest import narrative
            from noctusai_lib.domain.help_chat import create_help_chat_router
            def f():
                create_help_chat_router(knowledge_path="x.md")
                return narrative(None)
        """)
        syms = sorted(x["symbol"] for x in lps.scan_tree(tmp_path)["products/p/backend/app/svc.py"])
        assert syms == ["create_help_chat_router", "digest.narrative"]

    def test_prompt_constant_and_md_load_flagged_but_version_tag_not(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", SEAM + """
            from pathlib import Path
            _SYSTEM_PROMPT = "x"
            PROMPT_VERSION = "v1"
            def f():
                sys_txt = Path("CLAUDE.md").read_text()
                return chat_completion(messages=[{"role": "system", "content": _SYSTEM_PROMPT}, PROMPT_VERSION])
        """)
        kinds = sorted((x["kind"], x["symbol"]) for x in lps.scan_tree(tmp_path)["products/p/backend/app/svc.py"])
        assert kinds == [("call", "chat_completion"), ("md-prompt", "CLAUDE.md"), ("prompt-const", "_SYSTEM_PROMPT")]

    def test_registry_fed_function_is_clean(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", SEAM + """
            from noctusai_lib.integrations.prompt_registry import prompt_e_modelo
            async def f():
                texto, modelo = await prompt_e_modelo("minha.chave")
                return await chat_completion(messages=[{"role": "system", "content": texto}], model=modelo)
        """)
        assert check_llm_prompt_from_registry(repo_root=tmp_path) == []

    def test_unrelated_same_named_method_not_flagged(self, tmp_path):
        _write(tmp_path, "products/p/backend/app/svc.py", """
            def chat_completion(x):
                return x
            def f():
                return chat_completion(1)
        """)
        assert check_llm_prompt_from_registry(repo_root=tmp_path) == []

    def test_exempt_paths_clean(self, tmp_path):
        body = SEAM + "def f():\n    return chat_completion(messages=[])\n"
        for rel in (
            "seed/lib/backend/noctusai_lib/integrations/llm/providers/openai_provider.py",
            "seed/lib/backend/noctusai_lib/integrations/prompt_registry/core.py",
            "mcp/openai_mcp/tools/chat.py",
            "mcp/noctusai/tools/llm/x.py",
            "products/agents/backend/app/runtime/llm_runtime.py",
            "products/agents/backend/app/runtime/eval_driver_live.py",
            "products/agents/backend/app/studio/geracao.py",
            "products/p/backend/tests/test_x.py",
            "products/p/backend/app/test_helper.py",
        ):
            _write(tmp_path, rel, body)
        assert check_llm_prompt_from_registry(repo_root=tmp_path) == []

    def test_baseline_tolerates_then_flags_growth_and_new_file(self, tmp_path):
        rel = "products/p/backend/app/svc.py"
        _write(tmp_path, rel, SEAM + "def f():\n    chat_completion()\n")
        _baseline(tmp_path, {rel: 1})
        assert check_llm_prompt_from_registry(repo_root=tmp_path) == []
        _write(tmp_path, rel, SEAM + "def f():\n    chat_completion()\n    chat_completion()\n")
        assert len(check_llm_prompt_from_registry(repo_root=tmp_path)) == 1
        _write(tmp_path, "products/p/backend/app/new.py", SEAM + "def g():\n    chat_completion()\n")
        _write(tmp_path, rel, SEAM + "def f():\n    chat_completion()\n")
        assert [i["file"] for i in check_llm_prompt_from_registry(repo_root=tmp_path)] == ["products/p/backend/app/new.py"]

    def test_paths_scope_narrows_reporting(self, tmp_path):
        a, b = "products/p/backend/app/a.py", "products/p/backend/app/b.py"
        for rel in (a, b):
            _write(tmp_path, rel, SEAM + "def f():\n    chat_completion()\n")
        assert [i["file"] for i in check_llm_prompt_from_registry(paths=[a], repo_root=tmp_path)] == [a]

    def test_baseline_refresh_only_shrinks_and_drops_deleted_files(self, tmp_path):
        a, b = "products/p/backend/app/a.py", "products/p/backend/app/b.py"
        _write(tmp_path, a, SEAM + "def f():\n    chat_completion()\n    chat_completion()\n")
        _write(tmp_path, b, SEAM + "def f():\n    chat_completion()\n")
        assert refresh_llm_prompt_from_registry_baseline(tmp_path) == {a: 2, b: 1}
        (tmp_path / b).unlink()  # an absorbed product's file is deleted
        _write(tmp_path, a, SEAM + "def f():\n    chat_completion()\n")
        assert refresh_llm_prompt_from_registry_baseline(tmp_path) == {a: 1}
        _write(tmp_path, "products/p/backend/app/c.py", SEAM + "def f():\n    chat_completion()\n")
        assert refresh_llm_prompt_from_registry_baseline(tmp_path) == {a: 1}  # a new site is never ratified

    def test_file_clean_predicate(self, tmp_path):
        rel = "products/p/backend/app/svc.py"
        _write(tmp_path, rel, SEAM + "def f():\n    chat_completion()\n")
        assert lps.file_clean(tmp_path, rel) is False
        (tmp_path / rel).unlink()
        assert lps.file_clean(tmp_path, rel) is True

    def test_real_tree_holds_the_ratchet(self):
        """False-alarm replay: the committed baseline matches the tree, so nothing is flagged beyond it."""
        assert check_llm_prompt_from_registry(repo_root=REPO_ROOT) == []
