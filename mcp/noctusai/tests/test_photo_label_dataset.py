"""Colocated tests for noctus.dev.photo_label_dataset - labeler injected through the
executor seam; nothing in this repo is monkeypatched."""
from __future__ import annotations

import csv
import functools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from noctusai_lib.domain.photo_editing.labeling import parse_label  # noqa: E402
from tools.noctus.dev import photo_label_dataset as mod  # noqa: E402

GOOD = {
    "room_type": "cozinha", "exposure": "ok", "white_balance": "neutral", "verticals": "straight",
    "sky": "none", "windows": "n_a", "staging": "furnished", "framing": "normal", "lens": "normal",
    "quality_score": 4, "edit_needed": ["lift shadows"], "notes": "n",
}


def _labeler(fail: set[str] | None = None):
    calls: list[bytes] = []

    async def label(image):
        calls.append(image)
        if fail and image.decode() in fail:
            raise RuntimeError("provider down")
        return parse_label(json.dumps(GOOD))

    return label, calls


def _seam(labeler):
    return functools.partial(mod._execute, labeler=labeler)


def _tree(tmp_path: Path, names=("a", "b", "c")) -> Path:
    for n in names:
        d = tmp_path / "imv1"
        d.mkdir(exist_ok=True)
        (d / f"{n}.jpg").write_bytes(n.encode())
    (tmp_path / "imv1" / "notes.txt").write_text("skip")
    return tmp_path


def _rows(p: Path):
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


class TestPhotoLabelDataset:
    def test_dry_run_default_plans_and_writes_nothing(self, tmp_path):
        _tree(tmp_path)
        out = tmp_path / "out.csv"
        lab, calls = _labeler()
        r = mod.photo_label_dataset(photos_dir=str(tmp_path), base_dir=str(tmp_path), out_csv=str(out),
                                    executor=_seam(lab))
        assert r["status"] == "planned" and r["to_do"] == 3 and r["already_done"] == 0
        assert r["estimated_cost_usd"] > 0 and not out.exists() and calls == []

    def test_confirm_without_dry_run_false_still_plans(self, tmp_path):
        _tree(tmp_path)
        lab, calls = _labeler()
        r = mod.photo_label_dataset(photos_dir=str(tmp_path), base_dir=str(tmp_path),
                                    out_csv=str(tmp_path / "o.csv"), confirm=True, executor=_seam(lab))
        assert r["status"] == "planned" and calls == []

    def test_labels_resumes_and_passes_through(self, tmp_path):
        _tree(tmp_path)
        out = tmp_path / "out.csv"
        lab, calls = _labeler()
        kw = dict(photos_dir=str(tmp_path), base_dir=str(tmp_path), out_csv=str(out),
                  dry_run=False, confirm=True, executor=_seam(lab))
        r = mod.photo_label_dataset(**kw, limit=2)
        assert r["status"] == "applied" and r["labeled"] == 2 and r["errors"] == 0
        r2 = mod.photo_label_dataset(**kw)
        assert r2["already_done"] == 2 and r2["labeled"] == 1
        rows = _rows(out)
        assert len(rows) == 3 and len(calls) == 3
        assert {x["ref"] for x in rows} == {"imv1"} and rows[0]["room_type"] == "cozinha"
        assert rows[0]["edit_needed"] == "lift shadows"

    def test_csv_in_keeps_gallery_index(self, tmp_path):
        _tree(tmp_path, ("a",))
        src = tmp_path / "in.csv"
        src.write_text("ref,file,gallery_index\nimv1,imv1/a.jpg,7\n")
        lab, _ = _labeler()
        mod.photo_label_dataset(csv_in=str(src), base_dir=str(tmp_path), out_csv=str(tmp_path / "o.csv"),
                                dry_run=False, confirm=True, executor=_seam(lab))
        assert _rows(tmp_path / "o.csv")[0]["gallery_index"] == "7"

    def test_failure_is_logged_counted_after_one_retry(self, tmp_path):
        _tree(tmp_path)
        out = tmp_path / "out.csv"
        lab, calls = _labeler(fail={"b"})
        r = mod.photo_label_dataset(photos_dir=str(tmp_path), base_dir=str(tmp_path), out_csv=str(out),
                                    dry_run=False, confirm=True, executor=_seam(lab))
        assert r["labeled"] == 2 and r["errors"] == 1
        assert calls.count(b"b") == 2
        log = Path(str(out) + ".errors.log").read_text()
        assert "b.jpg" in log and "provider down" in log
        assert len(_rows(out)) == 2

    def test_needs_exactly_one_input(self, tmp_path):
        lab, _ = _labeler()
        r = mod.photo_label_dataset(out_csv=str(tmp_path / "o.csv"), executor=_seam(lab))
        assert r["ok"] is False

    def test_concurrency_is_clamped(self, tmp_path):
        # clamp is internal; a request above the max must still complete.
        _tree(tmp_path)
        lab, _ = _labeler()
        r = mod.photo_label_dataset(photos_dir=str(tmp_path), base_dir=str(tmp_path), out_csv=str(tmp_path / "o.csv"),
                                    concurrency=99, dry_run=False, confirm=True, executor=_seam(lab))
        assert r["labeled"] == 3

    def test_registered_under_the_dev_namespace(self):
        seen = {}

        class _Server:
            def tool(self, *, name, description):
                seen["name"], seen["description"] = name, description
                return lambda fn: fn

        mod.register(_Server())
        assert seen["name"] == "noctus.dev.photo_label_dataset"
        assert "dry_run" in seen["description"]


class TestRegistryRow:
    def test_missing_row_fails_loudly_naming_the_migration(self):
        import pytest
        from noctusai_lib.integrations.prompt_registry import FakePromptRegistry

        with pytest.raises(RuntimeError, match=r"registry row fotos\.rotular not found: apply core migration 122"):
            mod.require_row(FakePromptRegistry())

    def test_present_row_passes(self):
        from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, PromptEntry

        mod.require_row(FakePromptRegistry([PromptEntry("fotos.rotular", "n", "d", "anthropic", "claude-sonnet-5", "p",
                                                         capacidade="vision")]))

    def test_tool_has_no_provider_or_model_argument(self):
        import inspect

        params = inspect.signature(mod.photo_label_dataset).parameters
        assert "provider" not in params and "model" not in params
