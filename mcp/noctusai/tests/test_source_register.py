"""Colocated tests for noctus.dev.source_register - core driven through the reader/writer
seams; nothing in this repo is monkeypatched."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import source_register as mod  # noqa: E402

SEED = Path(__file__).resolve().parents[3] / mod.SEED_RELPATH


def _ev(source, outcome, ts="2026-11-01T00:00:00+00:00", **kw):
    return json.dumps({"ts": ts, "source": source, "outcome": outcome, **kw})


def _reader(*lines, err=None):
    return lambda: ("\n".join(lines), err)


class TestNormalize:
    def test_url_becomes_host_without_www(self):
        assert mod.normalize_source("https://www.Planalto.gov.br/ccivil_03/leis/l13709.htm") == "planalto.gov.br"

    def test_bare_key_with_path_is_kept(self):
        assert mod.normalize_source("gov.br/anpd/") == "gov.br/anpd"


class TestBuildEvent:
    def test_confirmed_needs_claim_and_evidence(self):
        try:
            mod.build_event(source="x.org", outcome="confirmed", claim="c")
        except ValueError as exc:
            assert "evidence" in str(exc)
        else:
            raise AssertionError("a confirmation without its evidence must be refused")

    def test_graded_needs_a_tier(self):
        try:
            mod.build_event(source="x.org", outcome="graded")
        except ValueError:
            return
        raise AssertionError("graded without tier must be refused")

    def test_bad_enums_refused(self):
        for kw in ({"outcome": "liked"}, {"outcome": "graded", "tier": "T9"}):
            try:
                mod.build_event(source="x.org", **kw)
            except ValueError:
                continue
            raise AssertionError(f"accepted {kw}")


class TestFold:
    def test_standing_learns_from_track_record(self):
        text = "\n".join([
            _ev("a.org", "graded", tier="T1"),
            *[_ev("a.org", "confirmed", ts=f"2026-11-0{i}T00:00:00+00:00", claim="c", evidence="e") for i in range(1, 4)],
            _ev("b.com", "graded", tier="T3"),
            _ev("b.com", "refuted", claim="c1", evidence="e1"),
            _ev("b.com", "refuted", ts="2026-11-02T00:00:00+00:00", claim="c2", evidence="e2"),
            _ev("b.com", "confirmed", claim="c3", evidence="e3"),
            _ev("c.net", "refuted", claim="c", evidence="e"),
            _ev("d.gov", "unreachable"), _ev("d.gov", "unreachable", ts="2026-11-02T00:00:00+00:00"),
        ])
        f = mod.fold(text, today=date(2026, 11, 10))
        assert f["a.org"]["standing"] == "proven" and f["a.org"]["tier"] == "T1"
        assert f["b.com"]["standing"] == "demote" and len(f["b.com"]["refuted_claims"]) == 2
        assert f["c.net"]["standing"] == "watch"
        assert f["d.gov"]["standing"] == "hard-to-reach"

    def test_regrade_wins_and_stale_flag(self):
        text = "\n".join([_ev("x.org", "graded", ts="2025-01-01T00:00:00+00:00", tier="T2"),
                          _ev("x.org", "graded", ts="2025-02-01T00:00:00+00:00", tier="T3")])
        row = mod.fold(text, today=date(2026, 11, 10))["x.org"]
        assert row["tier"] == "T3" and row["stale"] is True

    def test_duplicate_lines_count_once(self):
        line = _ev("x.org", "unverified")
        assert mod.fold(line + "\n" + line)["x.org"]["counts"]["unverified"] == 1


class TestTool:
    def test_read_filters_and_reports_degraded_and_malformed(self):
        out = mod.source_register("read", query="a.org", reader=_reader(
            _ev("a.org", "graded", tier="T1"), _ev("b.org", "graded", tier="T4"), "not json",
            err="store unreachable"))
        assert out["ok"] and [r["source"] for r in out["rows"]] == ["a.org"]
        assert out["malformed_lines"] == 1 and out["degraded"] == "store unreachable"

    def test_log_is_dry_run_by_default(self):
        written = []
        out = mod.source_register("log", source="https://arxiv.org/abs/1", outcome="graded", tier="T1",
                                  writer=lambda r: written.append(r) or {"status": "published"})
        assert out["status"] == "planned" and written == [] and out["row"]["source"] == "arxiv.org"

    def test_log_confirm_writes_through_the_seam(self):
        written = []
        out = mod.source_register("log", source="arxiv.org", outcome="refuted", claim="c", evidence="e",
                                  confirm=True, writer=lambda r: written.append(r) or {"status": "pending"})
        assert out["status"] == "spooled" and written[0]["outcome"] == "refuted"

    def test_invalid_log_is_not_ok(self):
        assert mod.source_register("log", source="x.org", outcome="nope")["ok"] is False

    def test_unknown_action_is_not_ok(self):
        assert mod.source_register("delete")["ok"] is False

    def test_registered_under_the_dev_namespace(self):
        seen = {}

        class _Server:
            def tool(self, *, name, description):
                seen["name"], seen["description"] = name, description
                return lambda fn: fn

        mod.register(_Server())
        assert seen["name"] == "noctus.dev.source_register"
        assert "noc-research" in seen["description"]


class TestSeed:
    def test_committed_seed_is_valid_and_folds(self):
        lines = [ln for ln in SEED.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for ln in lines:
            r = json.loads(ln)
            mod.build_event(**{k: r.get(k, "") for k in ("source", "outcome", "tier", "label", "claim",
                                                         "evidence", "question", "note", "by")}, ts=r["ts"])
        folded = mod.fold("\n".join(lines))
        assert folded["planalto.gov.br"]["tier"] == "T1"
        assert all(row["tier"] in mod.TIERS for row in folded.values())
