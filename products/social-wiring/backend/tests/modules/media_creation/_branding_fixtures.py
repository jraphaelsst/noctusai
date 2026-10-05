"""Shared helpers for the branding tests: real design-system folders + a tiny
synthetic one (so most tests do not depend on the folder's exact contents)."""
from __future__ import annotations

import base64
import json
from pathlib import Path

#: .../products/social-wiring/projects/core-studio/design-systems
DESIGN_SYSTEMS = Path(__file__).resolve().parents[4] / "projects" / "core-studio" / "design-systems"

# 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
WOFF2 = b"wOF2" + b"\x00" * 60

TOKENS = {
    "name": "Mini",
    "version": 1,
    "meta": {"source": "test"},
    "color": {
        "themes": [{"id": "light", "name": "Light"}, {"id": "dark", "name": "Dark"}],
        "tokens": [
            {"name": "ground", "value": "#f4f4f2", "usage": "paper"},
            {"name": "ink", "value": "#111111", "usage": "text"},
            {"name": "surface", "value": {"light": "{ground}", "dark": "{ink}"}, "usage": "bg"},
        ],
    },
    "type": {
        "fonts": [],
        "families": {"display": "Georgia, serif", "ui": "system-ui, sans-serif"},
        "groups": [
            {
                "name": "Post",
                "family": "display",
                "styles": [
                    {
                        "name": "headline",
                        "fontSize": "104px",
                        "lineHeight": 0.95,
                        "fontWeight": 700,
                        "sample": "Olá",
                        "usage": "main",
                    }
                ],
            }
        ],
    },
    "spacing": {"tokens": [{"name": "space-4", "value": "4px", "usage": "base"}]},
    "radius": {"tokens": [{"name": "radius-pill", "value": "999px", "usage": "pills"}]},
}

PREVIEW = '<style>.a{color:var(--ink);background:var(--surface)}</style><div class="a">Oi</div>'


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def mini_files(*, with_assets: bool = True) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = [
        ("tokens.json", json.dumps(TOKENS).encode()),
        ("README.md", b"# Mini\n\nBrand book."),
        ("design-system.json", json.dumps({"title": "Mini DS"}).encode()),
        ("sections/01-voz.md", "# Voz\n\nDireta.".encode()),
        ("components/Button/README.md", b"# Button\n\nGuideline."),
        ("components/Button/preview.html", PREVIEW.encode()),
        ("source/dump.html", b"<html></html>"),
    ]
    if with_assets:
        files += [
            ("assets/Logos/logo.png", PNG),
            ("assets/Logos/README.md", b"Use the lockup on light ground."),
            ("fonts/mini.woff2", WOFF2),
        ]
    return files


def payload_files(files: list[tuple[str, bytes]]) -> list[dict]:
    return [{"path": p, "content_base64": b64(d)} for p, d in files]


def folder_files(name: str) -> list[tuple[str, bytes]]:
    root = DESIGN_SYSTEMS / name
    assert root.is_dir(), f"design-system folder missing: {root}"
    return [
        (f"{name}/{p.relative_to(root).as_posix()}", p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]
