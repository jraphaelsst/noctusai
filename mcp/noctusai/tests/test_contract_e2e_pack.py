"""Tests for `noctus.dev.contract_e2e_pack`. All data is INVENTED; private root is a tmp dir."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "seed" / "lib" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import contract_e2e_pack as P  # noqa: E402
from tools.noctus.dev import drive_pull as DP  # noqa: E402

FID = "fid123"
PERSON = "Fulano Inventado Silva"


def _f(rel, doc_type, entity=None, kind=None, n=None, draft=False):
    return {"rel_path": rel, "sha256": "x" + rel[:6], "doc_type": doc_type, "entity": entity,
            "entity_kind": kind, "certidao_n": n, "text_source": "text_layer", "draft": draft}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(DP, "private_root", lambda: tmp_path)
    files = [
        _f("Matricula Visualizacao.pdf", "matricula"),
        _f("Matricula 123.pdf", "matricula"),
        _f("IPTU.pdf", "iptu_espelho"),
        _f(f"RG {PERSON}.pdf", "identidade", PERSON, "pf"),
        _f("CERTIDOES/%s/09 - serasa.pdf" % PERSON, "serasa_crednet", PERSON, "pf", 9),
        _f("CERTIDOES/%s/01 - a.pdf" % PERSON, "certidao", PERSON, "pf", 1),
        _f("CERTIDOES/%s/07 - b.png" % PERSON, "certidao", PERSON, "pf", 7),
        _f("CERTIDOES/%s/07 - c.png" % PERSON, "certidao", PERSON, "pf", 7),
        _f("Proposta banco.pdf", "banco_proposta"),
        _f("Contrato D4Sign.pdf", "contrato_d4sign"),
        _f("Contrato.docx", "contrato"),
        _f("Info PP.pdf", "outro"),
        _f("ANTIGO/Matricula velha.pdf", "matricula", draft=True),
    ]
    census = {"folder": {"numero": "900", "titulo": "t", "drive_folder_id": FID}, "files": files,
              "entities": [{"entity": PERSON, "kind": "pf", "presentes": [1, 7, 9], "faltando": [2, 3]}],
              "root_gaps": [], "entities_pj": 0}
    (tmp_path / "census").mkdir()
    (tmp_path / "census" / "900.json").write_text(json.dumps(census))
    tree = tmp_path / "drive-mirror" / FID / "tree"
    for f in files:
        p = tree / f["rel_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"data")
    return tmp_path


def test_phase_order_and_gabarito_never_uploaded(root):
    r = P.contract_e2e_pack("900")
    order = [P.PHASE_ORDER.index(s["phase"]) for s in r["steps"]]
    assert order == sorted(order)
    gab = [s for s in r["steps"] if s["phase"] == P.P_GAB]
    assert {s["doc_type"] for s in gab} == {"contrato", "contrato_d4sign"}
    assert all(not s["upload"] for s in gab)
    assert not any(s["upload"] for s in r["steps"] if s["doc_type"] in P._GABARITO)
    assert any(s["phase"] == P.P_OUT for s in r["steps"])


def test_certidao_before_visualizacao_and_multifile_cell(root):
    steps, _ = P.build_steps(P._load_census("900"))
    mat = next(s for s in steps if s["doc_type"] == "matricula")
    assert mat["count"] == 2  # draft excluded
    assert mat["files"][0]["rel_path"] == "Matricula 123.pdf"
    assert mat["visualizacao_flags"] == [False, True]
    cells = [s for s in steps if s["phase"] == P.P_CERT]
    assert [s["certidao_n"] for s in cells] == [1, 7]
    assert [s["multi_file_cell"] for s in cells] == [False, True]


def test_plan_output_has_no_paths_or_names(root):
    blob = json.dumps(P.contract_e2e_pack("900"), ensure_ascii=False)
    assert PERSON not in blob and ".pdf" not in blob and ".png" not in blob
    assert "entidade 1 (pf)" in blob


def test_stage_refuses_overwrite_and_perms(root):
    assert P.contract_e2e_pack("900", action="stage")["status"] == "planned"
    r = P.contract_e2e_pack("900", action="stage", confirm=True)
    assert r["status"] == "staged" and r["files_copied"] > 0
    out = root / "e2e-runs" / "900"
    run = json.loads((out / "run.json").read_text())
    assert (out / "run.json").stat().st_mode & 0o777 == 0o600
    assert run["dados_digitados"] and run["geracao"][-1]["cards_entry"]["numero"] == "900"
    assert all(s["status"] == "pendente" and s["achados"] == [] for s in run["steps"])
    again = P.contract_e2e_pack("900", action="stage", confirm=True)
    assert again["status"] == "refused_existing_run"
    assert P.contract_e2e_pack("900", action="stage", confirm=True, force=True)["status"] == "staged"
