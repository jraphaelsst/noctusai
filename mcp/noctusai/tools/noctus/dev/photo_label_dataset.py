"""noctus.dev.photo_label_dataset - label real-estate photos with the vision provider.

Room type + quality/edit attributes per photo (seed ``domain.photo_editing.labeling``). The prompt,
vendor and model are the prompt-registry row ``fotos.rotular`` (public.plataforma_agentes, seeded by core
migration 122, Anthropic) - edited in the registry UI, never a code prompt or a tool argument. Input is a CSV with a ``file`` column
(relative to ``base_dir``) OR a ``photos_dir`` (recursive glob; ``ref`` = parent folder).
Output is a resumable CSV: files already in ``out_csv`` are skipped. Per-photo failures
(after one retry) go to ``<out_csv>.errors.log`` and the result counts - never swallowed.
Usage is metered by the seed ``metered_call``; this tool only reports counts.

``confirm=False`` (or ``dry_run=True``, the default) returns the plan with a rough cost
estimate and writes nothing. The core takes a ``labeler`` seam so tests inject a fake.

KB § PATTERNS/architect/mcp-first-scripts.md
"""
from __future__ import annotations

import asyncio
import csv
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from . import toolkit_freshness as _toolkit_freshness

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PASS_THROUGH = ("ref", "file", "gallery_index")
MAX_CONCURRENCY = 8
#: Rough USD per photo (one image in, ~200 tokens out) - an estimate, not a meter.
EST_USD_PER_PHOTO = 0.008

Labeler = Callable[[bytes], Awaitable[Any]]


def _collect(csv_in: str | None, photos_dir: str | None, base_dir: Path) -> list[dict[str, str]]:
    if bool(csv_in) == bool(photos_dir):
        raise ValueError("pass exactly one of csv_in or photos_dir")
    if csv_in:
        with open(csv_in, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows and "file" not in rows[0]:
            raise ValueError("csv_in needs a `file` column")
        return rows
    root = Path(photos_dir)  # type: ignore[arg-type]
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in PHOTO_EXTS)
    return [{"ref": p.parent.name, "file": str(p.relative_to(base_dir) if p.is_relative_to(base_dir) else p)}
            for p in files]


def _done(out_csv: Path) -> set[str]:
    if not out_csv.exists():
        return set()
    with open(out_csv, newline="") as fh:
        return {r["file"] for r in csv.DictReader(fh)}


def require_row(registry) -> None:
    """Fail loudly BEFORE any photo is sent when the registry row is missing (never a code-prompt fallback)."""
    from noctusai_lib.domain.photo_editing.labeling import CHAVE
    from noctusai_lib.integrations.prompt_registry.types import ChaveNaoEncontrada

    try:
        registry.obter(CHAVE)
    except ChaveNaoEncontrada:
        raise RuntimeError(f"registry row {CHAVE} not found: apply core migration 122_seed_fotos_rotular") from None


def _default_labeler(org_id: str | None = None) -> Labeler:
    from noctusai_lib.domain.photo_editing.labeling import CHAVE, label_photo
    from noctusai_lib.integrations.prompt_registry import get_prompt_registry

    from ._llm_bootstrap import ensure_llm_configured, ensure_prompt_registry_configured

    ensure_llm_configured()
    ensure_prompt_registry_configured()
    require_row(get_prompt_registry())

    async def _label(image: bytes):
        return await label_photo(image, org_id=org_id)

    return _label


