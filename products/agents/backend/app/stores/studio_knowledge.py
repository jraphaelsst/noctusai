"""Agent Studio — knowledge library store (contract §B2/§D3/§E3, slice BE-KE).

``StudioKnowledgeStore`` — collections + documents (with a revision per
change) + full-text search + the paged ``read_document_part`` reader that
backs the ``kb_ler`` MCP tool (contract §E3). Agent resolution is NOT this
module's job: the routers resolve ``(org_id, key)`` through BE-DEF's
``StudioDefinitionStore`` (one resolver for every studio route).

Every store method takes ``org_id`` explicitly and filters by it — routes
use the admin client and bypass RLS (contract §B intro "Routes use the
admin client"), so this filter IS the authorization boundary. A foreign
``collection_id``/``doc_id`` raises :class:`~app.stores.errors.NotFound`
— never a 403 (contract §H.1 "never 403-leak").

Hardening (wave-1 security review): size caps (``app.studio.models.LIMITS``)
validated before every write; runtime reads by slug (``kb_ler``) see ACTIVE
documents only (M4) — the admin by-id read still sees archived ones; the
document list's free-text filter runs inside ``agents.list_knowledge_documents``
as a bound, LIKE-escaped parameter (L4) and search ``q`` is capped (L5);
every write goes through ``app.stores._db_errors`` so a unique violation is
a typed 409 ``slug_taken`` (supabase-py RAISES on 23505 — it never returns
empty rows).

Seed IO shape: Protocol + Fake + Real (``Supabase...``) + factory, per
``KB § PATTERNS/backend/seed-fake-real-adapter.md``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._db_errors import StudioConflict, exec_query, exec_rpc
from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from app.studio.models import LIMITS, LIST_QUERY_MAX, SEARCH_QUERY_MAX
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

__all__ = [
    "DOCUMENT_TYPES",
    "REVISION_OPS",
    "CollectionInput",
    "CollectionRecord",
    "DocumentInput",
    "DocumentPart",
    "DocumentRecord",
    "RevisionRecord",
    "SearchResult",
    "StudioKnowledgeStore",
    "FakeStudioKnowledgeStore",
    "SupabaseStudioKnowledgeStore",
    "get_studio_knowledge_store",
]

_SCHEMA = "agents"
_COLLECTIONS_TABLE = "knowledge_collections"
_DOCUMENTS_TABLE = "knowledge_documents"
_REVISIONS_TABLE = "knowledge_revisions"

#: Contract §B2 `knowledge_documents.tipo` CHECK.
DOCUMENT_TYPES = ("fonte", "sintese", "card", "template", "indice", "outro")
#: Contract §B2 `knowledge_revisions.op` CHECK.
REVISION_OPS = ("create", "update", "archive", "import")

#: Sentinel distinguishing "field not supplied" from "field explicitly set
#: to None/empty" in the partial-update methods below — a plain default of
#: ``None`` could never clear `tag`/`resumo` back to null.
_UNSET: Any = object()

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise ValueError(f"slug must match ^[a-z0-9]+(-[a-z0-9]+)*$; got {slug!r}")


def _validate_tipo(tipo: str) -> None:
    if tipo not in DOCUMENT_TYPES:
        raise ValueError(f"tipo must be one of {DOCUMENT_TYPES}; got {tipo!r}")


def _cap(value: str | None, key: str, what: str) -> None:
    """M3 — the same numbers as the 013 CHECKs."""
    limit = LIMITS[key]
    if value is not None and value is not _UNSET and len(value) > limit:
        raise ValueError(f"{what} exceeds {limit} characters ({len(value)})")


def _validate_collection_caps(*, nome: Any = None, tag: Any = None, descricao: Any = None) -> None:
    # Collection metadata is a LIVE, ungated prompt input (compiled into
    # every turn of the agent) — the tightest caps in the studio.
    _cap(nome, "collection.nome", "collection nome")
    _cap(tag, "collection.tag", "collection tag")
    _cap(descricao, "collection.descricao", "collection descricao")


def _validate_conteudo(conteudo: Any) -> None:
    _cap(conteudo, "document.conteudo", "document conteudo")


def _validate_list_query(q: str | None) -> None:
    if q is not None and len(q) > LIST_QUERY_MAX:
        raise ValueError(f"q exceeds {LIST_QUERY_MAX} characters")


def _validate_search_query(q: str) -> None:
    if len(q) > SEARCH_QUERY_MAX:
        raise ValueError(f"q exceeds {SEARCH_QUERY_MAX} characters")


def source_sha_of(conteudo: str) -> str:
    """The import-idempotency key (contract §B2/§F) — sha256 of the exact
    document body. Public so the (later) import endpoint can compute the
    SAME hash the store uses for its own dry-run comparisons."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


