"""D26 keeper — product backends never import the `anthropic` / `openai` SDK
directly; every LLM call goes through `noctusai_lib.integrations.llm` so it lands
in the central ledger `public.ai_usage` (D25)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tools.noctus.dev.compliance import check_no_direct_llm_sdk_import


def _repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="direct_llm_sdk_"))
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root


APP = "products/acme/backend/app/services/x.py"


def test_import_anthropic_is_flagged():
    issues = check_no_direct_llm_sdk_import(_repo({APP: "import anthropic\n"}))
    assert len(issues) == 1 and issues[0]["severity"] == "high"
    assert "anthropic" in issues[0]["issue"]


def test_from_openai_import_is_flagged():
    assert len(check_no_direct_llm_sdk_import(_repo({APP: "from openai import AsyncOpenAI\n"}))) == 1


def test_submodule_and_dynamic_import_are_flagged():
    body = "from openai.types import Model\nimport importlib\nm = importlib.import_module('anthropic')\n"
    assert len(check_no_direct_llm_sdk_import(_repo({APP: body}))) == 2


def test_the_seed_seam_is_clean():
    body = "from noctusai_lib.integrations.llm import chat_completion\n"
    assert check_no_direct_llm_sdk_import(_repo({APP: body})) == []


def test_seed_and_product_tests_are_out_of_scope():
    repo = _repo({
        "seed/lib/backend/noctusai_lib/integrations/llm/providers/openai_provider.py": "import openai\n",
        "products/acme/backend/tests/test_x.py": "import anthropic\n",
    })
    assert check_no_direct_llm_sdk_import(repo) == []


def test_prose_mentions_are_not_imports():
    body = '"""We used to import anthropic directly."""\nx = "from openai import AsyncOpenAI"\n'
    assert check_no_direct_llm_sdk_import(_repo({APP: body})) == []


def test_escape_hatch_needs_the_comment():
    body = "# llm-sdk-direct-ok: realtime voice API is not wrapped by the seed yet\nimport openai\n"
    assert check_no_direct_llm_sdk_import(_repo({APP: body})) == []


def test_live_tree_is_clean():
    """Run it against the real repo — the D26 baseline is zero offenders."""
    assert check_no_direct_llm_sdk_import() == []
