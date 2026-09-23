"""`check_contract_field_provenance_map` — the keeper (backstop) half of the
social-wiring F5 contract-generator field-provenance gate.

WHY (2026-09-17). `contrato_gerador`'s template + context builder together
emit ~140 distinct placeholder tokens; `CONTRACT-FIELD-PROVENANCE-MAP.md` § 3
hand-documents where each one comes from (clause, source document type,
extractor code path, confirmed storage, confirm/promote step, status). A
hand-typed inventory drifts the moment a clause is added to
`modelo_texto.py` without a matching doc row — this keeper is the backstop
so that can never silently regress. CLAUDE.md § 1 gate↔methodology-sync: the
map doc's own § 5 names this keeper as its enforcement mechanism.

Two test classes, pinned against synthetic `contrato_gerador` fixtures (never
the real product tree — the real tree is covered live by
`test_real_map_is_in_sync_with_real_generator` below):
  1. a placeholder token the generator emits but the map doc does not
     document → exactly one `high`-severity issue naming that token
  2. a fully-documented token set → zero issues
Plus honest-degradation coverage: the generator module absent (nothing to
gate), the map doc absent (one issue, not a crash), and a malformed
`TEMPLATE`/`return {...}` shape (returns cleanly, logged not raised).

→ KB § CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md § 3/§ 5.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_contract_field_provenance_map,
)

REPO = Path(__file__).resolve().parents[3]

_GERADOR_REL = "products/social-wiring/backend/app/modules/card_hub/contrato_gerador"
_MAP_REL = "KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md"

_MODELO_TEXTO = '''TEMPLATE = r"""
CLAUSULA {{ cl.objeto.ORD }}
{{ imovel.cidade }} - {{ imovel.uf }}
{%p if tem_financiamento %}
financiado
{%p endif %}
"""
'''

_CONTEXTO_OK = '''def montar_contexto():
    return {
        "cl": None,
        "par": None,
        "brl": None,
        "dias": None,
        "pct_extenso": None,
        "imovel": {},
    }
'''

_DERIVACAO_OK = '''def derivar_switches():
    return {"tem_financiamento": True}
'''

#: § 0a's marker pair (S2) — present in every fixture below EXCEPT
#: `TestSecao0aMarkerGuard`'s own, so the § 3 token-inventory tests stay
#: focused on that one concern (§ 0a's guard is structural-only here; see
#: `_CONTRACT_SECAO_0A_INICIO`/`_FIM` in `compliance.py`).
_SECAO_0A_MARCADORES = (
    "<!-- AUTOGEN:fontes-secao-0a:begin -->\n"
    "<!-- AUTOGEN:fontes-secao-0a:end -->\n"
)

_MAP_FULLY_DOCUMENTED = """# Contract field provenance map (fixture)

| token | §2 group |
|---|---|
| `cl.objeto.ORD` | Contrato / assinatura |
| `imovel` | Imóvel objeto |
| `imovel.cidade` | Imóvel objeto |
| `imovel.uf` | Imóvel objeto |
| `tem_financiamento` | Contrato / assinatura (§1.1 switches) |
""" + _SECAO_0A_MARCADORES

# Same generator, but the map is missing `imovel.uf`'s row.
_MAP_MISSING_ONE_TOKEN = """# Contract field provenance map (fixture)

