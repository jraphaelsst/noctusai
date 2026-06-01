"""Regression-test-the-detector for `check_embed_funnel_self_configures` — the
s4 keeper that blocks a new direct `generate_embedding()` call from forgetting
`ensure_llm_configured()`, which would re-open the recurring "LLM not configured"
drift on the live MCP-server path (it never calls configure_llm() at startup).

The keeper was promoted at N=2 (embed_sync 2026-05-30 + embed_text 2026-05-31
were each patched reactively, after a runtime failure) by explicit ratification
instead of waiting for the N=3 production failure.
KB § PATTERNS/common/funnel-self-satisfies-preconditions.md.
"""
from __future__ import annotations


class TestEmbedFunnelSelfConfigures:
    def _tools_file(self, root, rel, body):
        p = root / "mcp" / "noctusai" / "tools" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def test_silent_skip_non_noc_tree(self, tmp_path):
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        assert check_embed_funnel_self_configures(repo_root=tmp_path) == []

    def test_direct_embed_without_bootstrap_flagged_high(self, tmp_path):
        # A new funnel that calls generate_embedding() but forgot the bootstrap —
        # the exact shape that raised "LLM not configured" on the MCP-server path.
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        self._tools_file(tmp_path, "noctus/dev/newembed.py",
            'from noctusai_lib.integrations.llm import generate_embedding\n'
            'def embed_thing(text):\n'
            '    return generate_embedding(text)\n')
        issues = check_embed_funnel_self_configures(repo_root=tmp_path)
        hits = [i for i in issues if i["symbol"] == "embed-without-llm-bootstrap"]
        assert hits and all(i["severity"] == "high" for i in hits)
        assert hits[0]["file"].endswith("newembed.py")

    def test_self_configuring_funnel_not_flagged(self, tmp_path):
        # generate_embedding() + ensure_llm_configured() in the SAME function —
        # the canonical funnel-self-satisfies shape. Must NOT be flagged.
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        self._tools_file(tmp_path, "noctus/dev/newembed.py",
            'from ._llm_bootstrap import ensure_llm_configured\n'
            'from noctusai_lib.integrations.llm import generate_embedding\n'
            'def embed_thing(text):\n'
            '    ensure_llm_configured()\n'
            '    return generate_embedding(text)\n')
        assert check_embed_funnel_self_configures(repo_root=tmp_path) == []

    def test_routed_caller_with_no_direct_embed_not_flagged(self, tmp_path):
        # A caller that routes through embed_sync()/embed_text() holds no direct
        # generate_embedding() call — the funnel already self-configures, so the
        # caller is correctly ignored.
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        self._tools_file(tmp_path, "noctus/dev/newembed.py",
            'from . import _embedding_corpus as _ec\n'
            'def search(query):\n'
            '    return _ec.embed_sync(query)\n')
        assert check_embed_funnel_self_configures(repo_root=tmp_path) == []

    def test_attribute_form_embed_without_bootstrap_flagged(self, tmp_path):
        # `llm.generate_embedding(...)` (Attribute form) is caught the same way.
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        self._tools_file(tmp_path, "noctus/dev/newembed.py",
            'from noctusai_lib.integrations import llm\n'
            'def embed_thing(text):\n'
            '    return llm.generate_embedding(text)\n')
        issues = check_embed_funnel_self_configures(repo_root=tmp_path)
        assert [i for i in issues if i["symbol"] == "embed-without-llm-bootstrap"]

    def test_comment_or_string_mention_not_flagged(self, tmp_path):
        # A docstring / comment that names generate_embedding is not a call.
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        self._tools_file(tmp_path, "noctus/dev/newembed.py",
            '"""This module documents generate_embedding usage."""\n'
            'NAMES = ["generate_embedding"]\n'
            'def embed_thing(text):\n'
            '    return None\n')
        assert check_embed_funnel_self_configures(repo_root=tmp_path) == []

    def test_bootstrap_module_exempt(self, tmp_path):
        # _llm_bootstrap.py defines ensure_llm_configured and performs no embed —
        # exempt by construction (it would never call generate_embedding anyway,
        # but the exemption documents intent).
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        self._tools_file(tmp_path, "noctus/dev/_llm_bootstrap.py",
            'from noctusai_lib.integrations.llm import generate_embedding\n'
            'def probe(text):\n'
            '    return generate_embedding(text)\n')
        assert check_embed_funnel_self_configures(repo_root=tmp_path) == []

    def test_real_repo_has_no_violations(self):
        # Proves both live funnels (embed_sync + embed_text) self-configure AND
        # fails loudly if anyone adds a new direct generate_embedding() without
        # the bootstrap.
        from tools.noctus.dev.compliance import check_embed_funnel_self_configures
        assert check_embed_funnel_self_configures() == []
