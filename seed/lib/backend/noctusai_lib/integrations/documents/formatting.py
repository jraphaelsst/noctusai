"""Inline text formatting — the value objects every document path shares.

WHY THIS EXISTS
---------------
A registry document's bold and underlined passages carry meaning (the act
number, the owner's name, an "ônus" warning), and the office copies those
passages into contracts. Every rung of the transcription ladder used to
return plain text, so the formatting was lost at the source and nothing
downstream could get it back.

The model is deliberately TWO layers, not marked-up text:

- the plain `text` stays canonical and byte-identical to what it was — the
  matrícula act segmenter stores offsets into it, parsers read it, and a
  marked-up string would silently shift every one of those offsets;
- `FormatRange`s sit ALONGSIDE it as `[start, end)` offsets into that same
  text, so any slice of the text can be re-rendered with its formatting.

`Run` / `Paragraph` / `FormattedDocument` are the rendering-side shape: what
an ABNT PDF or a Word-pasteable HTML fragment is built from. The builders and
renderers live in `abnt.py`; this module holds only the shapes and the
persisted JSON form, so the transcriber and the renderers depend on one
definition instead of two guesses.

Contract: `projects/abnt-formatting-CONTRACT.md`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class FormatRange:
    """Bold and/or underline over `text[start:end]` of the owning text."""

    start: int  # inclusive offset into the owning text
    end: int  # exclusive
    bold: bool = False
    underline: bool = False

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"FormatRange inválido: [{self.start}, {self.end})")
        if not (self.bold or self.underline):
            raise ValueError("FormatRange sem formatação — não represente texto simples")


def ranges_to_json(ranges: Iterable[FormatRange]) -> list[dict[str, Any]]:
    """The persisted form (a `jsonb` array), ordered by `start` then `end`."""
    return [
        {"start": r.start, "end": r.end, "bold": r.bold, "underline": r.underline}
        for r in sorted(ranges, key=lambda r: (r.start, r.end))
    ]


def ranges_from_json(data: Optional[Iterable[dict[str, Any]]]) -> tuple[FormatRange, ...]:
    """Inverse of `ranges_to_json`. `None` (a row written before formatting
    existed) is the empty tuple; a malformed entry raises — a corrupted
    formatting column must not render as silently unformatted text."""
    if data is None:
        return ()
    return tuple(
        FormatRange(
            start=int(item["start"]),
            end=int(item["end"]),
            bold=bool(item.get("bold", False)),
            underline=bool(item.get("underline", False)),
        )
        for item in data
    )


@dataclass(frozen=True)
class Run:
    """A stretch of text with one formatting. May contain `\\n` (a line
    break inside the paragraph, as in a hard-wrapped registry line)."""

    text: str
    bold: bool = False
    underline: bool = False


class ParagraphKind(str, Enum):
    """The ABNT role of a paragraph. The renderer, not the source document,
    decides how each kind looks — that is what "ABNT by construction" means."""

    TITLE = "title"  # centered, bold
    HEADING = "heading"  # left, bold, no first-line indent
    BODY = "body"  # justified, first-line indent 1.25 cm, spacing 1.5
    QUOTE = "quote"  # long citation: 4 cm left indent, 10 pt, single spacing


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Run, ...]
    kind: ParagraphKind = ParagraphKind.BODY

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass(frozen=True)
class FormattedDocument:
    paragraphs: tuple[Paragraph, ...]
    #: Metadata title of the PDF (not rendered as a paragraph — add a TITLE
    #: paragraph for a visible one).
    title: Optional[str] = None


__all__ = [
    "FormatRange",
    "FormattedDocument",
    "Paragraph",
    "ParagraphKind",
    "Run",
    "ranges_from_json",
    "ranges_to_json",
]
