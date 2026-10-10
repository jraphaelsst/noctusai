"""keeper_delta — changed-keeper detection + aggregator call shapes (pure AST)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import keeper_delta as KD  # noqa: E402

BASE = '''
def _helper():
    return 1

def check_a(d):
    return []

def check_b():
    return _helper()

def check_c():
    return []

def check_all_products():
    out = []
    for d in dirs():
        out += check_a(d)
    out += check_b()
    out += check_c()
    return out
'''


def test_unchanged_source_has_no_changed_keepers():
    assert KD.changed_keepers(BASE, BASE) == []


def test_new_and_edited_keepers_are_changed():
    head = BASE.replace("def check_c():\n    return []", "def check_c():\n    return [1]")
    head += "\ndef check_new():\n    return []\n"
    assert KD.changed_keepers(BASE, head) == ["check_c", "check_new"]


def test_keeper_calling_a_changed_helper_is_changed():
    head = BASE.replace("def _helper():\n    return 1", "def _helper():\n    return 2")
    assert KD.changed_keepers(BASE, head) == ["check_b"]


def test_aggregator_itself_is_never_a_changed_keeper():
    head = BASE.replace("out = []", "out = list()")
    assert KD.changed_keepers(BASE, head) == []


def test_new_file_means_every_keeper():
    assert KD.changed_keepers(None, BASE) == ["check_a", "check_b", "check_c"]


def test_aggregator_call_shapes_are_derived():
    assert KD.aggregator_call_shapes(BASE) == {
        "check_a": "per_product", "check_b": "global", "check_c": "global"}


def test_real_compliance_aggregator_shapes_cover_known_keepers():
    src = (Path(__file__).resolve().parents[1] / "tools/noctus/dev/compliance.py").read_text()
    shapes = KD.aggregator_call_shapes(src)
    assert shapes["check_seed_compliance"] == "per_product"
    assert shapes["check_no_self_monkeypatch"] == "global"
