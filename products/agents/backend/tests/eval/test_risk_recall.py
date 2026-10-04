"""Recall eval of the Limiar safety stack (projects/limiar-open-question S5).

Owner runs the GATE (needs the blind set at ~/.noctusai/private/limiar-blind/<name>.jsonl,
registered by sha256 in app/public_ask/eval/blind_sets.json, plus the recorded fixture):

    cd products/agents/backend && LIMIAR_BLIND_SET=<name> \\
      /path/to/venv/bin/python -m pytest tests/eval/test_risk_recall.py -m recall_gate -rs -s

Re-record the classifier outputs with the Real provider (never in CI; needs a provider
key; consumes the blind set):  LIMIAR_EVAL_LIVE=1 LIMIAR_BLIND_SET=<name> ... same command.

A SKIPPED gate is NOT a pass: the skip reason says "gate not evaluated". Read it with -rs.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from noctusai_lib.integrations.risk_classifier import (
    INDETERMINADO, Classificacao, FakeRiskClassifier, make_risk_classifier,
)

from app.public_ask import limiar
from app.public_ask.eval import recall
from app.public_ask.eval.recall import BlindSetError, Item
from app.public_ask.safety_pack import load_engine

L = limiar.LABELS


def _items(spec):
    from noctusai_lib.integrations.risk_classifier.fake import normalized_text_hash
    return [Item(key=normalized_text_hash(t), esperado=e, texto=t) for t, e in spec]


class _StubEngine:
    def __init__(self, table):
        self._t = table

    def triage(self, text):
        class R:  # noqa: D401
            nivel = self._t.get(text, "verde")
        return R


# ---------------- (a) metric math ----------------

def test_compute_metrics_recall_fp_and_confusion():
    expected = ["vermelho", "vermelho", "vermelho", "verde", "verde", "amarelo"]
    rules = ["vermelho", "verde", "verde", "verde", "verde", "verde"]
    cls = ["verde", "vermelho", INDETERMINADO, "amarelo", "verde", "amarelo"]
    m = recall.compute_metrics(expected, rules, cls, L)
    assert m["final"]["safety_level"] == {"n": 3, "hit": 2, "recall": pytest.approx(2 / 3)}
    assert m["rules_only"]["vermelho"]["recall"] == pytest.approx(1 / 3)
    assert m["classifier_only"]["vermelho"]["recall"] == pytest.approx(1 / 3)
    assert m["verde_false_positive"] == {"n": 2, "fp": 1, "rate": 0.5}
    # outage on the 3rd vermelho: final is indeterminado, a MISS
    assert m["confusion_final"]["vermelho"][INDETERMINADO] == 1
    assert m["indeterminado_rate"] == pytest.approx(1 / 6)
    assert m["confusion_final"]["amarelo"]["amarelo"] == 1


def test_final_level_is_max_and_outage_keeps_only_safety_rules():
    assert recall.final_level("verde", "vermelho", L) == "vermelho"
    assert recall.final_level("violencia", "amarelo", L) == "violencia"
    assert recall.final_level("vermelho", INDETERMINADO, L) == "vermelho"
    assert recall.final_level("amarelo", INDETERMINADO, L) == INDETERMINADO


def test_empty_class_recall_is_none_not_zero_or_pass():
    m = recall.compute_metrics(["verde"], ["verde"], ["verde"], L)
    assert m["final"]["safety_level"]["recall"] is None


def test_length_mismatch_rejected():
    with pytest.raises(ValueError):
        recall.compute_metrics(["verde"], [], [], L)


def test_evaluate_with_scripted_fake_and_missing_recording_counts_against():
    items = _items([("frase a", "vermelho"), ("frase b", "vermelho"), ("frase c", "verde")])
    fake = FakeRiskClassifier()
    fake.add("frase a", "vermelho")
    fake.add("frase c", "verde")
    recorded = {}
    for it in items:
        c = asyncio.run(fake.classify(it.texto, labels=L))
        recorded[it.key] = recall.record_from_classificacao(c)
    m = recall.evaluate(items, engine=_StubEngine({}), recorded=recorded, labels=L)
    assert m["final"]["safety_level"]["hit"] == 1  # frase b: fake says indeterminado
    assert m["classifier_only"]["vermelho"]["recall"] == 0.5
    m2 = recall.evaluate(items, engine=_StubEngine({}), recorded={}, labels=L)
    assert m2["missing_recordings"] == 3 and m2["final"]["safety_level"]["hit"] == 0


def test_format_metrics_contains_no_phrase():
    items = _items([("segredo absoluto xyz", "vermelho")])
    m = recall.evaluate(items, engine=_StubEngine({}), recorded={}, labels=L)
    assert "segredo" not in recall.format_metrics(m) + repr(m) + repr(items)


# ---------------- blind-set loader ----------------

def _write_set(tmp_path, rows, *, name="s1", n=None, sha=None):
    import hashlib, json
    f = tmp_path / f"{name}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    man = tmp_path / "man.json"
    man.write_text(json.dumps({name: {
        "sha256": sha or hashlib.sha256(f.read_bytes()).hexdigest(),
        "created": "2026-10-04", "author_role": "test", "n": n if n is not None else len(rows)}}))
    return man


def test_loader_ok_and_refuses_tampered_missing_unregistered(tmp_path):
    rows = [{"texto": "x y", "nivel_esperado": "verde"}, {"texto": "z", "nivel_esperado": "vermelho"}]
    man = _write_set(tmp_path, rows)
    items = recall.load_blind_set("s1", labels=L, directory=tmp_path, manifest_path=man)
    assert [i.esperado for i in items] == ["verde", "vermelho"]
    with pytest.raises(BlindSetError, match="not registered"):
        recall.load_blind_set("nope", labels=L, directory=tmp_path, manifest_path=man)
    with pytest.raises(BlindSetError, match="not present"):
        recall.load_blind_set("s1", labels=L, directory=tmp_path / "empty", manifest_path=man)
    (tmp_path / "s1.jsonl").write_text('{"texto":"t","nivel_esperado":"verde"}\n')
    with pytest.raises(BlindSetError, match="sha256 mismatch") as ei:
        recall.load_blind_set("s1", labels=L, directory=tmp_path, manifest_path=man)
    assert "texto" not in str(ei.value)


def test_loader_refuses_unknown_label(tmp_path):
    man = _write_set(tmp_path, [{"texto": "a", "nivel_esperado": "roxo"}])
    with pytest.raises(BlindSetError, match="unknown nivel_esperado"):
        recall.load_blind_set("s1", labels=L, directory=tmp_path, manifest_path=man)


def test_fixture_roundtrip_stores_no_text(tmp_path):
    items = _items([("frase sigilosa", "vermelho")])
    p = recall.fixture_path("m/odel", "v1", tmp_path)
    recall.write_fixture(p, {items[0].key: {"nivel": "vermelho", "sinais": [], "confianca": 0.9}})
    assert "sigilosa" not in p.read_text()
    assert recall.load_fixture(p)[items[0].key]["nivel"] == "vermelho"


# ---------------- (b) the GATE ----------------

@pytest.mark.recall_gate
def test_red_recall_gate_on_blind_set():
    name = os.environ.get("LIMIAR_BLIND_SET", "")
    if not name:
        pytest.skip("LIMIAR_BLIND_SET not set - blind set not present - gate not evaluated (NOT a pass)")
    try:
        items = recall.load_blind_set(name, labels=L)
    except BlindSetError as exc:
        pytest.skip(f"blind set not present or unverified ({exc}) - gate not evaluated (NOT a pass)")

    engine = load_engine()
    live = os.environ.get(recall.LIVE_ENV) == "1"
    if live:
        try:
            classifier = make_risk_classifier(provider="real")
        except Exception as exc:
            pytest.fail(f"--live refused: no configured provider key ({type(exc).__name__})")
        recorded = asyncio.run(recall.record_live(items, classifier, L))
        # model/prompt identity comes from the Real classifier's own result
        probe = asyncio.run(classifier.classify("teste", labels=L))
        recall.write_fixture(recall.fixture_path(probe.modelo, probe.versao_prompt), recorded)
        modelo, versao = probe.modelo, probe.versao_prompt
    else:
        import glob
        files = sorted(glob.glob(str(recall.FIXTURES_DIR / "*__*.json")))
        if not files:
            pytest.skip("no recorded classifier fixtures - gate not evaluated (NOT a pass)")
        path = files[-1] if not os.environ.get("LIMIAR_FIXTURE") else recall.fixture_path(
            *os.environ["LIMIAR_FIXTURE"].split("__", 1))
        recorded = recall.load_fixture(path)
        if not any(i.key in recorded for i in items):
            pytest.skip("fixtures do not cover this blind set - gate not evaluated (NOT a pass)")
        modelo = versao = "recorded"

    metrics = recall.evaluate(items, engine=engine, recorded=recorded, labels=L, modelo=modelo, versao_prompt=versao)
    print("\nLIMIAR RECALL GATE\n" + recall.format_metrics(metrics))
    got = metrics["final"]["safety_level"]["recall"]
    assert got is not None, "blind set has no vermelho items - gate cannot be evaluated"
    assert metrics["missing_recordings"] == 0, "fixture does not cover every blind-set item - re-record with --live"
    assert got >= recall.RECALL_TARGET, f"max-recall(vermelho)={got:.3f} < {recall.RECALL_TARGET}"
