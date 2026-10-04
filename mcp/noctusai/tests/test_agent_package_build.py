"""Tests for noctus.dev.agent_package_build + agent_pull (agent-packages CONTRACT §B/§C/§E/§H).

Fixture package is generated under tmp_path — never depends on products/agents/packages/.
compile_prompt is the REAL Studio compiler (loaded from products/agents/backend).
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from tools.noctus.dev import agent_package_build as apb
from tools.noctus.dev import agent_pull as ap

REPO_ROOT = Path(__file__).resolve().parents[3]
KEY = "fix-advisor"

LEARN_HEAD = "| Data | Tipo | Aprendizado | Evidência | Status |\n|---|---|---|---|---|\n"
UP_ROW_A = "| 2026-10-01 | pitfall | Nunca assuma X | commit abc | new |\n"
UP_ROW_B = "| 2026-10-02 | practice | Prefira Y | PR 12 | promoted |\n"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_package(packages: Path, *, idioma="pt-BR", tools=("Read", "Grep", "Glob"), kind="dev-advisor") -> Path:
    root = packages / KEY
    _write(root / "package.yaml", yaml.safe_dump({
        "formato": "noctus.agent-package/v1", "key": KEY, "nome": "Fixture advisor",
        "descricao": "Advisor: used when testing the build.", "kind": kind, "idioma": idioma,
        "versao": "0.1.0", "owners": ["x"],
        "runtime": {"model": "claude-sonnet-5", "effort": "medium", "max_turns": 30,
                    "tool_policy": {"web_search": False, "knowledge": True}},
        "claude_code": {"tools": list(tools)}, "consumers": ["a/b"],
    }, allow_unicode=True))
    _write(root / "sections/10-identidade.md", "---\nchave: identidade\ntitulo: Identidade\nordem: 10\n---\nVocê é o advisor.\n")
    _write(root / "sections/20-regras.md", "---\nchave: regras\ntitulo: Regras\nordem: 20\n---\nSeja breve.\n")
    _write(root / "skills/revisar/SKILL.md", "---\nnome: revisar\ndescricao: Revisa algo\nordem: 10\n---\nPasso 1.\n")
    _write(root / "skills/revisar/references/guia.md", "# Guia\n\nconteúdo\n")
    _write(root / "knowledge/base/_collection.yaml", "nome: Base\ntag: BA\ndescricao: tudo\nordem: 10\n")
    _write(root / "knowledge/base/doc-um.md", "---\ntitulo: Doc um\ntipo: sintese\nproveniencia:\n  autor: eu\n---\nCorpo do doc.\n")
    _write(root / "evals.json", json.dumps([{
        "slug": "caso-um", "titulo": "Caso", "entrada": "pergunta?", "contexto": None,
        "criterios": {"deve": ["responde"], "nao_deve": ["inventa"]}, "rubrica": None, "tags": ["t"]}]))
    _write(root / "LEARNINGS.md", "# Learnings\n\n" + LEARN_HEAD + UP_ROW_A + UP_ROW_B)
    _write(root / "CHANGELOG.md", "# Changelog\n\n## 0.1.0\n\n- first cut\n")
    return root


@pytest.fixture
def packages(tmp_path):
    p = tmp_path / "packages"
    make_package(p)
    return p


def build(packages, **kw):
    return apb.agent_package_build(KEY, packages_dir=str(packages), repo_root=str(REPO_ROOT), **kw)


# ── validation ──────────────────────────────────────────────────────────────


def test_valid_package_builds_and_writes_dist(packages):
    r = build(packages)
    assert r["ok"], r
    assert r["status"] == "built"
    assert r["importer_validation"]["status"] in {"ok", "ok_subset_f", "skipped"}
    dist = packages / KEY / "dist"
    assert (dist / "bundle.json").is_file()
    assert (dist / "claude" / ".claude" / "agents" / f"{KEY}.md").is_file()
    assert (dist / "claude" / "agents" / KEY / "skills/revisar/references/guia.md").is_file()
    assert (dist / "claude" / "agents" / KEY / "knowledge/base/_collection.yaml").is_file()
    bundle = json.loads((dist / "bundle.json").read_text())
    assert bundle["agente"]["kind"] == "dev-advisor"
    assert bundle["versao"]["versao_semver"] == "0.1.0"
    assert bundle["versao"]["package_sha"] == r["sha"]
    assert bundle["versao"]["notas"].startswith("- first cut")


def test_duplicate_section_chave_rejected(packages):
    _write(packages / KEY / "sections/30-regras.md", "---\nchave: regras\ntitulo: Dup\nordem: 30\n---\nx\n")
    r = build(packages)
    assert not r["ok"] and any("duplicate chave" in e for e in r["errors"])


def test_duplicate_skill_nome_via_folder_mismatch_rejected(packages):
    _write(packages / KEY / "skills/outra/SKILL.md", "---\nnome: revisar\ndescricao: d\nordem: 20\n---\ncorpo\n")
    r = build(packages)
    assert not r["ok"]
    assert any("must equal the folder name" in e for e in r["errors"]) and any("duplicate nome" in e for e in r["errors"])


def test_bad_evals_rejected(packages):
    _write(packages / KEY / "evals.json", json.dumps([
        {"slug": "a", "titulo": "t", "entrada": "e", "criterios": {"deve": [], "nao_deve": []}},
        {"slug": "a", "titulo": "t", "entrada": "e", "criterios": {"deve": ["x"]}, "extra": 1},
    ]))
    r = build(packages)
    assert not r["ok"]
    joined = "\n".join(r["errors"])
    assert "at least one item" in joined and "duplicate 'a'" in joined and "unknown key 'extra'" in joined


@pytest.mark.parametrize("tool", ["Write", "Edit", "Bash"])
def test_write_tool_on_dev_advisor_refused(tmp_path, tool):
    p = tmp_path / "pk"
    make_package(p, tools=("Read", tool))
    r = apb.agent_package_build(KEY, packages_dir=str(p), repo_root=str(REPO_ROOT))
    assert not r["ok"] and any("A10" in e for e in r["errors"])


def test_runtime_kind_may_carry_other_tools(tmp_path):
    p = tmp_path / "pk"
    make_package(p, tools=("Read", "Write"), kind="runtime")
    assert apb.agent_package_build(KEY, packages_dir=str(p), repo_root=str(REPO_ROOT))["ok"]


def test_changelog_must_mention_version(packages):
    _write(packages / KEY / "CHANGELOG.md", "# Changelog\n\n## 0.0.9\n- old\n")
    r = build(packages)
    assert not r["ok"] and any("CHANGELOG.md" in e for e in r["errors"])


def test_bad_learnings_row_rejected(packages):
    _write(packages / KEY / "LEARNINGS.md", LEARN_HEAD + "| 2026 | nonsense | x | y | new |\n")
    r = build(packages)
    assert not r["ok"] and any("tipo" in e for e in r["errors"])


# ── determinism + output shape ──────────────────────────────────────────────


def test_sha_deterministic_and_ignores_dist(packages):
    root = packages / KEY
    a = apb.package_sha(root)
    build(packages)  # writes dist/
    assert apb.package_sha(root) == a
    _write(root / "sections/20-regras.md", "---\nchave: regras\ntitulo: Regras\nordem: 20\n---\nOutro.\n")
    assert apb.package_sha(root) != a


def test_build_twice_same_compiled_hash(packages):
    a, b = build(packages), build(packages)
    assert a["compiled_hash"] == b["compiled_hash"] and a["sha"] == b["sha"]


def test_frontmatter_and_header_comment(packages):
    r = build(packages)
    md = (packages / KEY / "dist/claude/.claude/agents" / f"{KEY}.md").read_text(encoding="utf-8")
    lines = md.splitlines()
    assert lines[0] == "---" and lines[1] == f"name: {KEY}"
    assert json.loads(lines[2].split("description: ", 1)[1]) == "Advisor: used when testing the build."
    assert lines[3] == "tools: Read, Grep, Glob" and lines[4] == "---"
    assert lines[5] == (f"<!-- GENERATED by noctus.dev.agent_pull from {KEY}@0.1.0 (sha {r['sha'][:12]}) — do not edit -->")
    assert "# Identidade" in md and "Você é o advisor." in md  # compiled by the real compile_prompt
    pj = json.loads((packages / KEY / "dist/claude/agents" / KEY / "PACKAGE.json").read_text())
    assert pj["sha"] == r["sha"] and pj["compiled_hash"] == r["compiled_hash"] and pj["versao"] == "0.1.0"


def test_adapter_block_per_language(tmp_path):
    pt, en = tmp_path / "pt", tmp_path / "en"
    make_package(pt, idioma="pt-BR")
    make_package(en, idioma="en")
    for pk in (pt, en):
        assert apb.agent_package_build(KEY, packages_dir=str(pk), repo_root=str(REPO_ROOT))["ok"]
    mdp = (pt / KEY / "dist/claude/.claude/agents" / f"{KEY}.md").read_text(encoding="utf-8")
    mde = (en / KEY / "dist/claude/.claude/agents" / f"{KEY}.md").read_text(encoding="utf-8")
    assert "# Superfície: Claude Code" in mdp and f"agents/{KEY}/skills/<nome>/SKILL.md" in mdp
    assert "as linhas mais recentes prevalecem" in mdp
    assert "# Surface: Claude Code" in mde and "newest rows win" in mde and "# Superfície" not in mde
    assert mdp.rstrip().endswith("citando a tag da coleção.")


# ── learnings merge ─────────────────────────────────────────────────────────


def test_merge_preserves_consumer_adds_upstream_idempotent():
    up = LEARN_HEAD + UP_ROW_A + UP_ROW_B
    consumer_row = "| 2026-10-03 | decision | Só do consumidor | local | novo |\n"
    cons = "# Mine\n\n" + LEARN_HEAD + consumer_row + UP_ROW_A + "\nnota final\n"
    merged, added = apb.merge_learnings(cons, up)
    assert [r.texto for r in added] == ["Prefira Y"]
    assert merged.index(consumer_row) < merged.index(UP_ROW_A) < merged.index(UP_ROW_B)
    assert merged.count(UP_ROW_A) == 1 and "nota final" in merged
    again, added2 = apb.merge_learnings(merged, up)
    assert again == merged and added2 == []


def test_merge_without_table_appends_header():
    merged, added = apb.merge_learnings("# only prose\n", LEARN_HEAD + UP_ROW_A)
    assert "# only prose" in merged and apb.LEARNINGS_HEADER in merged and len(added) == 1


def test_row_sha_identity_ignores_status_and_whitespace():
    assert apb.row_sha("2026-10-01", "Nunca  assuma X") == apb.row_sha("2026-10-01", "Nunca assuma X")
    assert apb.row_sha("2026-10-01", "a") != apb.row_sha("2026-10-02", "a")


# ── agent_pull ──────────────────────────────────────────────────────────────

NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def pull(packages, repo, **kw):
    return ap.agent_pull(KEY, str(repo), packages_dir=str(packages), repo_root=str(REPO_ROOT), now=NOW, **kw)


def test_pull_dry_run_writes_nothing(packages, tmp_path):
    repo = tmp_path / "consumer"
    repo.mkdir()
    r = pull(packages, repo)
    assert r["ok"] and r["status"] == "planned" and r["to_write"]
    assert not any(repo.iterdir())


def test_pull_confirm_writes_lock_and_is_idempotent(packages, tmp_path):
    repo = tmp_path / "consumer"
    repo.mkdir()
    r = pull(packages, repo, confirm=True, install_hook=True)
    assert r["status"] == "pulled" and r["install_hook"]["hook"] == "install"  # full hook coverage: test_agent_sync_tools.py
    lock = json.loads((repo / "agents.lock.json").read_text())
    assert lock["formato"] == "noctus.agents-lock/v1"
    assert lock["agents"] == [{"key": KEY, "versao": "0.1.0", "sha": apb.package_sha(packages / KEY)}]
    assert (repo / f".claude/agents/{KEY}.md").is_file()
    assert (repo / f"agents/{KEY}/skills/revisar/SKILL.md").is_file()
    again = pull(packages, repo, confirm=True)
    assert again["status"] == "up_to_date" and not again["to_write"]


def test_pull_merges_learnings_and_keeps_project_block_and_removes_stale(packages, tmp_path):
    repo = tmp_path / "consumer"
    pull(packages, (repo.mkdir() or repo), confirm=True)
    lp = repo / f"agents/{KEY}/LEARNINGS.md"
    local = "| 2026-10-09 | decision | Local | l | novo |\n"
    lp.write_text(lp.read_text() + local)
    lock = json.loads((repo / "agents.lock.json").read_text())
    lock["project"] = {"slug": "p"}
    (repo / "agents.lock.json").write_text(json.dumps(lock))
    # upstream: new learning, bumped version, a skill removed
    root = packages / KEY
    _write(root / "LEARNINGS.md", (root / "LEARNINGS.md").read_text() + "| 2026-10-04 | pitfall | Novo upstream | e | new |\n")
    _write(root / "package.yaml", (root / "package.yaml").read_text().replace("0.1.0", "0.2.0"))
    _write(root / "CHANGELOG.md", "## 0.2.0\n- two\n## 0.1.0\n- one\n")
    shutil.rmtree(root / "skills")
    r = pull(packages, repo, confirm=True)
    text = lp.read_text()
    assert local in text and "Novo upstream" in text and text.count("Nunca assuma X") == 1
    assert [x["texto"] for x in r["learnings_added"]] == ["Novo upstream"]
    assert not (repo / f"agents/{KEY}/skills/revisar/SKILL.md").exists()
    new_lock = json.loads((repo / "agents.lock.json").read_text())
    assert new_lock["project"] == {"slug": "p"} and new_lock["agents"][0]["versao"] == "0.2.0"


# ── check mode ──────────────────────────────────────────────────────────────


def test_check_mode_detects_hand_edit_missing_and_extra(packages, tmp_path):
    repo = tmp_path / "consumer"
    pull(packages, (repo.mkdir() or repo), confirm=True)
    ok = build(packages, check=str(repo))
    assert ok["ok"] and ok["status"] == "check_ok"
    md = repo / f".claude/agents/{KEY}.md"
    md.write_text(md.read_text().replace("Seja breve.", "Seja longo."))
    (repo / f"agents/{KEY}/skills/revisar/references/guia.md").unlink()
    _write(repo / f"agents/{KEY}/knowledge/base/intruso.md", "x")
    bad = build(packages, check=str(repo))
    assert not bad["ok"] and bad["status"] == "check_failed"
    assert bad["check"]["missing"] == [f"agents/{KEY}/skills/revisar/references/guia.md"]
    assert bad["check"]["extra"] == [f"agents/{KEY}/knowledge/base/intruso.md"]
    assert "Seja longo." in bad["check"]["changed"][0]["diff"]


def test_check_ignores_consumer_learnings_and_built_at(packages, tmp_path):
    repo = tmp_path / "consumer"
    pull(packages, (repo.mkdir() or repo), confirm=True)
    lp = repo / f"agents/{KEY}/LEARNINGS.md"
    lp.write_text(lp.read_text() + "| 2026-10-09 | decision | Local | l | novo |\n")
    pj = repo / f"agents/{KEY}/PACKAGE.json"
    d = json.loads(pj.read_text())
    d["built_at"] = "1999-01-01T00:00:00Z"
    pj.write_text(json.dumps(d))
    assert build(packages, check=str(repo))["ok"]


def test_bundle_carries_claude_tree_matching_dist(packages):
    """§C4 (amended 2026-10-03): top-level `claude: [{caminho, conteudo}]` == the dist/claude tree."""
    r = build(packages)
    assert r["ok"], r
    dist = packages / KEY / "dist"
    bundle = json.loads((dist / "bundle.json").read_text(encoding="utf-8"))
    claude = bundle["claude"]
    assert [c["caminho"] for c in claude] == sorted(r["files"])
    for c in claude:
        assert (dist / "claude" / c["caminho"]).read_text(encoding="utf-8") == c["conteudo"]
    assert f".claude/agents/{KEY}.md" in {c["caminho"] for c in claude}
    assert r["importer_validation"]["status"] in {"ok", "skipped"}
