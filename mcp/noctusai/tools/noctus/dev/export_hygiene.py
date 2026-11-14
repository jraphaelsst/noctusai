"""Export hygiene (security standard S10) — the ONE pre-write scan every exporter runs.

An export (agent mirror, agent package, knowledge bundle) ships files out of the repo's trust boundary.
Before any artifact is written, every file it would ship is checked for:

* **secrets** — the canonical ``noctusai_lib.security`` scanner (``find_secret_findings``); no second scanner;
* **absolute home paths** (``/Users/<x>/``, ``/home/<x>/``, ``C:\\Users\\<x>\\``) — they leak the author's
  filesystem layout / username. DECISION: REFUSE, not scrub (a silent rewrite changes what was reviewed).

A hit raises :class:`ExportRefused` naming file + rule only — never the matched value. Callers must scan BEFORE
creating the output directory/file so no partial artifact is left behind.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

from noctusai_lib.security import find_secret_findings

_HOME_PATH_RE = re.compile(r"(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\)")
# Placeholders that are documentation, not a leak.
_HOME_PATH_OK = frozenset({"/Users/<x>/", "/home/<x>/"})


class ExportRefused(Exception):
    """An export the hygiene scan refuses. ``findings`` = ``[{"path", "rule"}]`` (never values)."""

    def __init__(self, findings: list[dict[str, str]]) -> None:
        self.findings = findings
        super().__init__("; ".join(f"{f['path']}: {f['rule']}" for f in findings))

    def errors(self) -> list[str]:
        return [f"export hygiene (S10): {f['path']}: {f['rule']}" for f in self.findings]


# Generated artifacts legitimately carry content digests (package sha, compiled_hash, git revision). A hex run
# on a line that names itself a digest is not a credential; every OTHER line is scanned in full, and the known
# key patterns + home-path rule still apply to the digest lines.
_DIGEST_LINE_RE = re.compile(r"(?i)(sha|hash|digest|revision)")
_HEX_RUN_RE = re.compile(r"\b[0-9a-f]{32,}\b")


def _without_labelled_digests(text: str) -> str:
    return "\n".join(_HEX_RUN_RE.sub("<digest>", ln) if _DIGEST_LINE_RE.search(ln) else ln for ln in text.split("\n"))


def scan_text(text: str) -> list[str]:
    """Rule names tripped by ``text`` (deduplicated, ordered). Never returns values."""
    rules: list[str] = []
    text = _without_labelled_digests(text)
    for name, _value in find_secret_findings(text):
        rule = f"secret:{name}"
        if rule not in rules:
            rules.append(rule)
    for m in _HOME_PATH_RE.finditer(text):
        if m.group(0) not in _HOME_PATH_OK:
            rules.append("absolute_home_path")
            break
    return rules


def scan_files(files: Mapping[str, str] | Iterable[tuple[str, str]]) -> list[dict[str, str]]:
    items = files.items() if isinstance(files, Mapping) else files
    out: list[dict[str, str]] = []
    for path, text in items:
        for rule in scan_text(text):
            out.append({"path": path, "rule": rule})
    return out


def guard_export(files: Mapping[str, str] | Iterable[tuple[str, str]]) -> None:
    """Raise :class:`ExportRefused` when any file trips the scan. Call before writing anything."""
    findings = scan_files(files)
    if findings:
        raise ExportRefused(findings)
