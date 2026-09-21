"""Agent Studio — knowledge library store (contract §B2/§D3/§E3, slice BE-KE).

Two seed-shaped IO surfaces live in this module:

1. ``StudioKnowledgeStore`` — collections + documents (with a revision per
   change) + full-text search + the paged ``read_document_part`` reader
   that backs the (later, BE-RT-owned) ``kb_ler`` MCP tool contract §E3.
2. ``AgentLookup`` — a deliberately MINIMAL ``(org_id, key) -> agent``
   resolver, separate from ``app.stores.agents.AgentStore``. Wave-1 slices
   never import each other's unfinished code (contract §J2.3): BE-DEF owns
   ``app/stores/studio_definitions.py`` (not present in this branch yet)
   and is the eventual place a `definition_mode`-aware store belongs, but
   BE-KE's routers need *something* today to resolve a studio agent by key
   and read its `definition_mode` / `publicacao_limiar` — both added to
   ``agents.agents`` by 012 (a parallel, not-yet-merged migration). This
   lookup queries those columns directly; it does not attempt to become
   the canonical agent store.

Every store method takes ``org_id`` explicitly and filters by it — routes
use the admin client and bypass RLS (contract §B intro "Routes use the
admin client"), so this filter IS the authorization boundary. A foreign
``collection_id``/``doc_id`` raises :class:`~app.stores.errors.NotFound`
— never a 403 (contract §H.1 "never 403-leak").

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

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound

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
    "StudioAgentRef",
    "AgentLookup",
    "FakeAgentLookup",
    "SupabaseAgentLookup",
    "get_agent_lookup",
]

_SCHEMA = "agents"
_COLLECTIONS_TABLE = "knowledge_collections"
_DOCUMENTS_TABLE = "knowledge_documents"
_REVISIONS_TABLE = "knowledge_revisions"
_AGENTS_TABLE = "agents"

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

    def get_document_by_slug(self, org_id: UUID, agent_id: UUID, slug: str) -> DocumentRecord: ...

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
        """Upsert keyed on ``source_sha`` (contract §F import semantics).
        Returns ``(record, "created" | "updated" | "unchanged")`` — the
        importer aggregates these into its response counters. Writes a
        ``knowledge_revisions`` row with ``op="import"`` for created/updated,
        never for unchanged."""
        ...

    def search(
        self, org_id: UUID, agent_id: UUID, query: str, *, colecao: str | None = None, limite: int = 8,
    ) -> list[SearchResult]:
        """The SAME ranked search the (later) `kb_buscar` tool calls
        (contract §D3) — backed by `agents.search_knowledge` in Real."""
        ...

    def read_document_part(
        self, org_id: UUID, agent_id: UUID, slug: str, *, parte: int = 1, max_chars: int = 24000,
    ) -> DocumentPart:
        """The kb_ler contract (§E3) — raises :class:`NotFound` for an
        unknown slug OR a `parte` outside `1..total_partes`."""
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
        for row in self._collections.values():
            if row["org_id"] == org_id and row["agent_id"] == agent_id and row["slug"] == data.slug:
                raise ValueError(f"slug {data.slug!r} already exists for this agent")
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

    def get_document_by_slug(self, org_id: UUID, agent_id: UUID, slug: str) -> DocumentRecord:
        for row in self._own_documents(org_id, agent_id):
            if row["slug"] == slug:
                return self._document_record(row)
        raise NotFound(f"document {slug!r} not found for agent {agent_id}")

    def create_document(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, data: DocumentInput, author_id: UUID,
    ) -> DocumentRecord:
        _validate_slug(data.slug)
        _validate_tipo(data.tipo)
        for row in self._own_documents(org_id, agent_id):
            if row["slug"] == data.slug:
                raise ValueError(f"slug {data.slug!r} already exists for this agent")
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
        sha = source_sha_of(conteudo)
        existing = None
        for row in self._own_documents(org_id, agent_id):
            if row["slug"] == slug:
                existing = row
                break
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
            "collection_id": collection_id, "titulo": titulo, "tipo": tipo,
            "proveniencia": dict(proveniencia or {}), "resumo": resumo, "conteudo": conteudo,
            "source_sha": sha, "updated_at": utcnow(),
        })
        self._write_revision(org_id, existing, op="import", author_id=author_id, motivo="import")
        return self._document_record(existing), "updated"

    def search(
        self, org_id: UUID, agent_id: UUID, query: str, *, colecao: str | None = None, limite: int = 8,
    ) -> list[SearchResult]:
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
    ) -> DocumentPart:
        doc = self.get_document_by_slug(org_id, agent_id, slug)
        collection = self._collections.get(doc.collection_id)
        colecao_slug = collection["slug"] if collection else ""
        tag = collection["tag"] if collection else None
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

    def list_collections(self, org_id: UUID, agent_id: UUID) -> list[CollectionRecord]:
        resp = (
            self._collections().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
            .order("ordem").order("created_at")
            .execute()
        )
        return [self._collection_record(r) for r in (resp.data or [])]

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
        payload = {
            "org_id": str(org_id), "agent_id": str(agent_id), "slug": data.slug, "nome": data.nome,
            "tag": data.tag, "descricao": data.descricao, "ordem": data.ordem,
        }
        resp = self._collections().insert(payload).execute()
        rows = resp.data or []
        if not rows:
            raise ValueError(f"slug {data.slug!r} already exists for this agent")
        return self._collection_record(rows[0])

    def update_collection(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *,
        nome: Any = _UNSET, tag: Any = _UNSET, descricao: Any = _UNSET, ordem: Any = _UNSET,
    ) -> CollectionRecord:
        updates: dict[str, Any] = {"updated_at": utcnow_iso()}
        if nome is not _UNSET:
            updates["nome"] = nome
        if tag is not _UNSET:
            updates["tag"] = tag
        if descricao is not _UNSET:
            updates["descricao"] = descricao
        if ordem is not _UNSET:
            updates["ordem"] = ordem
        resp = (
            self._collections().update(updates)
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(collection_id))
            .execute()
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
        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
        query = (
            self._documents().select("*", count="exact")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("collection_id", str(collection_id))
        )
        if tipo:
            query = query.eq("tipo", tipo)
        if q:
            escaped = q.replace(",", "").replace("%", "")
            query = query.or_(f"titulo.ilike.%{escaped}%,resumo.ilike.%{escaped}%,conteudo.ilike.%{escaped}%")
        start = (page - 1) * page_size
        resp = query.order("updated_at", desc=True).range(start, start + page_size - 1).execute()
        rows = resp.data or []
        return [self._document_record(r) for r in rows], int(resp.count or 0)

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

    def get_document_by_slug(self, org_id: UUID, agent_id: UUID, slug: str) -> DocumentRecord:
        resp = (
            self._documents().select("*")
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("slug", slug)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"document {slug!r} not found for agent {agent_id}")
        return self._document_record(rows[0])

    def create_document(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, data: DocumentInput, author_id: UUID,
    ) -> DocumentRecord:
        _validate_slug(data.slug)
        _validate_tipo(data.tipo)
        payload = {
            "org_id": str(org_id), "collection_id": str(collection_id), "agent_id": str(agent_id),
            "slug": data.slug, "titulo": data.titulo, "tipo": data.tipo,
            "proveniencia": dict(data.proveniencia or {}), "resumo": data.resumo,
            "conteudo": data.conteudo, "source_sha": source_sha_of(data.conteudo), "ativo": True,
        }
        resp = self._documents().insert(payload).execute()
        rows = resp.data or []
        if not rows:
            raise ValueError(f"slug {data.slug!r} already exists for this agent")
        record = self._document_record(rows[0])
        self._insert_revision(org_id, record, op="create", author_id=author_id, motivo=None)
        return record

    def update_document(
        self, org_id: UUID, agent_id: UUID, doc_id: UUID, *, author_id: UUID | None, motivo: str | None = None,
        titulo: Any = _UNSET, tipo: Any = _UNSET, resumo: Any = _UNSET, conteudo: Any = _UNSET,
        proveniencia: Any = _UNSET, ativo: Any = _UNSET,
    ) -> DocumentRecord:
        before = self.get_document(org_id, agent_id, doc_id)
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
        resp = (
            self._documents().update(updates)
            .eq("org_id", str(org_id)).eq("agent_id", str(agent_id)).eq("id", str(doc_id))
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"document {doc_id} not found for agent {agent_id}")
        record = self._document_record(rows[0])
        self._insert_revision(org_id, record, op=op, author_id=author_id, motivo=motivo)
        return record

    def list_revisions(self, org_id: UUID, agent_id: UUID, doc_id: UUID) -> list[RevisionRecord]:
        self.get_document(org_id, agent_id, doc_id)
        resp = (
            self._revisions().select("*")
            .eq("org_id", str(org_id)).eq("document_id", str(doc_id))
            .order("created_at", desc=True)
            .execute()
        )
        return [self._revision_record(r) for r in (resp.data or [])]

    def upsert_document_by_source_sha(
        self, org_id: UUID, agent_id: UUID, collection_id: UUID, *, slug: str, titulo: str, tipo: str,
        resumo: str | None, proveniencia: dict[str, Any] | None, conteudo: str, author_id: UUID | None = None,
    ) -> tuple[DocumentRecord, str]:
        _validate_slug(slug)
        _validate_tipo(tipo)
        sha = source_sha_of(conteudo)
        try:
            existing = self.get_document_by_slug(org_id, agent_id, slug)
        except NotFound:
            existing = None
        if existing is None:
            record = self.create_document(
                org_id, agent_id, collection_id,
                DocumentInput(slug=slug, titulo=titulo, tipo=tipo, conteudo=conteudo, resumo=resumo, proveniencia=proveniencia),
                author_id=author_id,
            )
            return record, "created"
        if existing.source_sha == sha:
            return existing, "unchanged"
        record = self.update_document(
            org_id, agent_id, existing.id, author_id=author_id, motivo="import",
            titulo=titulo, tipo=tipo, resumo=resumo, conteudo=conteudo, proveniencia=proveniencia,
        )
        return record, "updated"

    def search(
        self, org_id: UUID, agent_id: UUID, query: str, *, colecao: str | None = None, limite: int = 8,
    ) -> list[SearchResult]:
        params = {
            "p_org_id": str(org_id), "p_agent_id": str(agent_id), "p_query": query,
            "p_colecao": colecao, "p_limite": max(min(limite, 20), 1),
        }
        resp = self._client.schema(_SCHEMA).rpc("search_knowledge", params).execute()
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
    ) -> DocumentPart:
        doc = self.get_document_by_slug(org_id, agent_id, slug)
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
        self._revisions().insert(payload).execute()

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


# ── AgentLookup — minimal (org_id, key) -> studio agent resolver ─────────


@dataclass(frozen=True)
class StudioAgentRef:
    id: UUID
    org_id: UUID
    key: str
    nome: str
    definition_mode: str
    ativo: bool
    publicacao_limiar: float


class AgentLookup(Protocol):
    def get_by_key(self, org_id: UUID, key: str) -> StudioAgentRef:
        """Raises :class:`NotFound` for an unknown key."""
        ...


class FakeAgentLookup:
    """In-memory :class:`AgentLookup` — tests seed rows via :meth:`seed`."""

    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, str], StudioAgentRef] = {}

    def seed(
        self, org_id: UUID, key: str, *, agent_id: UUID | None = None, nome: str | None = None,
        definition_mode: str = "studio", ativo: bool = True, publicacao_limiar: float = 0.800,
    ) -> StudioAgentRef:
        ref = StudioAgentRef(
            id=agent_id or uuid4(), org_id=org_id, key=key, nome=nome or key,
            definition_mode=definition_mode, ativo=ativo, publicacao_limiar=publicacao_limiar,
        )
        self._rows[(org_id, key)] = ref
        return ref

    def get_by_key(self, org_id: UUID, key: str) -> StudioAgentRef:
        ref = self._rows.get((org_id, key))
        if ref is None:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        return ref


class SupabaseAgentLookup:
    """Real :class:`AgentLookup` — reads `definition_mode` /
    `publicacao_limiar` (012 columns) directly off `agents.agents`."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_by_key(self, org_id: UUID, key: str) -> StudioAgentRef:
        resp = (
            self._client.schema(_SCHEMA).table(_AGENTS_TABLE)
            .select("id, org_id, key, nome, definition_mode, ativo, publicacao_limiar")
            .eq("org_id", str(org_id)).eq("key", key)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            raise NotFound(f"agent {key!r} not found for org {org_id}")
        row = rows[0]
        return StudioAgentRef(
            id=UUID(str(row["id"])), org_id=UUID(str(row["org_id"])), key=row["key"], nome=row["nome"],
            definition_mode=row["definition_mode"], ativo=bool(row.get("ativo", False)),
            publicacao_limiar=float(row["publicacao_limiar"]),
        )


def get_agent_lookup(settings: Any) -> AgentLookup:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeAgentLookup()
    from app.database import get_admin_client

    return SupabaseAgentLookup(get_admin_client())
