"""The "Fontes" catalogue must keep pointing at things that exist."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.platform_templates import service as S
from app.services.platform_templates.sources import SOURCES, list_sources

ROOT = Path(__file__).resolve().parents[5]


@pytest.mark.parametrize("src", SOURCES, ids=lambda s: s["path"])
def test_every_source_path_exists(src):
    assert (ROOT / src["path"]).exists(), f"stale source pointer: {src['path']}"


def test_kinds_are_known_and_each_kind_is_covered():
    assert {s["kind"] for s in SOURCES} <= set(S.KINDS)
    assert {s["kind"] for s in SOURCES} >= {"agent", "message", "document", "repo_workflow"}


def test_filtering():
    assert all(s["kind"] == "message" for s in list_sources(kind="message"))
    assert all(s["product"] == "social-wiring" for s in list_sources(product="social-wiring"))
