"""LGPD ledger PII guard: detector, writer refusals, and the commit keeper.

Every personal value here is SYNTHESIZED at runtime (a computed-valid CPF,
a generated phone) so this file itself never trips `check_ledger_pii`.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from tools.noctus.dev import _pii_guard as g
from tools.noctus.dev._ledger_store import FileLedger
from tools.noctus.dev.compliance import check_ledger_pii


def _cpf(base9: str = "123456789") -> str:
    d = [int(c) for c in base9]
    for n in (9, 10):
        s = sum(v * w for v, w in zip(d[:n], range(n + 1, 1, -1)))
        d.append((s * 10 % 11) % 10)
    return "".join(map(str, d))


def _cnpj(base12: str = "112223330001") -> str:
    d = [int(c) for c in base12]
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n, w in ((12, w1), (13, [6] + w1)):
        r = sum(v * x for v, x in zip(d[:n], w)) % 11
        d.append(0 if r < 2 else 11 - r)
    return "".join(map(str, d))


CPF = _cpf()
CPF_FMT = f"{CPF[:3]}.{CPF[3:6]}.{CPF[6:9]}-{CPF[9:]}"
BAD_CPF = CPF[:-1] + str((int(CPF[-1]) + 1) % 10)
PHONE = "+55" + "11" + "9" + "8765" + "4321"


class TestPiiGuard:
    def test_valid_cpf_flagged_formatted_and_bare(self):
        assert g.find_pii(f"cpf {CPF_FMT}")[0][0] == "cpf"
        assert g.find_pii(f"cpf {CPF}")[0][0] == "cpf"

    def test_cpf_without_checksum_not_flagged(self):
        assert g.find_pii(f"id {BAD_CPF}") == []
        assert g.find_pii("11111111111") == []

    def test_cnpj_flagged_only_with_checksum(self):
        assert g.find_pii(_cnpj())[0][0] == "cnpj"
        bad = _cnpj()[:-1] + str((int(_cnpj()[-1]) + 1) % 10)
        assert g.find_pii(bad) == []

    def test_phone_requires_br_format(self):
        assert g.find_pii(f"titulo='{PHONE}'")[0][0] == "phone"
        assert g.find_pii("(11) 98765-4321")[0][0] == "phone"
        assert g.find_pii("version 1234567890123 build 20261019") == []
        assert g.find_pii("epoch 1760000000000") == []

    def test_email_team_and_placeholder_excluded(self):
        assert g.find_pii("joaoraphaelsst@gmail.com") == []
        assert g.find_pii("noreply@anthropic.com a@example.com") == []
        assert g.find_pii("git@72.61.28.36") == []
        assert g.find_pii("+@router.get")== []
        assert g.find_pii("maria.silva@empresa.com.br")[0][0] == "email"

    def test_personal_date_needs_label(self):
        assert g.find_pii("data_casamento: 2015-04-02")[0][0] == "personal-date"
        assert g.find_pii("nascimento 02/04/1990")[0][0] == "personal-date"
        assert g.find_pii("created 2015-04-02") == []

    def test_assert_names_kind_and_field_never_value(self):
        with pytest.raises(g.PiiLedgerError) as ei:
            g.assert_no_pii(json.dumps({"description": f"probe {CPF_FMT}"}), field="row")
        msg = str(ei.value)
        assert ei.value.kind == "cpf" and ei.value.field == "description"
        assert CPF not in msg and CPF_FMT not in msg

    def test_redact_keeps_surrounding_text(self):
        out, counts = g.redact(f"a {CPF_FMT} b {PHONE} c")
        assert out == "a [REDACTED-cpf] b [REDACTED-phone] c"
        assert counts == {"cpf": 1, "phone": 1}


class TestLedgerWriters:
    def test_file_ledger_refuses_and_writes_nothing(self, tmp_path):
        led = FileLedger(name="x.ndjson", path=tmp_path / "x.ndjson")
        with pytest.raises(g.PiiLedgerError):
            led.append([json.dumps({"description": f"cpf {CPF}"})], message="m")
        assert not (tmp_path / "x.ndjson").exists()
        led.append([json.dumps({"description": "clean"})], message="m")
        assert (tmp_path / "x.ndjson").exists()

    def test_auto_improvement_log_entry_refuses(self, tmp_path, monkeypatch):
        from tools.noctus.dev import auto_improvement as ai
        monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "ai.ndjson")
        with pytest.raises(g.PiiLedgerError):
            ai.log_entry(scope="scoped", kind="drift", target="t",
                         description=f"probe phone {PHONE}")

    def test_branch_pointer_row_refuses(self, tmp_path, monkeypatch):
        from tools.noctus.dev import branch_pointer as bp
        monkeypatch.setattr(bp, "LEDGER_PATH", tmp_path / "bp.ndjson")
        with pytest.raises(g.PiiLedgerError):
            bp._ledger().append([json.dumps({"brief": f"cpf {CPF}"})], message="m")

    def test_findings_append_refuses(self, tmp_path, monkeypatch):
        from tools.noctus.dev import findings as fd
        f = tmp_path / "findings.md"
        f.write_text("# F\n\n## Slips\n- _(none)_\n")
        monkeypatch.setattr(fd, "_locate", lambda slug: f)
        r = fd.findings_append("p", "Slips", f"customer {PHONE}")
        assert r["ok"] is False and r["pii_kind"] == "phone"
        assert PHONE not in json.dumps(r)
        assert PHONE not in f.read_text()

    def test_phase_learning_refuses(self, tmp_path):
        from tools.noctus.dev import phase_learnings as pl
        with pytest.raises(g.PiiLedgerError):
            pl.log_learning(project_slug="p", phase_number=0, phase_title=None, learning_kind="other",
                            learning_text=f"cpf {CPF_FMT}", db_path=tmp_path / "pl.sqlite")

    def test_brief_ledger_refuses_softly(self, tmp_path, monkeypatch):
        from tools.noctus.dev import brief_ledger as bl
        monkeypatch.setattr(bl, "_ledger_path", lambda: tmp_path / "b.ndjson")
        r = bl.append(slug="s", agent="a", target_files=[], description=f"cpf {CPF}")
        assert r["ok"] is False and CPF not in json.dumps(r)
        assert not (tmp_path / "b.ndjson").exists()


def _git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


class TestCheckLedgerPii:
    def test_clean_ledger_passes(self, tmp_path):
        root = _git_repo(tmp_path)
        (root / "project-history").mkdir()
        (root / "project-history" / "a.ndjson").write_text('{"d": "all good"}\n')
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        assert check_ledger_pii(repo_root=root) == []

    def test_flags_cpf_with_line_and_kind_no_value(self, tmp_path):
        root = _git_repo(tmp_path)
        (root / "project-history").mkdir()
        (root / "project-history" / "a.ndjson").write_text(
            '{"d": "ok"}\n' + json.dumps({"d": f"cpf {CPF_FMT}", "p": PHONE}) + "\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        issues = check_ledger_pii(repo_root=root)
        assert {i["kind"] for i in issues} == {"cpf", "phone"}
        assert all(i["line"] == 2 and i["severity"] == "critical" for i in issues)
        assert all(CPF not in i["issue"] and PHONE not in i["issue"] for i in issues)

    def test_paths_scope_and_non_ledger_files_ignored(self, tmp_path):
        root = _git_repo(tmp_path)
        (root / "project-history").mkdir()
        (root / "project-history" / "bad.ndjson").write_text(f'{{"d":"{CPF}"}}\n')
        (root / "notes.txt").write_text(CPF)
        assert check_ledger_pii(repo_root=root, paths=["notes.txt"]) == []
        assert len(check_ledger_pii(repo_root=root, paths=["project-history/bad.ndjson"])) == 1

    def test_redacted_marker_is_clean(self, tmp_path):
        root = _git_repo(tmp_path)
        (root / "findings.md").write_text("- cpf [REDACTED-cpf] phone [REDACTED-phone]\n")
        assert check_ledger_pii(repo_root=root, paths=["findings.md"]) == []
