"""Catalog service — browse the transcripts/summaries the pipeline writes.

The pipeline writes markdown at ``data/{transcripts,summaries}/<module>/<lesson>.md``
(lessons produced before module-organization land flat under the base dir). This
service is a pure filesystem read over that tree — no DB, no LLM. A *lesson* is a
``.md`` stem; it "has" a transcript/summary when the matching file exists. Flat
(module-less) lessons are grouped under the synthetic module :data:`ROOT_MODULE`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Synthetic module name for lessons written flat (no module subfolder).
ROOT_MODULE = "geral"


@dataclass(frozen=True)
class ModuleSummaryRow:
    name: str
    lessons: int
    transcripts: int
    summaries: int


@dataclass(frozen=True)
class LessonSummaryRow:
    lesson: str
    has_transcript: bool
    has_summary: bool
    transcript_chars: int
    summary_chars: int


def _safe_segment(seg: str) -> bool:
    """Reject path-traversal / separators in a URL-supplied module/lesson name."""
    return bool(seg) and "/" not in seg and "\\" not in seg and seg not in (".", "..")


class CatalogService:
    """Filesystem browse over a KE data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.transcripts_dir = data_dir / "transcripts"
        self.summaries_dir = data_dir / "summaries"

    # ── discovery ──────────────────────────────────────────────────
    def _module_names(self) -> list[str]:
        names: set[str] = set()
        for base in (self.transcripts_dir, self.summaries_dir):
            if not base.is_dir():
                continue
            for child in base.iterdir():
                if child.is_dir():
                    names.add(child.name)
                elif child.suffix.lower() == ".md":
                    names.add(ROOT_MODULE)
        return sorted(names)

    def _dir_for(self, base: Path, module: str) -> Path:
        return base if module == ROOT_MODULE else base / module

    def _stems(self, base: Path, module: str) -> set[str]:
        d = self._dir_for(base, module)
        if not d.is_dir():
            return set()
        return {p.stem for p in d.glob("*.md") if p.is_file()}

    # ── public ─────────────────────────────────────────────────────
    def list_modules(self) -> list[ModuleSummaryRow]:
        rows: list[ModuleSummaryRow] = []
        for name in self._module_names():
            t = self._stems(self.transcripts_dir, name)
            s = self._stems(self.summaries_dir, name)
            rows.append(
                ModuleSummaryRow(
                    name=name, lessons=len(t | s), transcripts=len(t), summaries=len(s)
                )
            )
        return rows

    def module_lessons(self, module: str) -> list[LessonSummaryRow] | None:
        """Lessons of *module*, or ``None`` when the module is unknown/unsafe."""
        if not _safe_segment(module) or module not in self._module_names():
            return None
        t = self._stems(self.transcripts_dir, module)
        s = self._stems(self.summaries_dir, module)
        rows: list[LessonSummaryRow] = []
        for lesson in sorted(t | s):
            tp = self._dir_for(self.transcripts_dir, module) / f"{lesson}.md"
            sp = self._dir_for(self.summaries_dir, module) / f"{lesson}.md"
            rows.append(
                LessonSummaryRow(
                    lesson=lesson,
                    has_transcript=tp.is_file(),
                    has_summary=sp.is_file(),
                    transcript_chars=len(tp.read_text(encoding="utf-8")) if tp.is_file() else 0,
                    summary_chars=len(sp.read_text(encoding="utf-8")) if sp.is_file() else 0,
                )
            )
        return rows

    def lesson_content(self, module: str, lesson: str) -> tuple[str | None, str | None] | None:
        """``(transcript, summary)`` markdown, or ``None`` when neither exists/unsafe."""
        if not (_safe_segment(module) and _safe_segment(lesson)):
            return None
        tp = self._dir_for(self.transcripts_dir, module) / f"{lesson}.md"
        sp = self._dir_for(self.summaries_dir, module) / f"{lesson}.md"
        transcript = tp.read_text(encoding="utf-8") if tp.is_file() else None
        summary = sp.read_text(encoding="utf-8") if sp.is_file() else None
        if transcript is None and summary is None:
            return None
        return (transcript, summary)