# ── dataclasses ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CollectionInput:
    slug: str
    nome: str
    tag: str | None = None
    descricao: str = ""
    ordem: int = 0


@dataclass(frozen=True)
class CollectionRecord:
    id: UUID
    org_id: UUID
    agent_id: UUID
    slug: str
    nome: str
    tag: str | None
    descricao: str
    ordem: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DocumentInput:
    slug: str
    titulo: str
    tipo: str
    conteudo: str
    resumo: str | None = None
    proveniencia: dict[str, Any] | None = None


@dataclass(frozen=True)
class DocumentRecord:
    id: UUID
    org_id: UUID
    collection_id: UUID
    agent_id: UUID
    slug: str
    titulo: str
    tipo: str
    proveniencia: dict[str, Any]
    resumo: str | None
    conteudo: str
    source_sha: str
    ativo: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RevisionRecord:
    id: UUID
    org_id: UUID
    document_id: UUID
    op: str
    snapshot: dict[str, Any]
    author_id: UUID | None
    motivo: str | None
    created_at: datetime


@dataclass(frozen=True)
class SearchResult:
    doc_id: UUID
    slug: str
    titulo: str
    colecao: str
    tag: str | None
    tipo: str
    trecho: str
    rank: float


@dataclass(frozen=True)
class DocumentPart:
    slug: str
    titulo: str
    colecao: str
    tag: str | None
    tipo: str
    proveniencia: dict[str, Any]
    parte: int
    total_partes: int
    conteudo: str


