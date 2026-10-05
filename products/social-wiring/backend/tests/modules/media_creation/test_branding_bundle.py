"""Design-system folder -> bundle parsing."""
from __future__ import annotations

import json

import pytest

from app.modules.media_creation.branding.bundle import (
    BundleError,
    parse_bundle,
    sniff_asset,
)

from ._branding_fixtures import PNG, TOKENS, WOFF2, folder_files, mini_files


def test_parses_mini_folder():
    b = parse_bundle(mini_files())
    assert b.name == "Mini DS"  # design-system.json title wins
    assert b.tokens["color"]["tokens"][0]["name"] == "ground"
    assert b.brand_book.startswith("# Mini")
    assert [c.name for c in b.components] == ["Button"]
    assert b.components[0].preview_html.startswith("<style>")
    assert {(a.kind, a.label) for a in b.assets} == {("logo", "logo.png"), ("font", "mini.woff2")}
    # extra sections: the sections/ file + the Logos group README
    assert {s["title"] for s in b.sections} == {"Voz", "Assets: Logos"}
    # source/** is NOT imported — and it is REPORTED, not dropped silently
    assert b.ignored == ["source/dump.html"]


def test_strips_the_folder_picker_prefix():
    prefixed = [(f"mini-ds/{p}", d) for p, d in mini_files()]
    assert parse_bundle(prefixed).name == "Mini DS"


def test_limiar_folder_is_importable():
    b = parse_bundle(folder_files("nos-no-limiar-monica"))
    assert b.name == "Nós no Limiar"
    assert {a.label for a in b.assets if a.kind == "logo"} == {
        "logo-lockup.png", "logo-lockup-light.png", "logo-mark.png",
    }
    assert {c.name for c in b.components} >= {"Button", "Chip", "TabBar", "Cover"}
    assert all(c.preview_html for c in b.components)
    assert any(i.startswith("source/") for i in b.ignored)


def test_template_folder_is_importable():
    b = parse_bundle(folder_files("branding-template"))
    assert {c.name for c in b.components} >= {"Accents", "HeadlineStack", "PostFrame"}


def test_missing_tokens_is_an_error():
    with pytest.raises(BundleError) as ei:
        parse_bundle([("README.md", b"x")])
    assert "tokens.json" in ei.value.errors[0]


def test_collects_every_problem_at_once():
    files = [
        ("tokens.json", json.dumps(TOKENS).encode()),
        ("components/Bad/preview.html", b"<script>1</script>"),
        ("assets/Logos/fake.png", b"not an image"),
        ("assets/Weird/x.png", PNG),
    ]
    with pytest.raises(BundleError) as ei:
        parse_bundle(files)
    text = " | ".join(ei.value.errors)
    assert "components/Bad/preview.html" in text
    assert "fake.png" in text
    assert "unknown asset group" in text


@pytest.mark.parametrize("path", ["../evil.json", "/abs/tokens.json", "a/../../b"])
def test_rejects_unsafe_paths(path):
    with pytest.raises(BundleError):
        parse_bundle([("tokens.json", b"{}"), (path, b"x")])


def test_font_in_image_group_is_rejected():
    files = [("tokens.json", json.dumps(TOKENS).encode()), ("assets/Logos/f.woff2", WOFF2)]
    with pytest.raises(BundleError) as ei:
        parse_bundle(files)
    assert "font file cannot go" in ei.value.errors[0]


def test_svg_is_not_an_accepted_asset():
    files = [
        ("tokens.json", json.dumps(TOKENS).encode()),
        ("assets/Logos/x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>"),
    ]
    with pytest.raises(BundleError):
        parse_bundle(files)


def test_warns_when_declared_font_file_is_absent():
    t = json.loads(json.dumps(TOKENS))
    t["type"]["fonts"] = [{"family": "F", "file": "fonts/ghost.woff2", "weight": "400"}]
    b = parse_bundle([("tokens.json", json.dumps(t).encode())])
    assert any("ghost.woff2" in w for w in b.warnings)


def test_sniff_decides_by_bytes():
    assert sniff_asset(PNG) == ("image/png", "image")
    assert sniff_asset(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("image/webp", "image")
    assert sniff_asset(b"MZ\x90\x00") is None
