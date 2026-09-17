"""Pure per-path-shape mapping functions (contract §B.6).

Every function here takes ``(path, content)`` for one bundle line and
returns a ``MappingResult`` — zero, one, or several ``MappedEntity``
rows ready for ``KnowledgeStore.import_entity`` (§A.11), or a warning
when the path isn't a recognised shape. Nothing here is stateful or
async; the transactional orchestration (dedup across commits, the
transaction, provenance) lives in ``run.py``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.importer.bundle import BundleInvalid

# ---------------------------------------------------------------------------
# Shared shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MappedEntity:
    """One entity ready for ``store.import_entity(org_id, entity_type,
    natural_key, snapshot, prov)``. Natural keys per §A.11:
    ``kb_entry``→slug · ``decision``/``open_question``/``task``→codigo ·
    ``roadmap_phase``→codigo · ``timeline_event``→``data|titulo``.
    """

    entity_type: str
    natural_key: str
    snapshot: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MappingResult:
    """Outcome of mapping one bundle line."""

    entities: tuple[MappedEntity, ...] = ()
    warning: str | None = None
    skipped: bool = False


# ---------------------------------------------------------------------------
# Frontmatter / markdown helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---\\n...\\n---`` YAML-lite frontmatter block off
    ``content``. Only flat ``key: value`` scalar lines are recognised —
    every frontmatter shape in the contract (titulo/data/estado/codigo/
    origem/...) is a scalar. Returns ``({}, content)`` when there is no
    frontmatter block.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        frontmatter[key] = value

    return frontmatter, content[match.end():]


def extract_first_heading(body: str) -> str | None:
    """First ``# Heading`` line in ``body``, or None."""
    match = _HEADING_RE.search(body)
    return match.group(1).strip() if match else None


def _slugify_segment(segment: str) -> str:
    return _SLUG_STRIP_RE.sub("-", segment.strip().lower()).strip("-")


def derive_slug_from_path(path: str) -> str:
    """Kebab-case slug from every remaining path segment once the
    ``KNOWLEDGE-BASE/`` prefix and ``.md`` suffix are stripped, e.g.
    ``KNOWLEDGE-BASE/DOMINIO/REGULATORIO/pnrs.md`` -> ``dominio-regulatorio-pnrs``.
    """
    p = path
    if p.startswith("KNOWLEDGE-BASE/"):
        p = p[len("KNOWLEDGE-BASE/"):]
    if p.endswith(".md"):
        p = p[: -len(".md")]
    segments = [s for s in p.split("/") if s]
    return "-".join(_slugify_segment(s) for s in segments)