| token | §2 group |
|---|---|
| `cl.objeto.ORD` | Contrato / assinatura |
| `imovel` | Imóvel objeto |
| `imovel.cidade` | Imóvel objeto |
| `tem_financiamento` | Contrato / assinatura (§1.1 switches) |
""" + _SECAO_0A_MARCADORES


def _write_gerador(root: Path, *, modelo=_MODELO_TEXTO, contexto=_CONTEXTO_OK, derivacao=_DERIVACAO_OK) -> None:
    d = root / _GERADOR_REL
    d.mkdir(parents=True, exist_ok=True)
    (d / "modelo_texto.py").write_text(modelo, encoding="utf-8")
    (d / "contexto.py").write_text(contexto, encoding="utf-8")
    (d / "derivacao.py").write_text(derivacao, encoding="utf-8")


def _write_map(root: Path, body: str) -> None:
    p = root / _MAP_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


class TestMissingTokenIsFlagged:
    def test_undocumented_placeholder_flagged_by_name(self, tmp_path):
        _write_gerador(tmp_path)
        _write_map(tmp_path, _MAP_MISSING_ONE_TOKEN)

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert issues[0]["product"] == "social-wiring"
        assert "imovel.uf" in issues[0]["issue"]
        assert _MAP_REL in issues[0]["file"]

    def test_multiple_undocumented_tokens_each_get_their_own_issue(self, tmp_path):
        _write_gerador(tmp_path)
        _write_map(tmp_path, "# empty map\n\n| token | group |\n|---|---|\n" + _SECAO_0A_MARCADORES)

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        # 5 distinct dotted/bare tokens the fixture template+context+switches
        # emit: cl.objeto.ORD, imovel, imovel.cidade, imovel.uf, tem_financiamento
        flagged = {i["issue"] for i in issues}
        assert len(issues) == 5, issues
        assert any("imovel.uf" in msg for msg in flagged)
        assert any("tem_financiamento" in msg for msg in flagged)


class TestFullyMappedSetPasses:
    def test_every_placeholder_documented_zero_issues(self, tmp_path):
        _write_gerador(tmp_path)
        _write_map(tmp_path, _MAP_FULLY_DOCUMENTED)

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert issues == [], issues

    def test_extra_doc_rows_beyond_the_code_set_are_not_flagged(self, tmp_path):
        # A doc row for a field the generator doesn't (yet) emit — e.g. a
        # `no_source_yet` row with a placeholder name but no live template
        # token — must never be treated as a problem.
        _write_gerador(tmp_path)
        _write_map(
            tmp_path,
            _MAP_FULLY_DOCUMENTED + "| `posse.prorrogacao_dias` | Posse |\n",
        )

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert issues == [], issues


class TestHonestDegradation:
    def test_no_generator_module_returns_no_issues(self, tmp_path):
        # A fixture repo (or a future tree where the generator was removed)
        # with no modelo_texto.py at all — nothing to gate, not an error.
        issues = check_contract_field_provenance_map(repo_root=tmp_path)
        assert issues == []

    def test_generator_present_map_doc_absent_is_one_named_issue(self, tmp_path):
        _write_gerador(tmp_path)
        # No _write_map call — the doc simply does not exist on this tree.

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert _MAP_REL in issues[0]["file"]

    def test_malformed_template_constant_degrades_to_no_issues_not_a_crash(self, tmp_path):
        # `TEMPLATE` renamed / not a plain string assignment — the AST walk
        # can't find its expected shape. Must log + return cleanly, never
        # raise into the caller (compliance checks are advisory infra).
        _write_gerador(tmp_path, modelo="TEMPLATE_RENAMED = 'not the constant we look for'\n")
        _write_map(tmp_path, _MAP_FULLY_DOCUMENTED)

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert issues == []

    def test_malformed_montar_contexto_degrades_to_no_issues_not_a_crash(self, tmp_path):
        _write_gerador(tmp_path, contexto="def montar_contexto():\n    return None\n")
        _write_map(tmp_path, _MAP_FULLY_DOCUMENTED)

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert issues == []


class TestSecao0aMarkerGuard:
    """§ 0a (S2) — structural only: both `AUTOGEN:fontes-secao-0a` markers
    must be present. Byte-identical drift is a different test
    (`test_proveniencia_kb_sync.py`, product-side, imports `fontes.py`
    live) — this keeper never imports product code."""

    def test_missing_both_markers_is_flagged(self, tmp_path):
        _write_gerador(tmp_path)
        _write_map(tmp_path, _MAP_FULLY_DOCUMENTED.replace(_SECAO_0A_MARCADORES, ""))

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        secao_0a = [i for i in issues if "fontes-secao-0a" in i["issue"]]
        assert len(secao_0a) == 1, issues
        assert secao_0a[0]["severity"] == "high"

    def test_missing_one_marker_is_flagged(self, tmp_path):
        _write_gerador(tmp_path)
        so_metade = "<!-- AUTOGEN:fontes-secao-0a:begin -->\n"
        _write_map(tmp_path, _MAP_FULLY_DOCUMENTED.replace(_SECAO_0A_MARCADORES, so_metade))

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert any("fontes-secao-0a" in i["issue"] for i in issues), issues

    def test_both_markers_present_no_secao_0a_issue(self, tmp_path):
        _write_gerador(tmp_path)
        _write_map(tmp_path, _MAP_FULLY_DOCUMENTED)

        issues = check_contract_field_provenance_map(repo_root=tmp_path)

        assert not any("fontes-secao-0a" in i["issue"] for i in issues), issues


class TestContractFieldProvenanceMap:
    """The live guard: the actual repo's map doc must already cover every
    token the actual repo's generator emits. This is the test that fails
    the moment a real clause ships without its provenance row — everything
    above pins the MECHANISM against small synthetic fixtures."""

    def test_real_map_is_in_sync_with_real_generator(self):
        modelo = REPO / _GERADOR_REL / "modelo_texto.py"
        if not modelo.is_file():
            return  # generator not present on this checkout — nothing to assert
        issues = check_contract_field_provenance_map(repo_root=REPO)
        assert issues == [], issues
