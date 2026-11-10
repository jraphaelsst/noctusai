"""check_raw_waha_client_construction: a WAHA client is built only by the seed factory (line policy v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_raw_waha_client_construction  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
LIB = "seed/lib/backend/noctusai_lib"


def _tree(tmp_path, files: dict[str, str]) -> Path:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    return tmp_path


def test_raw_construction_in_seed_and_via_attribute_are_flagged(tmp_path):
    root = _tree(tmp_path, {
        f"{LIB}/domain/x.py": "from a import WahaClient\nc = WahaClient('u', 'k')\n",
        f"{LIB}/domain/y.py": "import m\nc = m.client.WahaClient('u', 'k')\n",
    })
    out = check_raw_waha_client_construction(repo_root=root)
    assert sorted((i["file"], i["line"]) for i in out) == [(f"{LIB}/domain/x.py", 2), (f"{LIB}/domain/y.py", 2)]
    assert all(i["severity"] == "high" for i in out)


def test_factory_module_tests_and_annotated_lines_are_exempt(tmp_path):
    root = _tree(tmp_path, {
        f"{LIB}/integrations/whatsapp/__init__.py": "c = WahaClient('u')\n",
        f"{LIB}/integrations/whatsapp/client.py": "c = WahaClient('u')\n",
        "seed/lib/backend/tests/test_a.py": "c = WahaClient('u')\n",
        f"{LIB}/domain/ok.py": "c = WahaClient('u')  # noc-allow: raw-waha-client -- migration shim, removed next slice\n",
        f"{LIB}/domain/bare.py": "c = WahaClient('u')  # noc-allow: raw-waha-client\n",
        f"{LIB}/domain/typed.py": "def f(c: WahaClient): ...\nx = FakeWahaClient()\n",
    })
    assert [i["file"] for i in check_raw_waha_client_construction(repo_root=root)] == [f"{LIB}/domain/bare.py"]


def test_paths_scope_judges_only_the_given_files(tmp_path):
    root = _tree(tmp_path, {f"{LIB}/domain/a.py": "WahaClient('u')\n", f"{LIB}/domain/b.py": "WahaClient('u')\n"})
    assert len(check_raw_waha_client_construction(repo_root=root, paths=[f"{LIB}/domain/a.py"])) == 1


def test_real_repo_is_clean():
    assert check_raw_waha_client_construction(repo_root=REPO) == []