def _paginate_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into pages of at most ``max_chars`` characters,
    breaking on paragraph boundaries (``\\n\\n``) wherever possible — the
    kb_ler contract (§E3): "pages of <= 24 000 chars, split on paragraph
    boundaries". A single paragraph longer than ``max_chars`` is hard-split
    (never silently dropped, never an infinite loop)."""
    if not text:
        return [""]
    paragraphs = text.split("\n\n")
    pages: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pages.append(current)
            current = ""
        if len(para) <= max_chars:
            current = para
            continue
        # A single paragraph exceeds max_chars on its own — hard-split it.
        for start in range(0, len(para), max_chars):
            chunk = para[start : start + max_chars]
            if len(chunk) == max_chars:
                pages.append(chunk)
            else:
                current = chunk
    if current:
        pages.append(current)
    return pages or [""]


# ── StudioKnowledgeStore ─────────────────────────────────────────────────


class StudioKnowledgeStore(Protocol):
    def list_collections(self, org_id: UUID, agent_id: UUID) -> list[CollectionRecord]: ...

    def get_collection(self, org_id: UUID, agent_id: UUID, collection_id: UUID) -> CollectionRecord:
        """Raises :class:`NotFound` for an unknown/foreign collection id."""
        ...

    def create_collection(self, org_id: UUID, agent_id: UUID, data: CollectionInput) -> CollectionRecord: ...

    def update_collection(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        nome: str | Any = _UNSET, tag: str | None | Any = _UNSET,
        descricao: str | Any = _UNSET, ordem: int | Any = _UNSET,
    ) -> CollectionRecord: ...

    def count_documents(self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, ativo_only: bool = True) -> int: ...

    def list_documents(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        q: str | None = None, tipo: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[DocumentRecord], int]: ...

    def get_document(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> DocumentRecord:
        """Raises :class:`NotFound` for an unknown/foreign document id."""
        ...

    def get_document_by_slug(
        self, org_id: UUID, agent_id: UUID, slug: str, *, include_inactive: bool = False,
    ) -> DocumentRecord:
        """ACTIVE documents only unless ``include_inactive`` (M4) — an
        archived document must never be served to the runtime. Raises
        :class:`NotFound`."""
        ...

    def find_document_by_slug(
        self, org_id: UUID, agent_id: UUID, slug: str, *, include_inactive: bool = False,
    ) -> DocumentRecord | None:
        """Same lookup as :meth:`get_document_by_slug`, ``None`` when absent
        (the explicit "maybe" read — never an ``except NotFound`` fallback)."""
        ...

    def create_document(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, data: DocumentInput, author_id: UUID,
    ) -> DocumentRecord: ...

    def update_document(
        self, org_id: UUID, agent_id: UUID, doc_id: UUID, *, author_id: UUID | None, motivo: str | None = None,
        titulo: str | Any = _UNSET, tipo: str | Any = _UNSET, resumo: str | None | Any = _UNSET,
        conteudo: str | Any = _UNSET, proveniencia: dict[str, Any] | Any = _UNSET, ativo: bool | Any = _UNSET,
    ) -> DocumentRecord: ...

    def list_revisions(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> list[RevisionRecord]: ...

    def upsert_document_by_source_sha(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, slug: str, titulo: str, tipo: str,
        resumo: str | None, proveniencia: dict[str, Any] | None, conteudo: str, author_id: UUID | None = None,
    ) -> tuple[DocumentRecord, str]:
        """Upsert keyed on ``slug``, change-detected on ``source_sha``
        (contract §F import semantics). Returns ``(record, "created" |
        "updated" | "unchanged")`` — the importer aggregates these into its
        response counters. Writes a ``knowledge_revisions`` row with
        ``op="import"`` for created AND updated, never for unchanged. A slug
        that already lives in ANOTHER collection raises
        ``StudioConflict('slug_in_other_collection')`` — an import never
        silently moves a document. An archived document keeps ``ativo``."""
        ...

    def search(
        self, org_id: UUID, agent_id: UUID, query: str, *, colecao: str | None = None, limite: int = 8,
    ) -> list[SearchResult]:
        """The SAME ranked search the (later) `kb_buscar` tool calls
        (contract §D3) — backed by `agents.search_knowledge` in Real."""
        ...

    def read_document_part(
        self, org_id: UUID, agent_id: UUID, slug: str, *, parte: int = 1, max_chars: int = 24000,
        include_inactive: bool = False,
    ) -> DocumentPart:
        """The kb_ler contract (§E3) — raises :class:`NotFound` for an
        unknown OR archived slug (M4) OR a `parte` outside
        `1..total_partes`."""
        ...


class FakeStudioKnowledgeStore:
    """In-memory :class:`StudioKnowledgeStore`."""

    def __init__(self) -> None:
        self._collections: dict[UUID, dict[str, Any]] = {}
        self._documents: dict[UUID, dict[str, Any]] = {}
        self._revisions: dict[UUID, list[dict[str, Any]]] = {}

    # -- collections --------------------------------------------------

    def list_collections(self, org_id: UUID, agent_id: UUID) -> list[CollectionRecord]:
        rows = [
            row for row in self._collections.values()
            if row["org_id"] == org_id and row["agent_id"] == agent_id
        ]
        rows.sort(key=lambda r: (r["ordem"], r["created_at"]))
        return [self._collection_record(r) for r in rows]

    def get_collection(self, org_id: UUID, agent_id: UUID, collection_id: UUID) -> CollectionRecord:
        row = self._collections.get(collection_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"collection {collection_id} not found for agent {agent_id}")
        return self._collection_record(row)

    def create_collection(self, org_id: UUID, agent_id: UUID, data: CollectionInput) -> CollectionRecord:
        _validate_slug(data.slug)
        _validate_collection_caps(nome=data.nome, tag=data.tag, descricao=data.descricao)
        for row in self._collections.values():
            if row["agent_id"] == agent_id and row["slug"] == data.slug:
                # 013 UNIQUE (agent_id, slug)
                raise StudioConflict("slug_taken", f"slug {data.slug!r} already exists for this agent")
        now = utcnow()
        row = {
            "id": uuid4(), "org_id": org_id, "agent_id": agent_id, "slug": data.slug,
            "nome": data.nome, "tag": data.tag, "descricao": data.descricao, "ordem": data.ordem,
            "created_at": now, "updated_at": now,
        }
        self._collections[row["id"]] = row
        return self._collection_record(row)

    def update_collection(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        nome: Any = _UNSET, tag: Any = _UNSET, descricao: Any = _UNSET, ordem: Any = _UNSET,
    ) -> CollectionRecord:
        _validate_collection_caps(nome=nome, tag=tag, descricao=descricao)
        row = self._collections.get(collection_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"collection {collection_id} not found for agent {agent_id}")
        if nome is not _UNSET:
            row["nome"] = nome
        if tag is not _UNSET:
            row["tag"] = tag
        if descricao is not _UNSET:
            row["descricao"] = descricao
        if ordem is not _UNSET:
            row["ordem"] = ordem
        row["updated_at"] = utcnow()
        return self._collection_record(row)

    def count_documents(self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, ativo_only: bool = True) -> int:
        return sum(
            1 for row in self._documents.values()
            if row["org_id"] == org_id and row["agent_id"] == agent_id
            and row["collection_id"] == collection_id and (not ativo_only or row["ativo"])
        )

    # -- documents ------------------------------------------------------

    def _own_documents(self, org_id: UUID, agent_id: UUID):
        return [
            row for row in self._documents.values()
            if row["org_id"] == org_id and row["agent_id"] == agent_id
        ]

    def list_documents(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        q: str | None = None, tipo: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[DocumentRecord], int]:
        _validate_list_query(q)
        rows = [
            row for row in self._own_documents(org_id, agent_id)
            if row["collection_id"] == collection_id
        ]
        if tipo:
            rows = [r for r in rows if r["tipo"] == tipo]
        if q:
            needle = q.lower()
            rows = [
                r for r in rows
                if needle in r["titulo"].lower()
                or needle in (r["resumo"] or "").lower()
                or needle in r["conteudo"].lower()
            ]
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
        total = len(rows)
        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return [self._document_record(r) for r in page_rows], total

    def get_document(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> DocumentRecord:
        row = self._documents.get(doc_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"document {doc_id} not found for agent {agent_id}")
        return self._document_record(row)

    def find_document_by_slug(
        self, org_id: UUID, agent_id: UUID, slug: str, *, include_inactive: bool = False,
    ) -> DocumentRecord | None:
        for row in self._own_documents(org_id, agent_id):
            if row["slug"] == slug and (include_inactive or row["ativo"]):
                return self._document_record(row)
        return None

    def get_document_by_slug(
        self, org_id: UUID, agent_id: UUID, slug: str, *, include_inactive: bool = False,
    ) -> DocumentRecord:
        doc = self.find_document_by_slug(org_id, agent_id, slug, include_inactive=include_inactive)
        if doc is None:
            raise NotFound(f"document {slug!r} not found for agent {agent_id}")
        return doc

    def create_document(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, data: DocumentInput, author_id: UUID,
    ) -> DocumentRecord:
        _validate_slug(data.slug)
        _validate_tipo(data.tipo)
        _validate_conteudo(data.conteudo)
        for row in self._documents.values():
            if row["agent_id"] == agent_id and row["slug"] == data.slug:
                # 013 UNIQUE (agent_id, slug)
                raise StudioConflict("slug_taken", f"slug {data.slug!r} already exists for this agent")
        now = utcnow()
        row = {
            "id": uuid4(), "org_id": org_id, "collection_id": collection_id, "agent_id": agent_id,
            "slug": data.slug, "titulo": data.titulo, "tipo": data.tipo,
            "proveniencia": dict(data.proveniencia or {}), "resumo": data.resumo,
            "conteudo": data.conteudo, "source_sha": source_sha_of(data.conteudo),
            "ativo": True, "created_at": now, "updated_at": now,
        }
        self._documents[row["id"]] = row
        self._write_revision(org_id, row, op="create", author_id=author_id, motivo=None)
        return self._document_record(row)

    def update_document(
        self, org_id: UUID, agent_id: UUID, doc_id: UUID, *, author_id: UUID | None, motivo: str | None = None,
        titulo: Any = _UNSET, tipo: Any = _UNSET, resumo: Any = _UNSET, conteudo: Any = _UNSET,
        proveniencia: Any = _UNSET, ativo: Any = _UNSET,
    ) -> DocumentRecord:
        _validate_conteudo(conteudo)
        row = self._documents.get(doc_id)
        if row is None or row["org_id"] != org_id or row["agent_id"] != agent_id:
            raise NotFound(f"document {doc_id} not found for agent {agent_id}")
        op = "archive" if (ativo is False and row["ativo"]) else "update"
        if titulo is not _UNSET:
            row["titulo"] = titulo
        if tipo is not _UNSET:
            _validate_tipo(tipo)
            row["tipo"] = tipo
        if resumo is not _UNSET:
            row["resumo"] = resumo
        if conteudo is not _UNSET:
            row["conteudo"] = conteudo
            row["source_sha"] = source_sha_of(conteudo)
        if proveniencia is not _UNSET:
            row["proveniencia"] = dict(proveniencia or {})
        if ativo is not _UNSET:
            row["ativo"] = ativo
        row["updated_at"] = utcnow()
        self._write_revision(org_id, row, op=op, author_id=author_id, motivo=motivo)
        return self._document_record(row)

    def list_revisions(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> list[RevisionRecord]:
        # Ownership check (agent_id) via the document itself.
        self.get_document(org_id, agent_id, doc_id)
        rows = self._revisions.get(doc_id, [])
        return [self._revision_record(r) for r in sorted(rows, key=lambda r: r["created_at"], reverse=True)]

    def upsert_document_by_source_sha(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, slug: str, titulo: str, tipo: str,
        resumo: str | None, proveniencia: dict[str, Any] | None, conteudo: str, author_id: UUID | None = None,
    ) -> tuple[DocumentRecord, str]:
        _validate_slug(slug)
        _validate_tipo(tipo)
        _validate_conteudo(conteudo)
        sha = source_sha_of(conteudo)
        existing = None
        for row in self._own_documents(org_id, agent_id):
            if row["slug"] == slug:
                existing = row
                break
        if existing is not None and existing["collection_id"] != collection_id:
            raise StudioConflict(
                "slug_in_other_collection",
                f"document {slug!r} already lives in another collection — an import never moves it",
            )
        if existing is None:
            now = utcnow()
            row = {
                "id": uuid4(), "org_id": org_id, "collection_id": collection_id, "agent_id": agent_id,
                "slug": slug, "titulo": titulo, "tipo": tipo, "proveniencia": dict(proveniencia or {}),
                "resumo": resumo, "conteudo": conteudo, "source_sha": sha, "ativo": True,
                "created_at": now, "updated_at": now,
            }
            self._documents[row["id"]] = row
            self._write_revision(org_id, row, op="import", author_id=author_id, motivo="import")
            return self._document_record(row), "created"
        if existing["source_sha"] == sha:
            return self._document_record(existing), "unchanged"
        existing.update({
            "titulo": titulo, "tipo": tipo,
            "proveniencia": dict(proveniencia or {}), "resumo": resumo, "conteudo": conteudo,
            "source_sha": sha, "updated_at": utcnow(),
        })
        self._write_revision(org_id, existing, op="import", author_id=author_id, motivo="import")
        return self._document_record(existing), "updated"

    def search(
        self, org_id: UUID, agent_id: UUID, query: str, *, colecao: str | None = None, limite: int = 8,
    ) -> list[SearchResult]:
        _validate_search_query(query)
        tokens = [t for t in query.lower().split() if t]
        limite = max(min(limite, 20), 1)
        results: list[tuple[float, dict[str, Any]]] = []
        for row in self._own_documents(org_id, agent_id):
            if not row["ativo"]:
                continue
            collection = self._collections.get(row["collection_id"])
            if collection is None:
                continue
            if colecao and collection["slug"] != colecao:
                continue
            titulo_l = row["titulo"].lower()
            resumo_l = (row["resumo"] or "").lower()
            conteudo_l = row["conteudo"].lower()
            score = 0.0
            for tok in tokens:
                score += titulo_l.count(tok) * 3.0
                score += resumo_l.count(tok) * 2.0
                score += conteudo_l.count(tok) * 1.0
            if score <= 0:
                continue
            results.append((score, row))
        results.sort(key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True)
        out: list[SearchResult] = []
        for score, row in results[:limite]:
            collection = self._collections[row["collection_id"]]
            out.append(SearchResult(
                doc_id=row["id"], slug=row["slug"], titulo=row["titulo"],
                colecao=collection["slug"], tag=collection["tag"], tipo=row["tipo"],
                trecho=_excerpt(row["resumo"] or row["conteudo"], tokens),
                rank=score,
            ))
        return out

    def read_document_part(
        self, org_id: UUID, agent_id: UUID, slug: str, *, parte: int = 1, max_chars: int = 24000,
        include_inactive: bool = False,
    ) -> DocumentPart:
        doc = self.get_document_by_slug(org_id, agent_id, slug, include_inactive=include_inactive)
        # FK ON DELETE CASCADE: a document's collection always exists.
        collection = self._collections[doc.collection_id]
        colecao_slug = collection["slug"]
        tag = collection["tag"]
        pages = _paginate_paragraphs(doc.conteudo, max_chars)
        if parte < 1 or parte > len(pages):
            raise NotFound(f"parte {parte} out of range for document {slug!r} ({len(pages)} total)")
        return DocumentPart(
            slug=doc.slug, titulo=doc.titulo, colecao=colecao_slug, tag=tag, tipo=doc.tipo,
            proveniencia=doc.proveniencia, parte=parte, total_partes=len(pages), conteudo=pages[parte - 1],
        )

    def _write_revision(self, org_id: UUID, row: dict[str, Any], *, op: str, author_id: UUID | None, motivo: str | None) -> None:
        snapshot = {k: v for k, v in row.items() if k != "conteudo"} | {"conteudo_chars": len(row["conteudo"])}
        rev = {
            "id": uuid4(), "org_id": org_id, "document_id": row["id"], "op": op,
            "snapshot": snapshot, "author_id": author_id, "motivo": motivo, "created_at": utcnow(),
        }
        self._revisions.setdefault(row["id"], []).append(rev)

    @staticmethod
    def _collection_record(row: dict[str, Any]) -> CollectionRecord:
        return CollectionRecord(**row)

    @staticmethod
    def _document_record(row: dict[str, Any]) -> DocumentRecord:
        return DocumentRecord(**row)

    @staticmethod
    def _revision_record(row: dict[str, Any]) -> RevisionRecord:
        return RevisionRecord(**row)


def _excerpt(text: str, tokens: list[str], *, width: int = 220) -> str:
    lowered = text.lower()
    idx = -1
    for tok in tokens:
        idx = lowered.find(tok)
        if idx != -1:
            break
    if idx == -1:
        return text[:width]
    start = max(idx - width // 2, 0)
    return text[start : start + width]


class SupabaseStudioKnowledgeStore:
    """Real :class:`StudioKnowledgeStore` — Postgres via the admin client.

    Bare table names (the client already carries ``schema="agents"``) —
    ``KB § PATTERNS/backend/postgrest-schema-targeting.md``.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _collections(self):
        return self._client.schema(_SCHEMA).table(_COLLECTIONS_TABLE)

    def _documents(self):
        return self._client.schema(_SCHEMA).table(_DOCUMENTS_TABLE)

    def _revisions(self):
        return self._client.schema(_SCHEMA).table(_REVISIONS_TABLE)

    # -- collections --------------------------------------------------

    def _paged(self, build, *, label: str, order: tuple[tuple[str, bool], ...]) -> list[dict[str, Any]]:
        # PostgREST caps an unbounded select at 1000 rows silently
        # (KB § PATTERNS/backend/postgrest-row-cap.md).
        def fetch(start: int, end: int):
            q = build()
            for col, desc in order:
                q = q.order(col, desc=desc)
            return q.order("id").range(start, end).execute().data

        return list(iter_paged_rows(fetch, label=label))

    def list_collections(self, org_id: UUID, agent_id: UUID) -> list[CollectionRecord]:
        rows = self._paged(
            lambda: self._collections().select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id)),
            label=f"knowledge_collections agent_id={agent_id}", order=(("ordem", False), ("created_at", False)),
        )
        return [self._collection_record(r) for r in rows]

    def get_collection(self, org_id: UUID, agent_id: UUID, collection_id: UUID) -> CollectionRecord:
        resp = (
            self._collections().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(collection_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"collection {collection_id} not found for agent {agent_id}")
        return self._collection_record(rows[0])

    def create_collection(self, org_id: UUID, agent_id: UUID, data: CollectionInput) -> CollectionRecord:
        _validate_slug(data.slug)
        _validate_collection_caps(nome=data.nome, tag=data.tag, descricao=data.descricao)
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "slug": data.slug, "nome": data.nome,
            "tag": data.tag, "descricao": data.descricao, "ordem": data.ordem,
        }
        resp = exec_query(self._collections().insert(payload), unique_code="slug_taken")
        return self._collection_record(self._first(resp, f"collection {data.slug!r}"))

    def update_collection(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        nome: Any = _UNSET, tag: Any = _UNSET, descricao: Any = _UNSET, ordem: Any = _UNSET,
    ) -> CollectionRecord:
        _validate_collection_caps(nome=nome, tag=tag, descricao=descricao)
        updates: dict[str, Any] = {"updated_at": utcnow_iso()}
        if nome is not _UNSET:
            updates["nome"] = nome
        if tag is not _UNSET:
            updates["tag"] = tag
        if descricao is not _UNSET:
            updates["descricao"] = descricao
        if ordem is not _UNSET:
            updates["ordem"] = ordem
        resp = exec_query(
            self._collections().update(updates)
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(collection_id))
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"collection {collection_id} not found for agent {agent_id}")
        return self._collection_record(rows[0])

    def count_documents(self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, ativo_only: bool = True) -> int:
        q = (
            self._documents().select("id", count="exact")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("collection_id", str(collection_id))
        )
        if ativo_only:
            q = q.eq("ativo", True)
        resp = q.execute()
        return int(resp.count or 0)

    # -- documents ------------------------------------------------------

    def list_documents(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        q: str | None = None, tipo: str | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[DocumentRecord], int]:
        """``agents.list_knowledge_documents`` — ``q`` travels as a bound
        parameter and is LIKE-escaped in SQL (L4); it is never spliced into
        a PostgREST ``or=(...)`` filter string."""
        _validate_list_query(q)
        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
        resp = exec_rpc(self._client, _SCHEMA, "list_knowledge_documents", {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_collection_id": str(collection_id),
            "p_q": q or None, "p_tipo": tipo or None,
            "p_limit": page_size, "p_offset": (page - 1) * page_size,
        })
        data = resp.data
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or "items" not in data or "total" not in data:
            raise RuntimeError(f"list_knowledge_documents returned an unexpected shape: {data!r}")
        return [self._document_record(r) for r in data["items"]], int(data["total"])

    def get_document(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> DocumentRecord:
        resp = (
            self._documents().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(doc_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"document {doc_id} not found for agent {agent_id}")
        return self._document_record(rows[0])

    def find_document_by_slug(
        self, org_id: UUID, agent_id: UUID, slug: str, *, include_inactive: bool = False,
    ) -> DocumentRecord | None:
        q = (
            self._documents().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("slug", slug)
        )
        if not include_inactive:
            q = q.eq("ativo", True)
        rows = q.execute().data or []
        return self._document_record(rows[0]) if rows else None

    def get_document_by_slug(
        self, org_id: UUID, agent_id: UUID, slug: str, *, include_inactive: bool = False,
    ) -> DocumentRecord:
        doc = self.find_document_by_slug(org_id, agent_id, slug, include_inactive=include_inactive)
        if doc is None:
            raise NotFound(f"document {slug!r} not found for agent {agent_id}")
        return doc

    def create_document(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, data: DocumentInput, author_id: UUID,
    ) -> DocumentRecord:
        return self._create_document(org_id, agent_id, collection_id, data, author_id, op="create", motivo=None)

    def _create_document(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, data: DocumentInput,
        author_id: UUID | None, *, op: str, motivo: str | None,
    ) -> DocumentRecord:
        _validate_slug(data.slug)
        _validate_tipo(data.tipo)
        _validate_conteudo(data.conteudo)
        payload = {
            "org_id": str(org_id), "collection_id": str(collection_id), "agent_id": str(agent_id),
            "slug": data.slug, "titulo": data.titulo, "tipo": data.tipo,
            "proveniencia": dict(data.proveniencia or {}), "resumo": data.resumo,
            "conteudo": data.conteudo, "source_sha": source_sha_of(data.conteudo), "ativo": True,
        }
        resp = exec_query(self._documents().insert(payload), unique_code="slug_taken")
        record = self._document_record(self._first(resp, f"document {data.slug!r}"))
        self._insert_revision(org_id, record, op=op, author_id=author_id, motivo=motivo)
        return record

    def update_document(
        self, org_id: UUID, agent_id: UUID, doc_id: UUID, *, author_id: UUID | None, motivo: str | None = None,
        titulo: Any = _UNSET, tipo: Any = _UNSET, resumo: Any = _UNSET, conteudo: Any = _UNSET,
        proveniencia: Any = _UNSET, ativo: Any = _UNSET,
    ) -> DocumentRecord:
        return self._update_document(
            org_id, agent_id, doc_id, author_id=author_id, motivo=motivo, op=None,
            titulo=titulo, tipo=tipo, resumo=resumo, conteudo=conteudo, proveniencia=proveniencia, ativo=ativo,
        )

    def _update_document(
        self, org_id: UUID, agent_id: UUID, doc_id: UUID, *, author_id: UUID | None, motivo: str | None,
        op: str | None, titulo: Any = _UNSET, tipo: Any = _UNSET, resumo: Any = _UNSET,
        conteudo: Any = _UNSET, proveniencia: Any = _UNSET, ativo: Any = _UNSET,
    ) -> DocumentRecord:
        _validate_conteudo(conteudo)
        before = self.get_document(org_id, agent_id, doc_id)
        if op is None:
            op = "archive" if (ativo is False and before.ativo) else "update"
        updates: dict[str, Any] = {"updated_at": utcnow_iso()}
        if titulo is not _UNSET:
            updates["titulo"] = titulo
        if tipo is not _UNSET:
            _validate_tipo(tipo)
            updates["tipo"] = tipo
        if resumo is not _UNSET:
            updates["resumo"] = resumo
        if conteudo is not _UNSET:
            updates["conteudo"] = conteudo
            updates["source_sha"] = source_sha_of(conteudo)
        if proveniencia is not _UNSET:
            updates["proveniencia"] = dict(proveniencia or {})
        if ativo is not _UNSET:
            updates["ativo"] = ativo
        resp = exec_query(
            self._documents().update(updates)
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(doc_id))
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"document {doc_id} not found for agent {agent_id}")
        record = self._document_record(rows[0])
        self._insert_revision(org_id, record, op=op, author_id=author_id, motivo=motivo)
        return record

    def list_revisions(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> list[RevisionRecord]:
        self.get_document(org_id, agent_id, doc_id)
        rows = self._paged(
            lambda: self._revisions().select("*").eq("org_id", str(org_id)).eq("document_id", str(doc_id)),
            label=f"knowledge_revisions document_id={doc_id}", order=(("created_at", True),),
        )
        return [self._revision_record(r) for r in rows]

    def upsert_document_by_source_sha(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, slug: str, titulo: str, tipo: str,
        resumo: str | None, proveniencia: dict[str, Any] | None, conteudo: str, author_id: UUID | None = None,
    ) -> tuple[DocumentRecord, str]:
        _validate_slug(slug)
        _validate_tipo(tipo)
        _validate_conteudo(conteudo)
        sha = source_sha_of(conteudo)
        # Archived documents count: the slug is unique per agent regardless.
        existing = self.find_document_by_slug(org_id, agent_id, slug, include_inactive=True)
        if existing is not None and existing.collection_id != collection_id:
            raise StudioConflict(
                "slug_in_other_collection",
                f"document {slug!r} already lives in another collection — an import never moves it",
            )
        if existing is None:
            record = self._create_document(
                org_id, agent_id, collection_id,
                DocumentInput(slug=slug, titulo=titulo, tipo=tipo, conteudo=conteudo, resumo=resumo, proveniencia=proveniencia),
                author_id, op="import", motivo="import",
            )
            return record, "created"
        if existing.source_sha == sha:
            return existing, "unchanged"
        record = self._update_document(
            org_id, agent_id, existing.id, author_id=author_id, motivo="import", op="import",
            titulo=titulo, tipo=tipo, resumo=resumo, conteudo=conteudo, proveniencia=proveniencia,
        )
        return record, "updated"

    def search(
        self, org_id: UUID, agent_id: UUID, query: str, *, colecao: str | None = None, limite: int = 8,
    ) -> list[SearchResult]:
        _validate_search_query(query)
        params = {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_query": query,
            "p_colecao": colecao, "p_limite": max(min(limite, 20), 1),
        }
        resp = exec_rpc(self._client, _SCHEMA, "search_knowledge", params)
        rows = resp.data or []
        return [
            SearchResult(
                doc_id=UUID(str(r["doc_id"])), slug=r["slug"], titulo=r["titulo"],
                colecao=r["colecao"], tag=r.get("tag"), tipo=r["tipo"],
                trecho=r.get("trecho") or "", rank=float(r.get("rank") or 0.0),
            )
            for r in rows
        ]

    def read_document_part(
        self, org_id: UUID, agent_id: UUID, slug: str, *, parte: int = 1, max_chars: int = 24000,
        include_inactive: bool = False,
    ) -> DocumentPart:
        doc = self.get_document_by_slug(org_id, agent_id, slug, include_inactive=include_inactive)
        collection = self.get_collection(org_id, agent_id, doc.collection_id)
        pages = _paginate_paragraphs(doc.conteudo, max_chars)
        if parte < 1 or parte > len(pages):
            raise NotFound(f"parte {parte} out of range for document {slug!r} ({len(pages)} total)")
        return DocumentPart(
            slug=doc.slug, titulo=doc.titulo, colecao=collection.slug, tag=collection.tag, tipo=doc.tipo,
            proveniencia=doc.proveniencia, parte=parte, total_partes=len(pages), conteudo=pages[parte - 1],
        )

    def _insert_revision(self, org_id: UUID, record: DocumentRecord, *, op: str, author_id: UUID | None, motivo: str | None) -> None:
        snapshot = {
            "id": str(record.id), "slug": record.slug, "titulo": record.titulo, "tipo": record.tipo,
            "resumo": record.resumo, "proveniencia": record.proveniencia, "ativo": record.ativo,
            "source_sha": record.source_sha, "conteudo_chars": len(record.conteudo),
        }
        payload = {
            "org_id": str(org_id), "document_id": str(record.id), "op": op, "snapshot": snapshot,
            "author_id": str(author_id) if author_id else None, "motivo": motivo,
        }
        exec_query(self._revisions().insert(payload))

    @staticmethod
    def _first(resp, what: str) -> dict[str, Any]:
        rows = resp.data or []
        if not rows:
            # A successful INSERT ... RETURNING always yields the row; empty
            # data here is a driver/contract break, never "already exists"
            # (duplicates RAISE 23505 → StudioConflict above).
            raise RuntimeError(f"insert of {what} returned no row")
        return rows[0]

    @staticmethod
    def _collection_record(row: dict[str, Any]) -> CollectionRecord:
        return CollectionRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), agent_id=UUID(str(row["agent_id"])),
            slug=row["slug"], nome=row["nome"], tag=row.get("tag"), descricao=row.get("descricao") or "",
            ordem=int(row.get("ordem") or 0), created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _document_record(row: dict[str, Any]) -> DocumentRecord:
        return DocumentRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), collection_id=UUID(str(row["collection_id"])),
            agent_id=UUID(str(row["agent_id"])), slug=row["slug"], titulo=row["titulo"], tipo=row["tipo"],
            proveniencia=row.get("proveniencia") or {}, resumo=row.get("resumo"), conteudo=row["conteudo"],
            source_sha=row["source_sha"], ativo=bool(row.get("ativo", False)),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_record(row: dict[str, Any]) -> RevisionRecord:
        return RevisionRecord(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), document_id=UUID(str(row["document_id"])),
            op=row["op"], snapshot=row.get("snapshot") or {},
            author_id=UUID(str(row["author_id"])) if row.get("author_id") else None,
            motivo=row.get("motivo"), created_at=row["created_at"],
        )


def get_studio_knowledge_store(settings: Any) -> StudioKnowledgeStore:
    """Real when a Supabase service-role key is configured, Fake otherwise
    — same signal as :func:`app.stores.agents.get_agent_store`."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeStudioKnowledgeStore()
    from app.database import get_admin_client

    return SupabaseStudioKnowledgeStore(get_admin_client())
