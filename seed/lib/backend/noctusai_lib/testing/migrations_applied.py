"""In-repo record of which migration files were APPLIED in prod (``migrations-applied.json``).

``migrate_product`` tracks applied files by filename in ``<schema>.schema_migrations`` and never
re-runs one, so editing an applied file ships nowhere. The prod ledger is not readable from a unit
test, so ``migrate_product confirm=True`` mirrors every file it applies into
``products/<p>/backend/migrations-applied.json`` (``{"applied": {"NNN_x.sql": "<sha256>"}}``, the same
sha256 the ledger stores). Consumers: ``noctus.dev.render_organ_migration`` (applied latest file =>
ship a NEW revision file) and ``noctusai_lib.testing.organs.assert_organ_migration_current``
(applied files are frozen: byte-identical to the recorded sha, never compared to a generator).

Backfill for products applied before this record existed: read the live ledger read-only
(``SELECT filename, checksum FROM <schema>.schema_migrations``) and call ``record_applied``.

KB: ``KB § PATTERNS/architect/vertical-seed.md`` (Mounting an organ).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

__all__ = ["APPLIED_NAME", "load_applied", "record_applied", "sha256_text"]

APPLIED_NAME = "migrations-applied.json"


def sha256_text(sql: str) -> str:
    """Same hash migrate_product writes to the ledger."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _record_path(backend_dir: str | Path) -> Path:
    base = Path(backend_dir)
    if base.name == "migrations":
        base = base.parent
    elif (base / "backend").is_dir():
        base = base / "backend"
    return base / APPLIED_NAME


def load_applied(backend_dir: str | Path) -> dict[str, str]:
    """``{filename: sha256}``; ``{}`` when the product has no record yet. Malformed => ValueError."""
    path = _record_path(backend_dir)
    if not path.is_file():
        return {}
    applied = json.loads(path.read_text(encoding="utf-8")).get("applied")
    if not isinstance(applied, dict):
        raise ValueError(f"{path}: 'applied' must be an object {{filename: sha256}}")
    return dict(applied)


def record_applied(backend_dir: str | Path, files: Mapping[str, str]) -> Path:
    """Merge ``{filename: sha256}`` into the record (existing rows kept; sorted, stable output)."""
    path = _record_path(backend_dir)
    merged = {**load_applied(backend_dir), **files}
    body = {"_doc": "Migration files applied in prod (filename -> sha256 as stored in the ledger). "
                    "Maintained by noctus.dev.migrate_product confirm=True; applied files are frozen. "
                    "KB § PATTERNS/architect/vertical-seed.md.",
            "applied": dict(sorted(merged.items()))}
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path
