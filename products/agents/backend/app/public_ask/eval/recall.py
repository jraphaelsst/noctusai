"""Recall metrics + blind-set loading for the Limiar safety stack.

Outputs METRICS ONLY - counts, rates, a confusion matrix - never a phrase, never
a fragment of one. Blind sets live OUTSIDE git (``~/.noctusai/private/limiar-blind``);
only their sha256 is committed (``blind_sets.json``), and a missing or mismatching
file is refused, never read.

Final level = max(server rules, classifier) by the LabelSet order. A classifier
``indeterminado`` (fail-closed) is NOT a level: when the rules did not already
route to safety the final outcome is ``indeterminado`` and counts as a MISS for
every safety level (the service shows the editorial screen, not the safety one),
so recall is never flattered by an outage. See projects/limiar-open-question §5.2.

Run the gate (owner): see ``tests/eval/test_risk_recall.py`` docstring.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from noctusai_lib.integrations.risk_classifier import INDETERMINADO, Classificacao, LabelSet
from noctusai_lib.integrations.risk_classifier.fake import normalized_text_hash

DEFAULT_BLIND_DIR = Path("~/.noctusai/private/limiar-blind").expanduser()
BLIND_DIR_ENV = "LIMIAR_BLIND_DIR"
MANIFEST_PATH = Path(__file__).parent / "blind_sets.json"
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "eval" / "fixtures"
LIVE_ENV = "LIMIAR_EVAL_LIVE"
RECALL_TARGET = 0.95


class BlindSetError(RuntimeError):
    """Blind set missing, unverified, or malformed. Messages carry no content."""


@dataclass(frozen=True)
class Item:
    key: str  # sha256 of the normalized text - the only handle we keep
    esperado: str
    texto: str = field(repr=False, compare=False, default="")  # in-memory only


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blind_dir() -> Path:
    return Path(os.environ.get(BLIND_DIR_ENV) or DEFAULT_BLIND_DIR).expanduser()


def load_blind_set(
    name: str,
    *,
    labels: LabelSet,
    directory: Optional[Path] = None,
    manifest_path: Path = MANIFEST_PATH,
) -> list[Item]:
    """Load ``<directory>/<name>.jsonl`` after verifying its sha256 against the manifest."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BlindSetError(f"blind-set manifest unreadable: {type(exc).__name__}") from exc
    entry = manifest.get(name)
    if not isinstance(entry, dict) or not entry.get("sha256"):
        raise BlindSetError(f"blind set {name!r} is not registered in blind_sets.json - refusing")
    path = (directory or blind_dir()) / f"{name}.jsonl"
    if not path.is_file():
        raise BlindSetError(f"blind set {name!r} not present at {path.parent} - refusing")
    actual = _sha256(path)
    if actual != entry["sha256"]:
        raise BlindSetError(
            f"blind set {name!r} sha256 mismatch (manifest {entry['sha256']}, file {actual}) - refusing"
        )
    items: list[Item] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            texto, esperado = row["texto"], row["nivel_esperado"]
        except (ValueError, KeyError, TypeError) as exc:
            raise BlindSetError(f"blind set {name!r} line {lineno} malformed") from exc
        if esperado not in labels.niveis:
            raise BlindSetError(f"blind set {name!r} line {lineno}: unknown nivel_esperado")
        items.append(Item(key=normalized_text_hash(texto), esperado=esperado, texto=texto))
    if not items:
        raise BlindSetError(f"blind set {name!r} is empty")
    if entry.get("n") is not None and entry["n"] != len(items):
        raise BlindSetError(f"blind set {name!r} has {len(items)} rows, manifest says {entry['n']}")
    return items


# ---- recorded classifier fixtures -------------------------------------------------


def fixture_path(modelo: str, versao_prompt: str, directory: Path = FIXTURES_DIR) -> Path:
    safe = lambda s: "".join(c if c.isalnum() or c in "-._" else "_" for c in s)  # noqa: E731
    return directory / f"{safe(modelo)}__{safe(versao_prompt)}.json"


