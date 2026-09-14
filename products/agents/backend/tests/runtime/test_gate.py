"""``app.runtime.gate`` — the exact §E.4 table + exhaustiveness."""
from app.runtime import gate


class TestClassify:
    def test_every_leitura_name_classifies_leitura(self):
        for name in gate.LEITURA:
            assert gate.classify(name) == "leitura", name

    def test_every_escrita_name_classifies_escrita(self):
        for name in gate.ESCRITA:
            assert gate.classify(name) == "escrita", name

    def test_unknown_tool_is_denied(self):
        assert gate.classify("Bash") == "deny"
        assert gate.classify("mcp__academia__kb_apagar") == "deny"
        assert gate.classify("") == "deny"

    def test_exact_match_not_prefix_match(self):
        # A near-miss / versioned / extended name must NOT slip through as
        # an accidental leitura (contract §E.4: "architect debt" — exact
        # string equality, never endswith/startswith).
        assert gate.classify("mcp__academia__kb_escrever_v2") == "deny"
        assert gate.classify("mcp__academia__kb_escreverX") == "deny"
        assert gate.classify("xmcp__academia__kb_buscar") == "deny"

    def test_leitura_and_escrita_are_disjoint(self):
        assert set(gate.LEITURA) & set(gate.ESCRITA) == set()

    def test_leitura_includes_base_builtins(self):
        assert "WebSearch" in gate.LEITURA
        assert "Skill" in gate.LEITURA

    def test_escrita_has_exactly_twelve_academia_tools(self):
        assert len(gate.ESCRITA) == 12
        assert all(name.startswith("mcp__academia__") for name in gate.ESCRITA)


class TestResumo:
    def test_kb_escrever_resumo_names_titulo_and_categoria(self):
        text = gate.resumo(
            "mcp__academia__kb_escrever",
            {"titulo": "Regras de descarte", "categoria": "dominio", "corpo_md": "x", "motivo": "m"},
        )
        assert "Regras de descarte" in text
        assert "dominio" in text

    def test_every_escrita_tool_has_a_dedicated_resumo_branch(self):
        # A generic fallback string would be a silently-uninformative
        # approval card — every real escrita tool must hit a specific branch.
        for name in gate.ESCRITA:
            text = gate.resumo(name, {})
            assert text != f"Executar {name}.", name

    def test_resumo_never_raises_on_missing_fields(self):
        for name in gate.ESCRITA:
            gate.resumo(name, {})  # must not raise

    def test_resumo_on_unknown_tool_is_total_not_raising(self):
        text = gate.resumo("mcp__academia__nao_existe", {"a": 1})
        assert "mcp__academia__nao_existe" in text

    def test_resumo_truncates_long_titles(self):
        long_title = "x" * 200
        text = gate.resumo("mcp__academia__decisao_registrar", {"titulo": long_title})
        assert len(text) < len(long_title)
        assert "…" in text
