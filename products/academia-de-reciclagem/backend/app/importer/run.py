"""Transactional import orchestrator (contract §B.6 + §A.11).

``run_import`` is the only stateful/async piece of the importer: it
walks parsed ``BundleLine``s in commit-time order, maps each one via
``mapping.map_line``, and writes every resulting entity through
``KnowledgeStore.import_entity`` inside a single transaction —
all-or-nothing, idempotent on ``(git_sha, natural_key)`` by
construction of that store method.

``Provenance`` and ``KnowledgeStore`` are A1's real
``app/knowledge/`` module (contract §A.11), imported at runtime — A1
landed on ``dev`` and this branch was rebased onto it. Earlier revisions
of this module duck-typed a local ``_ImportProvenance`` while A1 was
still in flight; that stand-in is gone.
"""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, TypedDict
from uuid import UUID

from app.importer.bundle import BundleLine
from app.importer.mapping import map_line
from app.knowledge import KnowledgeStore, Provenance

# JSON-state entity types: a revision is only worth writing when the
# item's content actually changed vs. the previous commit's version of
# the same file (contract §B.6).
_DIFFED_ENTITY_TYPES = frozenset({"open_question", "roadmap_phase", "task"})

_CODE_RE = re.compile(r"^([A-Z]+)-(\d+)$")
_TRACKED_CODE_PREFIXES = ("D", "Q", "T")


class ImportReport(TypedDict):
    """``verificacao.revisoes_importadas`` counts ``import_entity`` CALLS
    issued this run, not net-new ``kb_revisions`` rows. A1's
    ``import_entity`` returns the (possibly-unchanged) row whether or
    not it actually wrote a revision — the idempotency signal
    (duplicate ``(git_sha, natural_key)``) is internal to the store, not
    exposed on the return value — so this counter cannot distinguish a
    genuine write from a no-op replay. A full idempotent re-run of the
    same bundle therefore reports the SAME ``revisoes_importadas`` as
    the first run, even though zero additional ``kb_revisions`` rows
    land (see ``tests/importer/test_run.py::TestIdempotentReplay``,
    which asserts on the store's revision count instead of this field).
    """

    verificacao: dict[str, Any]
    avisos: list[str]


def _track_code(max_codes: dict[str, int], codigo: str | None) -> None:
    if not codigo:
        return
    match = _CODE_RE.match(codigo)
    if not match:
        return
    prefix, number = match.group(1), int(match.group(2))
    if prefix in _TRACKED_CODE_PREFIXES:
        max_codes[prefix] = max(max_codes.get(prefix, 0), number)


def _newest_line_per_path(lines: list[BundleLine]) -> dict[str, BundleLine]:
    newest: dict[str, BundleLine] = {}
    for line in lines:
        current = newest.get(line.path)
        if current is None or line.git_committed_at_dt >= current.git_committed_at_dt:
            newest[line.path] = line
    return newest


def _verify_hashes_head_ok(
    last_processed_content_by_path: dict[str, str],
    newest_line_by_path: dict[str, BundleLine],
) -> bool:
    """sha256 of each processed path's LAST-seen content (in
    commit-time order) vs. sha256 of that path's newest bundle line.
    By construction these should always match when lines are processed
    in commit-time order — this is the internal-consistency check the
    contract calls ``hashes_head_ok``, and it exists to catch an
    ordering/processing bug, not to compare against anything external.
    """
    for path, content in last_processed_content_by_path.items():
        newest = newest_line_by_path.get(path)
        if newest is None:
            return False
        if sha256(content.encode("utf-8")).hexdigest() != sha256(
            newest.content.encode("utf-8")
        ).hexdigest():
            return False
    return True


async def run_import(
    store: KnowledgeStore,
    org_id: UUID,
    lines: list[BundleLine],
    importing_user_id: UUID,
) -> ImportReport:
    """Import every mapped entity from ``lines`` into ``store``, inside
    one transaction. Lines are processed in commit-time order
    (``git_committed_at`` ascending). Idempotent at the STORE level:
    re-running the same bundle writes zero additional ``kb_revisions``
    rows, because ``store.import_entity`` is idempotent on
    ``(git_sha, natural_key)`` (see ``ImportReport`` docstring for the
    corresponding caveat on the ``revisoes_importadas`` counter).
    """
    ordered = sorted(lines, key=lambda ln: ln.git_committed_at_dt)
    newest_line_by_path = _newest_line_per_path(lines)

    avisos: list[str] = []
    entidades: dict[str, int] = {}
    revisoes_importadas = 0
    max_codes: dict[str, int] = {}
    last_json_snapshot: dict[tuple[str, str], dict[str, Any]] = {}
    last_processed_content_by_path: dict[str, str] = {}

    async with store.transaction():
        for line in ordered:
            result = map_line(line.path, line.content)

            if result.warning:
                avisos.append(result.warning)

            if result.skipped or not result.entities:
                continue

            last_processed_content_by_path[line.path] = line.content

            prov = Provenance(
                author_kind="import",
                user_id=importing_user_id,
                git_sha=line.git_sha,
                git_author_raw=line.git_author_raw,
                git_committed_at=line.git_committed_at_dt,
                git_message=line.git_message,
            )

            for entity in result.entities:
                if entity.entity_type in _DIFFED_ENTITY_TYPES:
                    diff_key = (entity.entity_type, entity.natural_key)
                    previous = last_json_snapshot.get(diff_key)
                    last_json_snapshot[diff_key] = entity.snapshot
                    if previous is not None and previous == entity.snapshot:
                        continue  # unchanged since the prior commit's version

                await store.import_entity(
                    org_id,
                    entity.entity_type,
                    entity.natural_key,
                    entity.snapshot,
                    prov,
                )
                revisoes_importadas += 1
                entidades[entity.entity_type] = entidades.get(entity.entity_type, 0) + 1
                _track_code(max_codes, entity.snapshot.get("codigo"))

        await store.seed_counters(
            org_id, {prefix: max_codes.get(prefix, 0) for prefix in _TRACKED_CODE_PREFIXES}
        )

    hashes_head_ok = _verify_hashes_head_ok(
        last_processed_content_by_path, newest_line_by_path
    )

    return {
        "verificacao": {
            "revisoes_git": len(lines),
            "revisoes_importadas": revisoes_importadas,
            "entidades": entidades,
            "hashes_head_ok": hashes_head_ok,
            "codigos": {prefix: max_codes.get(prefix, 0) for prefix in _TRACKED_CODE_PREFIXES},
        },
        "avisos": avisos,
    }
