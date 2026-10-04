"""The Python interpreter must reproduce 100% of the vendored limiar conformance vectors."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.public_ask.safety_pack import PackError, load_engine, verify_lock
from app.public_ask.safety_pack.engine import LOCK_PATH, PACK_DIR

CONF = json.loads((PACK_DIR / "conformance.json").read_text(encoding="utf-8"))
ENGINE = load_engine()


def test_versao_matches_lock() -> None:
    assert CONF["versao"] == ENGINE.versao == verify_lock()["versao"]


@pytest.mark.parametrize(
    "case", CONF["normalizacao"], ids=lambda c: f"{c['categoria']}:{c['entrada'][:40]!r}"
)
def test_normalization_vector(case: dict) -> None:
    assert ENGINE.normalize(case["entrada"]) == case["normalizada"]


@pytest.mark.parametrize(
    "case", CONF["triagem"], ids=lambda c: f"{c['conjunto']}:{c['frase'][:50]!r}"
)
def test_triage_case(case: dict) -> None:
    assert ENGINE.normalize(case["frase"]) == case["normalizada"]
    r = ENGINE.triage(case["frase"])
    assert r.nivel == case["nivel"]
    assert list(r.sinais) == case["sinais"]
    assert list(r.regras) == case["regras"]
    assert r.versao == CONF["versao"]


def test_counts_cover_every_case() -> None:
    assert len(CONF["triagem"]) == CONF["contagens"]["triagem"]
    assert len(CONF["normalizacao"]) == CONF["contagens"]["normalizacao"]


def _copy_pack(tmp_path: Path) -> tuple[Path, Path]:
    pack = tmp_path / "limiar"
    shutil.copytree(PACK_DIR, pack)
    lock = tmp_path / "SOURCE.lock"
    shutil.copy(LOCK_PATH, lock)
    return pack, lock


def test_lock_mismatch_refused(tmp_path: Path) -> None:
    pack, lock = _copy_pack(tmp_path)
    load_engine(pack, lock)  # pristine copy loads
    (pack / "regras.json").write_text((pack / "regras.json").read_text() + " ", encoding="utf-8")
    with pytest.raises(PackError, match="does not match SOURCE.lock"):
        load_engine(pack, lock)


def test_missing_file_refused(tmp_path: Path) -> None:
    pack, lock = _copy_pack(tmp_path)
    (pack / "conformance.json").unlink()
    with pytest.raises(PackError):
        verify_lock(pack, lock)


def test_result_never_carries_input_text() -> None:
    sentinel = "zzsentinelxx quero morrer"
    r = ENGINE.triage(sentinel)
    flat = json.dumps([r.nivel, r.sinais, r.regras, r.versao])
    assert "sentinel" not in flat and "quero" not in flat
    assert set(r.__dataclass_fields__) == {"nivel", "sinais", "regras", "versao"}
