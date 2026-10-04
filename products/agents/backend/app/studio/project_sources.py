"""Consumer-repo project context → knowledge (Agent Packages §G2, §G3, §J2).

:func:`sync_project_sources` applies a FULL manifest for one ``(agent,
project)``:

* every file becomes a knowledge document of the collection
  ``projeto-<slug>`` (tag ``PRJ``), so Studio §E3 ``kb_buscar`` / ``kb_ler``
  reach it exactly like any other knowledge;
* upsert keyed on ``sha256`` — an unchanged file writes nothing (no revision);
* paths ABSENT from the manifest are removed (the document is archived — never
  served again — and the ledger row deleted), and a file that comes back is
  reactivated;
* a file over :data:`SOURCE_FILE_MAX_BYTES` is skipped with a listed warning
  and counts as absent (a stale copy of a file that outgrew the cap must not
  keep being served);
* hard excludes (``.env*``, keys, ``node_modules``, binaries) and the shared
  secret scan refuse the WHOLE call — a manifest that carries one is a client
  bug and must be loud, never partially applied.

The orchestration lives here (not in the router) so it is testable against the
Fakes and reused by nothing else's HTTP shape.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from app.schemas.packages import SOURCE_FILE_MAX_BYTES, SourceItem
from app.stores.agent_packages import AgentPackageStore, ProjectSourceRecord
from app.stores.errors import NotFound
from app.stores.studio_knowledge import CollectionInput, StudioKnowledgeStore, source_sha_of
from noctusai_lib.security import has_secret

__all__ = [
    "PROJECT_COLLECTION_TAG",
    "SourcesRefused",
    "collection_slug",
    "document_slug",
    "sources_sha",
    "sync_project_sources",
]

logger = logging.getLogger(__name__)

PROJECT_COLLECTION_TAG = "PRJ"
_COLLECTION_ORDER = 900

#: Path segments / basenames that must never be synced (§J2.2).
_FORBIDDEN_SEGMENTS = frozenset({"node_modules", ".git", ".ssh", ".aws", ".gnupg"})
_FORBIDDEN_SUFFIXES = (
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".der", ".crt", ".cer",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".heic",
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar",
    ".mp3", ".mp4", ".mov", ".wav", ".m4a", ".ogg", ".webm",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".jar", ".apk", ".ipa", ".aab",
    ".sqlite", ".db", ".lock",
)
_FORBIDDEN_BASENAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "credentials", "secrets.json"})
_DOC_TIPO = {"doc": "fonte", "codigo": "fonte", "quadro": "outro"}


class SourcesRefused(Exception):
    """The manifest is refused as a whole (``status`` + machine ``code``)."""

    def __init__(self, status: int, code: str, detail: str, **extra: object) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra


def collection_slug(project_slug: str) -> str:
    return f"projeto-{project_slug}"


def _slugify(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def document_slug(project_slug: str, path: str) -> str:
    """Deterministic, collision-proof per ``(project, path)``: the readable
    part is lossy (``a/b.md`` and ``a-b.md`` slugify alike), so a short hash
    of the exact path is appended. Matches the 013 slug CHECK, ≤ 128."""
    digest = hashlib.sha256(f"{project_slug}\0{path}".encode("utf-8")).hexdigest()[:10]
    readable = _slugify(f"{project_slug}-{path}")[:100].strip("-") or "arquivo"
    return f"{readable}-{digest}"


def sources_sha(records: list[ProjectSourceRecord]) -> str:
    """One stable fingerprint of a project's synced state (Studio shows it as
    "source sha"): sha256 over the sorted ``path\\0sha256`` lines."""
    body = "\n".join(f"{r.path}\0{r.sha256}" for r in sorted(records, key=lambda r: r.path))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _forbidden_reason(path: str) -> str | None:
    parts = path.split("/")
    base = parts[-1].lower()
    if any(p in _FORBIDDEN_SEGMENTS for p in parts[:-1]) or base in _FORBIDDEN_SEGMENTS:
        return "diretório excluído (node_modules/.git/…)"
    if base.startswith(".env"):
        return "arquivo .env* nunca é sincronizado"
    if base in _FORBIDDEN_BASENAMES:
        return "arquivo de credenciais"
    if base.endswith(_FORBIDDEN_SUFFIXES):
        return "extensão binária/chave excluída"
    return None


@dataclass
class _Counts:
    criados: int = 0
    atualizados: int = 0
    inalterados: int = 0
    removidos: int = 0


def _ensure_collection(knowledge: StudioKnowledgeStore, org_id: UUID, agent_id: UUID, project_slug: str):
    slug = collection_slug(project_slug)
    for col in knowledge.list_collections(org_id, agent_id):
        if col.slug == slug:
            return col
    return knowledge.create_collection(
        org_id, agent_id,
        CollectionInput(
            slug=slug, nome=f"Projeto: {project_slug}", tag=PROJECT_COLLECTION_TAG,
            descricao=f"Contexto do projeto {project_slug}, sincronizado do repositório a cada push.",
            ordem=_COLLECTION_ORDER,
        ),
    )


def sync_project_sources(
    *,
    org_id: UUID,
    agent_id: UUID,
    project_slug: str,
    items: list[SourceItem],
    author_id: UUID | None,
    packages: AgentPackageStore,
    knowledge: StudioKnowledgeStore,
) -> dict:
    """Apply the full manifest ``items`` (see module docstring). Raises
    :class:`SourcesRefused` (nothing written) on a forbidden path, a sha
    mismatch or a secret hit."""
    # ── whole-call validation first: nothing is written unless all of it passes
    forbidden = [(it.path, _forbidden_reason(it.path)) for it in items]
    forbidden = [(p, why) for p, why in forbidden if why]
    if forbidden:
        raise SourcesRefused(
            422, "forbidden_path", "O manifesto contém caminhos que nunca são sincronizados.",
            caminhos=[{"path": p, "motivo": why} for p, why in forbidden],
        )
    mismatched = [it.path for it in items if source_sha_of(it.conteudo) != it.sha256]
    if mismatched:
        raise SourcesRefused(
            422, "sha_mismatch", "sha256 diverge do conteúdo (sha256 do texto em UTF-8).", caminhos=mismatched,
        )
    leaked = [it.path for it in items if has_secret(it.conteudo)]
    if leaked:
        # Paths only — never the matched text.
        raise SourcesRefused(
            422, "secret_detected", "Possível segredo detectado; a sincronização foi abortada.", caminhos=leaked,
        )

    avisos: list[str] = []
    ignorados: list[dict[str, str]] = []
    keep: list[SourceItem] = []
    for it in items:
        size = len(it.conteudo.encode("utf-8"))
        if size > SOURCE_FILE_MAX_BYTES:
            ignorados.append({"path": it.path, "motivo": f"maior que {SOURCE_FILE_MAX_BYTES // 1024} KB ({size // 1024} KB)"})
        elif not it.conteudo.strip():
            ignorados.append({"path": it.path, "motivo": "arquivo vazio"})
        else:
            keep.append(it)
    for skipped in ignorados:
        avisos.append(f"{skipped['path']} ignorado: {skipped['motivo']}")

    collection = _ensure_collection(knowledge, org_id, agent_id, project_slug)
    existing = {r.path: r for r in packages.list_sources(org_id, agent_id, project_slug)}
    counts = _Counts()

    for it in keep:
        prev = existing.get(it.path)
        if prev is not None and prev.sha256 == it.sha256 and prev.tipo == it.tipo and prev.document_id is not None:
            counts.inalterados += 1
            continue
        record, outcome = knowledge.upsert_document_by_source_sha(
            org_id, agent_id, collection.id,
            slug=document_slug(project_slug, it.path), titulo=it.path, tipo=_DOC_TIPO[it.tipo],
            resumo=None,
            proveniencia={"origem": f"projeto:{project_slug}", "referencia": it.path, "notas": f"tipo={it.tipo}"},
            conteudo=it.conteudo, author_id=author_id,
        )
        if not record.ativo:
            # The path left the manifest earlier and is back: an import keeps
            # an archived document archived, so reactivate it explicitly.
            record = knowledge.update_document(
                org_id, agent_id, record.id, author_id=author_id, motivo="de volta ao manifesto", ativo=True,
            )
            outcome = "updated" if outcome == "unchanged" else outcome
        packages.upsert_source(
            org_id, agent_id, project_slug, path=it.path, sha256=it.sha256, tipo=it.tipo, document_id=record.id,
        )
        if outcome == "created":
            counts.criados += 1
        elif outcome == "updated":
            counts.atualizados += 1
        else:
            counts.inalterados += 1

    # ── delete-absent: stored paths that are not (kept) in this manifest
    kept_paths = {it.path for it in keep}
    gone = [r for p, r in existing.items() if p not in kept_paths]
    for rec in gone:
        if rec.document_id is not None:
            try:
                knowledge.update_document(
                    org_id, agent_id, rec.document_id, author_id=author_id,
                    motivo="removido do manifesto", ativo=False,
                )
            except NotFound:
                logger.warning(
                    "project sources: document %s of %s/%s already gone; dropping the ledger row only",
                    rec.document_id, project_slug, rec.path,
                )
    if gone:
        counts.removidos = packages.delete_sources(org_id, agent_id, project_slug, [r.path for r in gone])

    final = packages.list_sources(org_id, agent_id, project_slug)
    return {
        "projeto": project_slug,
        "colecao_id": collection.id,
        "colecao_slug": collection.slug,
        "total": len(final),
        "criados": counts.criados,
        "atualizados": counts.atualizados,
        "inalterados": counts.inalterados,
        "removidos": counts.removidos,
        "ignorados": ignorados,
        "avisos": avisos,
        "sources_sha": sources_sha(final),
    }