def _execute(
    *,
    csv_in: str | None = None,
    photos_dir: str | None = None,
    base_dir: str = ".",
    out_csv: str,
    concurrency: int = 3,
    limit: int | None = None,
    dry_run: bool = True,
    confirm: bool = False,
    labeler: Labeler | None = None,
    org_id: str | None = None,
) -> dict[str, Any]:
    from noctusai_lib.domain.photo_editing.labeling import CHAVE, LABEL_FIELDS

    base = Path(base_dir)
    concurrency = max(1, min(int(concurrency), MAX_CONCURRENCY))
    try:
        rows = _collect(csv_in, photos_dir, base)
    except (ValueError, OSError) as exc:
        return {"ok": False, "status": "error", "error": str(exc)}
    out_path = Path(out_csv)
    done = _done(out_path)
    todo = [r for r in rows if r["file"] not in done]
    if limit is not None:
        todo = todo[: max(0, int(limit))]
    plan = {
        "total": len(rows), "already_done": sum(1 for r in rows if r["file"] in done),
        "to_do": len(todo), "estimated_cost_usd": round(len(todo) * EST_USD_PER_PHOTO, 2),
        "out_csv": str(out_path),
    }
    if dry_run or not confirm:
        return {"ok": True, "status": "planned", "dry_run": True, **plan}

    label = labeler or _default_labeler(org_id)
    header = list(PASS_THROUGH) + list(LABEL_FIELDS) + ["label_method"]
    err_path = Path(str(out_path) + ".errors.log")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    new = not out_path.exists()
    stats = {"labeled": 0, "errors": 0}

    async def run() -> None:
        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        with open(out_path, "a", newline="") as out:
            w = csv.DictWriter(out, fieldnames=header, extrasaction="raise")
            if new:
                w.writeheader()

            async def one(r: dict[str, str]) -> None:
                err: Exception | None = None
                lab = None
                async with sem:
                    for _ in range(2):  # one retry
                        try:
                            lab = await label((base / r["file"]).read_bytes())
                            err = None
                            break
                        except Exception as exc:  # recorded per photo below, never swallowed
                            err = exc
                async with lock:
                    if lab is None:
                        stats["errors"] += 1
                        with open(err_path, "a") as fh:
                            fh.write(f"{r['file']}\t{type(err).__name__}: {err}\n")
                        return
                    w.writerow({**{k: r.get(k, "") for k in PASS_THROUGH}, **lab.as_row(),
                                "label_method": f"vision registry:{CHAVE} per photo"})
                    out.flush()
                    stats["labeled"] += 1

            await asyncio.gather(*(one(r) for r in todo))

    asyncio.run(run())
    return {"ok": True, "status": "applied", "dry_run": False, **plan, **stats,
            "errors_log": str(err_path) if stats["errors"] else None}


def _default_executor(**params: Any) -> dict[str, Any]:
    try:
        return _execute(**params)
    except RuntimeError as exc:  # missing registry row / credentials: a named, loud failure
        return {"ok": False, "status": "error", "error": str(exc)}


@_toolkit_freshness.refuse_gate("photo_label_dataset")
def photo_label_dataset(
    *,
    out_csv: str,
    csv_in: str | None = None,
    photos_dir: str | None = None,
    base_dir: str = ".",
    concurrency: int = 3,
    limit: int | None = None,
    dry_run: bool = True,
    confirm: bool = False,
    org_id: str | None = None,
    executor: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Label real-estate photos (room type + quality/edit attributes) with the vision registry row fotos.rotular (Anthropic); resumable CSV output."""
    run = executor or _default_executor
    return run(csv_in=csv_in, photos_dir=photos_dir, base_dir=base_dir, out_csv=out_csv,
               concurrency=concurrency, limit=limit, dry_run=dry_run, confirm=confirm,
               org_id=org_id)


def register(server) -> None:
    @server.tool(
        name="noctus.dev.photo_label_dataset",
        description=(
            "Label real-estate photos (room type + quality/edit attributes) with the vision provider "
            "through the registry row fotos.rotular (prompt/vendor/model live in the DB). Input: csv_in (a `file` column, relative to base_dir) OR photos_dir "
            "(recursive jpg/jpeg/png/webp). Output: resumable out_csv (done files skipped) + "
            "<out_csv>.errors.log. WRITE - dry_run=True (default) or confirm=False returns the plan with "
            "to_do / already_done / estimated_cost_usd and writes nothing; run with dry_run=False AND "
            "confirm=True. concurrency default 3 (max 8). Returns {ok, status, total, already_done, to_do, "
            "labeled, errors, ...}. KB § PATTERNS/architect/mcp-first-scripts.md"
        ),
    )
    def _photo_label_dataset(
        out_csv: str,
        csv_in: str | None = None,
        photos_dir: str | None = None,
        base_dir: str = ".",
        concurrency: int = 3,
        limit: int | None = None,
        dry_run: bool = True,
        confirm: bool = False,
        allow_stale_toolkit: bool = False,
    ) -> dict:
        return photo_label_dataset(
            out_csv=out_csv, csv_in=csv_in, photos_dir=photos_dir, base_dir=base_dir,
            concurrency=concurrency, limit=limit, dry_run=dry_run, confirm=confirm,
            allow_stale_toolkit=allow_stale_toolkit,
        )


__all__ = ["photo_label_dataset", "register"]