def _extract_section(body: str, heading: str) -> str | None:
    """Body of a ``## <heading>`` markdown section, up to the next ``##``
    heading (or end of string). Returns None when the heading is absent
    or its body is empty.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    section = match.group(1).strip()
    return section or None


# ---------------------------------------------------------------------------
# KB files — KNOWLEDGE-BASE/<FOLDER>/**.md and docs/{SPEC,OPEN-QUESTIONS}.md
# ---------------------------------------------------------------------------


def map_kb_file(path: str, content: str) -> MappedEntity:
    """``KNOWLEDGE-BASE/<FOLDER>/**.md`` -> ``kb_entry``. ``categoria`` is
    the top-level folder, lower-cased. ``DOMINIO/<SUB>/`` gives
    ``subcategoria``. ``titulo`` is the first ``#`` heading, falling back
    to frontmatter ``titulo``. Unknown frontmatter keys ride verbatim in
    ``frontmatter``.
    """
    frontmatter, body = parse_frontmatter(content)
    relative = path[len("KNOWLEDGE-BASE/"):]
    segments = relative.split("/")
    categoria = segments[0].lower()
    subcategoria = (
        segments[1].lower() if categoria == "dominio" and len(segments) > 2 else None
    )

    titulo = extract_first_heading(body) or frontmatter.get("titulo")
    extra_frontmatter = {k: v for k, v in frontmatter.items() if k != "titulo"}
    slug = derive_slug_from_path(path)

    snapshot = {
        "slug": slug,
        "categoria": categoria,
        "subcategoria": subcategoria,
        "titulo": titulo,
        "corpo_md": body.strip("\n"),
        "frontmatter": extra_frontmatter,
    }
    return MappedEntity(entity_type="kb_entry", natural_key=slug, snapshot=snapshot)


def map_doc_geral(path: str, content: str) -> MappedEntity:
    """``docs/SPEC.md`` / ``docs/OPEN-QUESTIONS.md`` -> ``kb_entry`` with
    ``categoria='geral'``.
    """
    frontmatter, body = parse_frontmatter(content)
    titulo = extract_first_heading(body) or frontmatter.get("titulo")
    extra_frontmatter = {k: v for k, v in frontmatter.items() if k != "titulo"}
    slug = derive_slug_from_path(path)

    snapshot = {
        "slug": slug,
        "categoria": "geral",
        "subcategoria": None,
        "titulo": titulo,
        "corpo_md": body.strip("\n"),
        "frontmatter": extra_frontmatter,
    }
    return MappedEntity(entity_type="kb_entry", natural_key=slug, snapshot=snapshot)


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

# A markdown table row: | D-nn | <Decisão cell> | <Motivo cell> |
# Matches only rows whose first cell IS a D-code — naturally excludes the
# `| # | Decisão | Motivo |` header and the `|---|---|---|` separator.
_DECISION_ROW_RE = re.compile(
    r"^\|\s*(D-\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE
)
_D_CODE_MENTION_RE = re.compile(r"\bD-\d+\b")


def map_decisions_bundle_file(path: str, content: str) -> list[MappedEntity]:
    """``KNOWLEDGE-BASE/DECISOES/0001-*.md`` -> one ``decision`` per
    matching table row. There are two such tables in the file; a single
    regex over the whole body picks up rows from both.
    """
    frontmatter, body = parse_frontmatter(content)
    data = frontmatter.get("data")

    entities: list[MappedEntity] = []
    for match in _DECISION_ROW_RE.finditer(body):
        codigo, decisao_cell, motivo_cell = match.group(1), match.group(2), match.group(3)
        snapshot = {
            "codigo": codigo,
            "titulo": decisao_cell,
            "decisao": decisao_cell,
            "motivo": motivo_cell,
            "data": data,
            "estado": "vigente",
        }
        entities.append(
            MappedEntity(entity_type="decision", natural_key=codigo, snapshot=snapshot)
        )
    return entities


def map_decision_single_file(path: str, content: str) -> MappedEntity:
    """``KNOWLEDGE-BASE/DECISOES/00nn-*.md`` (``nn != 0001``) -> one
    ``decision``. Frontmatter supplies ``codigo``/``titulo``/``data``/
    ``estado``; the ``## Contexto`` / ``## Decisão`` / ``## Motivo`` /
    ``## Alternativas rejeitadas`` sections fill the matching fields.
    Other D-codes mentioned in the body (excluding this file's own) go
    into ``relacionadas``.
    """
    frontmatter, body = parse_frontmatter(content)
    codigo = frontmatter.get("codigo")
    if not codigo:
        raise BundleInvalid(f"{path}: decision file missing frontmatter 'codigo'")

    relacionadas = sorted(
        {code for code in _D_CODE_MENTION_RE.findall(body) if code != codigo}
    )

    snapshot = {
        "codigo": codigo,
        "titulo": frontmatter.get("titulo"),
        "contexto": _extract_section(body, "Contexto"),
        "decisao": _extract_section(body, "Decisão"),
        "motivo": _extract_section(body, "Motivo"),
        "alternativas_rejeitadas": _extract_section(body, "Alternativas rejeitadas"),
        "data": frontmatter.get("data"),
        "estado": frontmatter.get("estado", "vigente"),
        "relacionadas": relacionadas,
    }
    return MappedEntity(entity_type="decision", natural_key=codigo, snapshot=snapshot)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

# ## YYYY-MM-DD[ — título] followed by the section body, up to the next
# dated heading or end of file.
_TIMELINE_SECTION_RE = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2})(?:\s*—\s*(.+?))?\s*\n(.*?)(?=^##\s+\d{4}-\d{2}-\d{2}|\Z)",
    re.MULTILINE | re.DOTALL,
)


_TITULO_MAX = 120
_MD_LEAD_RE = re.compile(r"^[\s>*#+-]+")
_MD_EMPHASIS_RE = re.compile(r"(\*\*|__|`)")


def _titulo_da_descricao(descricao: str, data: str) -> str:
    """A title for a ``## YYYY-MM-DD`` section that has none.

    `timeline_events.titulo` is NOT NULL (migration 006), so an untitled
    section must still carry one: the section's first line, stripped of
    list/quote/heading markers and emphasis, cut at the first " — " (the
    sibling's own "headline — detail" habit), capped at 120 chars. A
    section with no text at all falls back to "Registro de <data>".
    """
    for linha in descricao.splitlines():
        texto = _MD_EMPHASIS_RE.sub("", _MD_LEAD_RE.sub("", linha)).strip()
        if texto:
            texto = texto.split(" — ", 1)[0].strip()
            if len(texto) > _TITULO_MAX:
                texto = texto[: _TITULO_MAX - 1].rstrip() + "…"
            return texto
    return f"Registro de {data}"


def map_timeline_file(path: str, content: str) -> list[MappedEntity]:
    """``KNOWLEDGE-BASE/HISTORICO/TIMELINE.md`` -> one ``timeline_event``
    per ``## YYYY-MM-DD[ — título]`` section. Natural key ``data|titulo``.
    An untitled section gets a title derived from its first line
    (``_titulo_da_descricao``) — the column is NOT NULL.
    """
    _, body = parse_frontmatter(content)
    entities: list[MappedEntity] = []
    for match in _TIMELINE_SECTION_RE.finditer(body):
        data, titulo_raw, descricao_raw = match.group(1), match.group(2), match.group(3)
        descricao = descricao_raw.strip()
        titulo = (titulo_raw or "").strip() or _titulo_da_descricao(descricao, data)
        natural_key = f"{data}|{titulo}"
        snapshot = {"data": data, "titulo": titulo, "descricao": descricao}
        entities.append(
            MappedEntity(
                entity_type="timeline_event", natural_key=natural_key, snapshot=snapshot
            )
        )
    return entities


# ---------------------------------------------------------------------------
# Project state JSON
# ---------------------------------------------------------------------------

# path -> (entity_type, natural-key field, sibling fields to carry through)
_JSON_STATE_FILES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "projects/state/open-questions.json": (
        "open_question",
        "codigo",
        (
            "codigo",
            "pergunta",
            "por_que_importa",
            "bloqueia",
            "destino_kb",
            "estado",
            "resposta",
            "respondida_em",
        ),
    ),
    "projects/state/roadmap.json": (
        "roadmap_phase",
        "codigo",
        ("codigo", "titulo", "objetivo", "concluida_quando", "estado", "ordem"),
    ),
    "projects/state/tasks.json": (
        "task",
        "codigo",
        ("codigo", "titulo", "fase", "detalhe", "estado", "bloqueada_por"),
    ),
}


def map_json_state_file(path: str, content: str) -> list[MappedEntity]:
    """``projects/state/{open-questions,roadmap,tasks}.json`` -> one row
    per array item, carrying only the sibling keys named in the
    contract. Whether an item actually produces a revision (i.e. whether
    it CHANGED since the previous commit's version of this file) is
    ``run.py``'s job, not this pure function's — it always returns every
    current item.
    """
    entity_type, key_field, fields = _JSON_STATE_FILES[path]

    try:
        items = json.loads(content)
    except json.JSONDecodeError as exc:
        raise BundleInvalid(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(items, list):
        raise BundleInvalid(f"{path}: expected a JSON array")

    entities: list[MappedEntity] = []
    for item in items:
        if not isinstance(item, dict):
            raise BundleInvalid(f"{path}: expected an array of objects")
        codigo = item.get(key_field)
        if not codigo:
            raise BundleInvalid(f"{path}: item missing {key_field!r}")
        snapshot = {f: item.get(f) for f in fields}
        entities.append(
            MappedEntity(entity_type=entity_type, natural_key=codigo, snapshot=snapshot)
        )
    return entities


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_SKIPPED_PATHS: frozenset[str] = frozenset(
    {
        "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
        "KNOWLEDGE-BASE/INDEX.md",
        "KNOWLEDGE-BASE/DECISOES/INDEX.md",
    }
)
_DECISIONS_BUNDLE_RE = re.compile(r"^KNOWLEDGE-BASE/DECISOES/0001-[^/]*\.md$")
_DECISIONS_SINGLE_RE = re.compile(r"^KNOWLEDGE-BASE/DECISOES/(\d{4})-[^/]*\.md$")
_TIMELINE_PATH = "KNOWLEDGE-BASE/HISTORICO/TIMELINE.md"
_DOC_GERAL_PATHS: frozenset[str] = frozenset({"docs/SPEC.md", "docs/OPEN-QUESTIONS.md"})


def map_line(path: str, content: str) -> MappingResult:
    """Dispatch one bundle line to the matching §B.6 mapping rule.

    Order matters: the more specific path shapes (skip-list, JSON state,
    docs, decisions, timeline) are checked before the generic
    ``KNOWLEDGE-BASE/**/*.md`` -> kb_entry fallback.
    """
    if path in _SKIPPED_PATHS:
        return MappingResult(skipped=True)

    if path in _JSON_STATE_FILES:
        return MappingResult(entities=tuple(map_json_state_file(path, content)))

    if path in _DOC_GERAL_PATHS:
        return MappingResult(entities=(map_doc_geral(path, content),))

    if _DECISIONS_BUNDLE_RE.match(path):
        return MappingResult(entities=tuple(map_decisions_bundle_file(path, content)))

    single_match = _DECISIONS_SINGLE_RE.match(path)
    if single_match and single_match.group(1) != "0001":
        return MappingResult(entities=(map_decision_single_file(path, content),))

    if path == _TIMELINE_PATH:
        return MappingResult(entities=tuple(map_timeline_file(path, content)))

    if path.startswith("KNOWLEDGE-BASE/") and path.endswith(".md"):
        return MappingResult(entities=(map_kb_file(path, content),))

    return MappingResult(warning=f"unmapped path, skipped: {path}", skipped=True)