def load_fixture(path: Path) -> dict[str, dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BlindSetError(f"classifier fixture unreadable: {type(exc).__name__}") from exc


def write_fixture(path: Path, recorded: Mapping[str, Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def classificacao_from_record(rec: Mapping[str, Any], modelo: str, versao_prompt: str) -> Classificacao:
    return Classificacao(
        nivel=rec["nivel"],
        sinais=tuple(rec.get("sinais", ())),
        confianca=float(rec.get("confianca", 0.0)),
        modelo=modelo,
        versao_prompt=versao_prompt,
    )


def record_from_classificacao(c: Classificacao) -> dict[str, Any]:
    return {"nivel": c.nivel, "sinais": list(c.sinais), "confianca": c.confianca}


async def record_live(items: Sequence[Item], classifier: Any, labels: LabelSet) -> dict[str, dict[str, Any]]:
    """Call a (Real) classifier over the set; returns ``{key: record}`` - no text kept."""
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        try:
            c = await classifier.classify(" ".join(it.texto.split()), labels=labels)
            out[it.key] = record_from_classificacao(c)
        except Exception as exc:  # fail-closed, same as the route; type only
            out[it.key] = {"nivel": INDETERMINADO, "sinais": [], "confianca": 0.0, "erro": type(exc).__name__}
    return out


# ---- metrics ----------------------------------------------------------------------


def final_level(rules_nivel: str, cls_nivel: str, labels: LabelSet) -> str:
    """max(rules, classifier); a classifier outage leaves the rules' level only if it is
    already a safety-route level, else ``indeterminado``."""
    if cls_nivel == INDETERMINADO:
        return rules_nivel if labels.ordem(rules_nivel) >= labels.ordem("violencia") else INDETERMINADO
    return max(rules_nivel, cls_nivel, key=labels.ordem)


def _safe_div(a: int, b: int) -> Optional[float]:
    return a / b if b else None


def compute_metrics(
    expected: Sequence[str],
    rules: Sequence[str],
    classifier: Sequence[str],
    labels: LabelSet,
    *,
    safety_level: str = "vermelho",
    safe_level: str = "verde",
) -> dict[str, Any]:
    """Pure metric math over parallel level lists (rules/classifier may hold ``indeterminado``)."""
    if not (len(expected) == len(rules) == len(classifier)):
        raise ValueError("expected/rules/classifier must be the same length")
    final = [final_level(r, c, labels) for r, c in zip(rules, classifier)]
    cols = (*labels.niveis, INDETERMINADO)

    def recall(pred: Sequence[str], level: str) -> dict[str, Any]:
        n = sum(1 for e in expected if e == level)
        hit = sum(1 for e, p in zip(expected, pred) if e == level and p == level)
        return {"n": n, "hit": hit, "recall": _safe_div(hit, n)}

    def per_level(pred: Sequence[str]) -> dict[str, Any]:
        return {lv: recall(pred, lv) for lv in labels.niveis}

    def as_safe_miss(pred: Sequence[str], level: str) -> dict[str, Any]:
        """Recall of 'routed to >= level' - the operational reading for a safety class."""
        n = sum(1 for e in expected if e == level)
        hit = sum(
            1 for e, p in zip(expected, pred)
            if e == level and p != INDETERMINADO and labels.ordem(p) >= labels.ordem(level)
        )
        return {"n": n, "hit": hit, "recall": _safe_div(hit, n)}

    confusion = {e: {c: 0 for c in cols} for e in labels.niveis}
    for e, p in zip(expected, final):
        confusion[e][p] += 1
    n_verde = sum(1 for e in expected if e == safe_level)
    fp = sum(1 for e, p in zip(expected, final) if e == safe_level and p not in (safe_level, INDETERMINADO))
    return {
        "n": len(expected),
        "final": {"per_level": per_level(final), "safety_level": recall(final, safety_level)},
        "final_at_least": as_safe_miss(final, safety_level),
        "rules_only": per_level(rules),
        "classifier_only": per_level(classifier),
        "verde_false_positive": {"n": n_verde, "fp": fp, "rate": _safe_div(fp, n_verde)},
        "indeterminado_rate": _safe_div(sum(1 for p in final if p == INDETERMINADO), len(final)),
        "classifier_indeterminado_rate": _safe_div(sum(1 for p in classifier if p == INDETERMINADO), len(classifier)),
        "confusion_final": confusion,
    }


def evaluate(
    items: Sequence[Item],
    *,
    engine: Any,
    recorded: Mapping[str, Mapping[str, Any]],
    labels: LabelSet,
    modelo: str = "recorded",
    versao_prompt: str = "recorded",
) -> dict[str, Any]:
    """Run the rules engine live (deterministic) + recorded classifier outputs over a set.

    A text with no recorded verdict is treated as ``indeterminado`` and counted in
    ``missing_recordings`` (a stale fixture must lower the numbers, not pass quietly).
    """
    rules_l: list[str] = []
    cls_l: list[str] = []
    missing = 0
    for it in items:
        rules_l.append(engine.triage(" ".join(it.texto.split())).nivel)
        rec = recorded.get(it.key)
        if rec is None:
            missing += 1
            cls_l.append(INDETERMINADO)
        else:
            cls_l.append(classificacao_from_record(rec, modelo, versao_prompt).nivel)
    metrics = compute_metrics([i.esperado for i in items], rules_l, cls_l, labels)
    metrics["missing_recordings"] = missing
    return metrics


def format_metrics(metrics: Mapping[str, Any]) -> str:
    """Human summary - numbers only."""
    def pct(x: Optional[float]) -> str:
        return "n/a" if x is None else f"{x:.1%}"

    lines = [f"n={metrics['n']} missing_recordings={metrics.get('missing_recordings', 0)}"]
    for title, key in (("FINAL", "final"), ("RULES", "rules_only"), ("CLASSIFIER", "classifier_only")):
        per = metrics["final"]["per_level"] if key == "final" else metrics[key]
        lines.append(f"{title:<10} " + "  ".join(f"{lv}={pct(v['recall'])}({v['hit']}/{v['n']})" for lv, v in per.items()))
    fp = metrics["verde_false_positive"]
    lines.append(f"verde FP rate={pct(fp['rate'])} ({fp['fp']}/{fp['n']})  indeterminado rate={pct(metrics['indeterminado_rate'])}")
    return "\n".join(lines)


__all__ = [
    "BlindSetError", "Item", "RECALL_TARGET", "LIVE_ENV", "compute_metrics", "evaluate",
    "final_level", "fixture_path", "format_metrics", "load_blind_set", "load_fixture",
    "record_live", "write_fixture",
]
