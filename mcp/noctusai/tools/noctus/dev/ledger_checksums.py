"""Ledger checksum verification — an applied migration file must still be the file that ran.

``migrate_product`` records ``sha256(file)`` in ``<schema>.schema_migrations`` for every
file it applies, and until 2026-10-10 nothing ever read it back. The measurement that
day: 15 of 375 applied files no longer matched their ledger hash (8 edited in place by
the 2026-09-28 customer-role sweep, 7 edited after they ran) plus one sentinel row.
Two of those edits carried intent that never reached prod (seed's anon lockdown,
erp.current_org_id's customer exclusion) — an edit to an applied file is a change
that ships NOWHERE, silently. Now:

- ``migrate_product`` (sha mode) and ``predeploy_check`` (leg ``ledger_checksums``)
  compare every ledger row with ``sha256(git show <sha>:<file>)`` — the blessed/
  committed blob, never the working tree.
- A mismatch is refused unless ``products/<slug>/backend/migration-checksum-ack.json``
  acknowledges THAT exact state: ``(file, ledger_checksum, file_checksum)``. Editing an
  acknowledged file again changes ``file_checksum`` ⇒ refused again. Not a file-name
  allowlist.
- A ledger read that fails is ``inconclusive`` — never a pass.

The fix for drift is never "edit it back" or "rewrite the ledger": put the intent in a
NEW forward migration (replay-gated), confirm prod holds it, then acknowledge.

KB § PATTERNS/backend/migrate-product-mcp-tool.md § Ledger checksum verification.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

ACK_NAME = "migration-checksum-ack.json"

# NOC-REMEDIATE[migration-chain-rebaseline]: applied 001s (+ core 035, SW 011) were rewritten in place by the 2026-09-28 customer-role sweep; prod got the intent via the *_customer_role_isolation forward migrations (catalog-verified 2026-10-10) — resolves with a chain rebaseline — 2026-10-10
# NOC-REMEDIATE[post-apply-edit-audit]: applied files edited after they ran; each audited 2026-10-10 (applied blob found by its ledger hash, current intent catalog-verified live in prod) — acknowledged, no forward migration needed — 2026-10-10
# NOC-REMEDIATE[ledger-sentinel-checksum]: a ledger row whose checksum is a sentinel string, not a sha256 (SW 074 'applied-via-mcp-connector'); history stays as it ran, the row is never rewritten — 2026-10-10
REMEDIATE_CLASSES = frozenset({
    "migration-chain-rebaseline",
    "post-apply-edit-audit",
    "ledger-sentinel-checksum",
})

FETCH_SQL = "SELECT filename, checksum AS ledger_checksum FROM {schema}.schema_migrations ORDER BY filename;"


def sha256_text(sql: str) -> str:
    """Same hash migrate_product writes (``_checksum``)."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def parse_ack(raw: str | None, source: str) -> list[dict]:
    """Validated ack entries. A malformed file or an undeclared class raises ValueError."""
    if raw is None or not raw.strip():
        return []  # no ack file at this sha (or an empty one) — nothing acknowledged
    data = json.loads(raw)
    entries = data.get("acknowledged", [])
    for e in entries:
        missing = [k for k in ("file", "ledger_checksum", "file_checksum", "remediate") if not e.get(k)]
        if missing:
            raise ValueError(f"{source}: entry {e.get('file')!r} lacks {missing}")
        if e["remediate"] not in REMEDIATE_CLASSES:
            raise ValueError(
                f"{source}: entry {e['file']!r} names remediate class {e['remediate']!r}, not "
                f"declared in ledger_checksums.REMEDIATE_CLASSES — every acknowledged drift "
                f"needs a NOC-REMEDIATE destination."
            )
    return entries


def judge(
    ledger_rows: Iterable[Mapping[str, Any]],
    files: Mapping[str, str],
    ack: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pure verdict. ``files`` = {filename: content at the sha}; ``ledger_rows`` carry
    ``filename`` + ``ledger_checksum``. Returns status ``verified`` | ``drift``."""
    acked = {(a["file"], a["ledger_checksum"], a["file_checksum"]) for a in ack}
    drift: list[dict] = []
    acknowledged: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    checked = 0
    for row in ledger_rows:
        name, ledger = row.get("filename"), row.get("ledger_checksum")
        if not name:
            continue
        checked += 1
        if name not in files:
            drift.append({"file": name, "kind": "file_missing", "ledger_checksum": ledger, "file_checksum": None})
            continue
        current = sha256_text(files[name])
        if current == ledger:
            continue
        key = (name, ledger, current)
        if key in acked:
            acknowledged.append(name)
            seen.add(key)
            continue
        drift.append({"file": name, "kind": "content_changed", "ledger_checksum": ledger, "file_checksum": current})
    stale_ack = sorted(a for a, *_ in acked - seen)
    return {
        "status": "drift" if drift else "verified",
        "checked": checked,
        "drift": drift,
        "acknowledged": sorted(acknowledged),
        "stale_ack": stale_ack,
    }


def _git_show(root: Path, ref: str, path: str) -> str | None:
    proc = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=root, capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def verify(
    *,
    slug: str,
    schema: str,
    sha: str,
    files: Mapping[str, str],
    executor: Any,
    root: Path,
    ack_raw: str | None = None,
) -> dict[str, Any]:
    """Read the ledger through ``executor`` and judge it against ``files`` (the blobs at
    ``sha``). ``ack_raw`` defaults to the ack file AT ``sha``. Never raises:
    an unreadable ledger or a bad ack file is ``inconclusive``."""
    rel = f"products/{slug}/backend/{ACK_NAME}"
    if ack_raw is None:
        ack_raw = _git_show(root, sha, rel)
    try:
        ack = parse_ack(ack_raw, f"{rel}@{sha}")
    except (ValueError, json.JSONDecodeError) as exc:
        return {"status": "inconclusive", "sha": sha, "error": str(exc)}
    q = '"' + schema.replace('"', '""') + '"'
    result = executor.execute(FETCH_SQL.format(schema=q))
    if not result.get("ok"):
        return {"status": "inconclusive", "sha": sha,
                "error": f"ledger unreadable: {result.get('error') or 'unknown'}"}
    verdict = judge(result.get("rows") or [], files, ack)
    verdict["sha"] = sha
    return verdict


def chain_at(root: Path, slug: str, sha: str) -> dict[str, str]:
    """{filename: content} of a product's migrations at ``sha`` (direct children only)."""
    rel = f"products/{slug}/backend/migrations"
    proc = subprocess.run(["git", "ls-tree", "--name-only", sha, "--", f"{rel}/"],
                          cwd=root, capture_output=True, text=True)
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if line.endswith(".sql") and line.rpartition("/")[0] == rel:
            content = _git_show(root, sha, line)
            if content is not None:
                out[line.rpartition("/")[2]] = content
    return out


def format_drift(v: Mapping[str, Any]) -> str:
    items = "; ".join(f"{d['file']} ({d['kind']})" for d in v.get("drift", [])[:8])
    return (
        f"{len(v.get('drift', []))} applied migration(s) no longer match their ledger checksum "
        f"at {v.get('sha')}: {items}. An edit to an applied file ships nowhere — put the "
        f"intent in a NEW migration, confirm prod holds it, then acknowledge the exact state "
        f"in {ACK_NAME}. KB § PATTERNS/backend/migrate-product-mcp-tool.md."
    )


__all__ = [
    "ACK_NAME", "REMEDIATE_CLASSES", "chain_at", "format_drift", "judge",
    "parse_ack", "sha256_text", "verify",
]
