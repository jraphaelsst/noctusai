"""Colocated regression test for `check_structure_constructor_parity` (meta-detector: every keeper ships
Test<CamelCase>). Owner 2026-11-08: a field added to an entity's record must reach every constructor surface."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_structure_constructor_parity  # noqa: E402

RECORD = '''
from dataclasses import dataclass

@dataclass
class Thing:
    id: str
    nome: str
    kind: str = "a"

    @property
    def derived(self) -> bool:
        return True
'''

CONSTRUCTORS = '''
FIELDS = ("nome",)
CRIAR = (*FIELDS, "kind")

def create(nome, kind="a"):
    payload = {"nome": nome, "kind": kind}
    return Thing(id="1", nome=nome, kind=kind)
'''


def _manifest(surfaces: str) -> str:
    return (
        '_R = "products/p/backend/app/record.py"\n'
        'STRUCTURE_PARITY = {"thing": {"record": f"{_R}::Thing", "surfaces": [' + surfaces + ']}}\n'
    )


def _tree(tmp_path: Path, surfaces: str, record: str = RECORD, constructors: str = CONSTRUCTORS) -> Path:
    app = tmp_path / "products" / "p" / "backend" / "app"
    app.mkdir(parents=True)
    (app / "record.py").write_text(record)
    (app / "make.py").write_text(constructors)
    (app / "structure_parity.py").write_text(_manifest(surfaces))
    return tmp_path


_M = "products/p/backend/app/make.py"
ALL_SURFACES = f'''
    {{"name": "params", "target": "{_M}::create", "kind": "params", "exempt": {{"id": "generated"}}}},
    {{"name": "payload", "target": "{_M}::create", "kind": "dict_keys:payload", "exempt": {{"id": "generated"}}}},
    {{"name": "record", "target": "{_M}::create", "kind": "call_kwargs:Thing", "exempt": {{}}}},
    {{"name": "mcp", "target": "{_M}::CRIAR", "kind": "tuple", "exempt": {{"id": "generated"}}}},
'''


class TestStructureConstructorParity:
    def test_clean_case_no_issues(self, tmp_path):
        assert check_structure_constructor_parity(repo_root=_tree(tmp_path, ALL_SURFACES)) == []

    def test_no_manifest_no_issues(self, tmp_path):
        assert check_structure_constructor_parity(repo_root=tmp_path) == []

    def test_a_new_record_field_not_carried_is_flagged_on_every_surface(self, tmp_path):
        record = RECORD.replace('    kind: str = "a"\n', '    kind: str = "a"\n    fonte: str = "git"\n')
        issues = check_structure_constructor_parity(repo_root=_tree(tmp_path, ALL_SURFACES, record=record))
        assert len(issues) == 4 and all(i["severity"] == "high" for i in issues)
        assert all("fonte" in i["issue"] for i in issues)

    def test_an_exemption_with_a_reason_silences_only_that_surface(self, tmp_path):
        record = RECORD.replace('    kind: str = "a"\n', '    kind: str = "a"\n    fonte: str = "git"\n')
        surfaces = ALL_SURFACES.replace('"kind": "tuple", "exempt": {"id": "generated"}',
                                        '"kind": "tuple", "exempt": {"id": "generated", "fonte": "fixed at create"}')
        issues = check_structure_constructor_parity(repo_root=_tree(tmp_path, surfaces, record=record))
        assert len(issues) == 3 and not any("mcp" in i["issue"] for i in issues)

    def test_tuple_star_expansion_is_followed(self, tmp_path):
        constructors = CONSTRUCTORS.replace('CRIAR = (*FIELDS, "kind")', 'CRIAR = ("kind",)')
        issues = check_structure_constructor_parity(repo_root=_tree(tmp_path, ALL_SURFACES, constructors=constructors))
        assert len(issues) == 1 and "nome" in issues[0]["issue"] and "mcp" in issues[0]["issue"]

    def test_stale_and_reasonless_exemptions_are_flagged(self, tmp_path):
        surfaces = ALL_SURFACES.replace('"kind": "params", "exempt": {"id": "generated"}',
                                        '"kind": "params", "exempt": {"id": "", "gone": "removed field"}')
        issues = check_structure_constructor_parity(repo_root=_tree(tmp_path, surfaces))
        texts = " | ".join(i["issue"] for i in issues)
        assert "no longer has: gone" in texts and "without a reason: id" in texts

    def test_a_target_that_no_longer_resolves_is_flagged(self, tmp_path):
        surfaces = ALL_SURFACES.replace(f'"{_M}::create", "kind": "params"', f'"{_M}::create_v2", "kind": "params"')
        issues = check_structure_constructor_parity(repo_root=_tree(tmp_path, surfaces))
        assert len(issues) == 1 and "create_v2 not found" in issues[0]["issue"]
