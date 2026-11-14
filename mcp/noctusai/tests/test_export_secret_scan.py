"""S10 export hygiene contract: every exporter scans what it ships BEFORE writing, refuses with a typed error
naming file + rule (never the value), and leaves no partial artifact. The exporter set is DERIVED (AST over
``tools/noctus/dev``), not hand-listed: a tool module that looks like an exporter must call the shared
``export_hygiene`` guard or be declared exempt WITH a reason.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.noctus.dev import agent_export as ax  # noqa: E402
from tools.noctus.dev import agent_package_build as apb  # noqa: E402
from tools.noctus.dev import agent_sync_client as sc  # noqa: E402
from tools.noctus.dev import export_hygiene as eh  # noqa: E402
from tools.noctus.dev.knowledge_bundle_export import export_knowledge_bundle  # noqa: E402

DEV = Path(__file__).resolve().parents[1] / "tools" / "noctus" / "dev"
REPO_ROOT = Path(__file__).resolve().parents[3]
FAKE_SECRET = "ghp_" + "a1B2c3D4e5F6g7H8i9J0kLmN"  # fake, assembled so the scanner never flags this file
HEX64 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
HOME_PATH = "/Users/" + "someone/Documents/x.txt"

# Modules that LOOK like exporters (name) and write files but are deliberately not S10 exporters.
EXEMPT = {
    "agent_pull": "materialises build_package output (already guarded) into a consumer repo",
    "contract_e2e_pack": "stages private data into a 0700 private dir outside every git tree; never leaves the machine",
    "component_bundle": "read-only in-memory organ bundle returned to the caller; writes nothing",
    "safety_pack_sync": "inbound vendoring from limiar-app; not an outbound export",
}
_EXPORTER_NAME = re.compile(r"(export|bundle|package|_pack)")


def _imports_guard(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("export_hygiene"):
            return True
        if isinstance(n, ast.ImportFrom) and n.module in (None, "") and any(a.name == "export_hygiene" for a in n.names):
            return True
    return False


def _calls_guard(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {"guard_export", "scan_text", "scan_files"}
    return any(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) in names
               for n in ast.walk(tree))


def _candidates() -> list[Path]:
    out = []
    for p in sorted(DEV.glob("*.py")):
        if p.stem.startswith("_") or p.stem == "export_hygiene" or not _EXPORTER_NAME.search(p.stem):
            continue
        if "write_text" in p.read_text(encoding="utf-8") or "open(" in p.read_text(encoding="utf-8"):
            out.append(p)
    return out


def test_every_derived_exporter_calls_the_shared_scan_or_is_exempt():
    cands = _candidates()
    names = {p.stem for p in cands}
    assert {"agent_export", "agent_package_build", "knowledge_bundle_export"} <= names, names
    unguarded = [p.stem for p in cands if p.stem not in EXEMPT and not (_imports_guard(p) and _calls_guard(p))]
    assert not unguarded, f"exporters without the S10 scan (use export_hygiene.guard_export): {unguarded}"
    assert not [k for k in EXEMPT if k not in {p.stem for p in DEV.glob("*.py")}], "stale EXEMPT entry"


def test_scan_names_rule_never_value():
    f = eh.scan_files({"a.md": f"token {FAKE_SECRET}", "b.md": f"see {HOME_PATH}", "c.md": "clean /Users/<x>/ placeholder"})
    got = {(x["path"], x["rule"]) for x in f}
    assert {("a.md", "secret:github_pat"), ("b.md", "absolute_home_path")} <= got and not any(p == "c.md" for p, _ in got)
    assert FAKE_SECRET not in json.dumps(f) and "someone" not in json.dumps(f)


# ── behavioural: each exporter refuses, names file+rule, leaves nothing ─────────


def test_agent_export_refuses_and_writes_nothing(monkeypatch, tmp_path):
    from test_agent_export import ENV, _tree
    tree = _tree()
    tree["files"][2]["conteudo"] += f"\n{FAKE_SECRET}\n"
    monkeypatch.setattr(sc, "http_json", lambda *a, **k: sc.HttpResult(status=200, data=tree, text="{}"))
    r = ax.agent_export("media-analyst", confirm=True, worktree_path=str(tmp_path), env=ENV)
    assert not r["ok"] and r["status"] == "export_refused"
    assert any(f["rule"] == "secret:github_pat" and f["path"].endswith("SKILL.md") for f in r["findings"])
    assert FAKE_SECRET not in json.dumps(r)
    assert not (tmp_path / "agents").exists() and not (tmp_path / ".claude").exists()


@pytest.mark.parametrize("payload,rule", [(FAKE_SECRET, "secret:github_pat"), (HOME_PATH, "absolute_home_path")])
def test_agent_package_build_refuses_and_leaves_no_dist(tmp_path, payload, rule):
    from test_agent_package_build import KEY, make_package
    packages = tmp_path / "packages"
    root = make_package(packages)
    (root / "skills/revisar/references/guia.md").write_text(f"# Guia\n\n{payload}\n", encoding="utf-8")
    r = apb.agent_package_build(KEY, packages_dir=str(packages), repo_root=str(REPO_ROOT))
    assert not r["ok"] and r["status"] == "invalid"
    assert any("guia.md" in e and rule in e for e in r["errors"]), r["errors"]
    assert payload not in json.dumps(r)
    assert not (root / "dist").exists()


@pytest.mark.parametrize("payload,rule", [(FAKE_SECRET, "secret"), (HOME_PATH, "home")])
def test_knowledge_bundle_export_refuses_and_leaves_no_bundle(tmp_path, payload, rule):
    repo = tmp_path / "repo"
    (repo / "KNOWLEDGE-BASE").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "KNOWLEDGE-BASE/a.md").write_text(f"# A\n\n{payload}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True)
    out = tmp_path / "out"
    r = export_knowledge_bundle(str(repo), str(out))
    assert r.ok is False and r.refused_paths == ["KNOWLEDGE-BASE/a.md"]
    assert not out.exists()


def test_knowledge_bundle_carries_no_personal_author(tmp_path):
    repo = tmp_path / "repo"
    (repo / "KNOWLEDGE-BASE").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "jane.doe@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Jane Doe"], cwd=repo, check=True)
    (repo / "KNOWLEDGE-BASE/a.md").write_text("# A\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True)
    r = export_knowledge_bundle(str(repo), str(tmp_path / "out"))
    assert r.ok
    raw = Path(r.path).read_text(encoding="utf-8")
    assert "Jane" not in raw and "jane.doe" not in raw
    assert re.fullmatch(r"author-[0-9a-f]{12}", json.loads(raw.splitlines()[0])["git_author_raw"])


def test_labelled_digests_are_not_secrets_but_bare_hex_still_is():
    assert eh.scan_text('"sha": "' + HEX64 + '"') == []
    assert "secret:high_entropy_token" in eh.scan_text("api key " + HEX64)
