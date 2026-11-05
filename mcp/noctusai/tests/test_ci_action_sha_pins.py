"""Supply-chain keeper: every third-party GitHub Action is pinned to a full
40-hex commit SHA (GitHub's documented hardening practice).

Tags are mutable — the `aquasecurity/trivy-action` tag family was hijacked on
2026-03-19 and every workflow referencing it by tag ran attacker code. A SHA
cannot be re-pointed. Local actions (`uses: ./...`) are exempt. Dependabot's
`github-actions` ecosystem (see .github/dependabot.yml) keeps the SHAs fresh.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
GH = REPO / ".github"
SHA = re.compile(r"[0-9a-f]{40}")


def _files() -> list[Path]:
    return sorted([*GH.glob("workflows/*.yml"), *GH.glob("actions/**/action.yml")])


def _uses(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "uses" and isinstance(v, str):
                yield v
            else:
                yield from _uses(v)
    elif isinstance(node, list):
        for v in node:
            yield from _uses(v)


def test_workflow_files_found():
    assert _files(), "no workflow/action files found — glob regressed"


def test_every_third_party_action_is_sha_pinned():
    bad: list[str] = []
    for f in _files():
        for ref in _uses(yaml.safe_load(f.read_text(encoding="utf-8"))):
            if ref.startswith("./") or ref.startswith("docker://"):
                continue
            _, _, version = ref.partition("@")
            if not SHA.fullmatch(version):
                bad.append(f"{f.relative_to(REPO)}: {ref}")
    assert not bad, "actions not pinned to a 40-hex commit sha:\n" + "\n".join(bad)
